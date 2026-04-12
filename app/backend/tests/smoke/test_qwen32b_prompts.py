"""
Smoke test: Qwen2.5-32B + LoRA checkpoint-12400.
Compares baseline (minimal prompt) vs new yuri prompt for T1-T6.

Both variants go through apply_chat_template so the model receives a
properly formatted prompt — not raw text. Return type is a Tensor,
not a dict, so model.generate(inputs, ...) and slice via inputs.shape[1].

This is the ONLY inference run in this session. ~90 s total.
Model is cleaned up after the test (del + cuda.empty_cache).
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


def _generate(model, tokenizer, messages: list[dict], max_new_tokens: int = 150) -> str:
    """
    Format messages via apply_chat_template (returns Tensor), run model.generate,
    decode only the newly generated tokens.
    """
    # apply_chat_template with return_tensors="pt" returns a Tensor directly.
    inputs = tokenizer.apply_chat_template(
        messages,
        return_tensors="pt",
        add_generation_prompt=True,
    ).to("cuda")

    with torch.no_grad():
        output_ids = model.generate(
            inputs,                          # positional Tensor, NOT **dict
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=1.0,
            pad_token_id=tokenizer.eos_token_id,
        )

    new_tokens = output_ids[0][inputs.shape[1]:]   # slice via inputs.shape[1]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


@pytest.mark.smoke
@pytest.mark.slow
def test_qwen32b_yuri_prompt_regression():
    """Run T1-T6 with baseline and new yuri prompt, assert no regressions + T5 fix."""
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

    # Build glossary + character_list for new yuri prompt
    glossary_section = build_glossary_section([
        {"jp": c["jp"], "en": c["en"], "note": c["role"]}
        for c in glossary_data["characters"]
    ])
    character_list = build_character_list(glossary_data["characters"])

    results = []
    try:
        for tc in test_cases:
            # (a) Baseline — minimal prompt, user-role only
            baseline_content = (
                f"Translate the following Japanese to English:\n\n{tc['jp']}\n\nEnglish:"
            )
            baseline_messages = [{"role": "user", "content": baseline_content}]
            baseline_text = _generate(model, tokenizer, baseline_messages)

            # (b) New yuri prompt — system prompt (template) + source text as user message.
            # The template is a system prompt without {source_text}; the source text goes
            # in the user role separately — matching the pipeline's intended architecture.
            system_prompt = render_prompt(
                _QWEN32B_STAGE1,
                glossary=glossary_section,
                character_list=character_list,
                rag_context="",
            )
            new_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": tc["jp"]},
            ]
            new_text = _generate(model, tokenizer, new_messages)

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

    # Print summary table
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

    # Assertions
    regressed = [r for r in results if r["regressed"]]
    assert not regressed, (
        f"REGRESSION detected for: {[r['id'] for r in regressed]}\n"
        f"Details: {[(r['id'], r['baseline'], r['new']) for r in regressed]}"
    )

    # T1, T2, T5, T6 müssen mit dem neuen Prompt grün sein
    must_pass = {"T1", "T2", "T5", "T6"}
    failed = [r for r in results if r["id"] in must_pass and not r["new_pass"]]
    assert not failed, (
        f"Required cases failed with new yuri prompt: {[r['id'] for r in failed]}\n"
        + "\n".join(
            f"  {r['id']}: {r['new']!r}" for r in failed
        )
    )
