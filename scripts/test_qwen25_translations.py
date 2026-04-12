"""
Qwen2.5-32B+LoRA Translation Quality Test
Lädt checkpoint-12400, übersetzt 6 JP→EN Testsätze, misst Token-Rate.

Usage:
    conda run -n hime python -u scripts/test_qwen25_translations.py
"""

import os, sys, time, json, warnings
from pathlib import Path

# ── Live log file — written directly to disk, bypasses conda run buffering ─────
_LOG_PATH = Path(__file__).parent / "test_qwen25_live.log"
_log_file = open(_LOG_PATH, "w", encoding="utf-8", buffering=1)  # line-buffered

def log(msg: str = "") -> None:
    """Print to stdout AND flush to log file immediately."""
    print(msg, flush=True)
    _log_file.write(msg + "\n")
    _log_file.flush()

os.environ["UNSLOTH_SKIP_TORCHVISION_CHECK"] = "1"
os.environ["PYTHONUNBUFFERED"] = "1"
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="peft")

import unsloth
from unsloth import FastLanguageModel
import torch
from pathlib import Path

CHECKPOINT     = r"N:\Projekte\NiN\Hime\modelle\lora\Qwen2.5-32B-Instruct\checkpoint\checkpoint-12400"
MAX_SEQ_LEN    = 1024
MAX_NEW_TOKENS = 128   # 128 reicht für Satz-/Absatzübersetzungen; schneller, kein Endlos-Loop-Risiko

RESULTS_PATH   = Path(__file__).parent / "test_qwen25_results.json"

TEST_CASES = [
    {
        "id": "T1",
        "note": "Short dialogue — confession",
        "jp": "「好きだよ、千夏」\n「え……わたしのこと？」",
    },
    {
        "id": "T2",
        "note": "Honorific + name (Kanade), subject drop",
        "jp": "「先輩、また一緒に部室に来てくれますか？」と奏は少し俯きながら言った。",
    },
    {
        "id": "T3",
        "note": "Literary prose — sakura scene, no explicit subject",
        "jp": "桜の花びらが舞い散る中、二人は黙ったまま並んで歩いた。言葉はなくても、その沈黙は穏やかで、どこか幸せだった。",
    },
    {
        "id": "T4",
        "note": "Internal monologue — conflicted emotion",
        "jp": "（好きって言えない。でも、このまま何も言わないのは、もっと嫌だ。）",
    },
    {
        "id": "T5",
        "note": "Emotional climax — ずっと repetition + physical action",
        "jp": "「あなたのそばにいたい。ずっと、ずっと」\n涙が零れた。伸ばした手は、震えていた。",
    },
    {
        "id": "T6",
        "note": "Honorific chain — Ai-senpai / Rin-senpai / Ayame, three characters",
        "jp": "「藍先輩はいつも凛先輩のことを一番に考えてるんだなって、最近すごく感じます」と彩芽は微笑んだ。",
    },
]

SYSTEM_PROMPT = (
    "You are a professional Japanese to English translator specializing in yuri light novels. "
    "Translate accurately while preserving the intimate tone, character voices, and emotional nuance."
)


def build_prompt(jp: str) -> str:
    return (
        f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\nTranslate the following Japanese text to English:\n\n{jp}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


def save_partial(results: list, avg_tok_s: float) -> None:
    """Write current results to disk after every translation — crash-safe."""
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "checkpoint": CHECKPOINT,
                "complete": False,
                "avg_tok_per_sec": round(avg_tok_s, 2),
                "results": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )


def main() -> None:
    log(f"[test] checkpoint: {CHECKPOINT}")
    log(f"[test] max_new_tokens: {MAX_NEW_TOKENS}")
    log("[test] loading model...")

    t_load = time.time()
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=CHECKPOINT,
        max_seq_length=MAX_SEQ_LEN,
        dtype=None,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)
    log(f"[test] model loaded in {time.time() - t_load:.1f}s")
    log("=" * 70)

    results: list = []
    total_tokens = 0
    total_time = 0.0

    for i, tc in enumerate(TEST_CASES, 1):
        log(f"\n[{i}/{len(TEST_CASES)}] {tc['id']} — {tc['note']}")
        log(f"  JP: {tc['jp']}")

        prompt = build_prompt(tc["jp"])
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        input_len = inputs["input_ids"].shape[1]

        t0 = time.time()
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=False,
                repetition_penalty=1.05,
                pad_token_id=tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        elapsed = time.time() - t0

        out_ids = out[0][input_len:]
        en = tokenizer.decode(out_ids, skip_special_tokens=True).strip()
        tok_s = len(out_ids) / elapsed if elapsed > 0 else 0

        total_tokens += len(out_ids)
        total_time += elapsed

        log(f"  EN: {en}")
        log(f"  [{len(out_ids)} tok | {tok_s:.1f} tok/s | {elapsed:.1f}s]")

        results.append({
            "id": tc["id"],
            "jp": tc["jp"],
            "en": en,
            "tokens": len(out_ids),
            "tok_per_sec": round(tok_s, 2),
            "elapsed_s": round(elapsed, 2),
        })

        # Write after every translation — no data lost on crash
        avg = total_tokens / total_time if total_time > 0 else 0
        save_partial(results, avg)
        log(f"  [saved to {RESULTS_PATH.name}]")

    avg_tok_s = total_tokens / total_time if total_time > 0 else 0
    log("\n" + "=" * 70)
    log(
        f"DONE: {len(TEST_CASES)} translations | {total_tokens} tokens | "
        f"avg {avg_tok_s:.1f} tok/s | total {total_time:.1f}s"
    )

    # Final write — mark complete
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "checkpoint": CHECKPOINT,
                "complete": True,
                "avg_tok_per_sec": round(avg_tok_s, 2),
                "results": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    log(f"Results → {RESULTS_PATH}")


if __name__ == "__main__":
    main()
