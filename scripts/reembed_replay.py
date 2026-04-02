"""Re-embed replay.db transitions using the (pre-trained) transformer.

Reads packed state/action features from replay.db, runs the transformer
and action embedder forward passes, and writes the resulting embedding
vectors into the state_embedding/action_embedding columns.  After this,
IQL training can use the frozen-embedding fast path.

Usage:
    python scripts/reembed_replay.py \
        --db-path data/replay.db \
        --embedder-bundle checkpoints/embedder_bundle.pt \
        --batch-size 256
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl_agents.embedder_bundle import load_embedder_bundle
from rl_agents.utils.device import resolve_device as _resolve_device


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-embed replay.db with trained transformer")
    parser.add_argument("--db-path", type=str, required=True, help="Path to replay.db")
    parser.add_argument("--embedder-bundle", type=str, required=True, help="Path to embedder_bundle.pt")
    parser.add_argument("--batch-size", type=int, default=256, help="Batch size for forward passes")
    parser.add_argument("--device", type=str, default="cpu", help="Device for inference")
    parser.add_argument("--max-games", type=int, default=3000,
                        help="Only re-embed the most recent N completed games (0 = all)")
    args = parser.parse_args()

    print(f"[reembed] Loading embedder bundle from {args.embedder_bundle}...", flush=True)
    bundle = load_embedder_bundle(args.embedder_bundle)

    if "game_transformer_state_dict" not in bundle:
        print("[reembed] ERROR: Bundle has no transformer. Nothing to re-embed.", flush=True)
        return 1

    # Build transformer + action embedder
    from engine.card import CardDB
    from encoder.card_embedder import SlugVocab
    from encoder.game_transformer import GameTransformerEncoder, prime_dummy_vocab
    from encoder.action_embedder import ActionEmbedder
    from config import SLUG_INDEX_PATH

    card_db = CardDB(SLUG_INDEX_PATH)
    slug_vocab = SlugVocab.from_card_db(card_db)
    prime_dummy_vocab(card_db)

    gt_d_model       = int(bundle.get("game_transformer_d_model", 256))
    gt_n_heads       = int(bundle.get("game_transformer_n_heads", 8))
    gt_n_layers      = int(bundle.get("game_transformer_n_layers", 4))
    gt_hero_head_dim = int(bundle.get("game_transformer_hero_head_dim", 64))

    transformer = GameTransformerEncoder(
        slug_vocab_size=slug_vocab.size,
        d_model=gt_d_model,
        n_heads=gt_n_heads,
        n_layers=gt_n_layers,
        hero_head_dim=gt_hero_head_dim,
    )
    gt_sd = bundle["game_transformer_state_dict"]
    model_sd = transformer.state_dict()
    filtered = {k: v for k, v in gt_sd.items() if k in model_sd and model_sd[k].shape == v.shape}
    transformer.load_state_dict(filtered, strict=False)
    transformer.set_card_feats_lookup(card_db)
    transformer.eval()

    d_model = int(bundle.get("d_model", 128))
    action_embedder = ActionEmbedder(
        d_model=d_model,
        slug_vocab_size=slug_vocab.size,
        slug_vocab=slug_vocab,
    )
    ae_sd = {**{f"card_embedder.{k}": v for k, v in bundle.get("card_embedder_state_dict", {}).items()},
             **bundle.get("action_embedder_state_dict", {})}
    ae_model_sd = action_embedder.state_dict()
    ae_filtered = {k: v for k, v in ae_sd.items() if k in ae_model_sd and ae_model_sd[k].shape == v.shape}
    action_embedder.load_state_dict(ae_filtered, strict=False)
    action_embedder.eval()

    device = _resolve_device(args.device)
    transformer = transformer.to(device)
    action_embedder = action_embedder.to(device)

    state_out_dim = transformer.get_output_dim()
    action_out_dim = action_embedder.get_output_dim()
    print(f"[reembed] Transformer output: {state_out_dim}, ActionEmbedder output: {action_out_dim}", flush=True)

    # Load transitions that have packed features, optionally capped to recent games
    import sqlite3
    conn = sqlite3.connect(args.db_path)

    if args.max_games > 0:
        game_id_rows = conn.execute(
            "SELECT game_id FROM games WHERE winner IS NOT NULL "
            "ORDER BY rowid DESC LIMIT ?",
            (args.max_games,),
        ).fetchall()
        game_ids = [r[0] for r in game_id_rows]
        if game_ids:
            placeholders = ",".join("?" * len(game_ids))
            rows = conn.execute(
                f"SELECT e.transition_id, e.state_features, e.action_features "
                f"FROM embeddings e JOIN transitions t ON t.id = e.transition_id "
                f"WHERE t.game_id IN ({placeholders}) "
                f"AND e.state_features IS NOT NULL AND e.action_features IS NOT NULL",
                game_ids,
            ).fetchall()
        else:
            rows = []
        print(f"[reembed] max_games={args.max_games} → {len(game_ids)} games selected", flush=True)
    else:
        rows = conn.execute(
            "SELECT transition_id, state_features, action_features "
            "FROM embeddings WHERE state_features IS NOT NULL AND action_features IS NOT NULL"
        ).fetchall()
    conn.close()

    n_total = len(rows)
    if n_total == 0:
        print("[reembed] No packed features found. Nothing to re-embed.", flush=True)
        return 0

    print(f"[reembed] Re-embedding {n_total} transitions in batches of {args.batch_size}...", flush=True)

    t0 = time.time()
    n_done = 0

    # Process in batches and write back
    conn = sqlite3.connect(args.db_path)

    for batch_start in range(0, n_total, args.batch_size):
        batch_rows = rows[batch_start:batch_start + args.batch_size]
        B = len(batch_rows)

        # Unpack state features
        state_arrays = [np.frombuffer(r[1], dtype=np.float32) for r in batch_rows]
        action_arrays = [np.frombuffer(r[2], dtype=np.float32) for r in batch_rows]
        state_packed = torch.from_numpy(np.stack(state_arrays)).to(device)
        action_packed = torch.from_numpy(np.stack(action_arrays)).to(device)
        transition_ids = [r[0] for r in batch_rows]

        with torch.no_grad():
            state_embs = transformer.forward_packed_batch(state_packed).cpu().numpy()
            action_embs = action_embedder.forward_packed_batch(action_packed).cpu().numpy()

        # Write embeddings back to DB
        updates = []
        for i, tid in enumerate(transition_ids):
            state_blob = state_embs[i].astype(np.float32).tobytes()
            action_blob = action_embs[i].astype(np.float32).tobytes()
            updates.append((state_blob, action_blob, tid))

        conn.executemany(
            "UPDATE embeddings SET state_embedding = ?, action_embedding = ? "
            "WHERE transition_id = ?",
            updates,
        )

        n_done += B
        if n_done % (args.batch_size * 10) == 0 or n_done == n_total:
            conn.commit()
            elapsed = time.time() - t0
            rate = n_done / elapsed if elapsed > 0 else 0
            print(f"[reembed] {n_done}/{n_total} ({100*n_done/n_total:.0f}%) "
                  f"{rate:.0f} transitions/sec", flush=True)

    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    print(f"[reembed] Done. {n_total} transitions re-embedded in {elapsed:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
