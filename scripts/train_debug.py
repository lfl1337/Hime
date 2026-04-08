"""
Minimal debug training script — stripped of all recent additions.
Tests whether base Unsloth training still works.
"""
import os
from pathlib import Path
import torch
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ["UNSLOTH_SKIP_TORCHVISION_CHECK"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

PROJECT_ROOT = Path(os.environ.get("HIME_PROJECT_ROOT") or Path(__file__).resolve().parent.parent)

import unsloth  # Must be imported first
from unsloth import FastLanguageModel
from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset
import gc
import json
import time

# === PATHS ===
MODEL_NAME = "unsloth/Qwen2.5-32B-Instruct-bnb-4bit"
DATA_FILE = str(PROJECT_ROOT / "data" / "training" / "hime_training_all.jsonl")
OUTPUT_DIR = str(PROJECT_ROOT / "modelle" / "lora" / "Qwen2.5-32B-Instruct" / "checkpoint")
RESUME_FROM = None  # Set to checkpoint path for resume testing

# === MODEL ===
print(f"[DEBUG] Loading model...")
print(f"[DEBUG] CUDA available: {torch.cuda.is_available()}")
print(f"[DEBUG] GPU: {torch.cuda.get_device_name(0)}")
print(f"[DEBUG] VRAM total: {torch.cuda.get_device_properties(0).total_memory/1024**3:.1f}GB")

gc.collect()
torch.cuda.empty_cache()

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=1024,
    dtype=None,
    load_in_4bit=True,
    trust_remote_code=True,
    device_map="cuda:0",
    low_cpu_mem_usage=True,
    max_memory={0: "30GB", "cpu": "20GB"},
)

print(f"[DEBUG] Model loaded. VRAM: {torch.cuda.memory_allocated()/1024**3:.1f}GB alloc / {torch.cuda.memory_reserved()/1024**3:.1f}GB reserved")

print("[DEBUG] Applying LoRA...")
model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    lora_alpha=32,
    lora_dropout=0,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                     "gate_proj", "up_proj", "down_proj"],
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)

print(f"[DEBUG] LoRA applied. VRAM: {torch.cuda.memory_allocated()/1024**3:.1f}GB alloc / {torch.cuda.memory_reserved()/1024**3:.1f}GB reserved")

# === DATA ===
print("[DEBUG] Loading dataset...")
entries = []
with open(DATA_FILE, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        if not entry.get("input") or not entry.get("output"):
            continue
        if len(entry["input"]) < 50 or len(entry["output"]) < 50:
            continue

        PROMPT_TEMPLATE = """<|im_start|>system
You are a professional Japanese to English translator specializing in yuri light novels. Translate accurately while preserving the intimate tone, character voices, and emotional nuance.<|im_end|>
<|im_start|>user
{instruction}

{input}<|im_end|>
<|im_start|>assistant
{output}<|im_end|>"""

        text = PROMPT_TEMPLATE.format(
            instruction=entry.get("instruction", "Translate the following Japanese text to English."),
            input=entry["input"],
            output=entry["output"]
        )
        entries.append({"text": text})

from datasets import Dataset
split = int(len(entries) * 0.9)
train_dataset = Dataset.from_list(entries[:split])
eval_dataset = Dataset.from_list(entries[split:])
print(f"[DEBUG] Train: {len(train_dataset)}, Eval: {len(eval_dataset)}")

# === TRAINER — MINIMAL, NO CUSTOM CALLBACKS ===
print("[DEBUG] Creating trainer...")
args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=1,
    per_device_eval_batch_size=1,
    gradient_accumulation_steps=16,
    num_train_epochs=1,              # Just 1 epoch for testing speed
    warmup_ratio=0.05,
    learning_rate=2e-4,
    fp16=False,
    bf16=True,
    logging_steps=1,                 # Log EVERY step for debugging
    optim="adamw_8bit",
    weight_decay=0.01,
    lr_scheduler_type="cosine",
    seed=42,
    save_steps=10,                   # LOW for testing — save every 10 steps
    save_strategy="steps",
    save_total_limit=None,
    eval_steps=100,
    eval_strategy="steps",
    load_best_model_at_end=False,    # Simpler — no best model tracking
    report_to="none",
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
    max_seq_length=1024,
    args=args,
    packing=True,
)

# === TRAIN ===
print(f"[DEBUG] Starting training, resume from: {RESUME_FROM}")
print(f"[DEBUG] VRAM before train: {torch.cuda.memory_allocated()/1024**3:.1f}GB alloc, {torch.cuda.memory_reserved()/1024**3:.1f}GB reserved")
print(f"[DEBUG] System RAM free: {os.popen('powershell -c (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory').read().strip()} KB")

_start = time.time()
try:
    if RESUME_FROM:
        result = trainer.train(resume_from_checkpoint=RESUME_FROM)
    else:
        result = trainer.train()
    print(f"[DEBUG] Training complete! Final loss: {result.training_loss:.4f}")
    print(f"[DEBUG] Total time: {time.time()-_start:.0f}s")
except Exception as e:
    print(f"[DEBUG] TRAINING CRASHED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
finally:
    if torch.cuda.is_available():
        print(f"[DEBUG] Final VRAM: {torch.cuda.memory_allocated()/1024**3:.1f}GB alloc / {torch.cuda.memory_reserved()/1024**3:.1f}GB reserved")
    print(f"[DEBUG] Elapsed: {time.time()-_start:.0f}s")
