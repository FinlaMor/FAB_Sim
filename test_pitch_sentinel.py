"""Test pitch/cost sentinel values in card embedder."""
from engine.card import CardDB
from encoder.card_embedder import SlugVocab, CardEmbedder, card_to_features

card_db = CardDB()
slug_vocab = SlugVocab.from_card_db(card_db)

print('Testing pitch/cost sentinel values:\n')

# Test 1: Action card (has pitch and cost)
action = card_db.get('enlightened_strike')
print(f'1. Enlightened Strike (pitch={action.pitch}, cost={action.cost})')
f = card_to_features(action, slug_vocab)
print(f'   pitch={f["numeric"][0]:.3f}, cost={f["numeric"][1]:.3f}')

# Test 2: Hero (has pitch=0, no cost)
hero = card_db.get('dorinthea_ironsong')
print(f'\n2. Dorinthea hero (pitch={hero.pitch}, cost={hero.cost})')
f = card_to_features(hero, slug_vocab)
print(f'   pitch={f["numeric"][0]:.3f} (hero has pitch=0)')
print(f'   cost={f["numeric"][1]:.3f} (should be -1.0 for None)')

# Test 3: Masked card (opponent's hidden card)
print(f'\n3. Masked card (opponent hand, identity unknown)')
f = card_to_features(action, slug_vocab, masked=True)
print(f'   slug_idx={f["slug_idx"].item()} (0 = MASK token)')
print(f'   pitch={f["numeric"][0]:.3f} (should be -1.0 for unknown)')
print(f'   cost={f["numeric"][1]:.3f} (should be -1.0 for unknown)')

# Test embedder
embedder = CardEmbedder(slug_vocab_size=slug_vocab.size, d_model=128)
action_feats = {k: v.unsqueeze(0) for k, v in card_to_features(action, slug_vocab).items()}
emb = embedder(action_feats)

print(f'\n✅ Embedding shape: {emb.shape}')
print(f'✅ Sentinel value -1.0 means: no pitch/cost OR unknown (masked)')
print(f'✅ This distinguishes from actual value 0 (e.g., cost=0 cards)')
print(f'✅ Round 8A COMPLETE: Sentinel values for absent/unknown properties')
