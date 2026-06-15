"""
Measure the WCET of autoware.universe callback functions.
The default callback functions are in callbacks.txt, and sampled execution
 time is saved in the sampled_execution_time directory.

WCET is measured by EVT and possibly IESTA, with Ljung-Box test to ensure that
 the data satisfies the assumption of EVT.

This is a top-level command for users.
"""
import argparse
import logging
import os

from measure_ets_utils import SAMPLED_EXECUTION_TIME_DIR
from sampling_config import apply_cli_overrides, default_config_path, load_sampling_config
from sampling_manager import do_aw_sampling
from wcet_utils import calc_wcet_ms_by_block_maxima, gen_report


def _do_wcet_sampling_and_analysis(sampling_cfg, no_gen_report):
    do_aw_sampling(sampling_config=sampling_cfg)
    if not no_gen_report:
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        json_dir = os.path.join(cur_dir, SAMPLED_EXECUTION_TIME_DIR)
        cb_wcets = calc_wcet_ms_by_block_maxima(json_dir)
        gen_report(cb_wcets)


def _build_arg_parser(cur_dir: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=default_config_path(cur_dir),
        help="Path to sampling YAML config (default: %(default)s)",
    )
    parser.add_argument(
        "--num-sampling",
        "-i",
        type=int,
        default=None,
        help=(
            "Override sampling.num_sampling in the YAML config. "
            "The more of it, the more accurate of EVT."
        ),
    )
    parser.add_argument("--callback-names-txt", default=None, help="Override sampling.callback_names_txt")
    parser.add_argument(
        "--cool-down-seconds",
        type=float,
        default=None,
        help=(
            "Override sampling.cool_down_seconds in the YAML config for avoiding "
            "overheat and forced reboot"
        ),
    )
    parser.add_argument("--ld-preload", default=None, help="Override sampling.ld_preload")
    parser.add_argument("--rosbag-path", default=None, help="Override autoware.rosbag_path")
    parser.add_argument("--map-path", default=None, help="Override autoware.map_path")
    parser.add_argument("--vehicle-model", default=None, help="Override autoware.vehicle_model")
    parser.add_argument("--sensor-model", default=None, help="Override autoware.sensor_model")
    parser.add_argument("--launch-package", default=None, help="Override autoware.launch_package")
    parser.add_argument("--launch-file", default=None, help="Override autoware.launch_file")
    parser.add_argument(
        "--launch-extra-arg",
        action="append",
        default=None,
        help="Append one extra ros2 launch argument (repeatable).",
    )
    parser.add_argument(
        "--ready-timeout-seconds",
        type=int,
        default=None,
        help="Override autoware.ready_timeout_seconds",
    )
    parser.add_argument(
        "--elf-path-must-contain",
        default=None,
        help="Override measurement.elf_path_must_contain",
    )
    parser.add_argument(
        "--bag-play-rate-x86",
        type=float,
        default=None,
        help="Override measurement.bag_play_rate_x86",
    )
    parser.add_argument(
        "--bag-play-rate-arm",
        type=float,
        default=None,
        help="Override measurement.bag_play_rate_arm",
    )
    parser.add_argument(
        "--burn-in-seconds",
        type=float,
        default=None,
        help="Override measurement.burn_in_seconds",
    )
    parser.add_argument(
        "--min-pause-seconds",
        type=float,
        default=None,
        help="Override measurement.min_pause_seconds",
    )
    parser.add_argument(
        "--sample-duration-seconds-without-bag",
        type=float,
        default=None,
        help="Override measurement.sample_duration_seconds_without_bag",
    )
    parser.add_argument("--no-gen-report", action="store_true", help="Do not generate report, just get measurements only")
    return parser


def main():
    logging.basicConfig(level=logging.WARNING)
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    parser = _build_arg_parser(cur_dir)
    args = parser.parse_args()

    try:
        sampling_cfg = load_sampling_config(args.config, repo_dir=cur_dir)
        sampling_cfg = apply_cli_overrides(sampling_cfg, args=args)
        _do_wcet_sampling_and_analysis(sampling_cfg, args.no_gen_report)
    except KeyboardInterrupt:
        logging.warning("Sampling interrupted by user")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
