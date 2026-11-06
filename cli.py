#!/usr/bin/env python
# Author: François Guillemette
"""
CrazyVideoGenerator Command-Line Interface (CLI).
Dual-GPU Wan2.2-TI2V-5B video synthesis, diagnostics, model downloads, and benchmarks.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from app.config import (
    DEFAULT_CFG,
    DEFAULT_FPS,
    DEFAULT_FRAMES,
    DEFAULT_STEPS,
    MODEL_DIR,
    MODEL_ID,
    OUTPUTS_DIR,
    PRESETS,
)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.system_info import check_model_files, get_gpu_info, get_system_status


def cmd_doctor(args: argparse.Namespace) -> None:
    """Run diagnostics on host environment, GPUs, and model files."""
    print("=" * 60)
    print("  CrazyVideoGenerator — Environment & Hardware Diagnostics")
    print("=" * 60)

    # 1. Check Python
    print(f"[*] Python Version: {sys.version.split()[0]}")

    # 2. Check PyTorch & CUDA
    try:
        import torch
        cuda_avail = torch.cuda.is_available()
        cuda_count = torch.cuda.device_count() if cuda_avail else 0
        print(f"[*] PyTorch Version: {torch.__version__} (CUDA Available: {cuda_avail}, Devices: {cuda_count})")
        if cuda_avail:
            for i in range(cuda_count):
                name = torch.cuda.get_device_name(i)
                total_gib = round(torch.cuda.get_device_properties(i).total_memory / (1024**3), 2)
                print(f"    - GPU {i}: {name} ({total_gib} GiB)")
    except ImportError:
        print("[!] PyTorch is not installed in the current environment.")

    # 3. Check nvidia-smi
    print("\n[*] Querying nvidia-smi telemetry:")
    gpus = get_gpu_info()
    if gpus:
        for g in gpus:
            print(f"    - GPU {g['index']}: {g['name']}")
            print(f"      VRAM: {g['memory_used_gib']} / {g['memory_total_gib']} GiB (Free: {g['memory_free_gib']} GiB)")
            if g.get("temperature_c"):
                print(f"      Temp: {g['temperature_c']}°C, Util: {g.get('utilization_percent')}%")
    else:
        print("    [!] No GPU telemetry returned via nvidia-smi.")

    # 4. Check Wan2.2 Model Checkpoints
    print("\n[*] Checking Wan2.2 Model Status:")
    mstat = check_model_files()
    print(f"    - Model ID: {mstat['model_id']}")
    print(f"    - Target Dir: {mstat['path']}")
    print(f"    - Ready: {'[YES]' if mstat['is_ready'] else '[NO]'}")
    print(f"    - Disk Size: {mstat['total_size_gib']} GiB")
    if not mstat['is_ready']:
        print(f"    - Missing components: {', '.join(mstat['missing_components'])}")
        print("    Run 'python cli.py download' to fetch the checkpoint.")

    print("\n" + "=" * 60)


def cmd_download(args: argparse.Namespace) -> None:
    """Download Wan2.2-TI2V-5B checkpoint files from Hugging Face."""
    print("=" * 60)
    print(f"  Downloading Model: {MODEL_ID}")
    print(f"  Destination: {MODEL_DIR}")
    print("=" * 60)

    try:
        from huggingface_hub import snapshot_download
        from app.system_info import cleanup_orphaned_download_files, convert_model_shards_to_bf16

        print("[*] Cleaning up stale locks and orphaned download cache...")
        cleanup_orphaned_download_files(MODEL_DIR)

        t0 = time.time()
        snapshot_download(
            repo_id=MODEL_ID,
            local_dir=str(MODEL_DIR),
            local_dir_use_symlinks=False,
        )
        print("[*] Optimizing float32 transformer shards to bfloat16 in-place...")
        convert_model_shards_to_bf16(MODEL_DIR, progress_cb=lambda msg: print(f"    {msg}"))
        elapsed = round(time.time() - t0, 1)
        print(f"[OK] Download and optimization completed successfully in {elapsed}s.")
    except Exception as exc:
        print(f"[ERROR] Failed to download model: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_generate(args: argparse.Namespace) -> None:
    """Run headless text-to-video generation."""
    print("=" * 60)
    print("  CrazyVideoGenerator — CLI Generation")
    print("=" * 60)

    from app.pipeline import get_pipeline

    prompt = args.prompt
    preset_cfg = PRESETS.get(args.preset or "hd_16_9", PRESETS["hd_16_9"])
    width = args.width if args.width is not None else preset_cfg["width"]
    height = args.height if args.height is not None else preset_cfg["height"]
    num_frames = args.frames if args.frames is not None else preset_cfg["default_frames"]
    steps = args.steps
    cfg = args.cfg
    seed = args.seed
    fps = args.fps

    if args.preset and args.preset in PRESETS and args.width is None and args.height is None and args.frames is None:
        print(f"[*] Applying preset '{args.preset}': {width}x{height}, {num_frames} frames")

    if width % 32 != 0 or height % 32 != 0:
        print(f"[ERROR] Width ({width}) and height ({height}) must be multiples of 32.", file=sys.stderr)
        sys.exit(1)
    if num_frames < 17 or (num_frames - 1) % 4 != 0:
        print(f"[ERROR] Frame count ({num_frames}) must satisfy 4k + 1 and be >= 17 (e.g. 17, 33, 49, 65, 81).", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Prompt: \"{prompt}\"")
    print(f"[*] Settings: {width}x{height}, {num_frames} frames @ {fps} FPS, {steps} steps, CFG {cfg}, Seed {seed}")

    pipe = get_pipeline()

    def on_step(pdata: dict) -> None:
        print(
            f"\r    Step {pdata['step']}/{pdata['total_steps']} ({pdata['percent']}%) "
            f"- {pdata['it_per_sec']} it/s - ETA {pdata['eta_sec']}s",
            end="",
            flush=True,
        )

    print("[*] Launching generation pipeline...")
    result = pipe.generate_video(
        prompt=prompt,
        negative_prompt=args.negative_prompt,
        width=width,
        height=height,
        num_frames=num_frames,
        num_inference_steps=steps,
        guidance_scale=cfg,
        seed=seed,
        fps=fps,
        progress_callback=on_step,
    )
    print("\n[OK] Video successfully generated:")
    print(f"     Path: {result['video_path']}")
    print(f"     Size: {result['file_size_mb']} MB")


def cmd_smoke_test(args: argparse.Namespace) -> None:
    """Run a fast smoke test to verify dual-GPU inference end-to-end."""
    print("=" * 60)
    print("  CrazyVideoGenerator — Smoke Test")
    print("=" * 60)

    test_prompt = "A glowing paper lantern floating gently on a calm night river, reflections on ripples, high quality"
    print(f"[*] Running smoke test with prompt: \"{test_prompt}\"")

    from app.pipeline import get_pipeline

    draft_cfg = PRESETS["draft_16_9"]
    pipe = get_pipeline()
    result = pipe.generate_video(
        prompt=test_prompt,
        width=draft_cfg["width"],
        height=draft_cfg["height"],
        num_frames=draft_cfg["default_frames"],
        num_inference_steps=draft_cfg["recommended_steps"],
        guidance_scale=DEFAULT_CFG,
        seed=42,
        fps=DEFAULT_FPS,
    )
    print("\n[OK] Smoke test PASSED!")
    print(f"     Generated: {result['video_path']}")


def cmd_convert_bf16(args: argparse.Namespace) -> None:
    """Convert local text_encoder and transformer safetensors shards from float32 to bfloat16 in-place."""
    from app.system_info import convert_model_shards_to_bf16

    print("=" * 60)
    print("  CrazyVideoGenerator — In-Place bfloat16 Model Optimizer")
    print("=" * 60)

    convert_model_shards_to_bf16(MODEL_DIR, progress_cb=lambda msg: print(f"[*] {msg}"))

    mstat = check_model_files(max_age_sec=0.0)
    print("=" * 60)
    print(f"[OK] Conversion complete! New model disk size: {mstat['clean_size_gib']} GiB (Ready: {mstat['is_ready']})")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="CrazyVideoGenerator CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # doctor
    subparsers.add_parser("doctor", help="Inspect hardware, GPUs, and model checkpoints")

    # download
    subparsers.add_parser("download", help="Download Wan2.2-TI2V-5B checkpoint files")

    # generate
    gen_parser = subparsers.add_parser("generate", help="Generate a video from prompt")
    gen_parser.add_argument("-p", "--prompt", required=True, help="Text prompt")
    gen_parser.add_argument("--negative-prompt", default=None, help="Negative prompt")
    gen_parser.add_argument("--preset", default="hd_16_9", choices=list(PRESETS.keys()), help="Aspect preset")
    gen_parser.add_argument("-w", "--width", type=int, default=None, help="Width in pixels (multiple of 32)")
    gen_parser.add_argument("-H", "--height", type=int, default=None, help="Height in pixels (multiple of 32)")
    gen_parser.add_argument("-f", "--frames", type=int, default=None, help="Number of frames (4k+1)")
    gen_parser.add_argument("-s", "--steps", type=int, default=DEFAULT_STEPS, help="Inference steps")
    gen_parser.add_argument("-c", "--cfg", type=float, default=DEFAULT_CFG, help="Guidance scale")
    gen_parser.add_argument("--seed", type=int, default=-1, help="Random seed")
    gen_parser.add_argument("--fps", type=int, default=DEFAULT_FPS, help="Frames per second")

    # smoke-test
    subparsers.add_parser("smoke-test", help="Run rapid end-to-end smoke test")

    # convert-bf16
    subparsers.add_parser("convert-bf16", help="Convert float32 model shards to bfloat16 in-place (~50% disk savings)")

    args = parser.parse_args()
    if args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "download":
        cmd_download(args)
    elif args.command == "generate":
        cmd_generate(args)
    elif args.command == "smoke-test":
        cmd_smoke_test(args)
    elif args.command == "convert-bf16":
        cmd_convert_bf16(args)


if __name__ == "__main__":
    main()
