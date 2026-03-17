"""Print a concrete example of the data that flows into and out of AskAgentTransformer."""
import sys, math, random
sys.path.insert(0, '.')

import torch
from collections import Counter
from pathlib import Path

from engine.engine import new_game
from engine.card import CardDB
from engine.actions import legal_actions, Action
from rl_agents.transformer_policy import AskAgentTransformer, TransformerPolicyAgent, TransformerPolicyConfig
from encoder.card_embedder import SlugVocab

# ── Setup ──────────────────────────────────────────────────────────────────────
deck_dir = Path('decks')
decks = [
    str(deck_dir / 'oscillio_constella_intelligence_CC_lite.txt'),
    str(deck_dir / 'kayo_underhanded_cheat_CC_lite.txt'),
]
config = TransformerPolicyConfig()
vocab = SlugVocab()
card_db = CardDB()
model = AskAgentTransformer(slug_vocab=vocab, config=config)

class _Captured(Exception):
    pass

snapshot = {}

class SnapshotAgent:
    def __init__(self, pid):
        self.pid = pid
        self.calls = 0
    def __call__(self, state, options, context=None):
        self.calls += 1
        if not snapshot and options and isinstance(options[0], Action) and state.turn_number >= 4:
            snapshot['state'] = state
            snapshot['options'] = list(options)
            snapshot['pid'] = self.pid
            # Return a random choice first (so the state is valid), then raise on next call
        if snapshot and len(snapshot) == 3:
            # Second call after snapshot — abort the game loop
            snapshot['done'] = True
            raise _Captured()
        return random.Random(42 + self.calls).choice(list(options))

p1 = SnapshotAgent(1)
p2 = SnapshotAgent(2)

try:
    new_game(p1_deck_path=decks[0], p2_deck_path=decks[1], p1_agent=p1, p2_agent=p2, card_db=card_db)
except _Captured:
    pass

if not snapshot:
    print('No snapshot captured – game ended before turn 4 or no Action-typed decisions.')
    sys.exit(1)

state  = snapshot['state']
options = snapshot['options']
pid    = snapshot['pid']

player = state.players[pid]
opp    = state.players[3 - pid]

SEP = '=' * 70

# ── Raw Inputs ─────────────────────────────────────────────────────────────────
print(SEP)
print('TRANSFORMER INPUT BREAKDOWN')
print(f'Turn {state.turn_number}  |  Perspective: Player {pid}  |  Step: {state.step}')
print(SEP)

print()
print('[META TOKEN  — 20 raw scalars + step one-hot]')
meta_rows = [
    ('turn_number',    state.turn_number,          60,   'turn / 60'),
    ('is_active',      int(state.active_player==pid), 1,'active player?'),
    ('has_priority',   int(state.priority_player==pid),1,'holds priority?'),
    ('consec_passes',  state.consecutive_passes,   2,   ''),
    ('stack_depth',    len(state.stack_entries),   10,   'cards on stack'),
    ('chain_links',    len(state.chain_links),     10,   'chain links open'),
    ('self_health',    player.health,              50,   f'life = {player.health}'),
    ('opp_health',     opp.health,                 50,   f'life = {opp.health}'),
    ('self_resources', player.resources,           10,   ''),
    ('opp_resources',  opp.resources,              10,   ''),
    ('self_ap',        player.action_points,        5,   ''),
    ('opp_ap',         opp.action_points,           5,   ''),
    ('self_hand',      len(player.hand.cards),     12,   ''),
    ('opp_hand',       len(opp.hand.cards),        12,   ''),
    ('self_deck',      len(player.deck.cards),     80,   ''),
    ('opp_deck',       len(opp.deck.cards),        80,   ''),
    ('self_graveyard', len(player.graveyard.cards),80,   ''),
    ('opp_graveyard',  len(opp.graveyard.cards),   80,   ''),
    ('self_banished',  len(player.banished.cards), 80,   ''),
    ('opp_banished',   len(opp.banished.cards),    80,   ''),
]
for label, raw, denom, note in meta_rows:
    norm = min(float(raw), float(denom)) / float(denom)
    print(f'  {label:<22}  raw={str(raw):>5}  norm={norm:.3f}   {note}')
print(f'  {"step":<22}  {state.step.value!r}')

print()
print('[HAND CARDS]')
hand_cards = list(player.hand.cards)[:config.max_hand_cards]
for c in hand_cards:
    print(f'  {c.slug:<42} cost={getattr(c,"cost",None)!r:>4}  pitch={getattr(c,"pitch",None)!r:>4}  power={getattr(c,"power",None)!r}')

self_public, opp_public = model._collect_public_cards(state, pid)

print()
print(f'[PUBLIC SELF  — {len(self_public)} cards]')
for c in self_public[:12]:
    print(f'  {c.slug:<42} is_public={getattr(c,"is_public","?")}')
if len(self_public) > 12:
    print(f'  ... +{len(self_public)-12} more')

print()
print(f'[PUBLIC OPP  — {len(opp_public)} cards]')
for c in opp_public[:12]:
    print(f'  {c.slug:<42} is_public={getattr(c,"is_public","?")}')
if len(opp_public) > 12:
    print(f'  ... +{len(opp_public)-12} more')

ph_self = state.pitch_history.get(pid,   {})
ph_opp  = state.pitch_history.get(3-pid, {})

print()
print('[PITCH HISTORY SELF  — strict ordered, bottom of deck]')
if ph_self:
    for turn in sorted(ph_self):
        print(f'  turn {turn}: {ph_self[turn]}')
else:
    print('  (empty — no pitches yet, or history cleared by shuffle)')

print()
print('[PITCH HISTORY OPP  — shuffled within each turn]')
if ph_opp:
    for turn in sorted(ph_opp):
        print(f'  turn {turn}: {ph_opp[turn]}')
else:
    print('  (empty)')

deck_counts = Counter(c.slug for c in player.deck.cards)
print()
print(f'[DECK TOKENS  — {len(deck_counts)} unique slugs in {len(player.deck.cards)}-card deck (sorted by count)]')
for slug, cnt in sorted(deck_counts.items(), key=lambda x: -x[1])[:18]:
    bar = '*' * cnt
    print(f'  {slug:<42} x{cnt}  {bar}')
if len(deck_counts) > 18:
    print(f'  ... +{len(deck_counts)-18} more unique slugs')

print()
print(f'[LEGAL ACTIONS  — {len(options)} options]')
for a in options[:15]:
    pitch_slugs = [getattr(c, 'slug', c) for c in (a.pitch_cards or [])]
    card_name   = getattr(a.card, 'slug', a.card) if a.card else None
    print(f'  {str(a.type.value):<38} card={str(card_name):<32} pitch={pitch_slugs}')
if len(options) > 15:
    print(f'  ... +{len(options)-15} more')

# ── Token layout ───────────────────────────────────────────────────────────────
pitch_self_count = min(sum(len(v) for v in ph_self.values()), config.max_deck_tokens)
pitch_opp_count  = min(sum(len(v) for v in ph_opp.values()),  config.max_deck_tokens)
block_sizes = [
    ('CLS',          1),
    ('META',         1),
    ('HAND',         len(hand_cards)),
    ('PUBLIC_SELF',  len(self_public)),
    ('PUBLIC_OPP',   len(opp_public)),
    ('PITCH_SELF',   pitch_self_count),
    ('PITCH_OPP',    pitch_opp_count),
    ('DECK',         min(len(deck_counts), config.max_deck_tokens)),
    ('ACTION',       min(len(options), config.max_actions)),
]
total_tokens = sum(sz for _, sz in block_sizes)

print()
print(f'[TOKEN LAYOUT BEFORE FORWARD PASS  — {total_tokens} tokens, d_model={config.d_model}]')
for name, sz in block_sizes:
    bar = '#' * max(1, sz * 36 // max(total_tokens, 1)) if sz else ''
    print(f'  {name:<14} {sz:>3} tok   {bar}')

# ── Forward Pass ───────────────────────────────────────────────────────────────
print()
print(SEP)
print('TRANSFORMER OUTPUT')
print(SEP)

with torch.no_grad():
    output = model(state, options, perspective_player=pid)

print(f'Total sequence length : {output.token_count} tokens  (each = {config.d_model}-dim vector)')
print(f'Actions scored        : {output.action_count}')
print(f'State value (V-head)  : {output.value.item():+.4f}  (raw, un-normalized logit)')

if output.action_count > 0:
    probs = torch.softmax(output.logits, dim=0)
    top_k = min(6, output.action_count)
    top_idx = torch.topk(probs, top_k).indices.tolist()
    print()
    print(f'Top-{top_k} actions by policy probability (softmax over dot-product logits):')
    for rank, idx in enumerate(top_idx, 1):
        a = options[idx]
        pitch_slugs = [getattr(c, 'slug', c) for c in (a.pitch_cards or [])]
        card_name   = getattr(a.card, 'slug', a.card) if a.card else 'None'
        print(f'  [{rank}] p={probs[idx].item():.4f}  logit={output.logits[idx].item():+.3f}  '
              f'{str(a.type.value):<35} card={card_name!r}  pitch={pitch_slugs}')

    print()
    min_p = probs.min().item()
    max_p = probs.max().item()
    entropy = -(probs * torch.log(probs + 1e-9)).sum().item()
    print(f'Policy entropy  : {entropy:.3f} nats  (max={math.log(output.action_count):.3f} for uniform)')
    print(f'Prob range      : [{min_p:.4f}, {max_p:.4f}]')
    print(f'(Model is untrained — weights random, output is random but structurally correct)')
