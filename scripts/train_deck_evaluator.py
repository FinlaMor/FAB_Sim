"""scripts/train_deck_evaluator.py

Train the deck evaluator model (DeepSets or Set Transformer).

Phase 1: Bootstrap on fablazing play-rate data (synthetic win labels).
Phase 2: Fine-tune on actual Talishar game outcomes (when available).

Usage:
    # Bootstrap training from fablazing data (requires --meta-db, uses default if omitted)
    python scripts/train_deck_evaluator.py --bootstrap

    # Resume training from checkpoint (vocab loaded from checkpoint, no --meta-db needed)
    python scripts/train_deck_evaluator.py --resume checkpoints/deck_eval_best.pt

    # Fine-tune on game data (requires a checkpoint to resume from)
    python scripts/train_deck_evaluator.py --resume checkpoints/deck_eval_best.pt --games-db data/talishar_games.db

    # Set Transformer instead of DeepSets
    python scripts/train_deck_evaluator.py --bootstrap --model set_transformer
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
import warnings
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl_agents.deck_evaluator import (
    CardVocab,
    DeepSetsEvaluator,
    SetTransformerEvaluator,
    DeckWinDataset,
    FablazingBootstrapDataset,
    build_evaluator,
    save_checkpoint,
    load_checkpoint,
)

CHECKPOINT_DIR = Path("checkpoints")
META_DB = Path("data/fablazing_meta.db")


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

_interrupted = False


def _handle_signal(sig, frame):
    global _interrupted
    _interrupted = True
    print("\nInterrupt received — finishing current epoch...")


def train_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> dict:
    """Train for one epoch. Returns metrics dict."""
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for batch in loader:
        hero_ids = batch["hero_id"].to(device)
        opp_hero_ids = batch["opp_hero_id"].to(device)
        card_ids = batch["card_ids"].to(device)
        counts = batch["counts"].to(device)
        pad_mask = batch["pad_mask"].to(device)
        labels = batch["label"].to(device)
        card_credits = batch.get("card_credits")
        if card_credits is not None:
            card_credits = card_credits.to(device)

        logits = model(hero_ids, card_ids, counts, opp_hero_ids, pad_mask, card_credits).squeeze(-1)
        loss = nn.functional.binary_cross_entropy_with_logits(logits, labels)

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        total_loss += loss.item() * labels.size(0)
        preds = (logits > 0).float()
        binary_labels = (labels > 0.5).float()
        correct += (preds == binary_labels).sum().item()
        total += labels.size(0)

    return {
        "loss": total_loss / max(total, 1),
        "accuracy": correct / max(total, 1),
        "n_samples": total,
    }


@torch.no_grad()
def eval_epoch(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
) -> dict:
    """Evaluate on validation set. Returns metrics dict."""
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    for batch in loader:
        hero_ids = batch["hero_id"].to(device)
        opp_hero_ids = batch["opp_hero_id"].to(device)
        card_ids = batch["card_ids"].to(device)
        counts = batch["counts"].to(device)
        pad_mask = batch["pad_mask"].to(device)
        labels = batch["label"].to(device)
        card_credits = batch.get("card_credits")
        if card_credits is not None:
            card_credits = card_credits.to(device)

        logits = model(hero_ids, card_ids, counts, opp_hero_ids, pad_mask, card_credits).squeeze(-1)
        loss = nn.functional.binary_cross_entropy_with_logits(logits, labels)

        total_loss += loss.item() * labels.size(0)
        preds = (logits > 0).float()
        binary_labels = (labels > 0.5).float()
        correct += (preds == binary_labels).sum().item()
        total += labels.size(0)

    return {
        "loss": total_loss / max(total, 1),
        "accuracy": correct / max(total, 1),
        "n_samples": total,
    }


def train(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader | None,
    optimizer: torch.optim.Optimizer,
    scheduler: torch.optim.lr_scheduler._LRScheduler | None,
    device: torch.device,
    vocab: CardVocab,
    model_type: str,
    n_epochs: int = 50,
    checkpoint_dir: Path = CHECKPOINT_DIR,
    start_epoch: int = 0,
    checkpoint_prefix: str = "deck_eval",
) -> None:
    """Main training loop with checkpointing and early stopping."""
    global _interrupted

    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    best_val_loss = float("inf")
    patience = 10
    patience_counter = 0
    last_epoch = start_epoch

    print(f"\nTraining {model_type} for {n_epochs} epochs on {device}")
    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Model parameters: {n_params:,}")
    print()

    for last_epoch in range(start_epoch, start_epoch + n_epochs):
        epoch = last_epoch
        if _interrupted:
            print(f"Saving checkpoint at epoch {epoch}...")
            save_checkpoint(
                checkpoint_dir / f"{checkpoint_prefix}_interrupted.pt",
                model, vocab, optimizer, scheduler, epoch,
                model_type=model_type,
            )
            print("Checkpoint saved.")
            break

        t0 = time.time()
        train_metrics = train_epoch(model, train_loader, optimizer, device)
        dt = time.time() - t0

        log = (
            f"Epoch {epoch+1:>3}/{start_epoch + n_epochs}  "
            f"train_loss={train_metrics['loss']:.4f}  "
            f"train_acc={train_metrics['accuracy']:.3f}  "
            f"({dt:.1f}s)"
        )

        if val_loader is not None:
            val_metrics = eval_epoch(model, val_loader, device)
            log += (
                f"  val_loss={val_metrics['loss']:.4f}  "
                f"val_acc={val_metrics['accuracy']:.3f}"
            )

            if val_metrics["loss"] < best_val_loss:
                best_val_loss = val_metrics["loss"]
                patience_counter = 0
                save_checkpoint(
                    checkpoint_dir / f"{checkpoint_prefix}_best.pt",
                    model, vocab, optimizer, scheduler, epoch,
                    metrics=val_metrics,
                    model_type=model_type,
                )
                log += " *"
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    print(log)
                    print(f"\nEarly stopping after {patience} epochs without improvement.")
                    break
        else:
            # No validation — save every 10 epochs
            if (epoch + 1) % 10 == 0:
                save_checkpoint(
                    checkpoint_dir / f"{checkpoint_prefix}_epoch{epoch+1}.pt",
                    model, vocab, optimizer, scheduler, epoch,
                    metrics=train_metrics,
                    model_type=model_type,
                )

        if scheduler is not None:
            scheduler.step()

        print(log)

    # Save final checkpoint
    final_path = checkpoint_dir / f"{checkpoint_prefix}_final.pt"
    save_checkpoint(
        final_path,
        model, vocab, optimizer, scheduler, last_epoch,
        model_type=model_type,
    )
    print(f"\nFinal checkpoint saved to {final_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Train deck evaluator model")
    parser.add_argument("--bootstrap", action="store_true",
                        help="Bootstrap train on fablazing play-rate data")
    parser.add_argument("--games-db", type=Path, default=None,
                        help="Path to talishar_games.db for fine-tuning")
    parser.add_argument("--meta-db", type=Path, default=None,
                        help=f"Path to fablazing_meta.db (only used with --bootstrap, default: {META_DB})")
    parser.add_argument("--model", default="deepsets",
                        choices=["deepsets", "set_transformer"],
                        help="Model architecture (default: deepsets)")
    parser.add_argument("--embed-dim", type=int, default=64)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--n-heads", type=int, default=4)
    parser.add_argument("--n-layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--samples-per-hero", type=int, default=100,
                        help="Synthetic samples per hero for bootstrap (default: 100)")
    parser.add_argument("--resume", type=Path, default=None,
                        help="Resume from checkpoint")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default=None,
                        help="Device (default: cuda if available)")
    args = parser.parse_args()

    if not args.bootstrap and args.games_db is None and args.resume is None:
        parser.error(
            "Specify --bootstrap for initial training, --resume to continue from "
            "a checkpoint, or --games-db for fine-tuning."
        )

    # Deprecation warning: --meta-db without --bootstrap
    if args.meta_db is not None and not args.bootstrap:
        warnings.warn(
            "--meta-db is only used during --bootstrap and will be ignored. "
            "Vocabulary is loaded from the checkpoint when resuming.",
            DeprecationWarning,
            stacklevel=2,
        )

    # Default --meta-db for bootstrap
    if args.bootstrap and args.meta_db is None:
        args.meta_db = META_DB

    if args.bootstrap and not args.meta_db.exists():
        parser.error(f"--meta-db path does not exist: {args.meta_db}")

    # Setup
    signal.signal(signal.SIGINT, _handle_signal)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, _handle_signal)

    torch.manual_seed(args.seed)
    device = torch.device(args.device or ("cuda" if torch.cuda.is_available() else "cpu"))

    # Build vocabulary — source depends on mode
    start_epoch = 0
    if args.resume and args.resume.exists():
        print(f"Resuming from {args.resume}...")
        ckpt = load_checkpoint(args.resume)
        vocab = CardVocab.from_state_dict(ckpt["vocab"])
        print(f"  Vocab loaded from checkpoint — Cards: {vocab.n_cards}  Heroes: {vocab.n_heroes}")
        model = build_evaluator(
            vocab, ckpt.get("model_type", args.model),
            args.embed_dim, args.hidden_dim, args.n_heads, args.n_layers, args.dropout,
        )
        model.load_state_dict(ckpt["model_state_dict"])
        start_epoch = ckpt.get("epoch", 0) + 1
        model_type = ckpt.get("model_type", args.model)
    elif args.bootstrap:
        print(f"Building vocabulary from {args.meta_db}...")
        vocab = CardVocab.from_db(args.meta_db)
        print(f"  Cards: {vocab.n_cards}  Heroes: {vocab.n_heroes}")
        model = build_evaluator(
            vocab, args.model,
            args.embed_dim, args.hidden_dim, args.n_heads, args.n_layers, args.dropout,
        )
        model_type = args.model
    elif args.games_db is not None and args.games_db.exists():
        # No checkpoint and no bootstrap — build vocab from game data itself
        print(f"Building vocabulary from game data at {args.games_db}...")
        vocab = CardVocab.from_games_db(args.games_db)
        print(f"  Cards: {vocab.n_cards}  Heroes: {vocab.n_heroes}")
        model = build_evaluator(
            vocab, args.model,
            args.embed_dim, args.hidden_dim, args.n_heads, args.n_layers, args.dropout,
        )
        model_type = args.model
    else:
        parser.error(
            "Cannot build vocabulary without --bootstrap, --resume, or --games-db. "
            "Run with --bootstrap for synthetic data, --games-db for game outcomes, "
            "or --resume to continue from a checkpoint."
        )
        return  # unreachable, but satisfies type checker

    model = model.to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    if args.resume and args.resume.exists() and "optimizer_state_dict" in ckpt:
        optimizer.load_state_dict(ckpt["optimizer_state_dict"])

    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=args.epochs, eta_min=args.lr * 0.01,
    )
    if args.resume and args.resume.exists() and "scheduler_state_dict" in ckpt:
        scheduler.load_state_dict(ckpt["scheduler_state_dict"])

    # Phase 1: Bootstrap on fablazing data
    if args.bootstrap:
        print(f"\n=== Phase 1: Bootstrap training on fablazing data ===")
        print(f"Generating {args.samples_per_hero} samples per hero...")

        dataset = FablazingBootstrapDataset(
            args.meta_db, vocab,
            samples_per_hero=args.samples_per_hero,
            seed=args.seed,
        )
        print(f"Total samples: {len(dataset)}")

        # 80/20 split
        n_val = max(1, len(dataset) // 5)
        n_train = len(dataset) - n_val
        train_ds, val_ds = random_split(
            dataset, [n_train, n_val],
            generator=torch.Generator().manual_seed(args.seed),
        )

        train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=0)
        val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)

        train(
            model, train_loader, val_loader, optimizer, scheduler,
            device, vocab, model_type,
            n_epochs=args.epochs,
            start_epoch=start_epoch,
            checkpoint_dir=CHECKPOINT_DIR,
            checkpoint_prefix="deck_eval_bootstrap",
        )

    # Phase 2: Fine-tune on game outcomes
    if args.games_db is not None and args.games_db.exists():
        print(f"\n=== Phase 2: Fine-tuning on game outcomes ===")
        print(f"Loading games from {args.games_db}...")

        dataset = DeckWinDataset(args.games_db, vocab)
        print(f"Total samples: {len(dataset)}")

        if len(dataset) < 10:
            print("Not enough game data for fine-tuning. Skipping Phase 2.")
        else:
            # Split by game so both perspectives stay in the same split (no data leakage)
            from torch.utils.data import Subset
            train_idx, val_idx = dataset.split_by_game(val_frac=0.2, seed=args.seed)
            train_ds = Subset(dataset, train_idx)
            val_ds = Subset(dataset, val_idx)
            print(f"  Split: {len(train_ds)} train / {len(val_ds)} val (by game)")

            # Lower LR for fine-tuning
            ft_lr = args.lr * 0.1
            ft_optimizer = torch.optim.AdamW(model.parameters(), lr=ft_lr, weight_decay=1e-4)
            ft_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                ft_optimizer, T_max=args.epochs, eta_min=ft_lr * 0.01,
            )

            train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=0)
            val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)

            train(
                model, train_loader, val_loader, ft_optimizer, ft_scheduler,
                device, vocab, model_type,
                n_epochs=args.epochs,
                checkpoint_dir=CHECKPOINT_DIR,
                checkpoint_prefix="deck_eval_finetune",
            )

    print("\nDone!")


if __name__ == "__main__":
    main()
