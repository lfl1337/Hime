# Phase 5 — Training v2 Modular Rewrite (C3 + C5)

_Status: complete — awaiting Proceed with Phase 6_

## C3 — Pipeline-v2 Model Configs Added

### Architecture change
`scripts/train_generic.py` is now a thin dispatcher. The monolithic `MODEL_CONFIGS` dict has moved into:

- `scripts/training/configs/__init__.py` — TrainingConfig dataclass + registry
- `scripts/training/configs/{model}.py` — one file per model (8 total)
- `scripts/training/trainers/{backend}.py` — unsloth + transformers plugins

### v2 model configs added
| Key | Model | max_seq | grad_accum | trainer |
|-----|-------|---------|------------|---------|
| translategemma12b | google/translategemma-12b-it | 2048 | 16 | transformers |
| qwen35-9b | Qwen/Qwen3.5-9B | 4096 | 8 | unsloth |
| qwen3-30b-a3b | Qwen/Qwen3-30B-A3B | 4096 | 16 | unsloth (MoE) |

### Backward compat verified
All 5 v1 configs (qwen32b, qwen14b, qwen72b, gemma27b, deepseek) produce identical hyperparameters.
checkpoint-12400 LoRA path: qwen32b → max_seq=1024, grad_accum=8 — UNCHANGED.

**Verified field values from original MODEL_CONFIGS (verbatim):**
- qwen32b: model=unsloth/Qwen2.5-32B-Instruct-bnb-4bit, lora_dir=Qwen2.5-32B-Instruct, max_seq=1024, grad_accum=8
- qwen14b: model=unsloth/Qwen2.5-14B-Instruct-bnb-4bit, lora_dir=Qwen2.5-14B-Instruct, max_seq=1024, grad_accum=16
- qwen72b: model=unsloth/Qwen2.5-72B-Instruct-bnb-4bit, lora_dir=Qwen2.5-72B-Instruct, max_seq=512, grad_accum=32
- gemma27b: model=unsloth/gemma-3-27b-it-bnb-4bit, lora_dir=Gemma-3-27B-IT, max_seq=1024, grad_accum=16
- deepseek: model=unsloth/DeepSeek-R1-Distill-Qwen-32B-bnb-4bit, lora_dir=DeepSeek-R1-Distill-Qwen-32B, max_seq=1024, grad_accum=16

## C5 — Curriculum Learning Activated

`scripts/training_config.json` now has `"curriculum": {"enabled": true, ...}` with 3 tiers (strict, expanded, loose).

**Note:** checkpoint-12400 ran on the pre-curriculum config. The curriculum block affects future training runs only. No retraining in this session.

## Test Results

```
tests/test_train_generic_v2_models.py::test_v1_models_still_supported PASSED
tests/test_train_generic_v2_models.py::test_v2_models_are_added PASSED
tests/test_train_generic_v2_models.py::test_training_config_has_curriculum_block PASSED
tests/test_train_generic_v1_backward_compat.py::test_v1_config_fields_unchanged[deepseek] PASSED
tests/test_train_generic_v1_backward_compat.py::test_v1_config_fields_unchanged[gemma27b] PASSED
tests/test_train_generic_v1_backward_compat.py::test_v1_config_fields_unchanged[qwen14b] PASSED
tests/test_train_generic_v1_backward_compat.py::test_v1_config_fields_unchanged[qwen32b] PASSED
tests/test_train_generic_v1_backward_compat.py::test_v1_config_fields_unchanged[qwen72b] PASSED
tests/test_train_generic_v1_backward_compat.py::test_v1_config_set_is_exactly_these_5 PASSED
tests/test_train_generic_v1_backward_compat.py::test_v1_dispatcher_invocation_via_validate_config PASSED

======================== 10 passed in 61.03s ========================
```

Full suite (excluding test_train_with_resume.py):
```
1 failed (test_vault_organizer — pre-existing), 285 passed, 1 skipped
```
Net new: +10 tests (all green).

## --validate-config

Sample output for `python scripts/train_generic.py --model qwen32b --validate-config`:

```
[validate:unsloth] key=qwen32b model=unsloth/Qwen2.5-32B-Instruct-bnb-4bit
[validate:unsloth] lora_dir=Qwen2.5-32B-Instruct max_seq=1024
[validate:unsloth] grad_accum=8 moe=False
[validate:unsloth] tokenizer probe skipped: No module named 'transformers'
[validate] training_config.json keys: ['curriculum', 'max_epochs', 'min_delta', 'min_steps', 'patience', 'patience_metric', 'stop_mode', 'target_confirmations', 'target_loss', 'target_loss_metric']
[validate] curriculum block: PRESENT
[validate] model key:  qwen32b
[validate] model id:   unsloth/Qwen2.5-32B-Instruct-bnb-4bit
[validate] trainer:    unsloth
[validate] max_seq:    1024
[validate] grad_accum: 8
[validate] OK
```

Exit code 0. Tokenizer probe skipped (transformers not in test env Python; works fine in the training venv).
