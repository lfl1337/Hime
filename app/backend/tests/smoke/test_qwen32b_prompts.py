"""
Smoke test: Qwen2.5-32B + LoRA checkpoint-12400.
Compares baseline (minimal prompt) vs new yuri prompt for T1-T6.

This is the ONLY inference run in this session. ~90 s total.
Modell wird nach dem Test ordentlich entladen (del + cuda.empty_cache).
"""
import gc
import json
from pathlib import Path

import pytest
import torch


_CHECKPOINT_PATH = (
    Path(__file__).parents[4]
    / "modelle" / "lora" / "Qwen2.5-32B-Instruct" / "checkpoint-B" / "checkpoint-12400"
)
_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _check_case(tc: dict, output: str) -> bool:
    """Returns True if all pass criteria met."""
    output_lower = output.lower()
    for forbidden in tc.get("forbidden_substrings", []):
        if forbidden.lower() in output_lower:
            return False
    for expected in tc.get("expected_substrings", []):
        if expected.lower() not in output_lower:
            return False
    if tc.get("max_length_chars"):
        if len(output) > tc["max_length_chars"]:
            return False
    return True


@pytest.mark.smoke
@pytest.mark.slow
def test_qwen32b_yuri_prompt_regression():
    """Run T1-T6 with baseline and new prompt, assert no regressions + T5 fix."""
    if not _CHECKPOINT_PATH.exists():
        pytest.skip(
            f"Checkpoint not found: {_CHECKPOINT_PATH}\n"
            "Ask Luca for the correct checkpoint path."
        )

    from unsloth import FastLanguageModel
    from app.pipeline.prompts import (
        _QWEN32B_STAGE1,
        render_prompt,
        build_glossary_section,
        build_character_list,
    )

    test_cases = json.loads(
        (_FIXTURES / "yuri_smoke_test_cases.json").read_text(encoding="utf-8")
    )
    glossary_data = json.loads(
        (_FIXTURES / "yuri_smoke_test_glossary.json").read_text(encoding="utf-8")
    )

    # Load model + LoRA adapter in 4-bit
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(_CHECKPOINT_PATH),
        max_seq_length=2048,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)

    # Build glossary + character_list for new prompt
    glossary_section = build_glossary_section([
        {"jp": c["jp"], "en": c["en"], "note": c["role"]}
        for c in glossary_data["characters"]
    ])
    character_list = build_character_list(glossary_data["characters"])

    results = []
    try:
        for tc in test_cases:
            # (a) Baseline — minimal prompt (old behavior)
            baseline_prompt = (
                f"Translate the following Japanese to English:\n\n{tc['jp']}\n\nEnglish:"
            )
            baseline_ids = tokenizer(baseline_prompt, return_tensors="pt").to("cuda")
            with torch.no_grad():
                baseline_out = model.generate(
                    **baseline_ids,
                    max_new_tokens=150,
                    do_sample=False,
                    temperature=1.0,
                )
            baseline_text = tokenizer.decode(
                baseline_out[0][baseline_ids.input_ids.shape[1]:],
                skip_special_tokens=True,
            ).strip()

            # (b) New yuri prompt with glossary
            new_prompt = render_prompt(
                _QWEN32B_STAGE1,
                source_text=tc["jp"],
                glossary=glossary_section,
                character_list=character_list,
                rag_context="",
            )
            new_ids = tokenizer(new_prompt, return_tensors="pt").to("cuda")
            with torch.no_grad():
                new_out = model.generate(
                    **new_ids,
                    max_new_tokens=150,
                    do_sample=False,
                    temperature=1.0,
                )
            new_text = tokenizer.decode(
                new_out[0][new_ids.input_ids.shape[1]:],
                skip_special_tokens=True,
            ).strip()

            results.append({
                "id": tc["id"],
                "jp": tc["jp"],
                "baseline": baseline_text,
                "baseline_pass": _check_case(tc, baseline_text),
                "new": new_text,
                "new_pass": _check_case(tc, new_text),
                "improved": _check_case(tc, new_text) and not _check_case(tc, baseline_text),
                "regressed": _check_case(tc, baseline_text) and not _check_case(tc, new_text),
            })

    finally:
        # Cleanup — VRAM must be free after test
        del model, tokenizer
        gc.collect()
        torch.cuda.empty_cache()

    # Write JSON report
    report_dirs = sorted(
        Path("N:/Projekte/NiN/Hime/reports").glob("curriculum_prompts_fix_*")
    )
    out_dir = report_dirs[-1] if report_dirs else Path("N:/Projekte/NiN/Hime/reports")
    out_path = out_dir / "smoke_test_results.json"
    out_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSmoke test results written to: {out_path}")

    # Assertions
    regressed = [r for r in results if r["regressed"]]
    assert not regressed, (
        f"REGRESSION detected for: {[r['id'] for r in regressed]}\n"
        f"Details: {regressed}"
    )

    # T5 (pronoun masculinization) MUSS durch den neuen Prompt gefixt sein
    t5 = next((r for r in results if r["id"] == "T5"), None)
    assert t5 is not None, "T5 test case not found in fixtures"
    assert t5["new_pass"], (
        f"T5 (pronoun masculinization) still failing with new yuri prompt.\n"
        f"Output: {t5['new']!r}"
    )

    # Print summary
    print("\n--- Smoke Test Results ---")
    print(f"{'ID':<4} {'Base':>5} {'New':>5} {'Improved':>9} {'Regressed':>10}")
    for r in results:
        print(
            f"{r['id']:<4} "
            f"{'PASS' if r['baseline_pass'] else 'FAIL':>5} "
            f"{'PASS' if r['new_pass'] else 'FAIL':>5} "
            f"{'YES' if r['improved'] else 'no':>9} "
            f"{'YES' if r['regressed'] else 'no':>10}"
        )
