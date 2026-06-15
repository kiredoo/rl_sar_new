#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GUI launcher for measure_aw_wcet.py (Autoware pWCET / EVT script).

Features:
- Select ROS/Autoware setup.bash (will be sourced before running the script)
- Select measure_aw_wcet.py path (default: same directory as this GUI)
- Select one or more callbacks.txt files (run the script once per file)
- Optionally select an LD_PRELOAD .so
- Configure num_sampling (-i), default 100
- Configure cool-down-seconds (optional; if left empty, the CLI flag is omitted,
  so measure_aw_wcet.py uses its own default, typically None)
- Toggle --no-gen-report
- Add extra raw CLI arguments

Execution logic when multiple callbacks.txt are selected:

bash -lc "source <setup.bash> && \
  echo '=== Run 1/N: cb1 ===' && [ -f .measure_ets_cache.json ] && sudo rm .measure_ets_cache.json && \
  python3 measure_aw_wcet.py -i ... --callback-names-txt cb1 ... && \
  echo '=== Run 2/N: cb2 ===' && [ -f .measure_ets_cache.json ] && sudo rm .measure_ets_cache.json && \
  python3 measure_aw_wcet.py -i ... --callback-names-txt cb2 ... && ..."

In other words: for each callbacks.txt,
  1) remove .measure_ets_cache.json with sudo if it exists,
  2) run one full measure_aw_wcet.py session (including its internal -i iterations),
before moving on to the next file.
"""

import json
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

CONFIG_PATH = os.path.expanduser("~/.config/wcet_gui/config.json")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GUI_STOP_HARD_TIMEOUT_SEC = float(os.environ.get("WCET_GUI_STOP_HARD_TIMEOUT_SEC", "120"))
GUI_STOP_QUIET_TIMEOUT_SEC = float(os.environ.get("WCET_GUI_STOP_QUIET_TIMEOUT_SEC", "20"))
GUI_STOP_FINAL_KILL_WAIT_SEC = float(os.environ.get("WCET_GUI_STOP_FINAL_KILL_WAIT_SEC", "5"))
GUI_STOP_POLL_INTERVAL_SEC = 0.2


class WCETGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Autoware pWCET / EVT Launcher (measure_aw_wcet.py)")
        self.geometry("900x580")

        # ---- State variables ----
        default_script = os.path.join(BASE_DIR, "measure_aw_wcet.py")
        default_callbacks = os.path.join(BASE_DIR, "cb_names", "callbacks.txt")
        default_sampling_config = os.path.join(BASE_DIR, "config", "default_sampling.yaml")

        # setup.bash to be sourced before running
        self.var_setup_bash = tk.StringVar()

        self.var_script = tk.StringVar(value=default_script)
        self.var_sampling_config = tk.StringVar(value=default_sampling_config)
        # Can hold multiple callbacks.txt, separated by ';'
        self.var_callbacks = tk.StringVar(value=default_callbacks)
        self.var_ld_preload = tk.StringVar()

        # -i / --num-sampling; default 100
        self.var_num_sampling = tk.StringVar(value="100")
        # --cool-down-seconds; empty string means "omit the flag" (use script default)
        self.var_cooldown = tk.StringVar(value="")

        self.var_no_gen_report = tk.BooleanVar(value=False)
        self.var_extra_args = tk.StringVar(value="")

        self.proc = None  # subprocess handle
        self.proc_pgid = None
        self.stop_in_progress = False
        self.stop_thread = None
        self.last_output_ts = 0.0
        self.stop_requested_ts = None

        # Load previous GUI configuration (if any) and override defaults
        self._load_config()
        self._build_ui()

    # ------------------------------------------------------------------
    # GUI layout
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)

        root.columnconfigure(1, weight=1)

        row = 0

        # setup.bash
        self._add_path_row(
            parent=root,
            label="ROS / Autoware setup.bash (source before run):",
            var=self.var_setup_bash,
            browse_cmd=self._browse_setup_bash,
            row=row,
        )
        row += 1

        # measure_aw_wcet.py
        self._add_path_row(
            parent=root,
            label="pWCET script (measure_aw_wcet.py):",
            var=self.var_script,
            browse_cmd=self._browse_script,
            row=row,
        )
        row += 1

        self._add_path_row(
            parent=root,
            label="Sampling config YAML (optional):",
            var=self.var_sampling_config,
            browse_cmd=self._browse_sampling_config,
            row=row,
        )
        row += 1

        # callbacks.txt (multiple)
        self._add_path_row(
            parent=root,
            label="Callback names txt (one or more, ';' separated):",
            var=self.var_callbacks,
            browse_cmd=self._browse_callbacks,
            row=row,
        )
        row += 1

        # LD_PRELOAD
        self._add_path_row(
            parent=root,
            label="LD_PRELOAD .so (optional):",
            var=self.var_ld_preload,
            browse_cmd=self._browse_ld_preload,
            row=row,
        )
        row += 1

        # num_sampling
        ttk.Label(root, text="Num sampling (-i / --num-sampling):").grid(
            row=row, column=0, sticky="e", padx=5, pady=5
        )
        entry_sampling = ttk.Entry(root, textvariable=self.var_num_sampling, width=10)
        entry_sampling.grid(row=row, column=1, sticky="w", padx=5, pady=5)
        row += 1

        # cool-down-seconds (optional)
        ttk.Label(
            root,
            text="Cool-down seconds (--cool-down-seconds, optional):",
        ).grid(row=row, column=0, sticky="e", padx=5, pady=5)
        entry_cooldown = ttk.Entry(root, textvariable=self.var_cooldown, width=10)
        entry_cooldown.grid(row=row, column=1, sticky="w", padx=5, pady=5)
        row += 1

        # no-gen-report checkbox
        chk_no_report = ttk.Checkbutton(
            root,
            text="Do NOT generate report (--no-gen-report)",
            variable=self.var_no_gen_report,
        )
        chk_no_report.grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        row += 1

        # extra args
        ttk.Label(root, text="Extra args (raw CLI, optional):").grid(
            row=row, column=0, sticky="ne", padx=5, pady=5
        )
        entry_extra = ttk.Entry(root, textvariable=self.var_extra_args, width=80)
        entry_extra.grid(row=row, column=1, columnspan=2, sticky="we", padx=5, pady=5)
        row += 1

        # Run / Stop buttons
        btn_frame = ttk.Frame(root)
        btn_frame.grid(row=row, column=0, columnspan=3, sticky="we", pady=(10, 5))
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        self.btn_run = ttk.Button(btn_frame, text="Run pWCET", command=self.on_run)
        self.btn_run.grid(row=0, column=0, padx=5)

        self.btn_stop = ttk.Button(
            btn_frame, text="Stop", command=self.on_stop, state="disabled"
        )
        self.btn_stop.grid(row=0, column=1, padx=5)
        row += 1

        # Log area
        ttk.Label(root, text="Log output:").grid(
            row=row, column=0, sticky="w", padx=5, pady=(10, 0)
        )
        row += 1

        root.rowconfigure(row, weight=1)

        self.txt_log = tk.Text(root, height=15, wrap="word")
        self.txt_log.grid(
            row=row, column=0, columnspan=3, sticky="nsew", padx=5, pady=5
        )
        scroll = ttk.Scrollbar(root, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=scroll.set)
        scroll.grid(row=row, column=3, sticky="ns")

    def _add_path_row(
        self,
        parent: ttk.Frame,
        label: str,
        var: tk.StringVar,
        browse_cmd,
        row: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="e", padx=5, pady=5
        )
        entry = ttk.Entry(parent, textvariable=var, width=70)
        entry.grid(row=row, column=1, sticky="we", padx=5, pady=5)
        btn = ttk.Button(parent, text="Browse...", command=browse_cmd)
        btn.grid(row=row, column=2, padx=5, pady=5)

    # ------------------------------------------------------------------
    # File dialogs
    # ------------------------------------------------------------------
    def _browse_setup_bash(self) -> None:
        path = filedialog.askopenfilename(
            title="Select setup.bash",
            filetypes=[("Shell scripts", "*.bash *.sh"), ("All files", "*.*")],
        )
        if path:
            self.var_setup_bash.set(path)

    def _browse_script(self) -> None:
        path = filedialog.askopenfilename(
            title="Select measure_aw_wcet.py",
            initialdir=BASE_DIR,
            filetypes=[("Python scripts", "*.py"), ("All files", "*.*")],
        )
        if path:
            self.var_script.set(path)

    def _browse_sampling_config(self) -> None:
        path = filedialog.askopenfilename(
            title="Select sampling config YAML",
            initialdir=os.path.join(BASE_DIR, "config"),
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
        )
        if path:
            self.var_sampling_config.set(path)

    def _browse_callbacks(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select one or more callbacks.txt",
            initialdir=os.path.join(BASE_DIR, "cb_names"),
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if paths:
            joined = ";".join(paths)
            self.var_callbacks.set(joined)

    def _browse_ld_preload(self) -> None:
        path = filedialog.askopenfilename(
            title="Select LD_PRELOAD .so",
            filetypes=[("Shared libs", "*.so*"), ("All files", "*.*")],
        )
        if path:
            self.var_ld_preload.set(path)

    # ------------------------------------------------------------------
    # Run / Stop
    # ------------------------------------------------------------------
    def on_run(self) -> None:
        if self.proc is not None:
            messagebox.showwarning("Already running", "pWCET is already running.")
            return

        setup_bash = self.var_setup_bash.get().strip()
        script = self.var_script.get().strip()
        sampling_config = self.var_sampling_config.get().strip()
        callbacks_raw = self.var_callbacks.get().strip()
        ld_preload = self.var_ld_preload.get().strip()
        num_sampling = self.var_num_sampling.get().strip()
        cooldown = self.var_cooldown.get().strip()  # may be empty
        no_report = self.var_no_gen_report.get()
        extra_args = self.var_extra_args.get().strip()

        # --- Basic validation ---
        if not script or not os.path.isfile(script):
            messagebox.showerror("Error", "Please select a valid measure_aw_wcet.py.")
            return

        if sampling_config and not os.path.isfile(sampling_config):
            messagebox.showerror("Error", "Sampling config YAML path is not a valid file.")
            return

        if not callbacks_raw:
            messagebox.showerror("Error", "Please select at least one callbacks.txt.")
            return

        # Multiple callbacks.txt separated by ';'
        callback_list = [p.strip() for p in callbacks_raw.split(";") if p.strip()]
        if not callback_list:
            messagebox.showerror("Error", "Please select at least one callbacks.txt.")
            return

        for cb in callback_list:
            if not os.path.isfile(cb):
                messagebox.showerror(
                    "Error", f"callbacks.txt path is not a valid file:\n{cb}"
                )
                return

        if not num_sampling.isdigit():
            messagebox.showerror("Error", "Num sampling must be an integer.")
            return

        # cooldown: only validate if non-empty
        if cooldown:
            try:
                float(cooldown)
            except ValueError:
                messagebox.showerror("Error", "Cool-down seconds must be a number.")
                return

        if setup_bash and not os.path.isfile(setup_bash):
            messagebox.showerror("Error", "setup.bash path is not a valid file.")
            return

        # --- Base command (shared across all callback files; callbacks added per-run) ---
        base_cmd = [
            sys.executable or "python3",
            script,
        ]

        if sampling_config:
            base_cmd += ["--config", sampling_config]

        base_cmd += [
            "-i",
            num_sampling,
        ]

        if cooldown:
            base_cmd += ["--cool-down-seconds", cooldown]

        if ld_preload:
            base_cmd += ["--ld-preload", ld_preload]

        if no_report:
            base_cmd.append("--no-gen-report")

        if extra_args:
            base_cmd += shlex.split(extra_args)

        # --- Build per-callback segments: echo + remove cache + run script ---
        run_cmds = []
        total = len(callback_list)
        for idx, cb in enumerate(callback_list, start=1):
            echo_cmd = f'echo "=== Run {idx}/{total}: {os.path.basename(cb)} ==="'
            # Remove cache with sudo if present; ignore failure
            rm_cmd = (
                "[ -f .measure_ets_cache.json ] && "
                "sudo rm .measure_ets_cache.json || true"
            )

            cmd_args = base_cmd + ["--callback-names-txt", cb]
            cmd_str = " ".join(shlex.quote(x) for x in cmd_args)

            # Order: echo → remove cache → python ...
            run_cmds.append(echo_cmd)
            run_cmds.append(rm_cmd)
            run_cmds.append(cmd_str)

        # Chain all runs with && so that later runs only execute if previous ones succeed
        batch_body = " && ".join(run_cmds)

        # Prepend source setup.bash if provided
        shell_cmd_parts = []
        if setup_bash:
            shell_cmd_parts.append(f"source {shlex.quote(setup_bash)}")
        shell_cmd_parts.append(batch_body)
        shell_cmd = " && ".join(shell_cmd_parts)

        # Show the actual shell command in the log
        self._append_log(f"$ {shell_cmd}\n\n")

        # Save GUI config
        self._save_config()

        # Use bash -lc so that "source" and shell syntax work as expected
        try:
            self.proc = subprocess.Popen(
                ["bash", "-lc", shell_cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=BASE_DIR,
                start_new_session=True,
            )
            self.proc_pgid = self.proc.pid
            self.stop_in_progress = False
            self.last_output_ts = time.monotonic()
            self.stop_requested_ts = None
        except Exception as exc:  # pylint: disable=broad-except
            messagebox.showerror("Error", f"Failed to start process:\n{exc}")
            self.proc = None
            return

        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")

        t = threading.Thread(target=self._reader_thread, daemon=True)
        t.start()

    def _signal_process_group(self, sig: signal.Signals) -> None:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return

        pgid = self.proc_pgid
        if pgid is None:
            try:
                pgid = os.getpgid(proc.pid)
            except ProcessLookupError:
                return

        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return

    def _wait_for_process_exit(self, timeout: float) -> bool:
        proc = self.proc
        if proc is None:
            return True

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return True
            time.sleep(GUI_STOP_POLL_INTERVAL_SEC)
        return proc.poll() is not None

    def _stop_process_tree(self) -> None:
        proc = self.proc
        if proc is None:
            return

        pgid = self.proc_pgid
        try:
            if pgid is None:
                pgid = os.getpgid(proc.pid)
                self.proc_pgid = pgid
        except ProcessLookupError:
            pgid = None

        if pgid is not None:
            self._append_log(f"[INFO] Sending SIGINT to process group {pgid}.\n")
        self._signal_process_group(signal.SIGINT)

        stop_started = time.monotonic()
        while True:
            proc = self.proc
            if proc is None or proc.poll() is not None:
                return

            now = time.monotonic()
            total_wait = now - stop_started
            quiet_wait = now - self.last_output_ts

            # Behave like CLI Ctrl+C: let the backend finish its own cleanup
            # (write JSON, stop eBPF, stop rosbag/expect, stop ros2 launch).
            # Only force kill if it has been slow overall and also quiet for a while.
            if total_wait >= GUI_STOP_HARD_TIMEOUT_SEC and quiet_wait >= GUI_STOP_QUIET_TIMEOUT_SEC:
                if pgid is not None:
                    self._append_log(
                        f"[WARN] Graceful stop timed out; sending SIGKILL to process group {pgid}.\n"
                    )
                self._signal_process_group(signal.SIGKILL)
                self._wait_for_process_exit(GUI_STOP_FINAL_KILL_WAIT_SEC)
                return

            time.sleep(GUI_STOP_POLL_INTERVAL_SEC)

    def on_stop(self) -> None:
        if self.proc is None or self.stop_in_progress:
            return

        self.stop_in_progress = True
        self.stop_requested_ts = time.monotonic()
        self.btn_stop.config(state="disabled")
        self._append_log("\n[INFO] Stop requested by user.\n")
        self.stop_thread = threading.Thread(target=self._stop_process_tree, daemon=True)
        self.stop_thread.start()

    def _reader_thread(self) -> None:
        proc = self.proc
        assert proc is not None
        assert proc.stdout is not None
        for line in proc.stdout:
            self.last_output_ts = time.monotonic()
            self._append_log(line)
        ret = proc.wait()
        self._append_log(f"\n[INFO] Process finished with return code {ret}\n")
        self.after(0, self._on_process_done)

    def _on_process_done(self) -> None:
        self.proc = None
        self.proc_pgid = None
        self.stop_in_progress = False
        self.stop_thread = None
        self.stop_requested_ts = None
        self.btn_run.config(state="normal")
        self.btn_stop.config(state="disabled")

    def _append_log(self, text: str) -> None:
        def _do():
            self.txt_log.insert("end", text)
            self.txt_log.see("end")

        self.after(0, _do)

    # ------------------------------------------------------------------
    # Config load/save
    # ------------------------------------------------------------------
    def _load_config(self) -> None:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:  # pylint: disable=broad-except
            return

        self.var_setup_bash.set(cfg.get("setup_bash", ""))
        self.var_script.set(cfg.get("script", self.var_script.get()))
        self.var_sampling_config.set(cfg.get("sampling_config", self.var_sampling_config.get()))
        self.var_callbacks.set(cfg.get("callbacks", self.var_callbacks.get()))
        self.var_ld_preload.set(cfg.get("ld_preload", ""))
        self.var_num_sampling.set(cfg.get("num_sampling", "100"))
        self.var_cooldown.set(cfg.get("cooldown", ""))
        self.var_no_gen_report.set(cfg.get("no_gen_report", False))
        self.var_extra_args.set(cfg.get("extra_args", ""))

    def _save_config(self) -> None:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        cfg = {
            "setup_bash": self.var_setup_bash.get(),
            "script": self.var_script.get(),
            "sampling_config": self.var_sampling_config.get(),
            "callbacks": self.var_callbacks.get(),
            "ld_preload": self.var_ld_preload.get(),
            "num_sampling": self.var_num_sampling.get(),
            "cooldown": self.var_cooldown.get(),
            "no_gen_report": self.var_no_gen_report.get(),
            "extra_args": self.var_extra_args.get(),
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception as exc:  # pylint: disable=broad-except
            self._append_log(f"[WARN] Failed to save config: {exc}\n")


def main() -> None:
    app = WCETGui()
    app.mainloop()


if __name__ == "__main__":
    main()
