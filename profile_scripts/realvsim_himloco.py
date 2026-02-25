import rosbag
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import csv

# ----------------------------------------------------------
# Helper: Move window safely across backends
# ----------------------------------------------------------
def move_figure(fig, x, y, w, h):
    backend = matplotlib.get_backend()
    if backend == "TkAgg":
        fig.canvas.manager.window.wm_geometry(f"{w}x{h}+{x}+{y}")
    elif backend in ["Qt5Agg", "QtAgg"]:
        try:
            fig.canvas.manager.window.setGeometry(x, y, w, h)
        except Exception:
            fig.canvas.manager.window.move(x, y)
            fig.canvas.manager.window.resize(w, h)
    elif backend == "WXAgg":
        fig.canvas.manager.window.SetPosition((x, y))
        fig.canvas.manager.window.SetSize((w, h))
    else:
        print(f"[WARN] Can't move window for backend: {backend}")

# ----------------------------------------------------------
# CONFIG
# ----------------------------------------------------------
USE_SECONDS = True
STEP_SEC = 0.02

# Himloco plotting/index order
HIMLOCO_ORDER = [3, 4, 5, 0, 1, 2, 9, 10, 11, 6, 7, 8]
JOINT_NAMES_HIMLOCO = [
    "FL_hip", "FL_thigh", "FL_calf",
    "FR_hip", "FR_thigh", "FR_calf",
    "RL_hip", "RL_thigh", "RL_calf",
    "RR_hip", "RR_thigh", "RR_calf",
]

TOPIC = "/debug/action_dof_pos"
BAG_REAL = "real_delay.bag"
BAG_SIM  = "sim_delay.bag"

# analysis indices
STEP_PREV   = 99     # 1.98s anchor (also used for shifting q so q_shifted[99] == cmd[99])
STEP_START  = 100    # 2.00s step begins
STEP_STEADY = 275    # 5.50s steady-state error point (and steady-state actual for ΔPV in settling)

# Settling band settings
# ΔPV = |actual_steady - actual_initial| using SHIFTED curve
# band = max(SETTLING_PCT * ΔPV, MIN_BAND_RAD)
SETTLING_PCT = 0.05      # try 0.10 (10%) if 5% is too strict
MIN_BAND_RAD = 0.0      # minimum band radius in radians; set 0.0 to disable

# plotting alignment shift (visual-only)
SHIFT = 0  # in steps/messages (visual alignment only)

# CSV export
SAVE_CSV = True
CSV_PATH = "joint_analysis_summary.csv"

# ----------------------------------------------------------
# Load bags
# ----------------------------------------------------------
def load_bag(path, topic):
    bag = rosbag.Bag(path)
    data = []
    for _, msg, _ in bag.read_messages(topic):
        data.append(msg.data)
    bag.close()
    return np.array(data, dtype=float)

data1 = load_bag(BAG_REAL, TOPIC)
data2 = load_bag(BAG_SIM, TOPIC)

# Split: [0..11]=cmd/target, [12..23]=actual q
actions1  = data1[:, :12]
jointpos1 = data1[:, 12:]

actions2  = data2[:, :12]
jointpos2 = data2[:, 12:]

# ----------------------------------------------------------
# Reorder into HIMLOCO order
# ----------------------------------------------------------
actions1  = actions1[:,  HIMLOCO_ORDER]
jointpos1 = jointpos1[:, HIMLOCO_ORDER]
actions2  = actions2[:,  HIMLOCO_ORDER]
jointpos2 = jointpos2[:, HIMLOCO_ORDER]

# ----------------------------------------------------------
# Build shifted actual curves so that q_shifted[STEP_PREV] == cmd[STEP_PREV]
# (used for Rise time / Achieved / Overshoot / Settling time)
# ----------------------------------------------------------
def shift_actual_to_match_at_step(cmd_2d, q_2d, step_anchor):
    T = min(cmd_2d.shape[0], q_2d.shape[0])
    cmd = cmd_2d[:T, :]
    q = q_2d[:T, :]
    if T <= step_anchor:
        return q.copy()
    offsets = cmd[step_anchor, :] - q[step_anchor, :]
    return q + offsets  # broadcast per joint

jointpos1_shifted = shift_actual_to_match_at_step(actions1, jointpos1, STEP_PREV)
jointpos2_shifted = shift_actual_to_match_at_step(actions2, jointpos2, STEP_PREV)

# ----------------------------------------------------------
# Plot shift (optional) for sim alignment (visual only)
# ----------------------------------------------------------
def apply_shift(arr, shift):
    if shift <= 0:
        return arr
    pad = np.full((shift, arr.shape[1]), np.nan)
    shifted = np.vstack([pad, arr])
    return shifted[:arr.shape[0], :]

actions2_plot        = apply_shift(actions2, SHIFT)
jointpos2_plot       = apply_shift(jointpos2, SHIFT)
jointpos2_shift_plot = apply_shift(jointpos2_shifted, SHIFT)

actions1_plot        = actions1
jointpos1_plot       = jointpos1
jointpos1_shift_plot = jointpos1_shifted

# ----------------------------------------------------------
# X axis for plotting
# ----------------------------------------------------------
x1 = np.arange(actions1_plot.shape[0])
x2 = np.arange(actions2_plot.shape[0])

if USE_SECONDS:
    x1 = x1 * STEP_SEC
    x2 = x2 * STEP_SEC
    x_label = "Time (s)"
else:
    x_label = "Time step"

# ----------------------------------------------------------
# Analysis helpers
# ----------------------------------------------------------
def compute_response_metrics(cmd, q_shifted, step_prev, step_start, step_steady, step_sec,
                             settling_pct=0.10, min_band_rad=0.0):
    """
    SHIFTED used for:
      - Rise time (ms), Achieved, Overshoot (vs target)
      - Settling time (ms) using:
            ΔPV = |actual_steady - actual_initial|   (SHIFTED)
            band = max(settling_pct * ΔPV, min_band_rad)
        and band is centered at actual steady-state q_ss
        settling time = first time it enters band and stays in band until end (strict)

    Validity gate at step_prev based on old target (directional).
    If never achieved, rise time uses best peak (quantized).
    """
    T = min(len(cmd), len(q_shifted))
    eps = 1e-12
    out = {
        "rise_ms": None,        # None => Not Valid
        "achieved": False,
        "overshoot": None,
        "settling_ms": None,    # None => N/A
        "dpv": None,
        "band": None,
        "q_ss": None,
        "q_init": None,
    }

    if T <= step_start or step_prev < 0 or step_prev >= T:
        return out

    old_target = float(cmd[step_prev])
    new_target = float(cmd[step_start])
    q_prev = float(q_shifted[step_prev])

    # Direction from cmd step
    if abs(new_target - old_target) <= eps:
        direction = 0
    elif new_target > old_target:
        direction = +1
    else:
        direction = -1

    # Validity gate at step_prev (using shifted q)
    valid = True
    if direction == +1:
        if not (q_prev <= old_target + 1e-9):
            valid = False
    elif direction == -1:
        if not (q_prev >= old_target - 1e-9):
            valid = False

    seg_q = q_shifted[step_start:T]

    # Achieved mask (reach new target)
    if direction == +1:
        achieved_mask = (seg_q >= new_target)
    elif direction == -1:
        achieved_mask = (seg_q <= new_target)
    else:
        achieved_mask = (np.abs(seg_q - new_target) <= 1e-6)

    achieved = bool(np.any(achieved_mask))
    out["achieved"] = achieved

    # ---- Rise time (ms) with linear interpolation ----
    if valid:
        if achieved:
            first_idx = int(np.argmax(achieved_mask))
            k = step_start + first_idx

            if k <= step_start:
                out["rise_ms"] = 0.0
            else:
                k0 = k - 1
                q0 = float(q_shifted[k0])
                q1 = float(q_shifted[k])
                dt = float(step_sec)

                denom = (q1 - q0)
                if abs(denom) < 1e-12:
                    out["rise_ms"] = (k - step_start) * dt * 1000.0
                else:
                    frac = (new_target - q0) / denom
                    frac = float(np.clip(frac, 0.0, 1.0))
                    t_cross = (k0 * dt) + frac * dt
                    t_start = step_start * dt
                    out["rise_ms"] = (t_cross - t_start) * 1000.0
        else:
            # never achieved: use best peak in direction (quantized)
            if direction == +1:
                idx_event = step_start + int(np.nanargmax(seg_q))
            elif direction == -1:
                idx_event = step_start + int(np.nanargmin(seg_q))
            else:
                idx_event = step_start + int(np.nanargmin(np.abs(seg_q - new_target)))
            out["rise_ms"] = (idx_event - step_start) * step_sec * 1000.0
    else:
        out["rise_ms"] = None  # Not Valid

    # ---- Overshoot (only if achieved) ----
    if achieved:
        err = seg_q - new_target
        if direction == +1:
            out["overshoot"] = float(np.nanmax(err))
        elif direction == -1:
            out["overshoot"] = float(np.nanmin(err))
        else:
            kx = int(np.nanargmax(np.abs(err)))
            out["overshoot"] = float(err[kx])
    else:
        out["overshoot"] = None

    # ---- Settling time using ΔPV = |actual_steady - actual_initial| ----
    q_init = float(q_shifted[step_prev])
    if T > step_steady:
        q_ss = float(q_shifted[step_steady])
    else:
        q_ss = float(q_shifted[T - 1])

    dPV = abs(q_ss - q_init)
    band = settling_pct * dPV
    if min_band_rad > 0.0:
        band = max(band, float(min_band_rad))

    out["dpv"] = dPV
    out["band"] = band
    out["q_ss"] = q_ss
    out["q_init"] = q_init

    # If ΔPV is tiny AND min_band is disabled, settling time isn't meaningful
    if dPV < 1e-9 and (min_band_rad <= 0.0):
        out["settling_ms"] = None
        return out

    # Band around ACTUAL steady-state value
    in_band = np.abs(seg_q - q_ss) <= band

    # strict definition: first time it enters band and stays in band until end
    if np.any(in_band):
        suffix_all = np.logical_and.accumulate(in_band[::-1])[::-1]
        if np.any(suffix_all):
            i0 = int(np.argmax(suffix_all))
            out["settling_ms"] = i0 * step_sec * 1000.0
        else:
            out["settling_ms"] = None
    else:
        out["settling_ms"] = None

    return out

def steady_state_error(cmd, q_original, step_steady):
    """Uses ORIGINAL curve: actual - target at step_steady."""
    T = min(len(cmd), len(q_original))
    if T <= step_steady:
        return None
    return float(q_original[step_steady] - cmd[step_steady])

def fmt_rise(v):
    return "Not Valid" if v is None else f"{v:.2f} ms"

def fmt_settle(v):
    return "N/A" if v is None else f"{v:.2f} ms"

def fmt_num(v):
    return "N/A" if v is None else f"{v:.6f}"

def fmt_bool(b):
    return "True" if bool(b) else "False"

# ----------------------------------------------------------
# Analysis printout + CSV export
# ----------------------------------------------------------
print("\n===== Analysis (SHIFTED for rise/achieved/overshoot/settling; ORIGINAL for steady-state error) =====")
print(f"Anchor step={STEP_PREV} ({STEP_PREV*STEP_SEC:.2f}s), Step start={STEP_START} ({STEP_START*STEP_SEC:.2f}s), Steady step={STEP_STEADY} ({STEP_STEADY*STEP_SEC:.2f}s)")
print(f"Settling band: ±max({SETTLING_PCT*100:.1f}% * ΔPV, {MIN_BAND_RAD:.4f} rad), where ΔPV=|actual_steady - actual_initial| (SHIFTED)\n")

rows = []

for j in range(12):
    name = JOINT_NAMES_HIMLOCO[j]

    real_dyn = compute_response_metrics(
        cmd=actions1[:, j],
        q_shifted=jointpos1_shifted[:, j],
        step_prev=STEP_PREV,
        step_start=STEP_START,
        step_steady=STEP_STEADY,
        step_sec=STEP_SEC,
        settling_pct=SETTLING_PCT,
        min_band_rad=MIN_BAND_RAD
    )
    sim_dyn = compute_response_metrics(
        cmd=actions2[:, j],
        q_shifted=jointpos2_shifted[:, j],
        step_prev=STEP_PREV,
        step_start=STEP_START,
        step_steady=STEP_STEADY,
        step_sec=STEP_SEC,
        settling_pct=SETTLING_PCT,
        min_band_rad=MIN_BAND_RAD
    )

    # steady-state error uses ORIGINAL q (as requested)
    real_steady = steady_state_error(actions1[:, j], jointpos1[:, j], STEP_STEADY)
    sim_steady  = steady_state_error(actions2[:, j], jointpos2[:, j], STEP_STEADY)

    steady_diff = abs(real_steady - sim_steady) if (real_steady is not None and sim_steady is not None) else None

    # Terminal output
    print("--------")
    print(f"Joint Name: {name}")
    print("[Real]")
    print(f"Rise time: {fmt_rise(real_dyn['rise_ms'])}")
    print(f"Settling time: {fmt_settle(real_dyn['settling_ms'])}")
    print(f"Achieved: {fmt_bool(real_dyn['achieved'])}")
    print(f"Overshoot: {fmt_num(real_dyn['overshoot'])}")
    print(f"Steady-state error: {fmt_num(real_steady)}")
    print("[Sim]")
    print(f"Rise time: {fmt_rise(sim_dyn['rise_ms'])}")
    print(f"Settling time: {fmt_settle(sim_dyn['settling_ms'])}")
    print(f"Achieved: {fmt_bool(sim_dyn['achieved'])}")
    print(f"Overshoot: {fmt_num(sim_dyn['overshoot'])}")
    print(f"Steady-state error: {fmt_num(sim_steady)}")
    print()
    print(f"Steady-state error Diff: {fmt_num(steady_diff)}")

    # CSV row
    rows.append({
        "joint_name": name,

        "real_rise_time_ms": real_dyn["rise_ms"],
        "real_rise_time_valid": (real_dyn["rise_ms"] is not None),
        "real_settling_time_ms": real_dyn["settling_ms"],
        "real_achieved": bool(real_dyn["achieved"]),
        "real_overshoot": real_dyn["overshoot"],
        "real_steady_state_error": real_steady,

        "sim_rise_time_ms": sim_dyn["rise_ms"],
        "sim_rise_time_valid": (sim_dyn["rise_ms"] is not None),
        "sim_settling_time_ms": sim_dyn["settling_ms"],
        "sim_achieved": bool(sim_dyn["achieved"]),
        "sim_overshoot": sim_dyn["overshoot"],
        "sim_steady_state_error": sim_steady,

        "steady_state_error_diff": steady_diff,

        # optional debug columns for settling
        #"real_dpv": real_dyn["dpv"],
        #"real_band": real_dyn["band"],
        #"sim_dpv": sim_dyn["dpv"],
        #"sim_band": sim_dyn["band"],
    })

print("--------\n")

if SAVE_CSV:
    fieldnames = [
        "joint_name",
        "real_rise_time_ms", "real_rise_time_valid", "real_settling_time_ms",
        "real_achieved", "real_overshoot", "real_steady_state_error",
        "sim_rise_time_ms", "sim_rise_time_valid", "sim_settling_time_ms",
        "sim_achieved", "sim_overshoot", "sim_steady_state_error",
        "steady_state_error_diff",
        #"real_dpv", "real_band", "sim_dpv", "sim_band",
    ]
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"[CSV] Saved analysis to: {CSV_PATH}")

# ----------------------------------------------------------
# Plotting: 8 windows total (4 original + 4 shifted)
# ----------------------------------------------------------
WIN_W = 900
WIN_H = 700

positions8 = [
    (0, 0),                 (WIN_W, 0),
    (0, WIN_H),             (WIN_W, WIN_H),
    (2 * WIN_W, 0),         (3 * WIN_W, 0),
    (2 * WIN_W, WIN_H),     (3 * WIN_W, WIN_H),
]

groups = [
    (0, 1, 2),      # FL
    (3, 4, 5),      # FR
    (6, 7, 8),      # RL
    (9, 10, 11)     # RR
]

# ---- Original plots (4 windows) ----
for window_index, joint_group in enumerate(groups):
    fig = plt.figure(figsize=(12, 8))
    fig.suptitle(
        f"[ORIGINAL] Group {window_index+1}: {[JOINT_NAMES_HIMLOCO[j] for j in joint_group]}",
        fontsize=16
    )
    for subplot_index, j in enumerate(joint_group):
        ax = plt.subplot(3, 1, subplot_index + 1)
        ax.plot(x1, actions1_plot[:, j], label=f"real cmd ({JOINT_NAMES_HIMLOCO[j]})")
        ax.plot(x1, jointpos1_plot[:, j], label=f"real q  ({JOINT_NAMES_HIMLOCO[j]})")
        ax.plot(x2, actions2_plot[:, j], '--', label=f"sim cmd ({JOINT_NAMES_HIMLOCO[j]})")
        ax.plot(x2, jointpos2_plot[:, j], '--', label=f"sim q  ({JOINT_NAMES_HIMLOCO[j]})")
        ax.legend(loc="upper right")
        ax.set_xlabel(x_label)
        ax.set_ylabel("Value")
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    x, y = positions8[window_index]
    move_figure(fig, x, y, WIN_W, WIN_H)
    plt.show(block=False)

# ---- Shifted plots (4 windows) ----
for window_index, joint_group in enumerate(groups):
    fig = plt.figure(figsize=(12, 8))
    fig.suptitle(
        f"[SHIFTED@step{STEP_PREV}] Group {window_index+1}: {[JOINT_NAMES_HIMLOCO[j] for j in joint_group]}",
        fontsize=16
    )
    for subplot_index, j in enumerate(joint_group):
        ax = plt.subplot(3, 1, subplot_index + 1)
        ax.plot(x1, actions1_plot[:, j], label=f"real cmd ({JOINT_NAMES_HIMLOCO[j]})")
        ax.plot(x1, jointpos1_shift_plot[:, j], label=f"real q SHIFTED ({JOINT_NAMES_HIMLOCO[j]})")
        ax.plot(x2, actions2_plot[:, j], '--', label=f"sim cmd ({JOINT_NAMES_HIMLOCO[j]})")
        ax.plot(x2, jointpos2_shift_plot[:, j], '--', label=f"sim q SHIFTED ({JOINT_NAMES_HIMLOCO[j]})")
        ax.legend(loc="upper right")
        ax.set_xlabel(x_label)
        ax.set_ylabel("Value")
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    x, y = positions8[4 + window_index]
    move_figure(fig, x, y, WIN_W, WIN_H)
    plt.show(block=False)

plt.show()

