"""
Single-run measurement helper for one ROS 2 target process.

This command is intentionally simpler than measure_aw_wcet.py:
- it can start one target command, or attach to a target that is already running;
- it starts measure_ets.py once;
- it samples for a fixed duration;
- it stops eBPF and the optional target command cleanly;
- it only writes raw sampled_execution_time/*.json and does not run EVT/report generation.

Typical usage:
  python3 measure_single_target.py --config config/rl_itri_rl_sim_single.yaml
  python3 measure_single_target.py --config config/rl_itri_rl_real_go2_single.yaml \
      --target-cmd "ros2 run rl_ITRI rl_real_go2 eth0"
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import yaml

from measure_ets_utils import is_ebpf_loaded
from proc_manager import ProcManager
from python_cmd_utils import build_python_cmd
from sampling_config import _resolve_path  # reuse path behavior from the existing config loader


@dataclass
class SingleTargetConfig:
    repo_dir: str
    config_path: str
    target_cmd: Optional[str] = None
    target_log_filename: str = "single_target.log"
    target_ready_sleep_seconds: float = 5.0
    target_shutdown_on_finish: bool = True
    callback_names_txt: str = "cb_names/rl_itri_rl_sim_functions.txt"
    elf_path_must_contain: str = "rl_ITRI"
    duration_seconds: float = 30.0
    ignore_cache: bool = True
    wait_ebpf_timeout_seconds: float = 30.0


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    return value if isinstance(value, dict) else {}


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _load_single_target_config(config_path: Optional[str], *, repo_dir: str) -> SingleTargetConfig:
    resolved_config_path = config_path or os.path.join(repo_dir, "config", "rl_itri_rl_sim_single.yaml")
    resolved_config_path = os.path.abspath(os.path.expandvars(os.path.expanduser(resolved_config_path)))
    config_dir = os.path.dirname(resolved_config_path)

    if not os.path.exists(resolved_config_path):
        raise FileNotFoundError(f"No such config file: {resolved_config_path}")

    with open(resolved_config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Top-level YAML document must be a mapping: {resolved_config_path}")

    target = _section(raw, "target")
    measurement = _section(raw, "measurement")

    return SingleTargetConfig(
        repo_dir=repo_dir,
        config_path=resolved_config_path,
        target_cmd=target.get("command"),
        target_log_filename=str(target.get("log_filename", "single_target.log")),
        target_ready_sleep_seconds=float(target.get("ready_sleep_seconds", 5.0)),
        target_shutdown_on_finish=_as_bool(target.get("shutdown_on_finish"), True),
        callback_names_txt=_resolve_path(
            measurement.get("callback_names_txt", "cb_names/rl_itri_rl_sim_functions.txt"),
            config_dir=config_dir,
            repo_dir=repo_dir,
        ) or os.path.join(repo_dir, "cb_names", "rl_itri_rl_sim_functions.txt"),
        elf_path_must_contain=str(measurement.get("elf_path_must_contain", "rl_ITRI")),
        duration_seconds=float(measurement.get("duration_seconds", 30.0)),
        ignore_cache=_as_bool(measurement.get("ignore_cache"), True),
        wait_ebpf_timeout_seconds=float(measurement.get("wait_ebpf_timeout_seconds", 30.0)),
    )


def _apply_cli_overrides(cfg: SingleTargetConfig, args: argparse.Namespace) -> SingleTargetConfig:
    if args.target_cmd is not None:
        cfg.target_cmd = args.target_cmd
    if args.no_start_target:
        cfg.target_cmd = None
    if args.target_ready_sleep_seconds is not None:
        cfg.target_ready_sleep_seconds = args.target_ready_sleep_seconds
    if args.target_log_filename is not None:
        cfg.target_log_filename = args.target_log_filename
    if args.callback_names_txt is not None:
        cfg.callback_names_txt = _resolve_path(
            args.callback_names_txt,
            config_dir=os.path.dirname(cfg.config_path),
            repo_dir=cfg.repo_dir,
        ) or args.callback_names_txt
    if args.elf_path_must_contain is not None:
        cfg.elf_path_must_contain = args.elf_path_must_contain
    if args.duration_seconds is not None:
        cfg.duration_seconds = args.duration_seconds
    if args.wait_ebpf_timeout_seconds is not None:
        cfg.wait_ebpf_timeout_seconds = args.wait_ebpf_timeout_seconds
    if args.ignore_cache is not None:
        cfg.ignore_cache = args.ignore_cache
    return cfg


def _wait_for_ebpf_loaded(timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not is_ebpf_loaded():
        if time.monotonic() > deadline:
            raise TimeoutError(f"eBPF did not report loaded within {timeout_seconds:.1f} seconds")
        time.sleep(0.2)


def _build_ebpf_cmd(cfg: SingleTargetConfig) -> list[str]:
    ebpf_args = ["-i", cfg.callback_names_txt]
    if cfg.elf_path_must_contain:
        ebpf_args += ["--elf-path-must-contain", cfg.elf_path_must_contain]
    if cfg.ignore_cache:
        ebpf_args += ["--ignore-cache"]
    return build_python_cmd("measure_ets.py", ebpf_args, use_sudo=True)


def do_single_target_measurement(cfg: SingleTargetConfig) -> int:
    target_proc = None
    ebpf_proc = None

    try:
        if cfg.target_cmd:
            logging.warning("Start target command: %s", cfg.target_cmd)
            target_proc = ProcManager(
                ["bash", "-lc", cfg.target_cmd],
                log_filename=cfg.target_log_filename,
            )
            target_proc.start()
            if cfg.target_ready_sleep_seconds > 0:
                logging.warning("Wait %.1f seconds for target to load symbols", cfg.target_ready_sleep_seconds)
                time.sleep(cfg.target_ready_sleep_seconds)
        else:
            logging.warning("No target command configured; attach to already-running target processes")

        logging.warning("Start single eBPF measurement for %.1f seconds", cfg.duration_seconds)
        logging.warning("Callback list: %s", cfg.callback_names_txt)
        logging.warning("ELF path filter: %s", cfg.elf_path_must_contain or "<none>")
        ebpf_proc = ProcManager(_build_ebpf_cmd(cfg))
        ebpf_proc.start()

        _wait_for_ebpf_loaded(cfg.wait_ebpf_timeout_seconds)
        logging.warning("eBPF loaded; sampling for %.1f seconds", cfg.duration_seconds)
        time.sleep(cfg.duration_seconds)
        return 0
    finally:
        try:
            if ebpf_proc is not None:
                logging.warning("Terminating eBPF process, please wait.")
                ebpf_proc.stop()
        finally:
            if cfg.target_shutdown_on_finish and target_proc is not None:
                logging.warning("Terminating target process, please wait.")
                target_proc.stop()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one fixed-duration eBPF function measurement against one ROS 2 target")
    parser.add_argument("--config", default=None, help="Path to single-target YAML config")
    parser.add_argument("--target-cmd", default=None, help="Override target.command. It is executed by bash -lc.")
    parser.add_argument("--no-start-target", action="store_true", help="Do not start target; attach to already-running process")
    parser.add_argument("--target-ready-sleep-seconds", type=float, default=None, help="Override target.ready_sleep_seconds")
    parser.add_argument("--target-log-filename", default=None, help="Override target.log_filename")
    parser.add_argument("--callback-names-txt", "-i", default=None, help="Override measurement.callback_names_txt")
    parser.add_argument("--elf-path-must-contain", default=None, help="Override measurement.elf_path_must_contain")
    parser.add_argument("--duration-seconds", type=float, default=None, help="Override measurement.duration_seconds")
    parser.add_argument("--wait-ebpf-timeout-seconds", type=float, default=None, help="Override measurement.wait_ebpf_timeout_seconds")
    parser.add_argument("--use-cache", dest="ignore_cache", action="store_false", help="Use .measure_ets_cache.json instead of rescanning ELF symbols")
    parser.add_argument("--ignore-cache", dest="ignore_cache", action="store_true", help="Force rescanning ELF symbols")
    parser.set_defaults(ignore_cache=None)
    return parser


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    args = _build_arg_parser().parse_args()
    cfg = _load_single_target_config(args.config, repo_dir=repo_dir)
    cfg = _apply_cli_overrides(cfg, args)
    try:
        raise SystemExit(do_single_target_measurement(cfg))
    except KeyboardInterrupt:
        logging.warning("Single measurement interrupted by user")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
