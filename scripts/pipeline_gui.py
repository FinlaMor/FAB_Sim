"""Run the card-implementation pipeline with a pause button.

    python scripts/pipeline_gui.py

Pause takes effect at the NEXT CARD BOUNDARY, never mid-card. The pipeline
saves queue state after every card, so a boundary is the one place where
stopping costs nothing: the finished card is already recorded and the next has
not begun. That is why "Pause" reads as "finishing current card…" for a while
before it goes idle — it is waiting for real work to complete, not hanging.

Control travels through .pipeline_control.json rather than a signal or a pipe,
so it also works on a run started from a terminal, and a closed GUI leaves the
pipeline running rather than killing it mid-card.

Stdlib only (tkinter) — no new dependencies.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parent.parent
CONTROL_PATH = ROOT / ".pipeline_control.json"
PIPELINE = ROOT / "scripts" / "auto_implement_wtr.py"

POLL_MS = 120
MAX_LOG_LINES = 4000


def write_control(**state) -> None:
    CONTROL_PATH.write_text(json.dumps(state), encoding="utf-8")


def clear_control() -> None:
    write_control(paused=False, stop=False)


def queue_counts(set_code: str) -> tuple[dict, int]:
    """(status -> count, total) for a set's work queue."""
    path = ROOT / "engine" / "card_effects" / "json" / set_code / f"{set_code}_work_queue.json"
    try:
        cards = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}, 0
    counts: dict[str, int] = {}
    for card in cards:
        status = card.get("status", "?")
        counts[status] = counts.get(status, 0) + 1
    return counts, len(cards)


def sets_with_pending() -> list[tuple[str, int]]:
    """Every set code and its PENDING count, most work first.

    Only "pending" cards are picked up by the pipeline — a set can be entirely
    processed yet still show hundreds of cards under needs_review/candidate, so
    offering a bare set name invites starting a run that does nothing at all.
    """
    out = []
    for path in (ROOT / "engine" / "card_effects" / "json").glob("*/*_work_queue.json"):
        counts, total = queue_counts(path.parent.name)
        if total:
            out.append((path.parent.name, counts.get("pending", 0)))
    return sorted(out, key=lambda kv: (-kv[1], kv[0]))


class PipelineGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.proc: subprocess.Popen | None = None
        self.lines: queue.Queue[str] = queue.Queue()
        self.state = "idle"          # idle | running | pausing | paused | stopping
        self.current_card = "—"
        self.done_this_run = 0

        root.title("FAB card pipeline")
        root.geometry("980x620")
        root.minsize(760, 460)

        self._build_config(root)
        self._build_controls(root)
        self._build_status(root)
        self._build_log(root)

        clear_control()
        self.refresh_counts()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(POLL_MS, self.pump)

    # ---------------------------------------------------------------- layout
    def _build_config(self, root):
        frame = ttk.LabelFrame(root, text="Run")
        frame.pack(fill="x", padx=10, pady=(10, 6))

        pending_by_set = sets_with_pending()
        default_set = pending_by_set[0][0] if pending_by_set else "wtr"

        self.set_code = tk.StringVar(value=default_set)
        self.limit = tk.StringVar(value="")
        self.model = tk.StringVar(value="qwen2.5-coder:14b")
        self.audit_model = tk.StringVar(value="qwen2.5-coder:14b")
        # Which server answers /chat/completions. Without this the GUI would
        # silently fall back to Ollama (:11434) even with the much faster
        # llama.cpp GPU server running on :8080 — a slow run that looks fine.
        # Embeddings always go to Ollama on :11434 regardless (hardcoded, and
        # they degrade silently), so the GPU path wants BOTH servers up.
        self.base_url = tk.StringVar(
            value=os.environ.get("FAB_LLM_BASE_URL", "http://localhost:11434/v1"))

        row = ttk.Frame(frame)
        row.pack(fill="x", padx=8, pady=6)

        # A dropdown of real sets labelled with their pending counts: picking a
        # set with 0 pending would start a run that processes nothing.
        ttk.Label(row, text="Set").pack(side="left", padx=(0, 4))
        self.set_box = ttk.Combobox(row, textvariable=self.set_code, width=10,
                                    state="readonly",
                                    values=[s for s, _ in pending_by_set])
        self.set_box.pack(side="left", padx=(0, 4))
        self.lbl_set_pending = ttk.Label(row, text="", width=16)
        self.lbl_set_pending.pack(side="left", padx=(0, 14))

        for label, var, width in (("Limit (blank = all)", self.limit, 10),
                                  ("Implementer", self.model, 22),
                                  ("Auditor", self.audit_model, 22)):
            ttk.Label(row, text=label).pack(side="left", padx=(0, 4))
            ttk.Entry(row, textvariable=var, width=width).pack(side="left", padx=(0, 14))

        row2 = ttk.Frame(frame)
        row2.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(row2, text="LLM endpoint").pack(side="left", padx=(0, 4))
        ttk.Entry(row2, textvariable=self.base_url, width=34).pack(side="left", padx=(0, 8))
        ttk.Button(row2, text="Check", command=self.on_check).pack(side="left", padx=(0, 8))
        self.lbl_llm = ttk.Label(row2, text="")
        self.lbl_llm.pack(side="left")

        self.set_code.trace_add("write", lambda *_: self.refresh_counts())

    def _build_controls(self, root):
        frame = ttk.Frame(root)
        frame.pack(fill="x", padx=10, pady=(0, 6))

        self.btn_start = ttk.Button(frame, text="Start", command=self.on_start)
        self.btn_pause = ttk.Button(frame, text="Pause after current card",
                                    command=self.on_pause, state="disabled")
        self.btn_resume = ttk.Button(frame, text="Resume", command=self.on_resume,
                                     state="disabled")
        self.btn_stop = ttk.Button(frame, text="Stop after current card",
                                   command=self.on_stop, state="disabled")
        for b in (self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop):
            b.pack(side="left", padx=(0, 8))

    def _build_status(self, root):
        frame = ttk.Frame(root)
        frame.pack(fill="x", padx=10, pady=(0, 6))

        self.lbl_state = ttk.Label(frame, text="Idle", font=("", 11, "bold"))
        self.lbl_state.pack(side="left")
        self.lbl_card = ttk.Label(frame, text="   card: —")
        self.lbl_card.pack(side="left", padx=(14, 0))
        self.lbl_counts = ttk.Label(frame, text="")
        self.lbl_counts.pack(side="right")

    def _build_log(self, root):
        frame = ttk.Frame(root)
        frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log = tk.Text(frame, wrap="none", height=20,
                           bg="#101216", fg="#d8dee9", insertbackground="#d8dee9")
        scroll = ttk.Scrollbar(frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set, state="disabled")
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for tag, colour in (("ok", "#a3be8c"), ("warn", "#ebcb8b"),
                            ("bad", "#bf616a"), ("ctl", "#88c0d0")):
            self.log.tag_configure(tag, foreground=colour)

    # --------------------------------------------------------------- actions
    def on_start(self):
        if self.proc is not None:
            return
        clear_control()
        cmd = [sys.executable, "-u", str(PIPELINE), "--set", self.set_code.get().strip()]
        if self.limit.get().strip():
            cmd += ["--limit", self.limit.get().strip()]
        if self.model.get().strip():
            cmd += ["--model", self.model.get().strip()]
        if self.audit_model.get().strip():
            cmd += ["--audit-model", self.audit_model.get().strip()]
        if self.base_url.get().strip():
            cmd += ["--base-url", self.base_url.get().strip()]

        self.append(f"$ {' '.join(cmd)}\n", "ctl")
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(
            cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=creation,
        )
        threading.Thread(target=self._reader, daemon=True).start()
        self.set_state("running")

    def _reader(self):
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)  # sentinel: process ended

    def on_check(self):
        """Confirm the endpoint answers and report which models it serves."""
        import json as _json
        import urllib.request
        url = self.base_url.get().strip().rstrip("/") + "/models"
        try:
            with urllib.request.urlopen(url, timeout=4) as resp:
                ids = [m["id"] for m in _json.loads(resp.read().decode()).get("data", [])]
            wanted = self.model.get().strip()
            ok = wanted in ids
            self.lbl_llm.config(
                text=f"up · {len(ids)} model(s) · {wanted}: {'yes' if ok else 'NOT SERVED'}")
            self.append(f"[check] {url} -> {len(ids)} model(s): {', '.join(ids[:8])}\n",
                        "ok" if ok else "warn")
            if not ok:
                self.append(f"[check] '{wanted}' is not served here — "
                            f"the run would fail on every card\n", "warn")
        except Exception as exc:
            self.lbl_llm.config(text="unreachable")
            self.append(f"[check] {url} unreachable: {exc}\n", "bad")

    def on_pause(self):
        write_control(paused=True, stop=False)
        self.set_state("pausing")

    def on_resume(self):
        write_control(paused=False, stop=False)
        self.set_state("running")

    def on_stop(self):
        write_control(paused=False, stop=True)
        self.set_state("stopping")

    def on_close(self):
        if self.proc is not None and self.proc.poll() is None:
            # Leave the run going rather than killing it mid-card; a stray
            # paused flag would silently stall a terminal-started run.
            clear_control()
        self.root.destroy()

    # ----------------------------------------------------------------- state
    def set_state(self, state: str):
        self.state = state
        text, buttons = {
            "idle":     ("Idle",                              (1, 0, 0, 0)),
            "running":  ("Running",                           (0, 1, 0, 1)),
            "pausing":  ("Pausing — finishing current card…", (0, 0, 1, 1)),
            "paused":   ("Paused — safe to use your machine", (0, 0, 1, 1)),
            "stopping": ("Stopping after current card…",      (0, 0, 0, 0)),
        }[state]
        self.lbl_state.config(text=text)
        for btn, on in zip((self.btn_start, self.btn_pause,
                            self.btn_resume, self.btn_stop), buttons):
            btn.config(state="normal" if on else "disabled")
        self.set_box.config(state="readonly" if state == "idle" else "disabled")
        if state == "idle":
            self.refresh_counts()   # may re-disable Start if nothing is pending

    def refresh_counts(self):
        counts, total = queue_counts(self.set_code.get().strip())
        if not total:
            self.lbl_counts.config(text="(no work queue for this set)")
            self.lbl_set_pending.config(text="")
            return
        pending = counts.get("pending", 0)
        # Pending is the only number that decides whether a run does anything,
        # so it leads. The rest are prior outcomes, not remaining work.
        parts = [f"{k} {v}" for k, v in sorted(counts.items()) if k != "pending"]
        self.lbl_counts.config(
            text=f"{pending} pending of {total}   ·   " + "  ".join(parts))
        self.lbl_set_pending.config(
            text=f"{pending} pending" if pending else "nothing to do")
        if self.state == "idle":
            self.btn_start.config(state="normal" if pending else "disabled")

    def append(self, text: str, tag: str | None = None):
        self.log.config(state="normal")
        self.log.insert("end", text, tag or ())
        # Trim so a long run does not grow the widget without bound.
        if int(self.log.index("end-1c").split(".")[0]) > MAX_LOG_LINES:
            self.log.delete("1.0", f"{MAX_LOG_LINES // 4}.0")
        self.log.see("end")
        self.log.config(state="disabled")

    def pump(self):
        """Drain pipeline output on the Tk thread and reflect it in the UI."""
        drained = 0
        while drained < 200:
            try:
                line = self.lines.get_nowait()
            except queue.Empty:
                break
            drained += 1
            if line is None:
                self.proc = None
                self.set_state("idle")
                self.append("\n[run finished]\n", "ctl")
                self.refresh_counts()
                continue

            tag = None
            if "[control]" in line:
                tag = "ctl"
                if "PAUSED" in line:
                    self.set_state("paused")
                elif "RESUMED" in line:
                    self.set_state("running")
            elif "[DONE]" in line or "test PASSED" in line:
                tag = "ok"
            elif "[CANDIDATE]" in line or "needs_review" in line or "FAILED" in line:
                tag = "warn"
            elif "ERROR" in line or "Traceback" in line:
                tag = "bad"

            stripped = line.strip()
            # "[3/50] some_slug — Some Card"
            if stripped.startswith("[") and "]" in stripped and "/" in stripped.split("]")[0]:
                self.current_card = stripped.split("]", 1)[1].strip()
                self.lbl_card.config(text=f"   card: {self.current_card}")
                self.done_this_run += 1
                self.refresh_counts()

            self.append(line, tag)

        self.root.after(POLL_MS, self.pump)


def main() -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    PipelineGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
