from __future__ import annotations

from compare_seeded_talishar_vs_local_payloads import _normalize_talishar_decisions


def _decision(
    *,
    actor: int = 1,
    turn: int = 1,
    step: str = "action",
    chosen: str,
    legal: list[str],
    raw_type: str = "hand",
) -> dict:
    return {
        "actor": actor,
        "turn": turn,
        "step": step,
        "chosen_action_type": chosen,
        "legal_action_features": [{"action_type": action_type} for action_type in legal],
        "chosen_raw_action": {"type": raw_type},
    }


def test_normalization_removes_pass_only_windows() -> None:
    decisions = [
        _decision(chosen="pass", legal=["pass"], raw_type="pass_phase"),
        _decision(chosen="reaction_pass", legal=["reaction_pass"], step="combat_reaction", raw_type="pass_phase"),
    ]

    normalized, stats = _normalize_talishar_decisions(decisions)

    assert normalized == []
    assert stats["removed_pass_only"] == 2
    assert stats["removed_end_phase_ui"] == 0
    assert stats["removed_micro_interactions"] == 0


def test_normalization_removes_end_phase_and_store_arsenal_windows() -> None:
    decisions = [
        _decision(step="end_phase_beginning", chosen="pass", legal=["pass"], raw_type="pass_phase"),
        _decision(step="action", chosen="store_arsenal", legal=["store_arsenal"], raw_type="hand"),
    ]

    normalized, stats = _normalize_talishar_decisions(decisions)

    assert normalized == []
    assert stats["removed_end_phase_ui"] == 2
    assert stats["removed_pass_only"] == 0


def test_normalization_collapses_prompt_pass_between_semantic_actions() -> None:
    decisions = [
        _decision(actor=2, turn=3, step="action", chosen="play_card", legal=["play_card", "pass"], raw_type="hand"),
        _decision(actor=2, turn=3, step="action", chosen="pass", legal=["play_card", "pass"], raw_type="prompt_button"),
        _decision(actor=2, turn=3, step="action", chosen="play_card", legal=["play_card", "pass"], raw_type="hand"),
    ]

    normalized, stats = _normalize_talishar_decisions(decisions)

    assert [decision["chosen_action_type"] for decision in normalized] == ["play_card", "play_card"]
    assert stats["removed_micro_interactions"] == 1


def test_normalization_collapses_defend_finalize_pass() -> None:
    decisions = [
        _decision(actor=2, turn=4, step="combat_defend", chosen="defend_cards", legal=["defend_cards", "pass"], raw_type="hand"),
        _decision(actor=2, turn=4, step="combat_defend", chosen="pass", legal=["defend_cards", "pass"], raw_type="prompt_button"),
    ]

    normalized, stats = _normalize_talishar_decisions(decisions)

    assert [decision["chosen_action_type"] for decision in normalized] == ["defend_cards"]
    assert stats["removed_micro_interactions"] == 1


def test_normalization_keeps_meaningful_terminal_pass_choice() -> None:
    decisions = [
        _decision(actor=1, turn=5, step="action", chosen="play_card", legal=["play_card", "pass"], raw_type="hand"),
        _decision(actor=1, turn=5, step="action", chosen="pass", legal=["play_card", "pass"], raw_type="prompt_button"),
    ]

    normalized, stats = _normalize_talishar_decisions(decisions)

    assert [decision["chosen_action_type"] for decision in normalized] == ["play_card", "pass"]
    assert stats["removed_micro_interactions"] == 0