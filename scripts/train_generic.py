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


# ---------------------------------------------------------------------------
# Model configurations
# ---------------------------------------------------------------------------

MODEL_CONFIGS = {
    'qwen32b': {
        'model':    'unsloth/Qwen2.5-32B-Instruct-bnb-4bit',
        'lora_dir': 'Qwen2.5-32B-Instruct',
        'max_seq':  1024,
        'grad_accum': 16,
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
LORA_DROPOUT = 0.0

# Training defaults
LEARNING_RATE = 2e-4
BATCH_SIZE    = 1
SAVE_STEPS    = 100
EVAL_STEPS    = 100
LOGGING_STEPS = 10
WARMUP_RATIO  = 0.05
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


def apply_gpu_limit(limit_pct: int) -> None:
    import subprocess
    fraction = limit_pct / 100.0
    torch.cuda.set_per_process_memory_fraction(fraction)
    power_watts = int(575 * fraction)
    try:
        subprocess.run(
            ['nvidia-smi', '-pl', str(power_watts)],
            capture_output=True, timeout=5
        )
        print(f"[INFO] GPU limit: {limit_pct}% "
              f"({power_watts}W / {31.842 * fraction:.1f} GB VRAM reserved)")
    except Exception:
        print(f"[INFO] GPU memory fraction: {fraction:.2f} "
              f"({31.842 * fraction:.1f} GB VRAM reserved)")


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
        max_memory={0: "30GB", "cpu": "20GB"},  # Cap CPU RAM to prevent pagefile exhaustion
    )
    print(f"[INFO] Model loaded ({_time.time() - _load_start:.1f}s)")
    return model, tokenizer


def get_target_modules(model_name: str) -> list:
    """Return LoRA target modules for the model architecture."""
    return ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def apply_lora(model, tokenizer, output_dir: Path, resume_path: str | None):
    """Add LoRA adapter, auto-detecting existing checkpoints if no explicit resume path."""
    print(f"\n[..] Adding LoRA adapter (Rank={LORA_RANK})")

    # Auto-detect latest checkpoint if not explicitly provided
    if resume_path is None:
        cp_dir = output_dir / "checkpoint"
        if cp_dir.exists():
            checkpoints = sorted(cp_dir.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[-1]) if p.name.split("-")[-1].isdigit() else 0)
            if checkpoints:
                resume_path = str(checkpoints[-1])
                print(f"[i]  Auto-detected checkpoint: {checkpoints[-1].name}")

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

    if resume_path is None:
        total_params     = sum(p.numel() for p in model.parameters())
        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        print(f"[OK] Trainable parameters: {trainable_params:,} ({trainable_params/total_params*100:.2f}%)")

    return model, tokenizer, resume_path


class SaveCheckpointCallback(TrainerCallback):
    """Structured log lines for checkpoint saves and training lifecycle events."""

    def on_save(self, args, state, control, **kwargs):
        checkpoint = state.best_model_checkpoint or f"step-{state.global_step}"
        print(f"[CHECKPOINT] Saved: {checkpoint}")
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
          epochs: int, max_seq_len: int, grad_accum: int, resume_from: str | None):
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
        num_train_epochs=epochs,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=grad_accum,
        learning_rate=LEARNING_RATE,
        warmup_ratio=WARMUP_RATIO,
        weight_decay=WEIGHT_DECAY,
        lr_scheduler_type="cosine",
        optim="adamw_8bit",
        fp16=False,
        bf16=True,
        logging_steps=LOGGING_STEPS,
        save_steps=SAVE_STEPS,
        eval_steps=EVAL_STEPS,
        eval_strategy="steps",
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
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
        callbacks=[SaveCheckpointCallback()],
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
    parser.add_argument("--output-dir", default=None, help="Output directory for checkpoints/adapter")
    parser.add_argument("--gpu-limit",  type=int, default=98,
                        help="GPU VRAM usage limit %% (80–100). Default 98 leaves ~400 MB free for OS.")

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

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = (
        "expandable_segments:True,"
        "max_split_size_mb:512,"
        f"max_memory_fraction={args.gpu_limit/100:.2f}"
    )

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
    print(f"[INFO] GPU limit: {args.gpu_limit}% (~{31.842 * args.gpu_limit/100:.1f} GB VRAM)")
    apply_gpu_limit(args.gpu_limit)

    train_dataset, eval_dataset = load_training_data(data_file)
    model, tokenizer = load_model(model_hf_name, max_seq)
    model, tokenizer, resume_from = apply_lora(model, tokenizer, output_dir, args.resume)
    trainer = train(model, tokenizer, train_dataset, eval_dataset, output_dir,
                    epochs, max_seq, grad_accum, resume_from)

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
