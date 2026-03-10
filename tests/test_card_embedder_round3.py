"""Test Card embedder Round 3 improvements (counter types, state flags)."""

from encoder.card_embedder import CardEmbedder, SlugVocab, card_to_features
from engine.card import CardDB
import torch


print("=" * 70)
print("CARD EMBEDDER ROUND 3 TEST")
print("=" * 70)
print()

card_db = CardDB()
vocab = SlugVocab.from_card_db(card_db)
embedder = CardEmbedder(slug_vocab_size=vocab.size, d_model=128)

print("✓ CardEmbedder initialized successfully")
print()

# Test card_to_features with new numeric count (35)
card = card_db.get('pummel')
features = card_to_features(card, vocab)

print(f"Numeric features shape: {features['numeric'].shape}")
print(f"Expected: torch.Size([35])")
print()

if features['numeric'].shape[0] == 35:
    print("✅ PASS: N_NUMERIC = 35 (was 26)")
    print()
    print("Improvements:")
    print("  • Counter types split (7): power, defense, steam, flow, suspense, verse, energy")
    print("  • Special states added (3): face_up, is_attacking, is_defending")
    print("  • Total: +9 features (26 → 35)")
else:
    print(f"❌ FAIL: Expected 35 numeric features, got {features['numeric'].shape[0]}")

print()
print("=" * 70)
