"""
review_wtr_cards.py — Side-by-side card text / JSON reviewer.

Usage:
    python scripts/review_wtr_cards.py              # review all done cards
    python scripts/review_wtr_cards.py --slug foo   # review one specific card
    python scripts/review_wtr_cards.py --unreviewed # skip already approved cards

Approve  → JSON stays in wtr/, queue status set to "approved"
Reject   → JSON moved to wtr/needs_review/, queue status set to "needs_review"
Skip     → move to next card without changing anything
"""

from __future__ import annotations

import argparse
import json
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
# Overridden in main() via --set
WTR_DIR = ROOT / "engine" / "card_effects" / "json" / "wtr"
QUEUE_PATH = WTR_DIR / "wtr_work_queue.json"
REVIEW_DIR = WTR_DIR / "needs_review"


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_queue() -> list[dict]:
    with QUEUE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue: list[dict]) -> None:
    QUEUE_PATH.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")


def card_text_block(card: dict) -> str:
    lines = [
        f"Name:    {card.get('name', '')}",
        f"Slug:    {card.get('slug', '')}",
        f"Type:    {card.get('type_text', '')}",
        f"Cost:    {card.get('cost', 'N/A')}",
        f"Power:   {card.get('power', 'N/A')}",
        f"Defense: {card.get('defense', 'N/A')}",
        f"Set:     {card.get('set_id', '')}",
        "",
        "── Card Text ──────────────────────────────────────",
        "",
        card.get("functional_text") or "(no functional text)",
        "",
        "── Flavor Text ────────────────────────────────────",
        "",
        card.get("flavor_text") or "(none)",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reviewer GUI
# ---------------------------------------------------------------------------

class ReviewApp:
    def __init__(self, root: tk.Tk, cards: list[dict], queue: list[dict]) -> None:
        self.root = root
        self.cards = cards          # list of queue entries with a JSON file
        self.queue = queue
        self.index = 0

        root.title("WTR Card Reviewer")
        root.geometry("1200x700")
        root.configure(bg="#1e1e1e")

        mono = tkfont.Font(family="Consolas", size=10)
        label_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        btn_font = tkfont.Font(family="Segoe UI", size=12, weight="bold")

        # ── Progress bar area ──
        top = tk.Frame(root, bg="#1e1e1e")
        top.pack(fill="x", padx=12, pady=(10, 4))

        self.progress_var = tk.StringVar()
        tk.Label(top, textvariable=self.progress_var, bg="#1e1e1e", fg="#aaaaaa",
                 font=label_font).pack(side="left")

        self.status_var = tk.StringVar()
        tk.Label(top, textvariable=self.status_var, bg="#1e1e1e", fg="#66bb6a",
                 font=label_font).pack(side="right")

        # ── Main pane ──
        pane = tk.PanedWindow(root, orient="horizontal", bg="#333333",
                              sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=12, pady=4)

        # Left: card text
        left_frame = tk.Frame(pane, bg="#1e1e1e")
        tk.Label(left_frame, text="CARD TEXT", bg="#1e1e1e", fg="#888888",
                 font=label_font, anchor="w").pack(fill="x", padx=6, pady=(4, 2))
        self.card_text = tk.Text(left_frame, wrap="word", font=mono,
                                  bg="#252526", fg="#d4d4d4", relief="flat",
                                  insertbackground="white", state="disabled",
                                  padx=10, pady=10)
        lscroll = tk.Scrollbar(left_frame, command=self.card_text.yview)
        self.card_text.config(yscrollcommand=lscroll.set)
        lscroll.pack(side="right", fill="y")
        self.card_text.pack(fill="both", expand=True, padx=(6, 0))
        pane.add(left_frame, minsize=400)

        # Right: JSON
        right_frame = tk.Frame(pane, bg="#1e1e1e")
        tk.Label(right_frame, text="JSON EFFECT", bg="#1e1e1e", fg="#888888",
                 font=label_font, anchor="w").pack(fill="x", padx=6, pady=(4, 2))
        self.json_text = tk.Text(right_frame, wrap="none", font=mono,
                                  bg="#1e1e2e", fg="#cdd6f4", relief="flat",
                                  insertbackground="white", state="disabled",
                                  padx=10, pady=10)
        rscroll_y = tk.Scrollbar(right_frame, command=self.json_text.yview)
        rscroll_x = tk.Scrollbar(right_frame, orient="horizontal",
                                  command=self.json_text.xview)
        self.json_text.config(yscrollcommand=rscroll_y.set,
                               xscrollcommand=rscroll_x.set)
        rscroll_y.pack(side="right", fill="y")
        rscroll_x.pack(side="bottom", fill="x")
        self.json_text.pack(fill="both", expand=True, padx=(6, 0))
        pane.add(right_frame, minsize=400)

        # ── Button row ──
        btn_row = tk.Frame(root, bg="#1e1e1e")
        btn_row.pack(fill="x", padx=12, pady=10)

        tk.Button(btn_row, text="✗  Reject", command=self.reject,
                  bg="#c62828", fg="white", font=btn_font,
                  relief="flat", padx=24, pady=10,
                  activebackground="#e53935", activeforeground="white",
                  cursor="hand2").pack(side="left", padx=(0, 12))

        tk.Button(btn_row, text="→  Skip", command=self.skip,
                  bg="#37474f", fg="#cfd8dc", font=btn_font,
                  relief="flat", padx=24, pady=10,
                  activebackground="#546e7a", activeforeground="white",
                  cursor="hand2").pack(side="left", padx=(0, 12))

        tk.Button(btn_row, text="✓  Approve", command=self.approve,
                  bg="#2e7d32", fg="white", font=btn_font,
                  relief="flat", padx=24, pady=10,
                  activebackground="#388e3c", activeforeground="white",
                  cursor="hand2").pack(side="right")

        # Keyboard shortcuts
        root.bind("<Left>", lambda e: self.reject())
        root.bind("<Right>", lambda e: self.approve())
        root.bind("<space>", lambda e: self.skip())

        self._load_card()

    # ── Navigation ──────────────────────────────────────────────────────────

    def _load_card(self) -> None:
        if self.index >= len(self.cards):
            self._show_done()
            return

        card = self.cards[self.index]
        slug = card["slug"]
        total = len(self.cards)

        self.progress_var.set(f"Card {self.index + 1} / {total}  —  {slug}")
        self.status_var.set(f"[{card.get('status', '?')}]")

        # Card text panel
        self._set_text(self.card_text, card_text_block(card))

        # JSON panel
        json_path = WTR_DIR / f"{slug}.json"
        if json_path.exists():
            raw = json_path.read_text(encoding="utf-8")
            self._set_text(self.json_text, raw)
        else:
            self._set_text(self.json_text, f"(no JSON file found for {slug})")

    def _set_text(self, widget: tk.Text, content: str) -> None:
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.config(state="disabled")
        widget.yview_moveto(0)

    def _advance(self) -> None:
        self.index += 1
        self._load_card()

    def _queue_entry(self, slug: str) -> dict | None:
        for entry in self.queue:
            if entry["slug"] == slug:
                return entry
        return None

    # ── Actions ─────────────────────────────────────────────────────────────

    def approve(self) -> None:
        if self.index >= len(self.cards):
            return
        card = self.cards[self.index]
        slug = card["slug"]
        entry = self._queue_entry(slug)
        if entry:
            entry["status"] = "approved"
            save_queue(self.queue)
        self.status_var.set("[approved]")
        self._advance()

    def reject(self) -> None:
        if self.index >= len(self.cards):
            return
        card = self.cards[self.index]
        slug = card["slug"]

        # Move JSON file to needs_review/
        src = WTR_DIR / f"{slug}.json"
        if src.exists():
            REVIEW_DIR.mkdir(parents=True, exist_ok=True)
            dst = REVIEW_DIR / f"{slug}.json"
            shutil.move(str(src), str(dst))

        # Update queue
        entry = self._queue_entry(slug)
        if entry:
            entry["status"] = "needs_review"
            save_queue(self.queue)

        self.status_var.set("[rejected -> needs_review/]")
        self._advance()

    def skip(self) -> None:
        if self.index >= len(self.cards):
            return
        self._advance()

    def _show_done(self) -> None:
        self._set_text(self.card_text, "All cards reviewed!")
        self._set_text(self.json_text, "")
        self.progress_var.set("Done")
        self.status_var.set("")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Side-by-side FAB card JSON reviewer.")
    parser.add_argument("--slug", default=None, help="Review a single slug only.")
    parser.add_argument("--unreviewed", action="store_true",
                        help="Only show cards not yet approved or rejected.")
    parser.add_argument("--set", default="wtr", dest="set_code",
                        help="Set code to review (e.g. wtr, arc, cru). Default: wtr.")
    args = parser.parse_args()

    global WTR_DIR, QUEUE_PATH, REVIEW_DIR
    set_code = args.set_code.lower()
    WTR_DIR = ROOT / "engine" / "card_effects" / "json" / set_code
    QUEUE_PATH = WTR_DIR / f"{set_code}_work_queue.json"
    REVIEW_DIR = WTR_DIR / "needs_review"

    queue = load_queue()

    # Determine candidate cards
    reviewable_statuses = {"done", "approved", "needs_review"}
    candidates = [c for c in queue if c["status"] in reviewable_statuses]

    if args.slug:
        candidates = [c for c in candidates if c["slug"] == args.slug]
    elif args.unreviewed:
        candidates = [c for c in candidates if c["status"] == "done"]

    # Only include cards that actually have a JSON file in wtr/ right now
    candidates = [c for c in candidates if (WTR_DIR / f"{c['slug']}.json").exists()]

    if not candidates:
        print("No cards to review.")
        return

    print(f"Reviewing {len(candidates)} cards.")
    print("Keyboard shortcuts: ← Reject  |  Space Skip  |  → Approve")

    root = tk.Tk()
    ReviewApp(root, candidates, queue)
    root.mainloop()


if __name__ == "__main__":
    main()
