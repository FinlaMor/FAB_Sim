#!/usr/bin/env python3
"""Merge a FAB LoRA adapter into the local Qwen base model and load it into Ollama.

Usage:
    python offline_agents/torchtune_configs/export_to_ollama.py rules
    python offline_agents/torchtune_configs/export_to_ollama.py cards

This is the Windows-friendly export path for adapter-only downloads pulled back from cloud
training. It merges the LoRA adapter into models/qwen2.5-7b, saves a merged model under the
fine-tuned model directory, writes a Modelfile, and runs `ollama create`.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
BASE_MODEL_DIR = ROOT / "models" / "qwen2.5-7b"

ROLE_CONFIG = {
    "rules": {
        "ft_dir": ROOT / "models" / "fab-rules-ft",
        "model_name": "fab-rules-ft",
        "system": "You are an expert Flesh and Blood TCG rules agent. Be precise, cite rules sections, and flag implementation bugs clearly.",
    },
    "cards": {
        "ft_dir": ROOT / "models" / "fab-cards-ft",
        "model_name": "fab-cards-ft",
        "system": "You are an expert Flesh and Blood TCG card implementation validator. Cross-reference card implementations against official card text and rules, and flag bugs clearly.",
    },
}

# Qwen2.5 chat template (must match the base model's tokenizer_config.json chat_template)
_QWEN_TEMPLATE = (
    '{{- if .Messages }}\n'
    '{{- if or .System .Tools }}<|im_start|>system\n'
    '{{- if .System }}\n'
    '{{ .System }}\n'
    '{{- end }}<|im_end|>\n'
    '{{ end }}\n'
    '{{- range $i, $_ := .Messages }}\n'
    '{{- $last := eq (len (slice $.Messages $i)) 1 -}}\n'
    '{{- if eq .Role "user" }}<|im_start|>user\n'
    '{{ .Content }}<|im_end|>\n'
    '{{ else if eq .Role "assistant" }}<|im_start|>assistant\n'
    '{{ if .Content }}{{ .Content }}\n'
    '{{- end }}{{ if not $last }}<|im_end|>\n'
    '{{ end }}\n'
    '{{- end }}\n'
    '{{- if and (ne .Role "assistant") $last }}<|im_start|>assistant\n'
    '{{ end }}\n'
    '{{- end }}\n'
    '{{- else }}\n'
    '{{- if .System }}<|im_start|>system\n'
    '{{ .System }}<|im_end|>\n'
    '{{ end }}{{ if .Prompt }}<|im_start|>user\n'
    '{{ .Prompt }}<|im_end|>\n'
    '{{ end }}<|im_start|>assistant\n'
    '{{ end }}{{ .Response }}{{ if .Response }}<|im_end|>{{ end }}'
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=sorted(ROLE_CONFIG), help="Which fine-tuned model to export")
    parser.add_argument(
        "--quantize",
        default="q4_K_S",
        help="Optional Ollama quantization level (for example: q4_K_S). Use 'none' to disable.",
    )
    parser.add_argument(
        "--quantized-model-name",
        default=None,
        help="Optional explicit model name for the quantized Ollama model",
    )
    parser.add_argument(
        "--skip-ollama",
        action="store_true",
        help="Only build the merged Hugging Face model directory and Modelfile",
    )
    parser.add_argument(
        "--keep-merged",
        action="store_true",
        help="Keep an existing merged directory if present instead of rebuilding it",
    )
    return parser.parse_args()


def latest_epoch_dir(ft_dir: Path) -> Path:
    epoch_dirs = sorted(
        (path for path in ft_dir.glob("epoch_*") if path.is_dir()),
        key=lambda path: int(path.name.split("_", 1)[1]),
    )
    if not epoch_dirs:
        raise FileNotFoundError(f"No epoch_* directory found under {ft_dir}")
    return epoch_dirs[-1]


def ensure_exists(path: Path, description: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing {description}: {path}")


def build_modelfile(
    ft_dir: Path,
    model_name: str,
    system_prompt: str,
    num_ctx: int = 4096,
    num_gpu: int = 16,
) -> Path:
    modelfile = ft_dir / "Modelfile"
    content = "\n".join([
        "FROM ./merged",
        "",
        f'TEMPLATE """{_QWEN_TEMPLATE}"""',
        "",
        f'SYSTEM """{system_prompt}"""',
        "",
        "PARAMETER temperature 0.2",
        "PARAMETER top_p 0.9",
        f"PARAMETER num_ctx {num_ctx}",
        f"PARAMETER num_gpu {num_gpu}",
        "",
    ])
    modelfile.write_text(content, encoding="utf-8")
    return modelfile


def merge_adapter(base_dir: Path, adapter_dir: Path, merged_dir: Path) -> None:
    print(f"=== Loading base model from {base_dir} ===")
    tokenizer = AutoTokenizer.from_pretrained(base_dir)
    model = AutoModelForCausalLM.from_pretrained(
        base_dir,
        torch_dtype="auto",
        device_map="cpu",
        low_cpu_mem_usage=True,
    )

    print(f"=== Loading adapter from {adapter_dir} ===")
    model = PeftModel.from_pretrained(model, adapter_dir, is_trainable=False)

    print("=== Merging adapter into base model ===")
    model = model.merge_and_unload()

    if merged_dir.exists():
        shutil.rmtree(merged_dir)
    merged_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Saving merged model to {merged_dir} ===")
    model.save_pretrained(merged_dir, safe_serialization=True, max_shard_size="4GB")
    tokenizer.save_pretrained(merged_dir)
    if getattr(model, "generation_config", None) is not None:
        model.generation_config.save_pretrained(merged_dir)


def _quant_suffix(quantize: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", quantize.lower())


def _run_ollama_create(model_name: str, modelfile: Path, quantize: str | None = None) -> None:
    ollama_exe = shutil.which("ollama")
    if not ollama_exe:
        raise RuntimeError("Ollama is not on PATH. Install Ollama and ensure `ollama` is available.")

    cmd = [ollama_exe, "create", model_name, "-f", str(modelfile)]
    if quantize:
        cmd.extend(["-q", quantize])
        print(f"=== Creating Ollama model {model_name} (quantized: {quantize}) ===")
    else:
        print(f"=== Creating Ollama model {model_name} ===")
    subprocess.run(cmd, check=True)


def main() -> int:
    args = parse_args()
    role_cfg = ROLE_CONFIG[args.role]
    ft_dir = role_cfg["ft_dir"]
    model_name = role_cfg["model_name"]
    system_prompt = role_cfg["system"]
    quantize = None if args.quantize.lower() == "none" else args.quantize

    ensure_exists(BASE_MODEL_DIR, "base model directory")
    epoch_dir = latest_epoch_dir(ft_dir)
    ensure_exists(epoch_dir / "adapter_config.json", "adapter config")
    ensure_exists(epoch_dir / "adapter_model.safetensors", "adapter safetensors")

    merged_dir = ft_dir / "merged"
    if merged_dir.exists() and args.keep_merged:
        print(f"=== Reusing merged model at {merged_dir} ===")
    else:
        merge_adapter(BASE_MODEL_DIR, epoch_dir, merged_dir)

    modelfile = build_modelfile(
        ft_dir,
        model_name,
        system_prompt,
        num_ctx=4096,
        num_gpu=16,
    )
    print(f"=== Wrote Modelfile to {modelfile} ===")

    if not args.skip_ollama:
        _run_ollama_create(model_name, modelfile)
        print(f"=== Built unquantized model: {model_name} ===")

        if quantize:
            quantized_name = args.quantized_model_name or f"{model_name}-{_quant_suffix(quantize)}"
            _run_ollama_create(quantized_name, modelfile, quantize=quantize)
            print(f"=== Built quantized model: {quantized_name} ===")
            print(f"=== Done. Test with: ollama run {quantized_name} \"Hello\" ===")
        else:
            print(f"=== Done. Test with: ollama run {model_name} \"Hello\" ===")
    else:
        print("=== Skipped `ollama create` as requested ===")

    return 0


if __name__ == "__main__":
    sys.exit(main())
