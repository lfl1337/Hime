"""Tests for hyperparameter bounds on training start request."""
import pytest
from pydantic import ValidationError

from app.routers.training import StartTrainingRequest


class TestEpochs:
    def test_accepts_one_point_five(self):
        req = StartTrainingRequest(model_name="X", epochs=1.5)  # type: ignore
        assert req.epochs == pytest.approx(1.5)

    def test_rejects_negative(self):
        with pytest.raises(ValidationError):
            StartTrainingRequest(model_name="X", epochs=-1)  # type: ignore

    def test_rejects_too_large(self):
        with pytest.raises(ValidationError):
            StartTrainingRequest(model_name="X", epochs=21)  # type: ignore

    def test_rejects_zero(self):
        with pytest.raises(ValidationError):
            StartTrainingRequest(model_name="X", epochs=0)  # type: ignore


class TestLearningRate:
    def test_accepts_typical_value(self):
        req = StartTrainingRequest(model_name="X", learning_rate=5e-5)  # type: ignore
        assert req.learning_rate == pytest.approx(5e-5)

    def test_rejects_too_small(self):
        with pytest.raises(ValidationError):
            StartTrainingRequest(model_name="X", learning_rate=1e-7)  # type: ignore

    def test_rejects_too_large(self):
        with pytest.raises(ValidationError):
            StartTrainingRequest(model_name="X", learning_rate=1e-1)  # type: ignore


class TestBatchSize:
    def test_rejects_zero(self):
        with pytest.raises(ValidationError):
            StartTrainingRequest(model_name="X", batch_size=0)  # type: ignore

    def test_rejects_too_large(self):
        with pytest.raises(ValidationError):
            StartTrainingRequest(model_name="X", batch_size=128)  # type: ignore


class TestGradAccumSteps:
    def test_rejects_too_large(self):
        with pytest.raises(ValidationError):
            StartTrainingRequest(model_name="X", gradient_accumulation_steps=256)  # type: ignore


class TestLoraR:
    def test_rejects_zero(self):
        with pytest.raises(ValidationError):
            StartTrainingRequest(model_name="X", lora_r=0)  # type: ignore

    def test_rejects_too_large(self):
        with pytest.raises(ValidationError):
            StartTrainingRequest(model_name="X", lora_r=512)  # type: ignore


class TestLoraDropout:
    def test_accepts_zero(self):
        req = StartTrainingRequest(model_name="X", lora_dropout=0.0)  # type: ignore
        assert req.lora_dropout == 0.0

    def test_rejects_negative(self):
        with pytest.raises(ValidationError):
            StartTrainingRequest(model_name="X", lora_dropout=-0.01)  # type: ignore

    def test_rejects_above_half(self):
        with pytest.raises(ValidationError):
            StartTrainingRequest(model_name="X", lora_dropout=0.6)  # type: ignore
