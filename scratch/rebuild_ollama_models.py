"""Rebuild Ollama models with correct Qwen2.5 chat template (no re-merge needed)."""
import subprocess, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent

QWEN_TEMPLATE = (
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

CONFIGS = [
    {
        "ft_dir": ROOT / "models" / "fab-rules-ft",
        "system": "You are an expert Flesh and Blood TCG rules agent. Be precise, cite rules sections, and flag implementation bugs clearly.",
        "models": ["fab-rules-ft", "fab-rules-ft-q4ks"],
        "quantize": "q4_K_S",
    },
    {
        "ft_dir": ROOT / "models" / "fab-cards-ft",
        "system": "You are an expert Flesh and Blood TCG card implementation validator. Cross-reference card implementations against official card text and rules, and flag bugs clearly.",
        "models": ["fab-cards-ft", "fab-cards-ft-q4ks"],
        "quantize": "q4_K_S",
    },
]

ollama = shutil.which("ollama")

for cfg in CONFIGS:
    ft_dir = cfg["ft_dir"]
    merged_dir = ft_dir / "merged"
    assert merged_dir.exists(), f"Missing merged dir: {merged_dir}"

    # Write Modelfile pointing to the merged dir
    modelfile = ft_dir / "Modelfile"
    content = "\n".join([
        f"FROM {merged_dir}",
        "",
        f'TEMPLATE """{QWEN_TEMPLATE}"""',
        "",
        f'SYSTEM """{cfg["system"]}"""',
        "",
        "PARAMETER temperature 0.2",
        "PARAMETER top_p 0.9",
        "PARAMETER num_ctx 4096",
        "PARAMETER num_gpu 16",
        "",
    ])
    modelfile.write_text(content, encoding="utf-8")
    print(f"Wrote Modelfile: {modelfile}")

    base_model_name = cfg["models"][0]
    quantized_name = cfg["models"][1]
    quantize = cfg["quantize"]

    # Create unquantized model
    print(f"\n=== Creating {base_model_name} ===")
    subprocess.run([ollama, "create", base_model_name, "-f", str(modelfile)], check=True)

    # Create quantized model
    print(f"\n=== Creating {quantized_name} (quantize={quantize}) ===")
    subprocess.run([ollama, "create", quantized_name, "-f", str(modelfile), "-q", quantize], check=True)

    print(f"\nDone with {base_model_name} and {quantized_name}\n")

print("\nAll models rebuilt. Run: ollama list")
