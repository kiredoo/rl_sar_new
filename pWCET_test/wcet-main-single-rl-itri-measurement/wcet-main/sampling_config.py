"""Helpers for loading sampling configuration from YAML and applying CLI overrides."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Optional

import yaml

DEFAULT_TERMINAL_CANDIDATES = [
    "gnome-terminal",
    "x-terminal-emulator",
    "konsole",
    "xfce4-terminal",
    "mate-terminal",
    "lxterminal",
    "alacritty",
    "kitty",
    "terminator",
]

DEFAULT_CIE_SCRIPT = os.path.expanduser(
    "~/aga/autoware_CIE_MP/src/callback_isolated_executor/scripts/rt_all_symlink.sh"
)
DEFAULT_CIE_YAML = os.path.expanduser(
    "~/aga/autoware_CIE_MP/src/callback_isolated_executor/scripts/"
    "20251003_cbg304_25edf-cpu_190fifo90_89cfs_align-target-cp_tight-dl_caret-awu.yaml"
)


@dataclass
class CieConfig:
    enable: bool = True
    script: str = DEFAULT_CIE_SCRIPT
    yaml_path: str = DEFAULT_CIE_YAML
    expected_unapplied: int = 23
    tmux_session: str = "aga_wcet"
    tmux_window: str = "cie"
    wait_ready_timeout_s: int = 180
    finalize_timeout_s: int = 60
    attach_on_start: bool = True
    terminal_candidates: list[str] = field(default_factory=lambda: list(DEFAULT_TERMINAL_CANDIDATES))


@dataclass
class SamplingConfig:
    repo_dir: str
    config_path: str
    launch_package: str = "autoware_launch"
    launch_file: str = "logging_simulator.launch.xml"
    launch_extra_args: list[str] = field(default_factory=list)
    map_path: str = os.path.expanduser("~/autoware_map/sample-map-rosbag")
    rosbag_path: str = os.path.expanduser("~/autoware_map/sample-rosbag")
    vehicle_model: str = "sample_vehicle"
    sensor_model: str = "sample_sensor_kit"
    ready_timeout_seconds: int = 180

    callback_names_txt: str = "cb_names/callbacks.txt"
    num_sampling: int = 0
    cool_down_seconds: float = 60.0
    ld_preload: Optional[str] = None
    elf_path_must_contain: str = "autoware"
    bag_play_rate_x86: float = 1.0
    bag_play_rate_arm: float = 0.2
    burn_in_seconds: float = 5.0
    min_pause_seconds: float = 10.0
    sample_duration_seconds_without_bag: float = 15.0

    cie: CieConfig = field(default_factory=CieConfig)

    def build_ros2_launch_cmd(self) -> list[str]:
        cmd = [
            "ros2",
            "launch",
            self.launch_package,
            self.launch_file,
            f"map_path:={self.map_path}",
            f"vehicle_model:={self.vehicle_model}",
            f"sensor_model:={self.sensor_model}",
        ]
        cmd.extend(self.launch_extra_args)
        return cmd


def default_config_path(repo_dir: str) -> str:
    return os.path.join(repo_dir, "config", "default_sampling.yaml")


def _resolve_path(value: Optional[str], *, config_dir: str, repo_dir: str) -> Optional[str]:
    if value is None or value == "":
        return value
    expanded = os.path.expandvars(os.path.expanduser(value))
    if os.path.isabs(expanded):
        return expanded
    candidate = os.path.normpath(os.path.join(config_dir, expanded))
    if os.path.exists(candidate):
        return candidate
    return os.path.normpath(os.path.join(repo_dir, expanded))


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    section = data.get(key, {})
    return section if isinstance(section, dict) else {}


def load_sampling_config(config_path: Optional[str] = None, *, repo_dir: Optional[str] = None) -> SamplingConfig:
    resolved_repo_dir = repo_dir or os.path.dirname(os.path.abspath(__file__))
    resolved_config_path = config_path or default_config_path(resolved_repo_dir)
    resolved_config_path = os.path.abspath(os.path.expanduser(os.path.expandvars(resolved_config_path)))
    config_dir = os.path.dirname(resolved_config_path)

    if not os.path.exists(resolved_config_path):
        raise FileNotFoundError(f"No such config file: {resolved_config_path}")

    with open(resolved_config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Top-level YAML document must be a mapping: {resolved_config_path}")

    autoware = _section(raw, "autoware")
    sampling = _section(raw, "sampling")
    measurement = _section(raw, "measurement")
    cie_raw = _section(raw, "cie")

    cie = CieConfig(
        enable=bool(cie_raw.get("enable", True)),
        script=_resolve_path(cie_raw.get("script", DEFAULT_CIE_SCRIPT), config_dir=config_dir, repo_dir=resolved_repo_dir) or DEFAULT_CIE_SCRIPT,
        yaml_path=_resolve_path(cie_raw.get("yaml_path", DEFAULT_CIE_YAML), config_dir=config_dir, repo_dir=resolved_repo_dir) or DEFAULT_CIE_YAML,
        expected_unapplied=int(cie_raw.get("expected_unapplied", 23)),
        tmux_session=str(cie_raw.get("tmux_session", "aga_wcet")),
        tmux_window=str(cie_raw.get("tmux_window", "cie")),
        wait_ready_timeout_s=int(cie_raw.get("wait_ready_timeout_s", 180)),
        finalize_timeout_s=int(cie_raw.get("finalize_timeout_s", 60)),
        attach_on_start=bool(cie_raw.get("attach_on_start", True)),
        terminal_candidates=_as_list(cie_raw.get("terminal_candidates", DEFAULT_TERMINAL_CANDIDATES)),
    )

    return SamplingConfig(
        repo_dir=resolved_repo_dir,
        config_path=resolved_config_path,
        launch_package=str(autoware.get("launch_package", "autoware_launch")),
        launch_file=str(autoware.get("launch_file", "logging_simulator.launch.xml")),
        launch_extra_args=_as_list(autoware.get("launch_extra_args", [])),
        map_path=_resolve_path(autoware.get("map_path", "~/autoware_map/sample-map-rosbag"), config_dir=config_dir, repo_dir=resolved_repo_dir) or os.path.expanduser("~/autoware_map/sample-map-rosbag"),
        rosbag_path=_resolve_path(autoware.get("rosbag_path", "~/autoware_map/sample-rosbag"), config_dir=config_dir, repo_dir=resolved_repo_dir) or os.path.expanduser("~/autoware_map/sample-rosbag"),
        vehicle_model=str(autoware.get("vehicle_model", "sample_vehicle")),
        sensor_model=str(autoware.get("sensor_model", "sample_sensor_kit")),
        ready_timeout_seconds=int(autoware.get("ready_timeout_seconds", 180)),
        callback_names_txt=_resolve_path(sampling.get("callback_names_txt", "../cb_names/callbacks.txt"), config_dir=config_dir, repo_dir=resolved_repo_dir) or os.path.join(resolved_repo_dir, "cb_names", "callbacks.txt"),
        num_sampling=int(sampling.get("num_sampling", 0)),
        cool_down_seconds=float(sampling.get("cool_down_seconds", 60.0)),
        ld_preload=_resolve_path(sampling.get("ld_preload"), config_dir=config_dir, repo_dir=resolved_repo_dir),
        elf_path_must_contain=str(measurement.get("elf_path_must_contain", "autoware")),
        bag_play_rate_x86=float(measurement.get("bag_play_rate_x86", 1.0)),
        bag_play_rate_arm=float(measurement.get("bag_play_rate_arm", 0.2)),
        burn_in_seconds=float(measurement.get("burn_in_seconds", 5.0)),
        min_pause_seconds=float(measurement.get("min_pause_seconds", 10.0)),
        sample_duration_seconds_without_bag=float(measurement.get("sample_duration_seconds_without_bag", 15.0)),
        cie=cie,
    )


def apply_cli_overrides(cfg: SamplingConfig, *, args: Any) -> SamplingConfig:
    override_map = {
        "callback_names_txt": "callback_names_txt",
        "num_sampling": "num_sampling",
        "cool_down_seconds": "cool_down_seconds",
        "ld_preload": "ld_preload",
        "rosbag_path": "rosbag_path",
        "map_path": "map_path",
        "vehicle_model": "vehicle_model",
        "sensor_model": "sensor_model",
        "launch_package": "launch_package",
        "launch_file": "launch_file",
        "ready_timeout_seconds": "ready_timeout_seconds",
        "elf_path_must_contain": "elf_path_must_contain",
        "bag_play_rate_x86": "bag_play_rate_x86",
        "bag_play_rate_arm": "bag_play_rate_arm",
        "burn_in_seconds": "burn_in_seconds",
        "min_pause_seconds": "min_pause_seconds",
        "sample_duration_seconds_without_bag": "sample_duration_seconds_without_bag",
    }
    for attr, arg_name in override_map.items():
        value = getattr(args, arg_name, None)
        if value is None:
            continue
        if attr in {"callback_names_txt", "ld_preload", "rosbag_path", "map_path"}:
            value = _resolve_path(value, config_dir=os.path.dirname(cfg.config_path), repo_dir=cfg.repo_dir)
        setattr(cfg, attr, value)

    launch_extra_args = getattr(args, "launch_extra_arg", None)
    if launch_extra_args:
        cfg.launch_extra_args = [str(v) for v in launch_extra_args]
    return cfg
