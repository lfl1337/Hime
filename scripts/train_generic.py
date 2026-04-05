"""
Hime - Generic Multi-Model Training Script (Unsloth QLoRA)

Supports multiple model configurations via --model flag.
Usage:
    python train_generic.py --model qwen32b --run-name MyRun --epochs 3
    python train_generic.py --model qwen14b --run-name MyRun --resume /path/to/checkpoint

Supported models:
    qwen32b   - Qwen2.5-32B-Instruct (4bit)
    qwen14b   - Qwen2.5-14B-Instruct (4bit)
    qwen72b   - Qwen2.5-72B-Instruct (4bit)
    gemma27b  - Gemma 3-27B-IT (4bit)
    deepseek  - DeepSeek-R1-Distill-Qwen-32B (4bit)
"""

import argparse
import os
import sys

os.environ["UNSLOTH_SKIP_TORCHVISION_CHECK"] = "1"

import unsloth  # Must be imported first
from unsloth import FastLanguageModel

import gc
import json
import torch
from pathlib import Path
from datasets import Dataset
from transformers import TrainerCallback, TrainingArguments
from trl import SFTTrainer

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from callbacks.smart_stopping import SmartStoppingCallback
from callbacks.manual_save import ManualSaveCallback


# ---------------------------------------------------------------------------
# Model configurations
# ---------------------------------------------------------------------------

MODEL_CONFIGS = {
    'qwen32b': {
        'model':    'unsloth/Qwen2.5-32B-Instruct-bnb-4bit',
        'lora_dir': 'Qwen2.5-32B-Instruct',
        'max_seq':  1024,
        'grad_accum': 8,
    },
    'qwen14b': {
        'model':    'unsloth/Qwen2.5-14B-Instruct-bnb-4bit',
        'lora_dir': 'Qwen2.5-14B-Instruct',
        'max_seq':  1024,
        'grad_accum': 16,
    },
    'qwen72b': {
        'model':    'unsloth/Qwen2.5-72B-Instruct-bnb-4bit',
        'lora_dir': 'Qwen2.5-72B-Instruct',
        'max_seq':  512,
        'grad_accum': 32,
    },
    'gemma27b': {
        'model':    'unsloth/gemma-3-27b-it-bnb-4bit',
        'lora_dir': 'Gemma-3-27B-IT',
        'max_seq':  1024,
        'grad_accum': 16,
    },
    'deepseek': {
        'model':    'unsloth/DeepSeek-R1-Distill-Qwen-32B-bnb-4bit',
        'lora_dir': 'DeepSeek-R1-Distill-Qwen-32B',
        'max_seq':  1024,
        'grad_accum': 16,
    },
}

# LoRA defaults
LORA_RANK    = 16
LORA_ALPHA   = 32
LORA_DROPOUT  = 0.05   # Regularisierung gegen Overfitting

# Training defaults
LEARNING_RATE = 5e-5   # Gesenkt von 2e-4 — Feinschliff nach Loss-Plateau
BATCH_SIZE    = 1
SAVE_STEPS    = 50
EVAL_STEPS    = 500
LOGGING_STEPS = 10
WARMUP_STEPS  = 50     # Fixe 50 Steps statt 5% Ratio
WEIGHT_DECAY  = 0.01

PROJECT_ROOT = Path(r"C:\Projekte\Hime")
TRAINING_DIR = PROJECT_ROOT / "data" / "training"
MODELS_DIR   = PROJECT_ROOT / "modelle" / "lora"

PROMPT_TEMPLATE = """<|im_start|>system
You are a professional Japanese to English translator specializing in yuri light novels. Translate accurately while preserving the intimate tone, character voices, and emotional nuance.<|im_end|>
<|im_start|>user
{instruction}

{input}<|im_end|>
<|im_start|>assistant
{output}<|im_end|>"""


def load_training_data(data_file: Path) -> tuple:
    """Load and format training data from JSONL file."""
    import time as _time
    if not data_file.exists():
        raise FileNotFoundError(f"Training data not found: {data_file}")

    print(f"[..] Loading training data from {data_file.name} ...")
    _tok_start = _time.time()
    entries = []

    with open(data_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if not entry.get("input") or not entry.get("output"):
                continue
            if len(entry["input"]) < 50 or len(entry["output"]) < 50:
                continue
            text = PROMPT_TEMPLATE.format(
                instruction=entry.get("instruction", "Translate the following Japanese text to English."),
                input=entry["input"],
                output=entry["output"],
            )
            entries.append({"text": text})

    _tok_duration = _time.time() - _tok_start
    print(f"[OK] {len(entries):,} training examples loaded in {_tok_duration:.1f}s")

    split = int(len(entries) * 0.9)
    train_data = entries[:split]
    eval_data  = entries[split:]
    print(f"[OK] Train: {len(train_data):,} | Eval: {len(eval_data):,}")

    return Dataset.from_list(train_data), Dataset.from_list(eval_data)


def load_model(model_name: str, max_seq_len: int):
    """Load base model with Unsloth 4-bit quantization."""
    import time as _time
    print(f"\n[INFO] Loading model: {model_name}")
    print(f"     Max Seq Len: {max_seq_len}")
    _load_start = _time.time()
    # Free memory before loading to minimise peak pagefile pressure (OS Error 1455)
    gc.collect()
    torch.cuda.empty_cache()
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=max_seq_len,
        dtype=None,
        load_in_4bit=True,
        trust_remote_code=True,
        device_map="cuda:0",              # Load shards directly to GPU, skip CPU staging
        low_cpu_mem_usage=True,           # Load one shard at a time — avoids mapping all to RAM
        max_memory={0: "30GB", "cpu": "20GB"},
    )
    print(f"[INFO] Model loaded ({_time.time() - _load_start:.1f}s)")
    return model, tokenizer


def get_target_modules(model_name: str) -> list:
    """Return LoRA target modules for the model architecture."""
    return ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def apply_lora(model, tokenizer, output_dir: Path, resume_path: str | None,
               warm_start: bool = False):
    """Add LoRA adapter, auto-detecting existing checkpoints if no explicit resume path.

    warm_start: Load adapter weights from checkpoint but don't pass resume_from
                to trainer (fresh optimizer). Avoids VRAM fragmentation that causes
                catastrophic slowdown on 32GB GPUs.
    """
    print(f"\n[..] Adding LoRA adapter (Rank={LORA_RANK})")

    # Auto-detect latest checkpoint if not explicitly provided
    target_cp = None
    if resume_path is None:
        cp_dir = output_dir / "checkpoint"
        if cp_dir.exists():
            checkpoints = sorted(cp_dir.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[-1]) if p.name.split("-")[-1].isdigit() else 0)
            if checkpoints:
                target_cp = checkpoints[-1]
                if not warm_start:
                    resume_path = str(target_cp)
                print(f"[i]  Auto-detected checkpoint: {target_cp.name}")
    else:
        target_cp = Path(resume_path)

    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_RANK,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=get_target_modules(model.config.model_type if hasattr(model, 'config') else ''),
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    total_params     = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"[OK] Trainable parameters: {trainable_params:,} ({trainable_params/total_params*100:.2f}%)")

    if warm_start and target_cp is not None:
        adapter_file = Path(target_cp) / "adapter_model.safetensors"
        if adapter_file.exists():
            from safetensors.torch import load_file
            print(f"[i]  Warm-start: loading adapter weights from {target_cp.name} (no optimizer)")
            adapter_weights = load_file(str(adapter_file))
            # PEFT state_dict uses '.default.' in key names (adapter name),
            # but saved adapter files omit it. Remap keys to match model.
            remapped = {}
            for k, v in adapter_weights.items():
                new_key = k.replace(".lora_A.weight", ".lora_A.default.weight") \
                           .replace(".lora_B.weight", ".lora_B.default.weight")
                remapped[new_key] = v
            incompatible = model.load_state_dict(remapped, strict=False)
            loaded_count = len(remapped) - len(incompatible.unexpected_keys)
            print(f"[OK] Adapter weights loaded ({loaded_count} tensors). Optimizer will be fresh.")
            return model, tokenizer, None

    return model, tokenizer, resume_path


_CONFIG_PATH = Path(__file__).parent / "training_config.json"


def _load_stop_config(cli_args) -> dict:
    """Load stop config from training_config.json, then override with CLI args."""
    defaults: dict = {
        "stop_mode": "none",
        "target_loss": None,
        "target_loss_metric": "loss",
        "target_confirmations": 3,
        "patience": None,
        "patience_metric": "eval_loss",
        "min_delta": 0.001,
        "min_steps": 0,
        "max_epochs": None,  # resolved later from args.epochs
    }
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            file_config = json.load(f)
        # Only override defaults with non-null values from config file
        defaults.update({k: v for k, v in file_config.items() if v is not None})

    # CLI args override config file (only if explicitly provided by caller)
    if getattr(cli_args, "target_loss", None) is not None:
        defaults["target_loss"] = cli_args.target_loss
        if defaults["stop_mode"] == "none":
            defaults["stop_mode"] = "threshold"
    if getattr(cli_args, "patience", None) is not None:
        defaults["patience"] = cli_args.patience
        if defaults["stop_mode"] in ("none", "threshold"):
            defaults["stop_mode"] = "patience" if defaults["target_loss"] is None else "both"
    if getattr(cli_args, "min_delta", None) is not None:
        defaults["min_delta"] = cli_args.min_delta
    if getattr(cli_args, "min_steps", None) is not None:
        defaults["min_steps"] = cli_args.min_steps
    if getattr(cli_args, "max_epochs", None) is not None:
        defaults["max_epochs"] = cli_args.max_epochs

    return defaults


def _build_callbacks(stop_config: dict | None, output_dir: Path) -> list:
    """Build the callbacks list, optionally including SmartStoppingCallback."""
    cbs = [SaveCheckpointCallback(), ManualSaveCallback()]
    if stop_config is None:
        return cbs
    mode = stop_config.get("stop_mode", "none")
    has_target = stop_config.get("target_loss") is not None
    has_patience = stop_config.get("patience") is not None
    if mode != "none" and (has_target or has_patience):
        state_file = str(output_dir / "smart_stop_state.json")
        cbs.append(SmartStoppingCallback(
            target_loss=stop_config.get("target_loss"),
            target_loss_metric=stop_config.get("target_loss_metric", "loss"),
            target_confirmations=stop_config.get("target_confirmations", 3),
            patience=stop_config.get("patience"),
            patience_metric=stop_config.get("patience_metric", "eval_loss"),
            min_delta=stop_config.get("min_delta", 0.001),
            min_steps=stop_config.get("min_steps", 0),
            state_file=state_file,
        ))
    return cbs


class SaveCheckpointCallback(TrainerCallback):
    """Structured log lines for checkpoint saves and training lifecycle events."""

    def on_save(self, args, state, control, **kwargs):
        saved = f"checkpoint-{state.global_step}"
        best = f" | best={state.best_metric:.4f} @ {os.path.basename(state.best_model_checkpoint or '')}" if state.best_model_checkpoint else ""
        if torch.cuda.is_available():
            alloc = torch.cuda.memory_allocated() / 1024**3
            reserved = torch.cuda.memory_reserved() / 1024**3
            print(f"[CHECKPOINT] Saved: {saved}{best} (VRAM: {alloc:.1f}GB alloc / {reserved:.1f}GB reserved)")
        else:
            print(f"[CHECKPOINT] Saved: {saved}{best}")
        return control

    def on_train_begin(self, args, state, control, **kwargs):
        print(f"[INFO] Starting training: {state.max_steps} steps")
        return control

    def on_train_end(self, args, state, control, **kwargs):
        print(f"[FERTIG] Training completed at step {state.global_step}")
        return control

    def on_epoch_end(self, args, state, control, **kwargs):
        print(f"[EPOCH] Epoch {state.epoch:.2f} completed")
        return control


def train(model, tokenizer, train_dataset, eval_dataset, output_dir: Path,
          epochs: int, max_seq_len: int, grad_accum: int, resume_from: str | None,
          stop_config: dict | None = None):
    """Run training."""
    import time as _time
    adapter_name = output_dir.name
    print(f"\n[..] Starting training")
    print(f"     Model:      {adapter_name}")
    print(f"     Epochs:     {epochs}")
    print(f"     Batch:      {BATCH_SIZE} × {grad_accum} = {BATCH_SIZE * grad_accum}")
    print(f"     LR:         {LEARNING_RATE}")
    print(f"     Output:     {output_dir}")
    print(f"\n[i]  Stop with Ctrl+C — checkpoint every {SAVE_STEPS} steps")

    training_args = TrainingArguments(
        output_dir=str(output_dir / "checkpoint"),
        num_train_epochs=stop_config["max_epochs"] if (stop_config and stop_config.get("max_epochs") is not None) else epochs,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=grad_accum,
        learning_rate=LEARNING_RATE,
        warmup_steps=WARMUP_STEPS,
        weight_decay=WEIGHT_DECAY,
        lr_scheduler_type="cosine",
        optim="adamw_8bit",
        fp16=False,
        bf16=True,
        logging_steps=LOGGING_STEPS,
        save_steps=SAVE_STEPS,
        save_strategy="steps",
        eval_steps=EVAL_STEPS,
        eval_strategy="steps",
        save_total_limit=None,
        load_best_model_at_end=False,  # Decouples save/eval schedules (saves every 50, eval every 500)
        report_to="none",
        seed=42,
        dataloader_num_workers=0,
        dataloader_pin_memory=False,
        average_tokens_across_devices=False,
    )

    gc.collect()
    torch.cuda.empty_cache()

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        dataset_text_field="text",
        max_seq_length=max_seq_len,
        args=training_args,
        packing=True,
        callbacks=_build_callbacks(stop_config, output_dir),
    )

    _train_start = _time.time()
    try:
        if resume_from:
            print(f"[i]  Resuming from: {resume_from}")
            trainer.train(resume_from_checkpoint=resume_from)
        else:
            trainer.train()
    except KeyboardInterrupt:
        current_step = trainer.state.global_step if trainer.state else 0
        print(f"[UNTERBROCHEN] Training interrupted at step {current_step}")
        print(f"\n\n[i]  Saving checkpoint ...")
        trainer.save_model(str(output_dir / "checkpoint" / "interrupted"))
        print(f"[OK] Checkpoint saved")
        del trainer
        gc.collect()
        torch.cuda.empty_cache()
        print(f"[INFO] VRAM freed")
        return None

    _total_time = _time.time() - _train_start
    hrs, rem = divmod(int(_total_time), 3600)
    mins, secs = divmod(rem, 60)
    time_str = f"{hrs}h {mins}m {secs}s" if hrs else f"{mins}m {secs}s"
    print(f"[FERTIG] Training completed in {time_str}")
    return trainer


def save_adapter(model, tokenizer, output_dir: Path):
    """Save the finished LoRA adapter."""
    adapter_path = output_dir / "adapter"
    print(f"\n[..] Saving LoRA adapter → {adapter_path}")
    model.save_pretrained(str(adapter_path))
    tokenizer.save_pretrained(str(adapter_path))
    print(f"[OK] Adapter saved!")
    print(f"\n{'='*60}")
    print(f"  Training complete!")
    print(f"  Model:   {output_dir.name}")
    print(f"  Adapter: {adapter_path}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Hime Generic Training Script")
    parser.add_argument("--model",      required=True, choices=list(MODEL_CONFIGS.keys()), help="Model key")
    parser.add_argument("--run-name",   default=None, help="Run name (overrides auto-derived adapter name)")
    parser.add_argument("--epochs",     type=int, default=3, help="Number of training epochs")
    parser.add_argument("--resume",     default=None, help="Path to checkpoint to resume from")
    parser.add_argument("--log-file",   default=None, help="Tee stdout/stderr to this file")
    parser.add_argument("--data-file",  default=None, help="Path to JSONL training data file")
    parser.add_argument("--rank",       type=int, default=None, help="LoRA rank (overrides default)")
    parser.add_argument("--output-dir",  default=None,  help="Output directory for checkpoints/adapter")
    parser.add_argument("--target-loss", type=float, default=None, help="Stop when loss <= this value")
    parser.add_argument("--patience",    type=int,   default=None, help="Evals without improvement before stopping")
    parser.add_argument("--min-delta",   type=float, default=None, help="Min improvement for patience mode")
    parser.add_argument("--min-steps",   type=int,   default=None, help="Don't stop before this step")
    parser.add_argument("--max-epochs",  type=int,   default=None, help="Max training epochs")
    parser.add_argument("--full-resume", action="store_true",
                        help="Full resume incl. optimizer state (may cause VRAM thrashing on 32GB GPUs)")
    parser.add_argument("--fresh",       action="store_true",
                        help="Ignore checkpoints, train from scratch")

    # parse_known_args to ignore HuggingFace Trainer args passed from training_runner
    args, _ = parser.parse_known_args()

    cfg = MODEL_CONFIGS[args.model]
    model_hf_name = cfg['model']
    max_seq       = cfg['max_seq']
    grad_accum    = cfg['grad_accum']
    epochs        = args.epochs

    global LORA_RANK
    if args.rank:
        LORA_RANK = args.rank

    # Derive adapter name — use explicit lora_dir from config so directories
    # always match what training_runner.py and the frontend expect
    if args.run_name:
        adapter_name = args.run_name
    else:
        adapter_name = cfg.get('lora_dir', model_hf_name.split("/")[-1].replace("-bnb-4bit", ""))

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = MODELS_DIR / adapter_name
    output_dir.mkdir(parents=True, exist_ok=True)

    data_file = Path(args.data_file) if args.data_file else TRAINING_DIR / "hime_training_all.jsonl"

    stop_config = _load_stop_config(args)
    # --max-epochs overrides --epochs
    if stop_config.get("max_epochs") is not None:
        epochs = stop_config["max_epochs"]
    else:
        stop_config["max_epochs"] = epochs

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

    print("=" * 60)
    print(f"  Hime - Generic Training Script")
    print(f"  Model key: {args.model}")
    print(f"  HF model:  {model_hf_name}")
    print(f"  Run name:  {adapter_name}")
    print("=" * 60)

    if torch.cuda.is_available():
        gpu = torch.cuda.get_device_properties(0)
        vram = gpu.total_memory / 1024**3
        print(f"\n[OK] GPU: {gpu.name} ({vram:.1f} GB VRAM)")
    else:
        print("[!] No GPU found!")
        return

    print(f"[INFO] max_seq_length: {max_seq}")
    print(f"[INFO] grad_accum: {grad_accum}")
    print(f"[INFO] epochs: {epochs}")
    train_dataset, eval_dataset = load_training_data(data_file)
    model, tokenizer = load_model(model_hf_name, max_seq)
    _warm_start = not args.full_resume and not args.fresh
    if _warm_start:
        print(f"[INFO] Mode: warm-start (adapter weights from checkpoint, fresh optimizer)")
    elif args.full_resume:
        print(f"[INFO] Mode: full-resume (incl. optimizer + scheduler from checkpoint)")
    model, tokenizer, resume_from = apply_lora(model, tokenizer, output_dir, args.resume,
                                                warm_start=_warm_start)
    trainer = train(model, tokenizer, train_dataset, eval_dataset, output_dir,
                    epochs, max_seq, grad_accum, resume_from, stop_config=stop_config)

    if trainer is not None:
        save_adapter(model, tokenizer, output_dir)
        del model, trainer
        gc.collect()
        torch.cuda.empty_cache()
        print(f"[INFO] VRAM freed")


if __name__ == "__main__":
    class TeeOutput:
        def __init__(self, original, log_file):
            self.original = original
            self.log_file = log_file
            self._buffer  = ""

        def _timestamp(self) -> str:
            from datetime import datetime
            return datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

        def write(self, text):
            self.original.write(text)
            self._buffer += text
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                if line.strip():
                    self.log_file.write(f"{self._timestamp()} {line}\n")
                    self.log_file.flush()

        def flush(self):
            self.original.flush()
            if self._buffer.strip():
                self.log_file.write(f"{self._timestamp()} {self._buffer}\n")
                self.log_file.flush()
                self._buffer = ""

        def isatty(self): return False

    _parser = argparse.ArgumentParser(add_help=False)
    _parser.add_argument("--log-file", default=None)
    _args, _ = _parser.parse_known_args()
    if _args.log_file:
        Path(_args.log_file).parent.mkdir(parents=True, exist_ok=True)
        _log_fh = open(_args.log_file, "a", encoding="utf-8", buffering=1)
        sys.stdout = TeeOutput(sys.stdout, _log_fh)
        sys.stderr = TeeOutput(sys.stderr, _log_fh)

    main()
