#!/usr/bin/env python3
"""
Analyze a TorchScript (.pt) model:
  - Input / output shape (auto-detected)
  - All named parameters with shapes
  - Layer-by-layer architecture summary inferred from weight shapes

Usage:
  python3 src/rl_ITRI/scripts/analyze_model.py <path/to/model.pt>
  python3 src/rl_ITRI/scripts/analyze_model.py policy/go2/robot_lab/2026_06_08.pt
"""

import sys
import torch
import numpy as np


def infer_layer_type(name, shape):
    if len(shape) == 4:
        return f"Conv2d  kernel={shape[2]}x{shape[3]}  in={shape[1]}  out={shape[0]}"
    if len(shape) == 2:
        return f"Linear  in={shape[1]}  out={shape[0]}"
    if len(shape) == 1:
        return f"Bias/BN  size={shape[0]}"
    return f"Unknown  shape={shape}"


def analyze(pt_path):
    print(f"Loading: {pt_path}\n")
    model = torch.jit.load(pt_path, map_location="cpu")
    model.eval()

    # ── Parameters ────────────────────────────────────────────────────────────
    params = dict(model.named_parameters())
    print("=" * 60)
    print("PARAMETERS")
    print("=" * 60)
    total = 0
    for name, p in params.items():
        desc = infer_layer_type(name, list(p.shape))
        print(f"  {name:<45}  {str(list(p.shape)):<25}  {desc}")
        total += p.numel()
    print(f"\nTotal parameters: {total:,}\n")

    # ── Auto-detect input size ─────────────────────────────────────────────────
    print("=" * 60)
    print("INPUT / OUTPUT DETECTION")
    print("=" * 60)

    # First linear layer is MLP input (proprio + CNN features), NOT model input.
    # Model input = MLP input + depth pixels that go through CNN.
    # Try candidate input sizes by probing the model directly.
    mlp_input_size = None
    for name, p in params.items():
        if "weight" in name and len(p.shape) == 2:
            mlp_input_size = p.shape[1]
            break

    if mlp_input_size is None:
        print("Could not detect MLP input size.")
        return

    print(f"MLP input size (proprio + CNN features): {mlp_input_size}")

    # Probe candidate total input sizes
    found_size = None
    for input_size in [mlp_input_size, 5229, 4141, 45]:
        dummy = torch.zeros(1, input_size)
        with torch.no_grad():
            try:
                output = model(dummy)
                found_size = input_size
                print(f"\nModel input size: {input_size}  ✓")
                print(f"Input  shape: {list(dummy.shape)}")
                print(f"Output shape: {list(output.shape)}")
                break
            except Exception:
                print(f"Input size {input_size}  ✗")

    if found_size is None:
        print("\nCould not find valid input size from candidates.")
        print("Try running: model(torch.zeros(1, N)) manually.")
        return

    # ── CNN / MLP split analysis ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("ARCHITECTURE SUMMARY")
    print("=" * 60)

    conv_layers = [(n, p) for n, p in params.items() if "weight" in n and len(p.shape) == 4]
    linear_layers = [(n, p) for n, p in params.items() if "weight" in n and len(p.shape) == 2]

    if conv_layers:
        print("\nCNN layers:")
        for name, p in conv_layers:
            out_ch, in_ch, kH, kW = p.shape
            print(f"  {name:<40}  Conv2d({in_ch}, {out_ch}, kernel=({kH},{kW}))")

    if linear_layers:
        print("\nMLP layers:")
        for name, p in linear_layers:
            out_f, in_f = p.shape
            print(f"  {name:<40}  Linear({in_f} → {out_f})")

    # ── Proprioception / depth split ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("DEPTH IMAGE SPLIT PROBE")
    print("=" * 60)

    proprio_size = 45
    depth_flat = found_size - proprio_size
    if depth_flat > 0:
        h_candidates = [h for h in range(1, 200) if depth_flat % h == 0]
        print(f"Total input:        {input_size}")
        print(f"Proprioception:     {proprio_size}")
        print(f"Depth (flat):       {depth_flat}")
        print(f"Possible H×W:       ", end="")
        pairs = [(h, depth_flat // h) for h in h_candidates if h <= depth_flat // h]
        print(", ".join(f"{h}×{depth_flat//h}" for h in h_candidates[:10]))

        # Test with expected 54×96
        if depth_flat == 54 * 96:
            print(f"\nConfirmed: depth is 54×96 = {54*96} pixels  ✓")
        else:
            print(f"\nNote: 54×96 = {54*96}, but depth_flat = {depth_flat}  — mismatch!")
    else:
        print(f"Input size {input_size} ≤ proprio size {proprio_size}, no depth split possible.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_model.py <model.pt>")
        sys.exit(1)
    analyze(sys.argv[1])
