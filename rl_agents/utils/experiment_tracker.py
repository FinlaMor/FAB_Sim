"""Lightweight JSON-lines experiment tracker for hyperparameter sweeps."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class ExperimentTracker:
    """Append-only JSONL experiment logger with query helpers.

    Each run is stored as a single JSON line with fields:
      - run_id: unique identifier
      - timestamp: unix epoch seconds
      - hyperparameters: dict of config values
      - metrics: dict of training metrics (loss, win_rate, etc.)
      - tags: optional list of string tags for filtering
      - status: "running" | "completed" | "failed"
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def start_run(
        self,
        hyperparameters: Dict[str, Any],
        *,
        tags: Optional[List[str]] = None,
        run_id: Optional[str] = None,
    ) -> str:
        """Record a new run entry with status 'running'. Returns the run_id."""
        rid = run_id or uuid.uuid4().hex[:12]
        record: Dict[str, Any] = {
            "run_id": rid,
            "timestamp": time.time(),
            "hyperparameters": hyperparameters,
            "metrics": {},
            "tags": tags or [],
            "status": "running",
        }
        self._append(record)
        return rid

    def log_metrics(self, run_id: str, metrics: Dict[str, Any]) -> None:
        """Append a metrics-update entry for an existing run."""
        record: Dict[str, Any] = {
            "run_id": run_id,
            "timestamp": time.time(),
            "event": "metrics_update",
            "metrics": metrics,
        }
        self._append(record)

    def finish_run(
        self,
        run_id: str,
        metrics: Dict[str, Any],
        *,
        status: str = "completed",
    ) -> None:
        """Mark a run as completed (or failed) with final metrics."""
        record: Dict[str, Any] = {
            "run_id": run_id,
            "timestamp": time.time(),
            "event": "finish",
            "metrics": metrics,
            "status": status,
        }
        self._append(record)

    # ------------------------------------------------------------------
    # Read / query helpers
    # ------------------------------------------------------------------

    def load_runs(self) -> List[Dict[str, Any]]:
        """Load all entries from the JSONL file."""
        if not self.path.exists():
            return []
        entries: List[Dict[str, Any]] = []
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def get_run_summary(self, run_id: str) -> Dict[str, Any]:
        """Merge all entries for *run_id* into a single summary dict.

        Later entries override earlier ones for overlapping keys in metrics.
        """
        entries = [e for e in self.load_runs() if e.get("run_id") == run_id]
        if not entries:
            raise KeyError(f"No entries found for run_id={run_id!r}")
        summary: Dict[str, Any] = {
            "run_id": run_id,
            "hyperparameters": {},
            "metrics": {},
            "tags": [],
            "status": "unknown",
        }
        for entry in entries:
            if "hyperparameters" in entry:
                summary["hyperparameters"].update(entry["hyperparameters"])
            if "metrics" in entry:
                summary["metrics"].update(entry["metrics"])
            if "tags" in entry:
                summary["tags"] = entry["tags"]
            if "status" in entry:
                summary["status"] = entry["status"]
            if "timestamp" in entry:
                summary["timestamp"] = entry["timestamp"]
        return summary

    def best_run(self, metric: str, *, higher_is_better: bool = True) -> Dict[str, Any]:
        """Return the summary of the run with the best value for *metric*.

        Only considers finished runs that contain the requested metric.
        """
        summaries = self._all_summaries()
        candidates = [
            s for s in summaries
            if s["status"] == "completed" and metric in s["metrics"]
        ]
        if not candidates:
            raise ValueError(f"No completed runs with metric {metric!r}")
        return (max if higher_is_better else min)(
            candidates, key=lambda s: s["metrics"][metric]
        )

    def compare_configs(
        self, metric: str, *, higher_is_better: bool = True, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Return top-k run summaries sorted by *metric*."""
        summaries = self._all_summaries()
        candidates = [
            s for s in summaries
            if s["status"] == "completed" and metric in s["metrics"]
        ]
        candidates.sort(key=lambda s: s["metrics"][metric], reverse=higher_is_better)
        return candidates[:top_k]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _append(self, record: Dict[str, Any]) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def _all_summaries(self) -> List[Dict[str, Any]]:
        """Build per-run summaries for every unique run_id."""
        entries = self.load_runs()
        run_ids: List[str] = []
        seen: set[str] = set()
        for e in entries:
            rid = e.get("run_id", "")
            if rid and rid not in seen:
                run_ids.append(rid)
                seen.add(rid)
        return [self.get_run_summary(rid) for rid in run_ids]
