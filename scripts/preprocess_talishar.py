"""Preprocess Talishar SQLite game data into HDF5 tensor cache for IQL training.

Reads from the transitions table in the SQLite database, featurizes each
transition's state/action/next_state JSON, and writes padded numpy arrays
to an HDF5 file suitable for TransformerIQLTrainer.

Usage:
    python scripts/preprocess_talishar.py --db data/talishar_games.db --out data/iql_cache_v1.h5

The HDF5 file is disposable — regenerate it whenever the featurization or
model architecture changes.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time

import h5py
import numpy as np

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SLUG_INDEX_PATH
from rl_agents.fab_transformer import (
    DECISION_TYPE_TO_IDX,
    MAX_TOTAL_CARDS,
    META_DIM,
    TURN_PHASE_TO_IDX,
    build_card_vocab_and_attrs,
    featurize_action,
    featurize_state,
)


def _safe_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def preprocess(db_path: str, out_path: str, slug_index_path: str | None = None):
    slug_path = slug_index_path or SLUG_INDEX_PATH
    print(f"[preprocess] Loading card vocab from {slug_path}")
    vocab, attrs_np = build_card_vocab_and_attrs(slug_path)
    print(f"[preprocess] Vocab size: {len(vocab)}, attr shape: {attrs_np.shape}")

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row

    # Count transitions
    n = conn.execute("SELECT COUNT(*) FROM transitions").fetchone()[0]
    print(f"[preprocess] {n} transitions in {db_path}")
    if n == 0:
        print("[preprocess] No transitions — nothing to do.")
        return

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    with h5py.File(out_path, "w") as hf:
        # Pre-allocate datasets with HDF5 chunking for efficient writes
        h5_chunk = 512
        hf.create_dataset("state_card_ids", shape=(n, MAX_TOTAL_CARDS), dtype="int16", chunks=(h5_chunk, MAX_TOTAL_CARDS))
        hf.create_dataset("state_card_zones", shape=(n, MAX_TOTAL_CARDS), dtype="int8", chunks=(h5_chunk, MAX_TOTAL_CARDS))
        hf.create_dataset("state_card_mask", shape=(n, MAX_TOTAL_CARDS), dtype="bool", chunks=(h5_chunk, MAX_TOTAL_CARDS))
        hf.create_dataset("state_meta", shape=(n, META_DIM), dtype="float32", chunks=(h5_chunk, META_DIM))
        hf.create_dataset("state_turn_phase", shape=(n,), dtype="int8", chunks=(h5_chunk,))
        hf.create_dataset("state_decision_type", shape=(n,), dtype="int8", chunks=(h5_chunk,))

        hf.create_dataset("next_state_card_ids", shape=(n, MAX_TOTAL_CARDS), dtype="int16", chunks=(h5_chunk, MAX_TOTAL_CARDS))
        hf.create_dataset("next_state_card_zones", shape=(n, MAX_TOTAL_CARDS), dtype="int8", chunks=(h5_chunk, MAX_TOTAL_CARDS))
        hf.create_dataset("next_state_card_mask", shape=(n, MAX_TOTAL_CARDS), dtype="bool", chunks=(h5_chunk, MAX_TOTAL_CARDS))
        hf.create_dataset("next_state_meta", shape=(n, META_DIM), dtype="float32", chunks=(h5_chunk, META_DIM))
        hf.create_dataset("next_state_turn_phase", shape=(n,), dtype="int8", chunks=(h5_chunk,))
        hf.create_dataset("next_state_decision_type", shape=(n,), dtype="int8", chunks=(h5_chunk,))

        hf.create_dataset("action_card_id", shape=(n,), dtype="int16", chunks=(h5_chunk,))
        hf.create_dataset("action_mode_id", shape=(n,), dtype="int8", chunks=(h5_chunk,))

        hf.create_dataset("reward", shape=(n,), dtype="float32", chunks=(h5_chunk,))
        hf.create_dataset("done", shape=(n,), dtype="bool", chunks=(h5_chunk,))

        # Store vocab metadata for validation at training time (M2)
        hf.attrs["vocab_size"] = len(vocab)
        hf.attrs["attr_dim"] = int(attrs_np.shape[1])
        hf.attrs["max_total_cards"] = MAX_TOTAL_CARDS
        hf.attrs["meta_dim"] = META_DIM

        # Process in chunks — buffer rows in numpy, flush to HDF5 in bulk
        chunk_size = 512
        cursor = conn.execute(
            """SELECT state, next_state, action_taken, reward, done,
                      is_turn_player, num_actions, hp_delta, opp_hp_delta,
                      game_progress, turn_phase, decision_type
               FROM transitions ORDER BY id"""
        )

        # Pre-allocate write buffers
        buf_s_ids = np.zeros((chunk_size, MAX_TOTAL_CARDS), dtype=np.int16)
        buf_s_zones = np.zeros((chunk_size, MAX_TOTAL_CARDS), dtype=np.int8)
        buf_s_mask = np.zeros((chunk_size, MAX_TOTAL_CARDS), dtype=bool)
        buf_s_meta = np.zeros((chunk_size, META_DIM), dtype=np.float32)
        buf_s_phase = np.zeros(chunk_size, dtype=np.int8)
        buf_s_dec = np.zeros(chunk_size, dtype=np.int8)
        buf_ns_ids = np.zeros((chunk_size, MAX_TOTAL_CARDS), dtype=np.int16)
        buf_ns_zones = np.zeros((chunk_size, MAX_TOTAL_CARDS), dtype=np.int8)
        buf_ns_mask = np.zeros((chunk_size, MAX_TOTAL_CARDS), dtype=bool)
        buf_ns_meta = np.zeros((chunk_size, META_DIM), dtype=np.float32)
        buf_ns_phase = np.zeros(chunk_size, dtype=np.int8)
        buf_ns_dec = np.zeros(chunk_size, dtype=np.int8)
        buf_a_card = np.zeros(chunk_size, dtype=np.int16)
        buf_a_mode = np.zeros(chunk_size, dtype=np.int8)
        buf_reward = np.zeros(chunk_size, dtype=np.float32)
        buf_done = np.zeros(chunk_size, dtype=bool)

        t0 = time.time()
        idx = 0
        while True:
            rows = cursor.fetchmany(chunk_size)
            if not rows:
                break

            buf_len = len(rows)
            for bi, row in enumerate(rows):
                # Parse JSON blobs
                state_json = json.loads(row["state"])
                next_state_raw = row["next_state"]
                next_state_json = json.loads(next_state_raw) if next_state_raw else state_json
                action_json = json.loads(row["action_taken"])

                # Featurize state
                sf = featurize_state(state_json, vocab)
                sf["meta"][11] = float(row["is_turn_player"] or 0)
                sf["meta"][24] = _safe_int(row["num_actions"], 0) / 40.0
                sf["meta"][25] = _safe_float(row["hp_delta"], 0) / 20.0
                sf["meta"][26] = _safe_float(row["opp_hp_delta"], 0) / 20.0
                sf["meta"][27] = _safe_float(row["game_progress"], 0)

                tp_str = str(row["turn_phase"] or "").upper()
                sf["turn_phase_id"] = np.int8(TURN_PHASE_TO_IDX.get(tp_str, 0))
                dt_str = str(row["decision_type"] or "")
                sf["decision_type_id"] = np.int8(DECISION_TYPE_TO_IDX.get(dt_str, 0))

                # Featurize next state
                nsf = featurize_state(next_state_json, vocab)
                nsf["meta"][11] = float(row["is_turn_player"] or 0)

                # Featurize action
                af = featurize_action(action_json, vocab)

                # Fill buffers
                buf_s_ids[bi] = sf["card_ids"]
                buf_s_zones[bi] = sf["card_zones"]
                buf_s_mask[bi] = sf["card_mask"]
                buf_s_meta[bi] = sf["meta"]
                buf_s_phase[bi] = sf["turn_phase_id"]
                buf_s_dec[bi] = sf["decision_type_id"]
                buf_ns_ids[bi] = nsf["card_ids"]
                buf_ns_zones[bi] = nsf["card_zones"]
                buf_ns_mask[bi] = nsf["card_mask"]
                buf_ns_meta[bi] = nsf["meta"]
                buf_ns_phase[bi] = nsf["turn_phase_id"]
                buf_ns_dec[bi] = nsf["decision_type_id"]
                buf_a_card[bi] = af["card_id"]
                buf_a_mode[bi] = af["mode_id"]
                buf_reward[bi] = float(row["reward"])
                buf_done[bi] = bool(row["done"])

            # Flush entire chunk to HDF5 in one slice write
            sl = slice(idx, idx + buf_len)
            hf["state_card_ids"][sl] = buf_s_ids[:buf_len]
            hf["state_card_zones"][sl] = buf_s_zones[:buf_len]
            hf["state_card_mask"][sl] = buf_s_mask[:buf_len]
            hf["state_meta"][sl] = buf_s_meta[:buf_len]
            hf["state_turn_phase"][sl] = buf_s_phase[:buf_len]
            hf["state_decision_type"][sl] = buf_s_dec[:buf_len]
            hf["next_state_card_ids"][sl] = buf_ns_ids[:buf_len]
            hf["next_state_card_zones"][sl] = buf_ns_zones[:buf_len]
            hf["next_state_card_mask"][sl] = buf_ns_mask[:buf_len]
            hf["next_state_meta"][sl] = buf_ns_meta[:buf_len]
            hf["next_state_turn_phase"][sl] = buf_ns_phase[:buf_len]
            hf["next_state_decision_type"][sl] = buf_ns_dec[:buf_len]
            hf["action_card_id"][sl] = buf_a_card[:buf_len]
            hf["action_mode_id"][sl] = buf_a_mode[:buf_len]
            hf["reward"][sl] = buf_reward[:buf_len]
            hf["done"][sl] = buf_done[:buf_len]

            idx += buf_len

            elapsed = time.time() - t0
            rate = idx / elapsed if elapsed > 0 else 0
            print(
                f"\r[preprocess] {idx}/{n} ({100*idx/n:.1f}%) "
                f"— {rate:.0f} transitions/sec",
                end="", flush=True,
            )

        print(f"\n[preprocess] Done. Wrote {idx} transitions to {out_path}")
        print(f"[preprocess] File size: {os.path.getsize(out_path) / 1024**2:.1f} MB")

    # Save vocab alongside for reproducibility
    vocab_path = out_path.rsplit(".", 1)[0] + "_vocab.json"
    with open(vocab_path, "w", encoding="utf-8") as f:
        json.dump({"vocab_size": len(vocab), "attr_dim": int(attrs_np.shape[1])}, f)
    print(f"[preprocess] Vocab metadata saved to {vocab_path}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Preprocess Talishar DB → HDF5 for IQL")
    parser.add_argument("--db", default="data/talishar_games.db", help="SQLite database path")
    parser.add_argument("--out", default="data/iql_cache_v1.h5", help="Output HDF5 path")
    parser.add_argument("--slug-index", default=None, help="Path to slug_index.json")
    args = parser.parse_args()

    preprocess(args.db, args.out, args.slug_index)


if __name__ == "__main__":
    main()
