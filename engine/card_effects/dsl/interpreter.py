"""Runtime interpreter: given a CardDef and event, execute matching abilities."""
from __future__ import annotations

from engine.card_effects.dsl import coverage as _coverage


def _track_effect(card, effect_type: str) -> None:
    """Record that an effect actually executed (no-op unless coverage is on)."""
    tracker = _coverage.active()
    if tracker is not None:
        tracker.record_effect(getattr(card, "slug", "?"), effect_type)


def _track_ability(card, ability) -> None:
    """Record that an ability actually fired (no-op unless coverage is on)."""
    tracker = _coverage.active()
    if tracker is not None:
        key = ability.trigger or ability.ability_type
        tracker.record_ability(getattr(card, "slug", "?"), key)


def run_ability(ability, card, event, state) -> None:
    """Execute a single AbilityDef, tracking *card* as the current effect source
    (so effects can gate on their origin, e.g. Ripple Away's 'action card effect')."""
    from engine.context import (push_effect_source, pop_effect_source,
                                push_refs, pop_refs)
    push_effect_source(card)
    # One reference scope per ability execution, so "look at a card … destroy
    # it" can share that card between effects without a bespoke function, and
    # a nested ability cannot clobber an outer one's names.
    push_refs()
    try:
        _run_ability(ability, card, event, state)
    finally:
        pop_refs()
        pop_effect_source()


def _run_ability(ability, card, event, state) -> None:
    """Execute a single AbilityDef. Checks additional costs, conditions, then runs effects."""
    # Check target filter (CR 1.8.5 — if no legal target exists, ability cannot resolve)
    for cond in getattr(ability, 'target_filter', []):
        fn = cond.fn
        if fn is not None and not fn(card, event, state):
            return

    # Check and pay additional costs (mandatory extra costs — abort if unpayable)
    for cost in getattr(ability, 'additional_costs', []):
        if cost.check_fn is not None and not cost.check_fn(card, event, state):
            return  # cost not satisfiable — abort (play.py should have blocked this)
        if cost.pay_fn is not None:
            cost.pay_fn(card, event, state)

    # Check ability-level conditions (all must pass — AND logic)
    for cond in ability.conditions:
        fn = cond.fn
        if fn is not None and not fn(card, event, state):
            return

    # "The FIRST TIME an attack action card you control deals damage to an
    # opposing hero this turn", "the first time this deals damage to a hero".
    # A once-per-turn gate on a TRIGGERED ability, which the DSL could not
    # express: every such card invented a private flag (FIRST_ATTACK_DAMAGE_DEALT,
    # DASHING_FLASHFOOT_FIRST_DAMAGE) that nothing set, so it never fired.
    #
    # Checked here, past every other gate, so a trigger whose conditions FAILED
    # does not burn the turn's single use — "the first time X happens" means the
    # first time it actually happens.
    _opt = getattr(ability, 'params', None) or {}
    _once = _opt.get('once_per_turn')
    if _once:
        from engine.card_effects.ability_keywords import _controller_id
        from engine.effect_keywords import TURN_EVENT_MARKER
        # Keyed by the ability's own name when given ("once_per_turn": "earth"),
        # else the card slug, so two once-per-turn abilities on one card do not
        # share a single use.
        key = _once if isinstance(_once, str) else getattr(card, 'slug', '?')
        marker = f"{TURN_EVENT_MARKER}onceperturn:{key}"
        pid = _controller_id(card)
        player = state.players.get(pid) if pid in getattr(state, 'players', {}) else None
        if player is None:
            return
        if marker in player.current_turn_effects:
            return
        player.current_turn_effects.append(marker)

    # Past every gate — this ability is genuinely resolving, not just matched.
    _track_ability(card, ability)

    # "Whenever a TRAP YOU CONTROL TRIGGERS, ..." (Riptide). CR 8.2.7 retired
    # trap as a functional subtype keyword, so a trap is an ordinary card — in
    # practice a Defense Reaction — that happens to carry the Trap subtype, and
    # "triggers" means one of its abilities actually resolves. That is exactly
    # here: past the target filter, the costs, the conditions and the
    # once-per-turn gate, so a trap whose condition FAILED does not count as
    # having triggered.
    #
    # Dispatched to the controller's hero and permanents, not to the trap, since
    # the payoff lives on another card.
    _subtypes = getattr(card, "subtypes", None) or []
    if any(str(t).lower() == "trap" for t in _subtypes):
        from engine.card_effects.ability_keywords import _controller_id
        from engine.card_effects.dsl import dispatch as _dsl_dispatch
        _cid = _controller_id(card)
        _owner = state.players.get(_cid) if _cid in getattr(state, "players", {}) else None
        if _owner is not None:
            _listeners = ([_owner.hero] if _owner.hero is not None else [])                          + list(_owner.permanents.cards)
            for _listener in _listeners:
                _dsl_dispatch(state, "ON_TRAP_TRIGGER", _listener.slug,
                              card=_listener, event=event)

    # MODAL abilities ("Choose N"): the controller picks modes, each of which
    # is a compiled EffectDef. Non-modal abilities run their effects in order.
    if getattr(ability, 'modes', None):
        from engine.card_effects.ability_keywords import _ask_player, _controller_id, STOP
        cid = _controller_id(card)
        # `choose` is the minimum number of modes; `choose_max` (if > choose)
        # allows more, up to that many, for "choose 1 or both". Once the minimum
        # is met, a STOP sentinel is offered so the player can pick fewer than
        # the max.
        n_min = ability.choose or 1
        n_max = ability.choose_max if ability.choose_max and ability.choose_max > n_min else n_min
        remaining = list(range(len(ability.modes)))
        chosen = []
        while remaining and len(chosen) < min(n_max, len(ability.modes)):
            labels = [str(i) for i in remaining]
            if len(chosen) >= n_min:
                labels = labels + [STOP]
            pick = _ask_player(state, cid, labels, context="Choose a mode")
            if pick == STOP:
                break
            idx = (int(pick) if isinstance(pick, str) and pick.isdigit()
                   and int(pick) in remaining else remaining[0])
            chosen.append(idx)
            remaining.remove(idx)
        for idx in chosen:
            mode = ability.modes[idx]
            if mode.fn is None:
                continue
            # Honour a mode's own conditions (e.g. "+3 to a DAGGER attack") —
            # the loader pops them onto the EffectDef, and unlike the regular
            # effects loop they must be checked here explicitly.
            if all(c.fn is None or c.fn(card, event, state)
                   for c in getattr(mode, 'conditions', [])):
                _track_effect(card, mode.effect_type)
                mode.fn(card, event, state)

    # Execute effects in order
    for eff in ability.effects:
        # Check effect-level conditions
        all_ok = True
        for cond in eff.conditions:
            fn = cond.fn
            if fn is not None and not fn(card, event, state):
                all_ok = False
                break
        if all_ok and eff.fn is not None:
            _track_effect(card, eff.effect_type)
            eff.fn(card, event, state)


def dispatch_event(card_def, event_type: str, card, event, state) -> None:
    """Fire all abilities in card_def that match event_type."""
    from engine.card_effects.dsl.trigger_types import (
        ABILITY_TYPE_TO_EVENT, TRIGGER_TO_EVENT, TRIGGER_EVENT_GATES)

    # "They lose all hero card abilities until the end of their next turn."
    # An object that has lost its abilities has none to fire, so this is the
    # single funnel to stop them at: triggered, static and activated hero
    # abilities all dispatch through here. Legality is handled separately (an
    # ability that does not exist must not be OFFERED either), but this is what
    # makes the loss real rather than cosmetic.
    from engine.effect_keywords import hero_owner_with_abilities_disabled
    if hero_owner_with_abilities_disabled(state, card):
        return

    for ability in card_def.abilities:
        atype = ability.ability_type.upper()

        # Trigger-based: fire when ability.trigger resolves to event_type
        if atype in ("TRIGGERED", "STATIC_TRIGGERED", "DELAYED_TRIGGERED"):
            trigger_event = TRIGGER_TO_EVENT.get(ability.trigger or "",
                                                  ability.trigger or "")
            if trigger_event == event_type:
                # Sugar triggers (e.g. ON_GOLD_CREATED → ON_TOKEN_CREATED)
                # map to a broader engine event and gate on the payload.
                gate = TRIGGER_EVENT_GATES.get(ability.trigger or "")
                if gate is None or gate(event):
                    run_ability(ability, card, event, state)
            continue

        # WHILE_STATIC: a continuous static re-evaluated each attack-power
        # recalculation. It fires ONLY on RECALC_ATTACK_POWER so its
        # MODIFY_ATTACK lands in the stage-8 window (after the staged recalc)
        # and is not double-applied by unrelated dispatches. Conditions gate it.
        if atype == "WHILE_STATIC":
            # RECALC_DEFENSE is the defence-side mirror, dispatched once per
            # declared defender by engine._recalculate_total_defense. A card
            # authored "while defending, this has +1{d}" has no attack-power
            # recalculation to hang on, so before this it could not run at all.
            #
            # A WHILE_STATIC that names its recalculation runs only on that one.
            # Letting a defence static also fire during an attack recalculation
            # is not merely wasteful: combat.defense_recalc_card is None then,
            # and MODIFY_DEFENSE would fall back to its own source card and
            # quietly change the {d} of a card that is not defending anything.
            # Omitting the trigger means the attack recalculation, which is what
            # every WHILE_STATIC written before RECALC_DEFENSE existed meant.
            wanted = (ability.trigger or "RECALC_ATTACK_POWER").upper()
            if event_type == wanted:
                run_ability(ability, card, event, state)
            continue

        # PLAY / ACTION / MODAL / ATTACK_REACTION / DEFENSE_REACTION / ACTIVATE / INSTANT / STATIC:
        # matches if the mapped event equals event_type
        mapped = ABILITY_TYPE_TO_EVENT.get(atype)
        if mapped and mapped == event_type:
            run_ability(ability, card, event, state)
            continue
