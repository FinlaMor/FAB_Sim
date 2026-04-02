"""Tests for encoder/game_transformer.py — GameTransformerEncoder.

Coverage:
  1. Smoke: forward() runs without error on a minimal GameState.
  2. Output shape: returns (d_model,) tensor.
  3. Output is finite (no NaN / Inf).
  4. Both perspectives (player 1 and 2) produce different embeddings.
  5. Different game states produce different embeddings (encoder is sensitive).
  6. Same game state produces same embedding (deterministic in eval mode).
  7. Learns: a trivial supervised step lowers loss (backward pass works).
  8. Checkpoint round-trip: save → load → forward produces identical output.
  9. No reinitialization on reload: weights after load match weights before save.
  10. Device anchor: model.to() propagates to all components (device-portable).
  11. Masked opponent hand: N masked tokens correctly represent hand size.
  12. Pitch history: opponent pitch history tokens included when available.
  13. Truncation: very long zones don't crash and stay within max_seq_len.
  14. Schema metadata round-trip: get/validate_schema passes.
  15. get_output_dim() returns d_model.
  16. Drop-in signature: accepts (state, perspective_player=1) — same as GameStateEmbedder.
"""
from __future__ import annotations

import copy
import io
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.conftest import _make_card, _make_player, _mock_agent
from engine.state import CombatState, Event, GameState, Step
from engine.effects import EffectManager
from engine.state import EventManager
from encoder.card_embedder import SlugVocab
from encoder.game_transformer import GameTransformerEncoder, prime_dummy_vocab

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SMALL_VOCAB    = 64   # small enough to be fast in tests
_D_MODEL        = 32   # tiny model — fast, still exercises all paths
_N_HEADS        = 4
_N_LAYERS       = 2
_HERO_HEAD_DIM  = 8    # small hero head for tests
_OUT_DIM        = _D_MODEL + _HERO_HEAD_DIM  # expected output dim


def _make_encoder(vocab_size: int = _SMALL_VOCAB) -> GameTransformerEncoder:
    enc = GameTransformerEncoder(
        slug_vocab_size=vocab_size,
        d_model=_D_MODEL,
        n_heads=_N_HEADS,
        n_layers=_N_LAYERS,
        dim_feedforward=_D_MODEL * 2,
        dropout=0.0,   # no dropout so outputs are deterministic
        max_seq_len=64,
        hero_head_dim=_HERO_HEAD_DIM,
    )
    enc.eval()
    return enc


def _make_state(
    hand_size: int = 3,
    gy_size: int = 2,
    opp_hand_size: int = 2,
    with_combat: bool = False,
) -> GameState:
    p1 = _make_player(1)
    p2 = _make_player(2)

    for i in range(hand_size):
        c = _make_card(f"h{i}", f"Hand{i}", types=["Action"])
        c.owner = 1; c.controller = 1
        p1.hand.add(c)

    for i in range(gy_size):
        c = _make_card(f"g{i}", f"Grave{i}", types=["Action"])
        c.owner = 1; c.controller = 1
        p1.graveyard.add(c)

    for i in range(4):
        c = _make_card(f"d{i}", f"Deck{i}", types=["Action"])
        c.owner = 1; c.controller = 1
        p1.deck.add(c)

    for i in range(opp_hand_size):
        c = _make_card(f"oh{i}", f"OppHand{i}", types=["Action"])
        c.owner = 2; c.controller = 2
        p2.hand.add(c)

    combat = None
    if with_combat:
        atk = _make_card("atk", "Attack", types=["Action", "Attack"], base_power=4)
        atk.owner = 1; atk.controller = 1
        combat = CombatState(
            attacker_id=1,
            link_id=1,
            attack_power=4,
            base_attack_power=4,
            attack_card=atk,
            keywords=[],
            total_defense=0,
            defending_declared=True,
        )

    state = GameState(
        players={1: p1, 2: p2},
        active_player=1,
        player_agents={1: _mock_agent, 2: _mock_agent},
        step=Step.ACTION,
        turn_number=3,
        combat=combat,
        done=False,
        winner=None,
        card_db=None,
    )
    state.priority_player = 1
    state.effect_manager = EffectManager()
    state.event_manager = EventManager()
    return state


# ---------------------------------------------------------------------------
# 1. Smoke test
# ---------------------------------------------------------------------------

def test_forward_runs() -> None:
    enc = _make_encoder()
    state = _make_state()
    with torch.no_grad():
        out = enc(state, perspective_player=1)
    assert out is not None


# ---------------------------------------------------------------------------
# 2. Output shape
# ---------------------------------------------------------------------------

def test_output_shape() -> None:
    enc = _make_encoder()
    state = _make_state()
    with torch.no_grad():
        out = enc(state, perspective_player=1)
    assert out.shape == (_OUT_DIM,), f"Expected ({_OUT_DIM},), got {out.shape}"


# ---------------------------------------------------------------------------
# 3. Finite output (no NaN / Inf)
# ---------------------------------------------------------------------------

def test_output_finite() -> None:
    enc = _make_encoder()
    state = _make_state(hand_size=4, gy_size=5, opp_hand_size=3, with_combat=True)
    with torch.no_grad():
        out = enc(state, perspective_player=1)
    assert torch.isfinite(out).all(), "Output contains NaN or Inf"


# ---------------------------------------------------------------------------
# 4. Both perspectives produce different embeddings
# ---------------------------------------------------------------------------

def test_perspectives_differ() -> None:
    enc = _make_encoder()
    state = _make_state(hand_size=3, opp_hand_size=2)
    with torch.no_grad():
        out1 = enc(state, perspective_player=1)
        out2 = enc(state, perspective_player=2)
    assert not torch.allclose(out1, out2), \
        "P1 and P2 perspectives produced identical embeddings — likely a bug"


# ---------------------------------------------------------------------------
# 5. Different game states → different embeddings
# ---------------------------------------------------------------------------

def test_different_states_differ() -> None:
    enc = _make_encoder()
    state_a = _make_state(hand_size=1, gy_size=0)
    state_b = _make_state(hand_size=4, gy_size=3)
    with torch.no_grad():
        out_a = enc(state_a, perspective_player=1)
        out_b = enc(state_b, perspective_player=1)
    assert not torch.allclose(out_a, out_b), \
        "Different board states produced identical embeddings"


# ---------------------------------------------------------------------------
# 6. Deterministic in eval mode
# ---------------------------------------------------------------------------

def test_deterministic_eval() -> None:
    enc = _make_encoder()
    state = _make_state()
    with torch.no_grad():
        out1 = enc(state, perspective_player=1)
        out2 = enc(state, perspective_player=1)
    assert torch.allclose(out1, out2), "eval() forward is not deterministic"


# ---------------------------------------------------------------------------
# 7. Gradient flows — model can learn (backward pass works)
# ---------------------------------------------------------------------------

def test_backward_pass() -> None:
    """A single SGD step should reduce the loss."""
    enc = _make_encoder()
    enc.train()
    opt = torch.optim.SGD(enc.parameters(), lr=0.1)

    state = _make_state(hand_size=3, gy_size=2)
    target = torch.randn(_OUT_DIM)

    opt.zero_grad()
    out = enc(state, perspective_player=1)
    loss_before = torch.nn.functional.mse_loss(out, target)
    loss_before.backward()
    opt.step()

    enc.eval()
    with torch.no_grad():
        out_after = enc(state, perspective_player=1)
    loss_after = torch.nn.functional.mse_loss(out_after, target)

    assert loss_after.item() < loss_before.item(), \
        f"Loss did not decrease: before={loss_before.item():.6f}, after={loss_after.item():.6f}"


# ---------------------------------------------------------------------------
# 8. Checkpoint round-trip: save → load → same output
# ---------------------------------------------------------------------------

def test_checkpoint_roundtrip() -> None:
    enc = _make_encoder()
    state = _make_state()

    with torch.no_grad():
        out_before = enc(state, perspective_player=1)

    # Save to an in-memory buffer
    buf = io.BytesIO()
    torch.save({"state_dict": enc.state_dict(), "d_model": enc.d_model,
                "n_heads": enc.n_heads, "n_layers": enc.n_layers,
                "dim_feedforward": enc.dim_feedforward,
                "hero_head_dim": enc.hero_head_dim,
                "slug_vocab_size": enc.slug_vocab_size}, buf)
    buf.seek(0)

    # Reconstruct
    payload = torch.load(buf, map_location="cpu", weights_only=False)
    enc2 = GameTransformerEncoder(
        slug_vocab_size=payload["slug_vocab_size"],
        d_model=payload["d_model"],
        n_heads=payload["n_heads"],
        n_layers=payload["n_layers"],
        dim_feedforward=payload["dim_feedforward"],
        hero_head_dim=payload["hero_head_dim"],
        dropout=0.0,
        max_seq_len=64,
    )
    enc2.load_state_dict(payload["state_dict"])
    enc2.eval()

    with torch.no_grad():
        out_after = enc2(state, perspective_player=1)

    assert torch.allclose(out_before, out_after, atol=1e-6), \
        "Output changed after checkpoint save/load"


# ---------------------------------------------------------------------------
# 9. No reinitialization: loaded weights match saved weights exactly
# ---------------------------------------------------------------------------

def test_no_weight_reinitialization() -> None:
    enc = _make_encoder()

    # Record a specific weight tensor before save
    key = "slug_embed.weight"
    weight_before = enc.state_dict()[key].clone()

    buf = io.BytesIO()
    torch.save(enc.state_dict(), buf)
    buf.seek(0)

    enc2 = _make_encoder()
    enc2.load_state_dict(torch.load(buf, map_location="cpu", weights_only=True))

    weight_after = enc2.state_dict()[key]
    assert torch.equal(weight_before, weight_after), \
        "slug_embed.weight changed after save/load — weights were reinitialized"


# ---------------------------------------------------------------------------
# 10. Device portability: all internal tensors follow .to(device)
# ---------------------------------------------------------------------------

def test_device_anchor_propagates() -> None:
    """After .to('cpu'), forward() should not raise a device mismatch."""
    enc = _make_encoder()
    enc = enc.to("cpu")
    state = _make_state()
    with torch.no_grad():
        out = enc(state, perspective_player=1)
    assert out.device.type == "cpu"


# ---------------------------------------------------------------------------
# 11. Masked opponent hand: different hand sizes → different embeddings
# ---------------------------------------------------------------------------

def test_masked_hand_size_matters() -> None:
    """Opponent with 1 card in hand should produce a different embedding than 3."""
    enc = _make_encoder()
    state_small = _make_state(opp_hand_size=1)
    state_large = _make_state(opp_hand_size=3)
    with torch.no_grad():
        out_small = enc(state_small, perspective_player=1)
        out_large = enc(state_large, perspective_player=1)
    assert not torch.allclose(out_small, out_large), \
        "Opponent hand size 1 vs 3 produced identical embeddings — masked tokens not used"


# ---------------------------------------------------------------------------
# 12. Pitch history: injecting pitch_history attribute
# ---------------------------------------------------------------------------

def test_pitch_history_tokens() -> None:
    """When pitch_history is present, it should influence the embedding."""
    enc = _make_encoder()
    state_no_hist = _make_state()
    state_with_hist = _make_state()

    # Inject a pitch history on the state (keyed by player_id → {turn: [slugs]})
    state_with_hist.pitch_history = {
        2: {
            1: ["filler_0", "filler_1"],
            2: ["filler_2"],
        }
    }

    with torch.no_grad():
        out_no = enc(state_no_hist, perspective_player=1)
        out_yes = enc(state_with_hist, perspective_player=1)

    # The two should differ if pitch_history tokens are actually included
    # (they may not differ if the model has zero weights, but with random init they should)
    assert not torch.allclose(out_no, out_yes, atol=1e-5), \
        "Adding pitch_history had no effect on the embedding"


# ---------------------------------------------------------------------------
# 13. Truncation: very large zones don't crash
# ---------------------------------------------------------------------------

def test_truncation_large_zones() -> None:
    """A game state with hundreds of cards should be truncated to max_seq_len."""
    enc = _make_encoder()
    state = _make_state()

    p1 = state.players[1]
    for i in range(80):
        c = _make_card(f"extra_{i}", f"Extra{i}", types=["Action"])
        c.owner = 1; c.controller = 1
        p1.graveyard.add(c)
    for i in range(50):
        c = _make_card(f"deck_{i}", f"Deck{i}", types=["Action"])
        c.owner = 1; c.controller = 1
        p1.deck.add(c)

    with torch.no_grad():
        out = enc(state, perspective_player=1)

    assert out.shape == (_OUT_DIM,)
    assert torch.isfinite(out).all()


# ---------------------------------------------------------------------------
# 14. Schema metadata round-trip
# ---------------------------------------------------------------------------

def test_schema_metadata_roundtrip() -> None:
    enc = _make_encoder()
    meta = enc.get_schema_metadata()
    ok, errors = enc.validate_schema(meta, strict=True)
    assert ok, f"Schema validation failed: {errors}"


def test_schema_metadata_mismatch_detected() -> None:
    enc = _make_encoder()
    meta = enc.get_schema_metadata()
    meta["d_model"] = 999  # corrupt
    ok, errors = enc.validate_schema(meta, strict=True)
    assert not ok, "Schema validation should have caught d_model mismatch"


# ---------------------------------------------------------------------------
# 15. get_output_dim returns d_model
# ---------------------------------------------------------------------------

def test_get_output_dim() -> None:
    enc = _make_encoder()
    assert enc.get_output_dim() == _OUT_DIM


# ---------------------------------------------------------------------------
# 16. Drop-in signature compatibility
# ---------------------------------------------------------------------------

def test_drop_in_signature() -> None:
    """forward(state, perspective_player=N) must work exactly like GameStateEmbedder."""
    enc = _make_encoder()
    state = _make_state()
    # positional arg
    with torch.no_grad():
        out1 = enc(state, 1)
    # keyword arg
    with torch.no_grad():
        out2 = enc(state, perspective_player=1)
    assert torch.allclose(out1, out2)


# ---------------------------------------------------------------------------
# 17. Combat state tokens influence embedding
# ---------------------------------------------------------------------------

def test_combat_state_changes_embedding() -> None:
    enc = _make_encoder()
    state_no_combat = _make_state(with_combat=False)
    state_combat    = _make_state(with_combat=True)
    with torch.no_grad():
        out_no = enc(state_no_combat, perspective_player=1)
        out_yes = enc(state_combat,    perspective_player=1)
    assert not torch.allclose(out_no, out_yes), \
        "Combat state had no effect on embedding"
