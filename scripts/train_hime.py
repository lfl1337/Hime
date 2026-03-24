"""
Hime - Training Script (Unsloth QLoRA)
Trainiert LoRA Adapter für JP→EN Light Novel Übersetzung.

Verwendung:
    python train_hime.py

Modell wechseln: MODEL_NAME unten ändern, dann neu starten.
Stoppen:         Ctrl+C → Checkpoint wird gespeichert
Weitermachen:    Einfach neu starten, lädt letzten Checkpoint
"""

import argparse
import os
import sys
os.environ["UNSLOTH_SKIP_TORCHVISION_CHECK"] = "1"

import unsloth  # MUSS als erstes importiert werden!
from unsloth import FastLanguageModel

import gc, json, torch
from pathlib import Path
from datasets import Dataset
from transformers import TrainerCallback, TrainingArguments
from trl import SFTTrainer

# ═══════════════════════════════════════════════════════════════
#  HIER ANPASSEN - Einfach ändern und neu starten
# ═══════════════════════════════════════════════════════════════

# Modell wählen:
# "unsloth/Qwen2.5-32B-Instruct-bnb-4bit"    ← Qwen (zuerst)
# "unsloth/DeepSeek-R1-Distill-Qwen-32B-bnb-4bit" ← DeepSeek
# "unsloth/gemma-3-27b-it-bnb-4bit"          ← Gemma
MODEL_NAME = "unsloth/Qwen2.5-32B-Instruct-bnb-4bit"

# LoRA Parameter
LORA_RANK       = 16    # Reduziert von 32 → weniger VRAM
LORA_ALPHA      = 32    # Meist 2x LORA_RANK
LORA_DROPOUT    = 0.0   # 0 = Unsloth Fast Path aktiv!

# Training Parameter
LEARNING_RATE   = 2e-4
EPOCHS          = 3
BATCH_SIZE      = 1     # Reduziert von 2 → weniger VRAM
GRAD_ACCUM      = 16    # Erhöht → gleiche effektive Batch Size = 16
MAX_SEQ_LEN     = 1024  # Reduziert von 2048 → weniger VRAM
WARMUP_RATIO    = 0.05
WEIGHT_DECAY    = 0.01

# Checkpoint alle N Schritte speichern (tagsüber stoppen!)
SAVE_STEPS      = 100
EVAL_STEPS      = 100
LOGGING_STEPS   = 10

# ═══════════════════════════════════════════════════════════════

PROJECT_ROOT  = Path(r"C:\Projekte\Hime")
TRAINING_DIR  = PROJECT_ROOT / "data" / "training"
MODELS_DIR    = PROJECT_ROOT / "modelle" / "lora"

# Adapter Name aus Modell ableiten
ADAPTER_NAME  = MODEL_NAME.split("/")[-1].replace("-bnb-4bit", "")
OUTPUT_DIR    = MODELS_DIR / ADAPTER_NAME
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Alpaca-style Chat Template
PROMPT_TEMPLATE = """<|im_start|>system
You are a professional Japanese to English translator specializing in yuri light novels. Translate accurately while preserving the intimate tone, character voices, and emotional nuance.<|im_end|>
<|im_start|>user
{instruction}

{input}<|im_end|>
<|im_start|>assistant
{output}<|im_end|>"""


def load_training_data() -> Dataset:
    """Lädt und formatiert die Trainingsdaten."""
    import time as _time
    data_file = TRAINING_DIR / "hime_training_all.jsonl"

    if not data_file.exists():
        raise FileNotFoundError(f"Trainingsdaten nicht gefunden: {data_file}")

    print(f"[..] Lade Trainingsdaten aus {data_file.name} ...")
    print("[INFO] Starte Tokenisierung der Trainingsdaten...")
    _tok_start = _time.time()
    entries = []

    with open(data_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)

            # Nur vollständige Paare
            if not entry.get("input") or not entry.get("output"):
                continue
            if len(entry["input"]) < 50 or len(entry["output"]) < 50:
                continue

            # Prompt formatieren
            text = PROMPT_TEMPLATE.format(
                instruction=entry.get("instruction", "Translate the following Japanese text to English."),
                input=entry["input"],
                output=entry["output"]
            )
            entries.append({"text": text})

    _tok_duration = _time.time() - _tok_start
    print(f"[OK] {len(entries):,} Trainingsbeispiele geladen")
    print(f"[INFO] Tokenisierung abgeschlossen in {_tok_duration:.1f}s")

    # 90% Train, 10% Eval
    split = int(len(entries) * 0.9)
    train_data = entries[:split]
    eval_data  = entries[split:]

    print(f"[OK] Train: {len(train_data):,} | Eval: {len(eval_data):,}")

    return Dataset.from_list(train_data), Dataset.from_list(eval_data)


def load_model():
    """Lädt Basismodell mit Unsloth 4-bit Quantisierung."""
    import time as _time
    print(f"\n[INFO] Lade Modell: {MODEL_NAME}")
    print(f"     Max Seq Len: {MAX_SEQ_LEN}")

    _load_start = _time.time()
    # Free memory before loading to minimise peak pagefile pressure (OS Error 1455)
    gc.collect()
    torch.cuda.empty_cache()
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name      = MODEL_NAME,
        max_seq_length  = MAX_SEQ_LEN,
        dtype           = None,       # Auto: bfloat16 auf modernen GPUs
        load_in_4bit    = True,       # QLoRA
        trust_remote_code = True,
        device_map      = "cuda:0",              # Load shards directly to GPU, skip CPU staging
        low_cpu_mem_usage = True,                # Load one shard at a time — avoids mapping all to RAM
        max_memory      = {0: "30GB", "cpu": "20GB"},  # Cap CPU RAM to prevent pagefile exhaustion
    )
    _load_time = _time.time() - _load_start

    print(f"[INFO] Modell geladen ({_load_time:.1f}s)")
    return model, tokenizer


def apply_lora(model, tokenizer):
    """Fügt LoRA Adapter zum Modell hinzu."""
    print(f"\n[..] Füge LoRA Adapter hinzu (Rank={LORA_RANK})")

    # Prüfe ob bereits ein Checkpoint existiert
    checkpoint_path = OUTPUT_DIR / "checkpoint"
    if (checkpoint_path).exists():
        checkpoints = sorted(checkpoint_path.glob("checkpoint-*"))
        if checkpoints:
            latest = checkpoints[-1]
            print(f"[i]  Checkpoint gefunden: {latest.name} - lade ...")
            model = FastLanguageModel.get_peft_model(
                model,
                r              = LORA_RANK,
                lora_alpha     = LORA_ALPHA,
                lora_dropout   = LORA_DROPOUT,
                target_modules = get_target_modules(),
                bias           = "none",
                use_gradient_checkpointing = "unsloth",
                random_state   = 42,
            )
            return model, tokenizer, str(latest)

    model = FastLanguageModel.get_peft_model(
        model,
        r              = LORA_RANK,
        lora_alpha     = LORA_ALPHA,
        lora_dropout   = LORA_DROPOUT,
        target_modules = get_target_modules(),
        bias           = "none",
        use_gradient_checkpointing = "unsloth",  # Spart VRAM
        random_state   = 42,
    )

    # Parameter zählen
    total_params     = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"[OK] Trainierbare Parameter: {trainable_params:,} ({trainable_params/total_params*100:.2f}%)")

    return model, tokenizer, None


def get_target_modules():
    """Gibt LoRA Target Modules je nach Modell zurück."""
    if "gemma" in MODEL_NAME.lower():
        return ["q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj"]
    else:
        # Qwen2 / DeepSeek (Qwen-based)
        return ["q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj"]


class SaveCheckpointCallback(TrainerCallback):
    """Structured log lines for checkpoint saves, epoch ends, and training lifecycle."""

    def on_save(self, args, state, control, **kwargs):
        checkpoint = state.best_model_checkpoint or f"step-{state.global_step}"
        print(f"[CHECKPOINT] Gespeichert: {checkpoint}")
        return control

    def on_train_begin(self, args, state, control, **kwargs):
        print(f"[INFO] Starte Training: {state.max_steps} Steps")
        return control

    def on_train_end(self, args, state, control, **kwargs):
        print(f"[FERTIG] Training abgeschlossen bei Step {state.global_step}")
        return control

    def on_epoch_end(self, args, state, control, **kwargs):
        print(f"[EPOCH] Epoch {state.epoch:.2f} abgeschlossen")
        return control


def train(model, tokenizer, train_dataset, eval_dataset, resume_from=None):
    """Startet das Training."""
    import time as _time
    print(f"\n[..] Starte Training")
    print(f"     Modell:        {ADAPTER_NAME}")
    print(f"     Epochs:        {EPOCHS}")
    print(f"     Batch Size:    {BATCH_SIZE} × {GRAD_ACCUM} = {BATCH_SIZE * GRAD_ACCUM}")
    print(f"     Learning Rate: {LEARNING_RATE}")
    print(f"     Output:        {OUTPUT_DIR}")
    print(f"\n[i]  Stoppen mit Ctrl+C - Checkpoint alle {SAVE_STEPS} Schritte")

    training_args = TrainingArguments(
        output_dir                    = str(OUTPUT_DIR / "checkpoint"),
        num_train_epochs              = EPOCHS,
        per_device_train_batch_size   = BATCH_SIZE,
        per_device_eval_batch_size    = 1,            # Minimal eval VRAM usage
        gradient_accumulation_steps   = GRAD_ACCUM,
        learning_rate                 = LEARNING_RATE,
        warmup_ratio                  = WARMUP_RATIO,
        weight_decay                  = WEIGHT_DECAY,
        lr_scheduler_type             = "cosine",
        optim                         = "adamw_8bit", # 8-bit optimizer → weniger RAM
        fp16                          = False,         # RTX 5090: bf16 ist nativer
        bf16                          = True,
        logging_steps                 = LOGGING_STEPS,
        save_steps                    = SAVE_STEPS,
        eval_steps                    = EVAL_STEPS,
        eval_strategy                 = "steps",
        save_total_limit              = 3,
        load_best_model_at_end        = True,
        metric_for_best_model         = "eval_loss",
        report_to                     = "none",        # Kein WandB
        seed                          = 42,
        dataloader_num_workers        = 0,             # Windows Kompatibilität
        dataloader_pin_memory         = False,         # Weniger RAM-Pinning
        average_tokens_across_devices = False,         # Suppresses num_items_in_batch warning
    )

    # Clear VRAM before allocating trainer
    import gc
    gc.collect()
    torch.cuda.empty_cache()

    trainer = SFTTrainer(
        model              = model,
        tokenizer          = tokenizer,
        train_dataset      = train_dataset,
        eval_dataset       = eval_dataset,
        dataset_text_field = "text",
        max_seq_length     = MAX_SEQ_LEN,
        args               = training_args,
        packing            = True,         # Mehrere kurze Beispiele in einen Batch packen
        callbacks          = [SaveCheckpointCallback()],
    )

    # Training starten (mit oder ohne Checkpoint)
    _train_start = _time.time()
    try:
        if resume_from:
            print(f"[i]  Weitermachen von: {resume_from}")
            trainer.train(resume_from_checkpoint=resume_from)
        else:
            trainer.train()

    except KeyboardInterrupt:
        current_step = trainer.state.global_step if trainer.state else 0
        print(f"[UNTERBROCHEN] Training unterbrochen bei Step {current_step}")
        print(f"\n\n[i]  Speichere Checkpoint ...")
        trainer.save_model(str(OUTPUT_DIR / "checkpoint" / "interrupted"))
        print(f"[OK] Checkpoint gespeichert")
        del trainer
        gc.collect()
        torch.cuda.empty_cache()
        print(f"[INFO] VRAM freigegeben")
        return None

    _total_time = _time.time() - _train_start
    hrs, rem = divmod(int(_total_time), 3600)
    mins, secs = divmod(rem, 60)
    _time_str = f"{hrs}h {mins}m {secs}s" if hrs else f"{mins}m {secs}s"
    print(f"[FERTIG] Training abgeschlossen in {_time_str}")
    return trainer


def save_adapter(model, tokenizer):
    """Speichert den fertigen LoRA Adapter."""
    adapter_path = OUTPUT_DIR / "adapter"
    print(f"\n[..] Speichere LoRA Adapter → {adapter_path}")

    model.save_pretrained(str(adapter_path))
    tokenizer.save_pretrained(str(adapter_path))

    print(f"[OK] Adapter gespeichert!")
    print(f"\n{'='*60}")
    print(f"  Training abgeschlossen!")
    print(f"  Modell:  {ADAPTER_NAME}")
    print(f"  Adapter: {adapter_path}")
    print(f"{'='*60}")
    print(f"\n  Nächster Schritt: MODEL_NAME ändern und")
    print(f"  nächstes Modell trainieren!")


def main(resume_from_checkpoint=None):
    import gc

    # Memory / parallelism settings — must be set before any CUDA allocation
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True,max_split_size_mb:512")

    print("=" * 60)
    print(f"  Hime - Training Script")
    print(f"  Modell: {ADAPTER_NAME}")
    print("=" * 60)

    # GPU Info
    if torch.cuda.is_available():
        gpu = torch.cuda.get_device_properties(0)
        vram = gpu.total_memory / 1024**3
        print(f"\n[OK] GPU: {gpu.name} ({vram:.1f} GB VRAM)")
    else:
        print("[!] Keine GPU gefunden!")
        return

    # Config summary
    print(f"[INFO] max_seq_length: {MAX_SEQ_LEN}")
    print(f"[INFO] gradient_checkpointing: unsloth")
    print(f"[INFO] optimizer: adamw_8bit")
    print(f"[INFO] bf16: True")

    # Daten laden
    train_dataset, eval_dataset = load_training_data()

    # Modell laden
    model, tokenizer = load_model()

    # LoRA hinzufügen
    model, tokenizer, auto_resume = apply_lora(model, tokenizer)

    # CLI --resume_from_checkpoint takes priority over auto-detected checkpoint
    resume_from = resume_from_checkpoint if resume_from_checkpoint is not None else auto_resume
    if resume_from_checkpoint is not None:
        print(f"[i]  Resume override via CLI: {resume_from_checkpoint}")

    # Training
    trainer = train(model, tokenizer, train_dataset, eval_dataset, resume_from)

    # Adapter speichern (skip if training was interrupted)
    if trainer is not None:
        save_adapter(model, tokenizer)
        del model, trainer
        gc.collect()
        torch.cuda.empty_cache()
        print(f"[INFO] VRAM freigegeben")


if __name__ == "__main__":
    class TeeOutput:
        def __init__(self, original, log_file):
            self.original = original
            self.log_file = log_file
            self._buffer = ""

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
    _parser.add_argument("--resume_from_checkpoint", default=None)
    _args, _ = _parser.parse_known_args()
    if _args.log_file:
        Path(_args.log_file).parent.mkdir(parents=True, exist_ok=True)
        _log_fh = open(_args.log_file, "a", encoding="utf-8", buffering=1)
        sys.stdout = TeeOutput(sys.stdout, _log_fh)
        sys.stderr = TeeOutput(sys.stderr, _log_fh)

    main(resume_from_checkpoint=_args.resume_from_checkpoint)
