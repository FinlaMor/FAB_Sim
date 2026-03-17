import ollama, time

t = time.time()
r = ollama.chat(
    model="fab-cards-ft-q4ks",
    messages=[{"role": "user", "content": "Hello, what is 2+2?"}],
    options={"num_gpu": 16, "num_ctx": 256, "num_predict": 30},
)
elapsed = round(time.time() - t, 1)

with open("ollama_probe_out.txt", "w") as f:
    f.write(f"elapsed: {elapsed}s\n")
    f.write(f"done_reason: {r.done_reason}\n")
    f.write(f"eval_count: {r.eval_count}\n")
    f.write(f"content: {repr(r.message.content)}\n")

print(f"DONE in {elapsed}s")
print(repr(r.message.content))
