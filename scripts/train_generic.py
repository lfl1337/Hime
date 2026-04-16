"""
Hime training dispatcher (v2 modular rewrite).

Delegates to scripts/training/configs/<model>.py and scripts/training/trainers/<backend>.py.
The monolithic MODEL_CONFIGS dict has moved into per-model plugin files.

Backward-compat: v1 model keys (qwen32b, qwen14b, qwen72b, gemma27b, deepseek)
still work with identical hyperparameters. checkpoint-12400 is preserved.

Usage:
    python train_generic.py --model qwen32b --validate-config   # no VRAM, exit 0
    python train_generic.py --model qwen32b --run-name MyRun    # real training (not in remediation)
    python train_generic.py --help                               # shows all registered model keys

v1 model keys (backward-compat, checkpoint-12400):
    'qwen32b'  'qwen14b'  'qwen72b'  'gemma27b'  'deepseek'

v2 model keys (Pipeline-v2):
    'translategemma12b'  'qwen35-9b'  'qwen3-30b-a3b'
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Add scripts/ to sys.path so `training` package is importable
sys.path.insert(0, str(Path(__file__).parent))

from training.configs import all_config_keys, get_config
from training.trainers import get_trainer

_CONFIG_PATH = Path(__file__).parent / "training_config.json"


def main():
    parser = argparse.ArgumentParser(
        description="Hime Modular Training Dispatcher v2"
    )
    parser.add_argument(
        "--model", required=True, choices=all_config_keys(),
        help="Model key. All registered keys: " + ", ".join(all_config_keys()),
    )
    parser.add_argument(
        "--validate-config", action="store_true",
        help="Validate config chain (model path, tokenizer, training_config.json) without loading weights. Exit 0 on success.",
    )
    # Preserve all existing args from the original script
    parser.add_argument("--run-name",    default=None, help="Run name (overrides auto-derived adapter name)")
    parser.add_argument("--epochs",      type=int, default=3, help="Number of training epochs")
    parser.add_argument("--resume",      default=None, help="Path to checkpoint to resume from")
    parser.add_argument("--log-file",    default=None, help="Tee stdout/stderr to this file")
    parser.add_argument("--data-file",   default=None, help="Path to JSONL training data file")
    parser.add_argument("--rank",        type=int, default=None, help="LoRA rank (overrides default)")
    parser.add_argument("--output-dir",  default=None, help="Output directory for checkpoints/adapter")
    parser.add_argument("--target-loss", type=float, default=None, help="Stop when loss <= this value")
    parser.add_argument("--patience",    type=int,   default=None, help="Evals without improvement before stopping")
    parser.add_argument("--min-delta",   type=float, default=None, help="Min improvement for patience mode")
    parser.add_argument("--min-steps",   type=int,   default=None, help="Don't stop before this step")
    parser.add_argument("--max-epochs",  type=int,   default=None, help="Max training epochs")
    parser.add_argument("--max-steps",   type=int,   default=None, help="Stop after this many steps (for auto-restart cycle)")
    parser.add_argument("--full-resume", action="store_true",
                        help="Full resume incl. optimizer state (may cause VRAM thrashing on 32GB GPUs)")
    parser.add_argument("--fresh",       action="store_true",
                        help="Ignore checkpoints, train from scratch")
    parser.add_argument("--model-dir",   type=str,
        default=os.environ.get("HIME_MODELS_DIR", str(Path(__file__).resolve().parent.parent / "modelle")),
        help="Base models directory")
    parser.add_argument("--training-data", type=str,
        default=os.environ.get("HIME_TRAINING_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data" / "training")),
        help="Training data directory")

    # parse_known_args to ignore HuggingFace Trainer args passed from training_runner
    args, _ = parser.parse_known_args()

    cfg = get_config(args.model)
    trainer = get_trainer(cfg.trainer)

    if args.validate_config:
        trainer.validate_config(cfg)
        # Probe training_config.json
        try:
            with open(_CONFIG_PATH) as f:
                tcfg = json.load(f)
            print(f"[validate] training_config.json keys: {sorted(tcfg.keys())}")
            print(f"[validate] curriculum block: {'PRESENT' if 'curriculum' in tcfg else 'MISSING'}")
        except Exception as exc:
            print(f"[validate] training_config.json probe failed: {exc}")
        print(f"[validate] model key:  {cfg.key}")
        print(f"[validate] model id:   {cfg.model}")
        print(f"[validate] trainer:    {cfg.trainer}")
        print(f"[validate] max_seq:    {cfg.max_seq}")
        print(f"[validate] grad_accum: {cfg.grad_accum}")
        print("[validate] OK")
        return

    trainer.run(cfg, args)


if __name__ == "__main__":
    from tee_output import TeeOutput

    _parser = argparse.ArgumentParser(add_help=False)
    _parser.add_argument("--log-file", default=None)
    _args, _ = _parser.parse_known_args()
    if _args.log_file:
        Path(_args.log_file).parent.mkdir(parents=True, exist_ok=True)
        _log_fh = open(_args.log_file, "a", encoding="utf-8", buffering=1)
        sys.stdout = TeeOutput(sys.stdout, _log_fh)
        sys.stderr = TeeOutput(sys.stderr, _log_fh)

    main()
