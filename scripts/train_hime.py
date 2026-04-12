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

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from callbacks.smart_stopping import SmartStoppingCallback
from callbacks.manual_save import ManualSaveCallback

# Inserted by WS1 v1.2.1 — curriculum learning hook (NEXT RUN ONLY)
import sys as _sys2
_sys2.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "backend"))

try:
    from app.training.curriculum import CurriculumDataLoader, Tier
    from app.training.curriculum_callback import CurriculumCallback
    _CURRICULUM_AVAILABLE = True
except Exception as _e:
    print(f"[curriculum] Module unavailable ({_e}); falling back to legacy data loader")
    _CURRICULUM_AVAILABLE = False


def _load_curriculum_config() -> dict | None:
    cfg_path = Path(__file__).parent / "training_config.json"
    if not cfg_path.exists():
        return None
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return data.get("curriculum")
    except Exception:
        return None


def _load_curriculum_state(state_path: Path) -> dict | None:
    if not state_path.exists():
        return None
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return None

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
LORA_DROPOUT    = 0.05  # Regularisierung gegen Overfitting (deaktiviert Unsloth Fast Path)

# Training Parameter
LEARNING_RATE   = 5e-5  # Gesenkt von 2e-4 — Feinschliff nach Loss-Plateau
EPOCHS          = 3
BATCH_SIZE      = 1     # Reduziert von 2 → weniger VRAM
GRAD_ACCUM      = 8     # Halbiert von 16 → schnellere Steps, rauschigere Gradienten
MAX_SEQ_LEN     = 1024  # Reduziert von 2048 → weniger VRAM
WARMUP_STEPS    = 50    # Fixe 50 Steps statt 5% Ratio — reicht für frischen Optimizer
WEIGHT_DECAY    = 0.01

# Checkpoint alle N Schritte speichern (tagsüber stoppen!)
SAVE_STEPS      = 20
EVAL_STEPS      = 500
LOGGING_STEPS   = 10

# ═══════════════════════════════════════════════════════════════

_SCRIPT_ROOT  = Path(__file__).resolve().parent.parent
PROJECT_ROOT  = Path(os.environ.get("HIME_MODELS_DIR", str(_SCRIPT_ROOT / "modelle"))).parent
TRAINING_DIR  = Path(os.environ.get("HIME_TRAINING_DATA_DIR", str(_SCRIPT_ROOT / "data" / "training")))
MODELS_DIR    = Path(os.environ.get("HIME_MODELS_DIR", str(_SCRIPT_ROOT / "modelle"))) / "lora"

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

    # ----- Curriculum override (v1.2.1, NEXT RUN ONLY) -----
    cfg = _load_curriculum_config()
    if _CURRICULUM_AVAILABLE and cfg and cfg.get("enabled"):
        state_path = OUTPUT_DIR / "curriculum_state.json"
        state = _load_curriculum_state(state_path) or {}
        tier_idx = int(state.get("current_tier_index", 0))
        tiers_cfg = cfg["tiers"]
        if tier_idx >= len(tiers_cfg):
            tier_idx = len(tiers_cfg) - 1
        active_tier = tiers_cfg[tier_idx]
        min_score = float(active_tier["min_score"])
        source_file = TRAINING_DIR / "hime_training_all.jsonl"
        literary = [TRAINING_DIR / Path(p).name for p in cfg.get("literary_files", [])]

        print(f"[curriculum] tier={active_tier['name']} min_score={min_score}")
        loader = CurriculumDataLoader(source_file=source_file, literary_files=literary)
        ds = loader.load(min_score=min_score)
        # Format with PROMPT_TEMPLATE
        formatted = []
        for entry in ds:
            text = PROMPT_TEMPLATE.format(
                instruction=entry.get("instruction", "Translate the following Japanese text to English."),
                input=entry["input"],
                output=entry["output"],
            )
            formatted.append({"text": text})

        # 90/10 split (matches legacy path so downstream train() signature stays identical)
        split = int(len(formatted) * 0.9)
        train_data = formatted[:split]
        eval_data  = formatted[split:]
        print(f"[curriculum] formatted={len(formatted):,} | Train: {len(train_data):,} | Eval: {len(eval_data):,}")
        return Dataset.from_list(train_data), Dataset.from_list(eval_data)

    # ----- Legacy path -----
    # Loads hime_training_filtered.jsonl (104,866 pre-scored JParaCrawl pairs, score ≥ 0.70).
    # CurriculumDataLoader bypassed for all models until literary files are Bertalign-aligned.
    # See scripts/cleanup_candidates.md for what to restore once that's done.
    data_file = TRAINING_DIR / "hime_training_filtered.jsonl"

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
        max_memory      = {0: "30GB", "cpu": "20GB"},
    )
    _load_time = _time.time() - _load_start

    print(f"[INFO] Modell geladen ({_load_time:.1f}s)")
    return model, tokenizer


def _find_best_checkpoint():
    """Find the best checkpoint by eval_loss from trainer_state.json."""
    checkpoint_path = OUTPUT_DIR / "checkpoint"
    if not checkpoint_path.exists():
        return None
    checkpoints = sorted(checkpoint_path.glob("checkpoint-*"))
    if not checkpoints:
        return None

    best_cp = None
    best_loss = float("inf")
    for cp in checkpoints:
        state_file = cp / "trainer_state.json"
        if state_file.exists():
            with open(state_file) as f:
                state = json.load(f)
            metric = state.get("best_metric")
            if metric is not None and metric < best_loss:
                best_loss = metric
                best_cp = cp
    return best_cp


def apply_lora(model, tokenizer, warm_start=False, from_best=False):
    """Fügt LoRA Adapter zum Modell hinzu.

    warm_start: Load adapter weights from checkpoint but don't pass resume_from
                to trainer (fresh optimizer). Avoids VRAM fragmentation that causes
                catastrophic slowdown on 32GB GPUs.
    from_best:  Use the best checkpoint (by eval_loss) instead of the latest.
    """
    print(f"\n[..] Füge LoRA Adapter hinzu (Rank={LORA_RANK})")

    # Always create fresh LoRA adapter first
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

    # Parameter zählen
    total_params     = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"[OK] Trainierbare Parameter: {trainable_params:,} ({trainable_params/total_params*100:.2f}%)")

    # Check for existing checkpoints
    checkpoint_path = OUTPUT_DIR / "checkpoint"
    if not checkpoint_path.exists():
        return model, tokenizer, None

    checkpoints = sorted(checkpoint_path.glob("checkpoint-*"))
    if not checkpoints:
        return model, tokenizer, None

    if from_best:
        target_cp = _find_best_checkpoint()
        if target_cp is None:
            target_cp = checkpoints[-1]
        print(f"[i]  Bester Checkpoint: {target_cp.name}")
    else:
        target_cp = checkpoints[-1]
        print(f"[i]  Letzter Checkpoint: {target_cp.name}")

    if warm_start:
        # Warm-start: load adapter weights only, skip optimizer/scheduler/step.
        # This avoids CUDA memory fragmentation from loading optimizer.pt which
        # causes catastrophic performance degradation (~40x slower) on GPUs where
        # VRAM headroom < ~2GB after optimizer state is loaded.
        adapter_file = target_cp / "adapter_model.safetensors"
        if adapter_file.exists():
            from safetensors.torch import load_file
            print(f"[i]  Warm-Start: Lade Adapter-Gewichte aus {target_cp.name} (kein Optimizer)")
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
            print(f"[OK] Adapter-Gewichte geladen ({loaded_count} Tensoren). Optimizer wird frisch initialisiert.")
            return model, tokenizer, None  # No resume_from → fresh optimizer
        else:
            print(f"[!]  adapter_model.safetensors nicht gefunden in {target_cp.name}")
            return model, tokenizer, None
    else:
        # Full resume: Trainer loads adapter + optimizer + scheduler + step.
        # WARNING: May cause VRAM fragmentation and severe slowdown on 32GB GPUs.
        print(f"[i]  Full-Resume von: {target_cp.name} (inkl. Optimizer)")
        return model, tokenizer, str(target_cp)


def get_target_modules():
    """Gibt LoRA Target Modules je nach Modell zurück."""
    if "gemma" in MODEL_NAME.lower():
        return ["q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj"]
    else:
        # Qwen2 / DeepSeek (Qwen-based)
        return ["q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj"]


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
        "max_epochs": EPOCHS,
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
    if getattr(cli_args, "max_steps", None) is not None:
        defaults["max_steps"] = cli_args.max_steps

    return defaults


def _build_callbacks(stop_config: dict | None) -> list:
    """Build the callbacks list, optionally including SmartStoppingCallback and CurriculumCallback."""
    cbs = [SaveCheckpointCallback(), ManualSaveCallback()]
    if stop_config is not None:
        mode = stop_config.get("stop_mode", "none")
        has_target = stop_config.get("target_loss") is not None
        has_patience = stop_config.get("patience") is not None
        if mode != "none" and (has_target or has_patience):
            state_file = str(OUTPUT_DIR / "smart_stop_state.json")
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

    # Curriculum callback (v1.2.1, NEXT RUN ONLY) — appended if config has curriculum.enabled
    _cfg_check = _load_curriculum_config()
    if _CURRICULUM_AVAILABLE and _cfg_check and _cfg_check.get("enabled"):
        _tiers = [Tier(name=t["name"], min_score=float(t["min_score"])) for t in _cfg_check["tiers"]]
        _trigger = _cfg_check.get("promotion_trigger", {})
        cbs.append(
            CurriculumCallback(
                tiers=_tiers,
                state_path=OUTPUT_DIR / "curriculum_state.json",
                patience=int(_trigger.get("patience", 3)),
                min_delta=float(_trigger.get("min_delta", 0.001)),
            )
        )
    return cbs


class SaveCheckpointCallback(TrainerCallback):
    """Structured log lines for checkpoint saves, epoch ends, and training lifecycle."""

    def on_save(self, args, state, control, **kwargs):
        saved = f"checkpoint-{state.global_step}"
        best = f" | best={state.best_metric:.4f} @ {os.path.basename(state.best_model_checkpoint or '')}" if state.best_model_checkpoint else ""
        if torch.cuda.is_available():
            alloc = torch.cuda.memory_allocated() / 1024**3
            reserved = torch.cuda.memory_reserved() / 1024**3
            print(f"[CHECKPOINT] Gespeichert: {saved}{best} (VRAM: {alloc:.1f}GB alloc / {reserved:.1f}GB reserved)")
        else:
            print(f"[CHECKPOINT] Gespeichert: {saved}{best}")
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


def train(model, tokenizer, train_dataset, eval_dataset, resume_from=None, stop_config=None):
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
        max_steps                     = stop_config["max_steps"] if (stop_config and stop_config.get("max_steps")) else -1,
        num_train_epochs              = stop_config["max_epochs"] if stop_config else EPOCHS,
        per_device_train_batch_size   = BATCH_SIZE,
        per_device_eval_batch_size    = 1,            # Minimal eval VRAM usage
        gradient_accumulation_steps   = GRAD_ACCUM,
        learning_rate                 = LEARNING_RATE,
        warmup_steps                  = WARMUP_STEPS,
        weight_decay                  = WEIGHT_DECAY,
        lr_scheduler_type             = "cosine",
        optim                         = "adamw_8bit", # 8-bit optimizer → weniger RAM
        fp16                          = False,         # RTX 5090: bf16 ist nativer
        bf16                          = True,
        logging_steps                 = LOGGING_STEPS,
        save_steps                    = SAVE_STEPS,
        save_strategy                 = "steps",
        eval_steps                    = EVAL_STEPS,
        eval_strategy                 = "steps",
        save_total_limit              = None,
        load_best_model_at_end        = False,  # Decouples save/eval schedules (saves every 20, eval every 500)
        max_grad_norm                 = 0.5,    # Grad-clipping: Norms lagen bei 0.7–1.4, 0.5 für stabilere Schritte
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
        callbacks          = _build_callbacks(stop_config),
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


def main(resume_from_checkpoint=None, stop_config=None, warm_start=True, from_best=False, full_resume=False):
    import gc

    # Memory / parallelism settings — must be set before any CUDA allocation
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True,garbage_collection_threshold:0.6"

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

    # Resolve resume mode: --full-resume overrides warm_start
    if full_resume:
        warm_start = False
        print(f"[INFO] Modus: Full-Resume (Optimizer + Scheduler aus Checkpoint)")
    elif warm_start:
        print(f"[INFO] Modus: Warm-Start (Adapter-Gewichte laden, frischer Optimizer)")

    # Daten laden
    train_dataset, eval_dataset = load_training_data()

    # Modell laden
    model, tokenizer = load_model()

    # LoRA hinzufügen
    model, tokenizer, auto_resume = apply_lora(
        model, tokenizer, warm_start=warm_start, from_best=from_best
    )

    # CLI --resume_from_checkpoint takes priority over auto-detected checkpoint
    resume_from = resume_from_checkpoint if resume_from_checkpoint is not None else auto_resume
    if resume_from_checkpoint is not None:
        print(f"[i]  Resume override via CLI: {resume_from_checkpoint}")

    # Training
    trainer = train(model, tokenizer, train_dataset, eval_dataset, resume_from, stop_config=stop_config)

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
    _parser.add_argument("--target-loss",  type=float, default=None, help="Stop when loss <= this value")
    _parser.add_argument("--patience",     type=int,   default=None, help="Evals without improvement before stopping")
    _parser.add_argument("--min-delta",    type=float, default=None, help="Min improvement for patience mode")
    _parser.add_argument("--min-steps",    type=int,   default=None, help="Don't stop before this step")
    _parser.add_argument("--max-steps",    type=int,   default=None, help="Stop after this many total steps (overrides epochs)")
    _parser.add_argument("--max-epochs",   type=int,   default=None, help="Max training epochs")
    _parser.add_argument("--full-resume",  action="store_true",
                         help="Full resume incl. optimizer state (may cause VRAM thrashing on 32GB GPUs)")
    _parser.add_argument("--from-best",    action="store_true",
                         help="Use best checkpoint (by eval_loss) instead of latest")
    _parser.add_argument("--fresh",        action="store_true",
                         help="Ignore checkpoints, train from scratch")
    _parser.add_argument("--model-dir",    type=str,
        default=os.environ.get("HIME_MODELS_DIR", str(Path(__file__).resolve().parent.parent / "modelle")),
        help="Base models directory")
    _parser.add_argument("--training-data", type=str,
        default=os.environ.get("HIME_TRAINING_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data" / "training")),
        help="Training data directory")
    _parser.add_argument("--output-dir",   type=str,
        default=None,
        help="Override LoRA output directory")
    _args, _ = _parser.parse_known_args()

    # Apply path overrides to module-level globals before main() runs
    LORA_OUTPUT = _args.output_dir or str(Path(_args.model_dir) / "lora" / ADAPTER_NAME)
    DATA_PATH   = str(Path(_args.training_data) / "hime_training_filtered.jsonl")
    # Patch globals so load_training_data() and train() pick them up
    _mod = sys.modules[__name__]
    _mod.OUTPUT_DIR   = Path(LORA_OUTPUT)
    _mod.TRAINING_DIR = Path(_args.training_data)
    Path(LORA_OUTPUT).mkdir(parents=True, exist_ok=True)

    if _args.log_file:
        Path(_args.log_file).parent.mkdir(parents=True, exist_ok=True)
        _log_fh = open(_args.log_file, "a", encoding="utf-8", buffering=1)
        sys.stdout = TeeOutput(sys.stdout, _log_fh)
        sys.stderr = TeeOutput(sys.stderr, _log_fh)

    _stop_config = _load_stop_config(_args)
    main(
        resume_from_checkpoint=_args.resume_from_checkpoint,
        stop_config=_stop_config,
        warm_start=not _args.full_resume and not _args.fresh,
        from_best=_args.from_best,
        full_resume=_args.full_resume,
    )
