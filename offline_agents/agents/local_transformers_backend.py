from __future__ import annotations

from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, GenerationConfig


_STOP_PHRASES = [
    "\n\n\n",
    "Human:",
    "User:",
    "Assistant:",
    "### ",
]


def _trim_output(text: str) -> str:
    """Remove trailing verbosity: cut at the first hard stop phrase."""
    for phrase in _STOP_PHRASES:
        idx = text.find(phrase)
        if idx != -1:
            text = text[:idx]
    return text.strip()


class LocalTransformersBackend:
    """Lazy-loaded local Transformers backend for merged fine-tuned models."""

    def __init__(self, model_dir: Path, system_prompt: str, max_new_tokens: int = 256):
        self.model_dir = model_dir
        self.system_prompt = system_prompt
        self.max_new_tokens = max_new_tokens
        self._model = None
        self._tokenizer = None
        self._generation_config = None

    def is_available(self) -> bool:
        return (
            self.model_dir.exists()
            and (self.model_dir / "config.json").exists()
            and (self.model_dir / "model.safetensors.index.json").exists()
        )

    def _load(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return

        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_dir,
            device_map="cpu",
            low_cpu_mem_usage=True,
            torch_dtype="auto",
        )
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
        if self._tokenizer.pad_token_id is None and self._tokenizer.eos_token_id is not None:
            self._tokenizer.pad_token = self._tokenizer.eos_token
        self._generation_config = GenerationConfig.from_model_config(self._model.config)
        self._generation_config.max_new_tokens = self.max_new_tokens
        self._generation_config.do_sample = True
        self._generation_config.temperature = 0.1
        self._generation_config.repetition_penalty = 1.15
        self._generation_config.pad_token_id = self._tokenizer.pad_token_id
        self._generation_config.eos_token_id = self._tokenizer.eos_token_id

    def generate(self, prompt: str, context: str = "") -> str:
        self._load()

        user_content = f"{context}\n\n---\n\n{prompt}" if context else prompt
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]

        if hasattr(self._tokenizer, "apply_chat_template"):
            rendered_prompt = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            rendered_prompt = (
                f"System: {self.system_prompt}\n\n"
                f"User: {user_content}\n\n"
                "Assistant:"
            )

        inputs = self._tokenizer(rendered_prompt, return_tensors="pt")
        model_device = getattr(self._model, "device", torch.device("cpu"))
        inputs = {key: value.to(model_device) for key, value in inputs.items()}

        with torch.inference_mode():
            outputs = self._model.generate(
                **inputs,
                generation_config=self._generation_config,
            )

        generated_tokens = outputs[0][inputs["input_ids"].shape[1]:]
        raw = self._tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()
        return _trim_output(raw)