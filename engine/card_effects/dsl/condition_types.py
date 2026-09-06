"""Compile JSON condition objects into (card, event, state) -> bool callables."""
from __future__ import annotations
import re
from typing import Any, Callable


def _norm(value: str) -> str:
    """Fold a name to a comparable form.

    Card JSON authors keywords and traits in loose styles ("blood_debt",
    "Go Again") while card data stores them concatenated ("BloodDebt",
    "GoAgain"), so exact string comparison misses. Strip everything that is not
    alphanumeric and lowercase what remains.
    """
    return "".join(ch for ch in str(value) if ch.isalnum()).lower()


def _first_present(params, *keys, default=None):
    """First present key among `keys` — the scalar counterpart of _as_list."""
    for key in keys:
        value = params.get(key)
        if value is not None:
            return value
    return default


def _as_list(params, *keys) -> list:
    """First present key among `keys`, always as a list.

    Cards author singular and plural interchangeably ("class"/"classes",
    "subtype"/"subtypes") because both read naturally. A key the compiler does
    not look at leaves the filter EMPTY, so the condition matches nothing and
    the ability can never fire — the same outcome as an invented type, but
    invisible to a type-name audit, which only checks that the TYPE is real.
    Reading every spelling is what keeps that class from recurring.
    """
    for key in keys:
        value = params.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return list(value)
        return [value]
    return []


def _card_traits(card) -> set[str]:
    """Normalised classes + talents + color of a card, for `card_class` filters.

    Cards author a single "card_class" filter for what the game splits across
    class ("Guardian"), talent ("Earth"), and occasionally pitch color
    ("Blue"), so all three are matched against the one field.
    """
    _PITCH_COLOR = {1: "red", 2: "yellow", 3: "blue"}
    traits = set()
    for attr in ("classes", "talents"):
        for v in (getattr(card, attr, None) or []):
            traits.add(_norm(v))
    color = getattr(card, "color", None) or _PITCH_COLOR.get(getattr(card, "pitch", None))
    if color:
        traits.add(_norm(color))
    return traits


def _numeric_amount(value, state, card):
    """A condition's threshold as a NUMBER, or None when it cannot be resolved.

    Thresholds are authored as ints, as dynamic expressions
    ({"type":"COUNT_CHAIN_LINKS","talent":"Draconic"}), and — in older cards — as
    bare invented strings. Comparing an int against a raw string raises
    TypeError and aborts the game mid-resolution, so anything unresolvable
    returns None and the caller treats the condition as unmet instead.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except (TypeError, ValueError):
            return None
    if isinstance(value, dict):
        from engine.card_effects.dsl.effect_types import _resolve_amount
        resolved = _resolve_amount(value, state, card)
        return resolved if isinstance(resolved, (int, float)) else None
    return None


def _attack_card_cost(attack_card) -> int:
    """Printed resource cost of the attack card (0-cost cards stay 0)."""
    cost = getattr(attack_card, 'cost', None)
    if cost is None:
        cost = getattr(attack_card, 'raw_cost', None)
    return cost if cost is not None else 0


def compile_condition(ctype: str, params: dict[str, Any]) -> Callable | None:
    """Return a (card, event, state)->bool callable, or None (always-True)."""

    if ctype in ("none", "NONE", ""):
        return None

    # Dispatch on an UPPERCASE name. Every branch below is written in upper
    # case, so a card authoring "TalentContainsAny" fell through the whole
    # chain to the unknown-type error — an invented type as far as the
    # compiler is concerned, purely because of its casing. Normalising here
    # closes the class rather than adding a mixed-case alias per card.
    ctype = ctype.upper()

    # Threshold "amount" authored as an integer-literal string ("4") crashes the
    # numeric comparisons in *_GTE/_LTE conditions. Coerce a pure-integer string
    # to int once here; leave any non-numeric marker untouched.
    if isinstance(params.get("amount"), str):
        try:
            params = {**params, "amount": int(params["amount"])}
        except (TypeError, ValueError):
            pass

    # ── game phase ─────────────────────────────────────────────────────────
    if ctype == "DURING_TURN":
        # CR 4.1.8b: an effect that would only trigger during a player's turn
        # does not trigger during the start-of-game procedure. individual_turns
        # is 0 all through setup and becomes >=1 once the first turn begins, so
        # this gates a turn-restricted trigger out of start-of-game.
        #
        # An optional "phase" narrows it further ("during an action phase").
        # Combat happens inside the action phase (CR 4.3), so the combat steps
        # count as ACTION_PHASE.
        phase = _norm(params.get("phase") or "")
        # "during YOUR turn" / "during your OPPONENT'S turn". 14 nodes author
        # `player`, which was not read, so all of them fired on BOTH turns —
        # a restriction silently doing nothing rather than failing loudly.
        who = (params.get("player") or "ANY").upper()

        def _whose_turn(c, s, _who=who):
            if _who in ("ANY", ""):
                return True
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(c)
            active = getattr(s, "active_player", None)
            if _who in ("OPPONENT", "DEFENDING", "DEFENDER"):
                return active == 3 - cid
            return active == cid

        if not phase:
            return lambda c, e, s: (getattr(s, "individual_turns", 0) >= 1
                                    and _whose_turn(c, s))
        _PHASE_STEPS = {
            "actionphase": {"action", "combat_layer", "combat_attack", "combat_defend",
                            "combat_reaction", "combat_damage", "combat_resolution",
                            "combat_close"},
            "action": {"action", "combat_layer", "combat_attack", "combat_defend",
                       "combat_reaction", "combat_damage", "combat_resolution",
                       "combat_close"},
            "endphase": {"end_phase_beginning", "end_phase_cleanup", "end_turn"},
            "end": {"end_phase_beginning", "end_phase_cleanup", "end_turn"},
            "startphase": {"start_phase"},
            "start": {"start_phase"},
        }
        allowed = _PHASE_STEPS.get(phase)

        def _during(c, e, s, _allowed=allowed):
            if getattr(s, "individual_turns", 0) < 1:
                return False
            if not _whose_turn(c, s):
                return False
            if _allowed is None:
                return True
            step = getattr(s, "step", None)
            step = getattr(step, "value", step)
            return str(step) in _allowed
        return _during

    # ── combat presence ────────────────────────────────────────────────────
    if ctype == "IN_COMBAT":
        # "combat_role" restricts to the side the controller is on ("while this
        # is attacking" vs "defending"). Without it a card authored as two
        # role-gated branches fired BOTH branches in every combat.
        role = _norm(params.get("combat_role") or "")
        if not role:
            return lambda c, e, s: s.combat is not None

        def _in_combat_role(c, e, s, _role=role):
            from engine.card_effects.ability_keywords import _controller_id
            if s.combat is None:
                return False
            is_attacker = _controller_id(c) == s.combat.attacker_id
            if _role in ("attacker", "attacking"):
                return is_attacker
            if _role in ("defender", "defending"):
                return not is_attacker
            return True
        return _in_combat_role

    if ctype == "ATTACK_IS_WEAPON":
        return lambda c, e, s: s.combat is not None and getattr(s.combat, 'from_weapon', False)

    if ctype == "ATTACK_IS_NOT_WEAPON":
        return lambda c, e, s: s.combat is not None and not getattr(s.combat, 'from_weapon', False)

    if ctype == "ATTACK_CLASS_IN":
        classes = [_norm(v) for v in _as_list(params, "classes", "class",
                                              "talent", "talents")]

        def _aci(c, e, s, _cls=classes):
            if not s.combat or not getattr(s.combat, 'attack_card', None):
                return False
            # TALENTS as well as classes. "Ice or Elemental attack action card"
            # names two TALENTS, which never appear in `classes`, so a
            # classes-only match found neither and the filter matched nothing.
            have = _card_traits(s.combat.attack_card)
            return any(cl in have for cl in _cls)
        return _aci

    if ctype in ("ATTACK_NAME_IN", "ATTACK_IS_NAMED"):
        # "The next CROUCHING TIGER you play this turn" names the card, which
        # spans every colour variant, so the comparison strips the colour suffix
        # the way LAST_CHAIN_ATTACK does rather than demanding an exact slug.
        import re as _re
        wants = {_norm(v) for v in _as_list(params, "names", "name", "card_name") if v}

        def _ani(c, e, s, _w=wants):
            if not _w or not s.combat or not getattr(s.combat, 'attack_card', None):
                return False
            atk = s.combat.attack_card
            slug = _re.sub(r'_(red|yellow|blue)$', '', getattr(atk, 'slug', '') or '')
            return (_norm(slug) in _w
                    or _norm(getattr(atk, 'name', '') or '') in _w)
        return _ani

    if ctype == "WEAPON_SUBTYPE_IN":
        # Read under BOTH spellings. The compiler took "values" while three of
        # the five cards using this condition author "subtypes" — the natural
        # name given the condition is called SUBTYPE_IN — so those three gated
        # on an empty list, which matches nothing, and never fired. A parameter
        # name the compiler does not read fails exactly like an invented type
        # but is invisible to a type-name audit.
        values = [v.upper() for v in _as_list(params, "values", "subtypes", "subtype")]
        def _wsi(c, e, s, _vals=values):
            if not s.combat:
                return False
            w = getattr(s.combat, 'weapon', None) or getattr(s.combat, 'attack_card', None)
            subs = [x.upper() for x in (getattr(w, 'subtypes', None) or [])]
            return any(v in subs for v in _vals)
        return _wsi

    if ctype == "ATTACK_COST_GTE":
        amount = params.get("amount", 0)
        def _acg(c, e, s, _amt=amount):
            if not s.combat or not s.combat.attack_card:
                return False
            limit = _numeric_amount(_amt, s, c)
            if limit is None:
                return False
            return _attack_card_cost(s.combat.attack_card) >= limit
        return _acg

    if ctype == "ATTACK_COST_LTE":
        # Accept "cost" or "amount" key. Default high so a missing value never blocks.
        amount = params.get("cost", params.get("amount", 999))
        def _acl(c, e, s, _amt=amount):
            if not s.combat or not s.combat.attack_card:
                return False
            limit = _numeric_amount(_amt, s, c)
            if limit is None:
                return False
            return _attack_card_cost(s.combat.attack_card) <= limit
        return _acl

    if ctype == "ATTACK_TYPE_IN":
        # Cards author the type list under "types" OR "attack_type" (~7 usages
        # used the latter, unread -> empty list). Accept a string or a list.
        _raw = _as_list(params, "types", "attack_type", "attack_types",
                        "values", "type_name")
        if isinstance(_raw, str):
            _raw = [_raw]
        types = [v.lower() for v in _raw]
        def _ati(c, e, s, _types=types):
            if not s.combat or not getattr(s.combat, 'attack_card', None):
                return False
            atk = s.combat.attack_card
            # Types AND subtypes together, as CARD_IN_ZONE's filter already
            # does. "Attack" is a SUBTYPE in this card data — an attack action
            # card is types=['Action'], subtypes=['Attack'] — so the 10 nodes
            # asking for "Attack", "Weapon", "Dagger" or "Arrow" were testing a
            # list those words never appear in, and were false for every attack
            # in the game.
            card_types = [x.lower() for x in (getattr(atk, 'types', None) or [])]
            card_types += [x.lower() for x in (getattr(atk, 'subtypes', None) or [])]
            return any(t in card_types for t in _types)
        return _ati

    if ctype == "ATTACK_SUBTYPE_IN":
        # Types AND subtypes, for the third time in this audit. A WEAPON's
        # subtypes are ['TwoHanded', 'Hammer'] -- "Weapon" is a TYPE. A
        # subtypes-only reading made ironsong_response_blue's "target WEAPON
        # attack" filter false for every attack in the game, so the card did
        # nothing at all. Cards name either and mean the same thing by it.
        subtypes = [v.lower() for v in _as_list(params, "subtypes", "subtype",
                                                "types", "type")]

        def _asi(c, e, s, _subs=subtypes):
            if not s.combat or not getattr(s.combat, 'attack_card', None):
                return False
            ac = s.combat.attack_card
            have = {x.lower() for x in (getattr(ac, 'subtypes', None) or [])}
            have |= {x.lower() for x in (getattr(ac, 'types', None) or [])}
            # A weapon ATTACK is flagged on the combat, which is the reliable
            # signal when the attack card is not the weapon object itself.
            if getattr(s.combat, 'from_weapon', False):
                have.add("weapon")
            return any(st in have for st in _subs)
        return _asi

    if ctype in ("PITCHED_FOR_THIS", "PITCHED_TO_PLAY_THIS"):
        # "If a CHI was pitched to play this, ..." — the cards pitched to pay
        # for THIS card, which play._pitch_for_cost stamps on it. Distinct from
        # the pitch ZONE (which holds everything pitched this turn) and from
        # combat.pitched_for_attack (which is the activate path only).
        #
        #   {"type":"PITCHED_FOR_THIS","subtype":"Chi"}
        want_sub = _norm(params.get("subtype") or params.get("card_type") or "")
        want_col = _norm(params.get("color") or params.get("colour") or "")
        # "If a LIGHTNING card was pitched to play this" (Lightning Bond) — the
        # bond keywords name a CLASS or TALENT, which this could not ask about.
        want_cls = _norm(params.get("card_class") or params.get("class")
                         or params.get("talent") or "")
        # "If a NON-ATTACK ACTION card was pitched to play it" (Deathly Duet).
        # Two claims about ONE pitched card: it is an Action and it is not an
        # Attack. NOT around the whole condition says something different and
        # weaker — "no attack was pitched" — which is wrong the moment both an
        # attack and a non-attack are pitched to pay for the same card, exactly
        # the state where both of Deathly Duet's clauses should fire.
        not_sub = _norm(params.get("not_subtype")
                        or params.get("exclude_subtype") or "")

        def _pitched(c, e, s, _sub=want_sub, _col=want_col, _cls=want_cls,
                     _not=not_sub):
            for pc in (getattr(c, "pitched_for_this", None) or []):
                if _cls and _cls not in _card_traits(pc):
                    continue
                if _not:
                    have = {_norm(x) for x in (getattr(pc, "subtypes", None) or [])}
                    have |= {_norm(x) for x in (getattr(pc, "types", None) or [])}
                    if _not in have:
                        continue
                if _sub:
                    have = {_norm(x) for x in (getattr(pc, "subtypes", None) or [])}
                    have |= {_norm(x) for x in (getattr(pc, "types", None) or [])}
                    if _sub not in have:
                        continue
                if _col:
                    colour = (getattr(pc, "color", None)
                              or getattr(pc, "base_color", None) or "")
                    if _norm(colour) != _col:
                        continue
                return True
            return False
        return _pitched

    if ctype == "ATTACK_PITCH_POWER_GTE":
        # True if a card with printed power >= amount was pitched to pay for the
        # current attack (CR "pitched to attack with this"). Reads
        # combat.pitched_for_attack, NOT the pitch zone.
        amount = params.get("amount", params.get("power", 6))
        def _appg(c, e, s, _amt=amount):
            if not s.combat:
                return False
            for pc in getattr(s.combat, 'pitched_for_attack', None) or []:
                power = getattr(pc, 'power', None)
                if power is None:
                    power = getattr(pc, 'base_power', None)
                if power is not None and power >= _amt:
                    return True
            return False
        return _appg

    if ctype == "SOURCE_IS_ATTACK":
        # True when the ability's source card IS the current active attack. Used
        # by weapon self-buffs ("… to attack WITH THIS") so a WHILE_STATIC on the
        # weapon only applies to its own attack, not any attack in combat.
        def _sia(c, e, s):
            return bool(s.combat and getattr(s.combat, 'attack_card', None) is c)
        return _sia

    if ctype in ("ATTACK_CONTROLLED_BY_YOU", "ATTACKER_CONTROLLED_BY_YOU"):
        # True if the current attack is controlled by this card's controller.
        def _acby(c, e, s):
            from engine.card_effects.ability_keywords import _controller_id
            if not s.combat or not getattr(s.combat, 'attack_card', None):
                return False
            return getattr(s.combat.attack_card, 'controller', None) == _controller_id(c)
        return _acby

    if ctype == "CONTROLS_ATTACK_ACTION":
        # True if you control an attack action card in the current combat —
        # the active attack you control OR a card you're defending with
        # (CR: defending with an attack action card counts as controlling it).
        #
        # Two parameters were authored and unread, and each failed differently:
        #   opponent   leap_frog_vocal_sac asks about the OPPONENT's attack, so
        #              looking at your own inverted the gate.
        #   attack_class  scorpio_comet_tail is "only if you control a LIGHTNING
        #              attack"; unfiltered, any attack at all let it activate.
        #              Lightning is a TALENT, not a class -- the same trap as
        #              Mystic -- so the filter goes through _card_traits, which
        #              is what every other class filter in this file reads.
        want_opp = bool(_first_present(params, "opponent", "opposing",
                                       default=False))
        who = str(_first_present(params, "player", "controller",
                                 default="") or "").lower()
        if who in ("opponent", "opposing", "them"):
            want_opp = True
        wanted = [_norm(v) for v in _as_list(
            params, "attack_class", "class", "classes", "card_class") if v]

        def _caa(c, e, s, _opp=want_opp, _want=wanted):
            from engine.card_effects.ability_keywords import (
                _controller_id, controlled_attack_action_cards)
            pid = _controller_id(c)
            if _opp:
                pid = 3 - pid
            cards = controlled_attack_action_cards(s, pid)
            if _want:
                cards = [x for x in cards
                         if any(w in _card_traits(x) for w in _want)]
            return bool(cards)
        return _caa

    if ctype == "HAS_HEAD_OPP_DOESNT":
        # Headbutt: "if you have a head equipped and the defending hero doesn't".
        def _hhod(c, e, s):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(c)
            def has_head(p):
                return bool(p.head.cards) and not getattr(p.head.cards[0], 'face_down', False)
            return has_head(s.players[cid]) and not has_head(s.players[3 - cid])
        return _hhod

    if ctype == "DID_NOT_HIT":
        # True when the current combat's attack did not hit (e.g. Swing Big's
        # "when the combat chain closes, if this didn't hit …").
        return lambda c, e, s: (s.combat is not None
                                 and not getattr(s.combat, 'hit', False))

    if ctype == "DEFENDER_USED_HAND_CARD":
        return lambda c, e, s: (s.combat is not None
                                 and getattr(s.combat, 'defender_used_hand_card', False))

    if ctype == "DEFENDS_WITH_OTHER_HAND_CARD":
        # True if this card is defending together with ANOTHER card that came
        # from the defender's hand (Right Behind You). The source card itself is
        # excluded, so blocking with this card alone — even from hand — is not
        # enough; a second hand card must also be defending.
        def _dwohc(c, e, s):
            if s.combat is None:
                return False
            hand_ids = getattr(s.combat, 'hand_defender_ids', None) or set()
            return any(d is not c and getattr(d, 'object_id', None) in hand_ids
                       for d in s.combat.defending_cards)
        return _dwohc

    # ── keyword checks ─────────────────────────────────────────────────────
    if ctype in ("CHARGED_THIS_WAY", "CHARGED_TO_PLAY_THIS"):
        # "If a YELLOW card is charged this way, ..." — asks about the card the
        # optional CHARGE additional cost actually took, which the cost stamps
        # on the card being played. Distinct from "have you charged this turn",
        # which is a turn event and a different question.
        want = _norm(params.get("color") or params.get("colour") or "")

        def _charged(c, e, s, _w=want):
            got = getattr(c, "dsl_charged_color", None)
            if not got:
                return False
            return (not _w) or _norm(got) == _w
        return _charged

    if ctype == "REPRISE":
        def _reprise(c, e, s):
            from engine.card_effects.ability_keywords import reprise_check
            return reprise_check(s)
        return _reprise

    if ctype == "SELF_ATTACK_POWER_GTE":
        # "If this has N or more {p}" — the current attack's live power is at
        # least N (e.g. Chain of Brutality's 6-power threshold).
        try:
            amount = int(params.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0
        def _self_pow_gte(c, e, s, _n=amount):
            combat = s.combat
            return combat is not None and (combat.attack_power or 0) >= _n
        return _self_pow_gte

    if ctype == "ATTACK_POWER_GT_BASE":
        # "an attack with {p} greater than its base" — the current attack has
        # been pumped above its printed base power (e.g. Inertia Trap, which
        # reacts only to a boosted attack). Compares the live combat power to
        # the base recorded when the attack was declared.
        # "greater than TWICE its base" (Merciless Battleaxe) is the same
        # comparison with a factor. That card had it as SELF_ATTACK_POWER_GTE 2
        # -- "power is at least 2" -- which is true of nearly every attack, so
        # the gate did nothing and the axe had overpower whenever it swung.
        try:
            multiple = float(params.get("multiple", params.get("times", 1)) or 1)
        except (TypeError, ValueError):
            multiple = 1.0

        def _atk_gt_base(c, e, s, _m=multiple):
            combat = s.combat
            if combat is None:
                return False
            base = getattr(combat, "base_attack_power", 0) or 0
            return (combat.attack_power or 0) > base * _m
        return _atk_gt_base

    if ctype in ("ATTACK_BASE_POWER_LTE", "ATTACK_BASE_POWER_GTE"):
        # The current attack's printed BASE power vs a threshold ("an attack with
        # base {p} N or less/greater"). Reads the base recorded when the attack was
        # declared, not the pumped live value.
        #
        # The threshold may be an amount EXPRESSION rather than a number:
        # "while their base {p} is less than the number of Draconic chain links
        # you control" (Spreading Flames) is a comparison against a live count,
        # and a fixed number cannot say it.
        amount = params.get("amount", 0)
        lte = ctype == "ATTACK_BASE_POWER_LTE"
        strict = bool(params.get("strict"))

        def _abp(c, e, s, _a=amount, _lte=lte, _strict=strict):
            combat = s.combat
            if combat is None:
                return False
            base = getattr(combat, "base_attack_power", None)
            if base is None:
                base = getattr(getattr(combat, "attack_card", None), "base_power", 0) or 0
            if isinstance(_a, dict):
                from engine.card_effects.dsl.effect_types import _resolve_amount
                try:
                    threshold = int(_resolve_amount(_a, s, c))
                except (TypeError, ValueError):
                    return False
            else:
                threshold = _a
            if _lte:
                return base < threshold if _strict else base <= threshold
            return base > threshold if _strict else base >= threshold
        return _abp

    if ctype in ("ATTACK_PLAYED_FROM_ZONE", "ATTACK_PLAYED_FROM"):
        # "Attack action cards played FROM YOUR BANISHED ZONE get +3{p}"
        # (Baalghor). PLAYED_FROM_ZONE asks about the ability's SOURCE card; on a
        # hero static the source is the hero, which was never played from
        # anywhere. This asks about the card currently attacking.
        #
        #   {"type":"ATTACK_PLAYED_FROM_ZONE","zone":"banished"}
        want = _norm(params.get("zone") or params.get("from_zone") or "")

        def _apfz(c, e, s, _want=want):
            if not _want or not s.combat:
                return False
            atk = getattr(s.combat, "attack_card", None)
            if atk is None:
                return False
            zone = (getattr(atk, "played_from_zone", "") or ''
                    or getattr(atk, "prev_zone", "") or '')
            return _norm(zone) == _want
        return _apfz

    if ctype in ("IS_DEFENDING_CARD", "DEFENDING_CARD_IS"):
        # Describes the defender currently being evaluated by
        # engine._recalculate_total_defense (combat.defense_recalc_card).
        #
        #   {"type":"IS_DEFENDING_CARD"}                       — this card is it
        #   {"type":"DEFENDING_CARD_IS","subtype":"Attack",
        #    "controlled_by":"ATTACKER"}                       — "your attack
        #                                                        action cards"
        #   {"type":"DEFENDING_CARD_IS","equipment":true}
        #   {"type":"DEFENDING_CARD_IS","cost_gte":3}
        #
        # Every "while defending" static needs one of these, because the
        # RECALC_DEFENSE dispatch reaches every source once per defender: with
        # no way to name a defender, a static would apply to all of them.
        self_only = ctype == "IS_DEFENDING_CARD"
        want_types = [t.lower() for t in _as_list(
            params, "card_type", "card_types", "types", "subtype", "subtypes")]
        want_equipment = params.get("equipment")
        cost_gte = params.get("cost_gte")
        controlled_by = str(params.get("controlled_by")
                            or params.get("player") or "").upper()

        def _dci(c, e, s, _self=self_only, _t=want_types, _eq=want_equipment,
                 _cge=cost_gte, _by=controlled_by):
            combat = s.combat
            if combat is None:
                return False
            target = getattr(combat, "defense_recalc_card", None)
            if target is None:
                # Outside the defence-recalc pass there is no "defender being
                # evaluated", and the answer used to be an unconditional False.
                # beneath_the_surface_yellow asks "while this is DEFENDING" from
                # an ON_LEAVE_PLAY trigger, which never runs inside that pass,
                # so its whole ability could never fire. Membership on the chain
                # is the same question asked without the recalc context.
                if _self:
                    return any(d is c for d in
                               (getattr(combat, "defending_cards", None) or []))
                return False
            if _self:
                return target is c
            if _t:
                traits = [x.lower() for x in (getattr(target, 'types', None) or [])]
                traits += [x.lower() for x in (getattr(target, 'subtypes', None) or [])]
                if not any(t in traits for t in _t):
                    return False
            if _eq is not None and bool(getattr(target, 'is_equipment', False)) is not bool(_eq):
                return False
            if _cge is not None and (getattr(target, 'cost', None) or 0) < _cge:
                return False
            if _by:
                from engine.card_effects.ability_keywords import _controller_id
                owner = getattr(target, 'controller', None)
                if _by in ("ATTACKER", "ATTACKING"):
                    if owner != combat.attacker_id:
                        return False
                elif _by in ("SELF", "YOU", "CONTROLLER"):
                    if owner != _controller_id(c):
                        return False
                elif _by in ("DEFENDER", "DEFENDING", "OPPONENT"):
                    if owner == combat.attacker_id:
                        return False
            return True
        return _dci

    if ctype == "DEFENDING_CARD_COUNT":
        # "While this is defended by less than 2 NON-EQUIPMENT cards, it has
        # +1{p}" (Barraging Brawnhide, Stony Woottonhog). Both cards had this as
        # a DEFENDER_USED_HAND_CARD check, which is a boolean about hand cards
        # and cannot count, plus — on one of them — RESTRICT_DEFENSE_TO_HEAD_-
        # EQUIPMENT used as a CONDITION, which is an effect name.
        #
        #   {"type":"DEFENDING_CARD_COUNT","amount":2,"comparison":"lt",
        #    "equipment":false}
        #
        # `equipment` filters the cards counted: false counts only non-equipment,
        # true only equipment, omitted counts every declared defender.
        #
        # `power_gte_attack` counts only defenders whose {p} is at least the
        # attack's, for "while this ISN'T defended by a card with equal or
        # greater {p}" (Out Muscle) — a comparison against the live attack, so
        # no fixed number can stand in for it.
        try:
            need = int(params.get("amount", 1))
        except (TypeError, ValueError):
            need = 1
        comparison = _norm(params.get("comparison") or "gte")
        equipment = params.get("equipment")
        vs_attack_power = bool(params.get("power_gte_attack"))
        # `types` counts only defenders carrying ALL of the listed traits, read
        # from types and subtypes together — "defended by an ATTACK ACTION card"
        # is type Action plus subtype Attack, and either half alone is a
        # different set (an Attack Reaction is not an attack action card, and a
        # weapon is not a card that defends). ALL rather than ANY because every
        # phrasing that needs this names a compound card type.
        want_types = [str(t).lower() for t in (params.get("types") or [])]
        # "If a GUARDIAN OFF-HAND WITH 1 OR MORE {d} is defending this chain
        # link" (Shield Bash). Class and defence are properties of the
        # DEFENDER; that card asked ATTACK_CLASS_IN / ATTACK_SUBTYPE_IN /
        # ATTACK_PITCH_POWER_GTE instead, all three about the attack, so it read
        # every clause off the wrong object.
        want_class = _norm(params.get("card_class") or params.get("class") or "")
        defense_gte = params.get("defense_gte")
        _OPS = {"gte": lambda a, b: a >= b, "gt": lambda a, b: a > b,
                "lte": lambda a, b: a <= b, "lt": lambda a, b: a < b,
                "eq": lambda a, b: a == b, "neq": lambda a, b: a != b}

        def _dcc(c, e, s, _n=need, _cmp=comparison, _eq=equipment,
                 _vsp=vs_attack_power, _ty=want_types, _cls=want_class,
                 _dge=defense_gte):
            if not s.combat:
                return False
            cards = getattr(s.combat, "defending_cards", None) or []
            if _eq is not None:
                cards = [d for d in cards
                         if bool(getattr(d, "is_equipment", False)) is bool(_eq)]
            if _ty:
                def _traits(d):
                    out = [str(x).lower() for x in (getattr(d, "types", None) or [])]
                    out += [str(x).lower() for x in (getattr(d, "subtypes", None) or [])]
                    return out
                cards = [d for d in cards
                         if all(t in _traits(d) for t in _ty)]
            if _cls:
                cards = [d for d in cards if _cls in _card_traits(d)]
            if _dge is not None:
                try:
                    need_d = int(_dge)
                except (TypeError, ValueError):
                    need_d = None
                if need_d is not None:
                    cards = [d for d in cards
                             if (getattr(d, "defense", None)
                                 if getattr(d, "defense", None) is not None
                                 else getattr(d, "base_defense", None) or 0) >= need_d]
            if _vsp:
                atk_power = getattr(s.combat, "attack_power", 0) or 0
                cards = [d for d in cards
                         if (getattr(d, "power", None) or 0) >= atk_power]
            return _OPS.get(_cmp, _OPS["gte"])(len(cards), _n)
        return _dcc

    if ctype in ("ATTACK_ORDINAL_EQ", "ATTACK_ORDINAL_GTE"):
        # The current attack's ordinal this turn ("your second attack each turn"):
        # attacks_this_turn is 1 during the first attack, 2 during the second, …
        amount = params.get("amount", 2)
        eq = ctype == "ATTACK_ORDINAL_EQ"
        def _ord(c, e, s, _a=amount, _eq=eq):
            combat = s.combat
            if combat is None:
                return False
            n = getattr(s.players[combat.attacker_id], "attacks_this_turn", 0)
            return n == _a if _eq else n >= _a
        return _ord

    if ctype == "IN_GRAVEYARD":
        # "if you have a <name>/<type> in your graveyard" — true when the controller's
        # graveyard holds >= count cards matching an optional name / type filter.
        want_name = (params.get("name") or "").lower()
        want_types = [t.lower() for t in (params.get("types") or [])]
        count_gte = params.get("count_gte", 1)
        player_target = (params.get("player") or "SELF").upper()
        def _ing(c, e, s, _n=want_name, _t=want_types, _cge=count_gte, _pt=player_target):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(c)
            tid = (3 - cid) if _pt in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            gy = getattr(s.players[tid], "graveyard", None)
            if gy is None:
                return False
            n = 0
            for card in gy.cards:
                if _n and (getattr(card, "name", "") or "").lower() != _n \
                        and getattr(card, "slug", "") != _n:
                    continue
                if _t:
                    cts = [x.lower() for x in (getattr(card, "types", None) or [])
                           + (getattr(card, "subtypes", None) or [])]
                    if not any(x in cts for x in _t):
                        continue
                n += 1
            return n >= _cge
        return _ing

    if ctype == "CRUSH":
        def _crush(c, e, s):
            from engine.card_effects.ability_keywords import crush_check
            return crush_check(e, s)
        return _crush

    if ctype == "COMBO":
        # Accept either "names" or "combo_names" key for JSON flexibility
        combo_names = params.get("names", params.get("combo_names", []))
        def _combo(c, e, s, _cn=combo_names):
            from engine.card_effects.ability_keywords import combo_check
            return combo_check(s, _cn)
        return _combo

    if ctype == "COMBO_CONTAINS":
        # True if the last chain-link's base slug contains the given card name.
        # "base slug" strips the color suffix (e.g. "whelming_gustwave_red" →
        # "whelming_gustwave"). Cards author the name under "card"/"card_name"
        # (a display name like "Crouching Tiger") or "substring"; only
        # "substring" was read, so with the others unread it defaulted to "" and
        # `"" in slug` matched EVERYTHING (the combo gate always fired). Read all
        # three, normalise a display name to a slug fragment, and require a
        # non-empty value.
        raw = (params.get("substring") or params.get("card")
               or params.get("card_name") or "").strip().lower()
        substring = raw.replace(" ", "_")
        def _combo_contains(c, e, s, _sub=substring):
            if not _sub or not s.chain_links:
                return False
            import re
            last_slug = s.chain_links[-1].attack_slug
            last_base = re.sub(r'_(red|yellow|blue)$', '', last_slug)
            return _sub in last_base or _sub in last_slug
        return _combo_contains

    if ctype == "SURGE":
        amount = params.get("amount", 1)
        def _surge(c, e, s, _amt=amount):
            from engine.card_effects.ability_keywords import surge_check
            return surge_check(e, _amt)
        return _surge

    if ctype == "RUPTURE":
        def _rupture(c, e, s):
            from engine.card_effects.ability_keywords import rupture_check
            return rupture_check(s)
        return _rupture

    if ctype == "GO_FISH":
        def _gf(c, e, s):
            from engine.card_effects.ability_keywords import effect_go_fish
            return effect_go_fish(s, e)
        return _gf

    # ── player state ───────────────────────────────────────────────────────
    if ctype == "HEALTH_GT_OPP":
        def _hgo(c, e, s):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(c)
            return s.players[pid].life > s.players[3 - pid].life
        return _hgo

    if ctype == "HEALTH_LT_OPP":
        # "If you have less {h} than an OPPOSING SHADOW HERO" — the narrowing is
        # part of the condition, not decoration. ray_of_hope_yellow passed
        # `opponent_subtypes: ["shadow"]` into a handler that read no parameters
        # at all, so it fired against any opponent whatsoever and the card put
        # itself into the soul in matchups it says nothing about.
        want = [_norm(t) for t in
                (params.get("opponent_subtypes") or params.get("hero_type")
                 or params.get("classes") or []) if t]

        def _hlo(c, e, s, _want=want):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(c)
            opp = s.players[3 - pid]
            if _want:
                hero = getattr(opp, "hero", None)
                if hero is None:
                    return False
                traits = _card_traits(hero)
                if not any(t in traits for t in _want):
                    return False
            return s.players[pid].life < opp.life
        return _hlo

    if ctype == "DECK_EMPTY":
        def _de(c, e, s):
            from engine.card_effects.ability_keywords import _controller_id
            pid = _controller_id(c)
            return len(s.players[pid].deck.cards) == 0
        return _de

    if ctype == "PLAYED_FROM_ARSENAL":
        # card.prev_zone is 'arsenal' when played from arsenal (set by Zone tracking).
        #
        # `value` (default True) is the expected answer, matching IS_ACTIVE_PLAYER:
        # value:false means "NOT played from arsenal". It was unread, so a card
        # asking for the negative got the positive - the opposite branch entirely.
        #
        # Two attributes carry this fact. play.py stamps `played_from_zone`
        # explicitly at the moment of play; Zone.add sets `prev_zone` on every
        # move, so it is the last zone rather than the played-from zone. They
        # agree during an attack (arsenal → combat chain), but a card put onto
        # the chain by any other route has only one of them. Prefer the explicit
        # stamp and fall back to the generic one, so neither path reads as "not
        # played from arsenal" when it was.
        want = params.get("value", True)

        def _pfa(c, e, s, _w=want):
            zone = (getattr(c, 'played_from_zone', '') or ''
                    or getattr(c, 'prev_zone', '') or '')
            return (zone.lower() == 'arsenal') is bool(_w)
        return _pfa

    if ctype == "IS_ACTIVE_PLAYER":
        # `value` (default True) is the expected answer: value:false means "it is
        # NOT your turn" (an opponent's turn). Previously the field was ignored,
        # so every card that wrote value:false to mean "on an opponent's turn"
        # (Emeritus Scolding, Pry, Timekeeper's Whim) silently fired on the wrong
        # turn — honour it here.
        want = bool(params.get("value", True))
        def _iap(c, e, s, _want=want):
            from engine.card_effects.ability_keywords import _controller_id
            return (_controller_id(c) == s.active_player) == _want
        return _iap

    # ── card / zone ────────────────────────────────────────────────────────
    if ctype == "HAS_KEYWORD":
        # Authored as "keyword" (singular) or "keywords" (a list — match any).
        # The list form used to fall back to an empty keyword and be always
        # false, killing the whole ability. Matching is normalised so
        # "blood_debt" finds the stored "BloodDebt".
        wanted = params.get("keywords")
        if not wanted:
            wanted = [params.get("keyword", "")]
        wanted = [k for k in wanted if k]

        def _has_kw(c, e, s, _w=wanted):
            have = getattr(c, 'keywords', None) or []
            if not have or not _w:
                return False
            if any(k in have for k in _w):
                return True
            have_n = {_norm(h) for h in have}
            return any(_norm(k) in have_n for k in _w)
        return _has_kw

    if ctype == "CARD_IN_ZONE":
        # Zones: cards author either "zone" (singular) or "zones" (a list, ~19
        # usages) — read both. Optional filters: cost_gte/cost_lte, filter_types,
        # and `color` (red/yellow/blue via pitch 1/2/3, ~14 usages) which was
        # previously ignored.
        # A nested `filter` dict is a fourth way to spell the same options
        # ({"filter": {"power_gte": 6}}); it was not read, so those nodes had NO
        # filter at all — and a dropped filter here does not disable the
        # condition, it makes it match ANY card in the zone.
        nested = params.get("filter")
        if isinstance(nested, dict):
            params = {**nested, **{k: v for k, v in params.items()
                                   if k != "filter"}}
        zones = params.get("zones")
        if not zones:
            zones = [params.get("zone", "")]
        zones = [z.lower() for z in zones if z]
        # Cards say "with cost 0", "with 1{p}" as often as they say "or more".
        # The exact spellings were unread, so those nodes matched on cost/power
        # not at all.
        exact_cost = params.get("cost")
        cost_gte = params.get("cost_gte", exact_cost)
        cost_lte = params.get("cost_lte", exact_cost)
        # "a card with 6 or more {p} in your pitch zone" — authored as
        # power_gte, or as pitch_power_gte on the wrong condition entirely
        # (REF_PITCH_IS, which tests a referenced card's PITCH VALUE).
        exact_power = params.get("power")
        power_gte = params.get("power_gte", params.get("pitch_power_gte",
                                                       exact_power))
        power_lte = params.get("power_lte", exact_power)
        # "a FACE-UP yellow card in any arsenal" — arsenal and banished cards
        # track visibility, so this is a real restriction rather than decoration.
        want_face_up = params.get("face_up")
        # "a card named X in your arsenal". Authored as "card", which was
        # unread, so the condition asked only whether the zone was non-empty.
        want_name = _first_present(params, "card_name", "card", "name",
                                   default=None)
        # filter_types / card_type / subtypes / subtype all name the same thing
        # here: the matcher below already checks types AND subtypes together.
        # 47 nodes author one of the unread spellings, and a dropped filter does
        # not disable the condition — it makes it TOO PERMISSIVE, which is worse
        # than failing closed: "an instant in your graveyard" silently becomes
        # "any card in your graveyard".
        filter_types = [t.lower() for t in _as_list(
            params, "filter_types", "card_type", "card_types",
            "subtypes", "subtype")]
        color = (params.get("color") or "").lower()
        # card_class: a class ("Guardian"), talent ("Earth") or color ("Blue")
        # filter; keywords: match any (e.g. "blood_debt"). Both were ignored,
        # making the condition too permissive.
        card_class = _norm(params.get("card_class") or "")
        _classes_alias = _as_list(params, "classes", "class", "class_in",
                                  "talent", "talents")
        if not card_class and _classes_alias:
            card_class = _norm(_classes_alias[0])
        want_kws = [k for k in _as_list(params, "keywords", "keyword") if k]
        # count_gte: >= N cards match; "amount" is a legacy alias for count_gte
        count_gte = params.get("count_gte", params.get("amount"))
        count_eq  = params.get("count_eq")
        # "if you have NO cards in hand / in your arsenal / in your soul" is
        # authored as amount: 0 by all three cards that say it, and as a >=
        # threshold that is TRUE FOR EVERY STATE — the exact opposite of the
        # restriction each card is stating. Zero is meaningless as a lower
        # bound, so "exactly none" is the only reading that is not vacuous.
        if count_eq is None and count_gte == 0 and "count_gte" not in params:
            count_gte, count_eq = None, 0
        _PITCH_COLOR = {1: "red", 2: "yellow", 3: "blue"}

        # "a card in THEIR graveyard" — 7 nodes author `player`, which was not
        # read, so every one of them looked at the controller's own zone.
        who = str(_first_present(params, "player", "controller", "controlled_by",
                                 default="SELF")).upper()

        def _ciz(c, e, s, _zs=zones, _cge=cost_gte, _cle=cost_lte, _ft=filter_types,
                 _col=color, _nge=count_gte, _neq=count_eq,
                 _cc=card_class, _kws=want_kws, _pge=power_gte, _ple=power_lte,
                 _who=who, _fu=want_face_up, _nm=want_name):
            from engine.card_effects.ability_keywords import _controller_id
            _cid = _controller_id(c)
            # "in ANY arsenal" / "each hero's graveyard" — both players' zones.
            if _who in ("ANY", "ALL", "EACH", "BOTH"):
                _pids = [pid for pid in (_cid, 3 - _cid) if pid in s.players]
            else:
                _pid = (3 - _cid) if _who in ("OPPONENT", "DEFENDING", "DEFENDER") else _cid
                if _pid not in s.players:
                    return False
                _pids = [_pid]
            count = 0
            for _pid in _pids:
              player = s.players[_pid]
              for _z in _zs:
                zone_obj = getattr(player, _z, None)
                if zone_obj is None:
                    continue
                for card in zone_obj.cards:
                    cost = getattr(card, 'cost', None) or 0
                    if _cge is not None and cost < _cge:
                        continue
                    if _cle is not None and cost > _cle:
                        continue
                    if _ft:
                        card_types = [t.lower() for t in (getattr(card, 'subtypes', None) or [])]
                        card_types += [t.lower() for t in (getattr(card, 'types', None) or [])]
                        if not any(t in card_types for t in _ft):
                            continue
                    if _col:
                        # Card.color is None on a real card until something sets
                        # it; the PRINTED colour is on base_color.
                        card_color = (getattr(card, 'color', None)
                                      or getattr(card, 'base_color', None)
                                      or _PITCH_COLOR.get(getattr(card, 'pitch', None)))
                        if (card_color or "").lower() != _col:
                            continue
                    if _pge is not None or _ple is not None:
                        power = getattr(card, 'power', None)
                        if power is None:
                            power = getattr(card, 'base_power', None)
                        if power is None:
                            continue          # no printed power: cannot match
                        if _pge is not None and power < _pge:
                            continue
                        if _ple is not None and power > _ple:
                            continue
                    if _cc and _cc not in _card_traits(card):
                        continue
                    if _kws:
                        have = {_norm(k) for k in (getattr(card, 'keywords', None) or [])}
                        if not any(_norm(k) in have for k in _kws):
                            continue
                    if _fu is not None and bool(getattr(card, 'is_public', False)) is not bool(_fu):
                        continue
                    if _nm and _norm(_nm) not in (_norm(getattr(card, 'name', '') or ''),
                                                  _norm(getattr(card, 'slug', '') or '')):
                        continue
                    count += 1
            # "an Ice card ... FOR EACH FLOW COUNTER on it" — the threshold is
            # itself a count, so it has to be resolved rather than compared as a
            # raw dict (which is never equal to an int, so the gate was always
            # false).
            from engine.card_effects.dsl.effect_types import _resolve_amount
            if _neq is not None:
                try:
                    return count == int(_resolve_amount(_neq, s, c))
                except (TypeError, ValueError):
                    return False
            if _nge is not None:
                try:
                    return count >= int(_resolve_amount(_nge, s, c))
                except (TypeError, ValueError):
                    return False
            return count >= 1  # default: at least one matching card

        return _ciz

    if ctype in ("COUNTER_GTE", "COUNTER_LTE", "COUNTER_EQ"):
        # How many counters of a kind are on THIS card.
        #
        # There was no LTE or EQ, so "when this has NO steam counters, destroy
        # it" was written as COUNTER_GTE 0 — true for every card at all times.
        # Teklo Core destroyed itself at the start of every turn regardless of
        # its counters, which is the opposite of what it says.
        #
        # effect_put_counter writes BOTH a card-level tally and a player-level
        # one keyed by (slug, ZONE, kind). The player-level key goes stale the
        # moment the card changes zone — an aim counter put on a card in the
        # arsenal is unfindable once it moves to the combat chain — so the
        # card's own tally is the authority and the player-level dict is only a
        # fallback for counters recorded before the card carried them.
        kind = (params.get("counter_type") or params.get("counter")
                or params.get("type") or "")
        threshold = params.get("min", params.get("amount", 1))
        kindop = ctype

        def _counter_cmp(c, e, s, _ct=kind, _n=threshold, _op=kindop):
            from engine.card_effects.ability_keywords import _controller_id
            have = (getattr(c, "counters", None) or {}).get(_ct)
            if have is None:
                cid = _controller_id(c)
                player = s.players.get(cid) if cid is not None else None
                have = (player.counters.get((c.slug, c.zone, _ct), 0)
                        if player is not None else 0)
            if _op == "COUNTER_LTE":
                return have <= _n
            if _op == "COUNTER_EQ":
                return have == _n
            return have >= _n
        return _counter_cmp

    if ctype == "FLAG_SET":
        flag = params.get("flag", "")
        def _fs(c, e, s, _f=flag):
            from engine.card_effects.ability_keywords import _controller_id
            return _f in s.players[_controller_id(c)].current_turn_effects
        return _fs

    if ctype == "CHAIN_HIT_COUNT_GTE":
        # True when the current chain has >= N prior hits (mask_of_momentum: 3rd+ hit).
        amount = params.get("amount", 3)
        def _cgh(c, e, s, _amt=amount):
            return len(getattr(s, 'chain_links', [])) >= _amt - 1
        return _cgh

    if ctype == "BANISHED_TO_PLAY_THIS":
        # "If a card with 6 or more {p} is banished THIS WAY, this gets go
        # again" (Ram Raider) / "you may banish a card with blood debt from
        # your hand. IF YOU DO, ..." (Shadow of Ursur).
        #
        # The banished ZONE cannot answer either question -- it holds every
        # card banished all game, by anyone, for any reason. "This way" is
        # about what THIS card's cost took, which cost_types._stamp_banished
        # records on the card being played, the same way play.py stamps
        # pitched_for_this.
        #
        #   {"type":"BANISHED_TO_PLAY_THIS"}                 "if you do"
        #   {"type":"BANISHED_TO_PLAY_THIS","power_gte":6}   "with 6 or more {p}"
        #
        # A bare use asks only that SOMETHING was banished to pay for this,
        # which is what an optional additional cost's "if you do" means.
        want_power = params.get("power_gte", params.get("power"))

        def _banished_to_play(c, e, s, _p=want_power):
            banished = getattr(c, "banished_for_this", None) or []
            if not banished:
                return False
            if _p is None:
                return True
            try:
                need = int(_p)
            except (TypeError, ValueError):
                return True
            for card in banished:
                power = getattr(card, "power", None)
                if power is None:
                    power = getattr(card, "base_power", None)
                if (power or 0) >= need:
                    return True
            return False
        return _banished_to_play

    if ctype == "DISCARDED_CARD_POWER_GTE":
        # "If the discarded card has 6 or more {p}, this gains go again."
        #
        # It read the power off the EVENT, which works only where the discarded
        # card IS the event -- an on-discard trigger. For the cards that
        # actually use this condition the discard is an ADDITIONAL COST, so the
        # event is the play event, which has no power: the answer was 0, the
        # clause could never fire, and the printed keyword granted go again
        # regardless. Breakneck Battery's whole gamble paid out every time.
        #
        # cost_types._stamp_discarded now records what a discard cost took on
        # the card being played, the same way play.py stamps pitched_for_this,
        # so the condition can still be asked long after the discard -- which
        # a WHILE_STATIC re-evaluated on every recalculation must be able to do.
        # The event is still consulted first so on-discard triggers keep
        # working.
        amount = params.get("amount", 0)

        def _dcpg(c, e, s, _amt=amount):
            power = getattr(e, 'power', None) or getattr(e, 'base_power', None) or 0
            if (power or 0) >= _amt:
                return True
            for card in (getattr(c, 'discarded_for_this', None) or []):
                if (getattr(card, 'power', None)
                        or getattr(card, 'base_power', None) or 0) >= _amt:
                    return True
            return False
        return _dcpg

    if ctype == "CODEFENDER_POWER_GTE":
        # True when the source defends together with ANOTHER card of >= N power
        # (CR 7.0.5e). E.g. Apex Bonebreaker: "When this defends together with a
        # card with 6 or more {p}, …".
        min_power = params.get("min", params.get("power", params.get("amount", 6)))
        def _cdp(c, e, s, _min=min_power):
            if not s.combat:
                return False
            for d in (s.combat.defending_cards or []):
                if d is c:
                    continue
                if (getattr(d, 'power', None) or 0) >= _min:
                    return True
            return False
        return _cdp

    if ctype in ("EVENT_THIS_TURN", "DID_THIS_TURN"):
        # "if you've dealt arcane damage this turn", "if you've pitched a blue
        # card", "if you've attacked with a weapon twice" — one condition over
        # markers the canonical keyword functions record.
        #
        #   {"type":"EVENT_THIS_TURN","event":"damage","qualifier":"arcane"}
        #   {"type":"EVENT_THIS_TURN","event":"pitch","qualifier":"blue"}
        #   {"type":"EVENT_THIS_TURN","event":"draw","count":2}
        #
        # `event` is one of damage / pitch / banish / draw / create / play /
        # roll / charge / transcend — the full set is whatever engine code passes
        # to effect_keywords._record_turn_event, and "play" in particular carries
        # slug, name, types, subtypes, classes, talents and COLOUR as qualifiers
        # (see play.py), so "if you've played another blue card this turn" is
        # expressible and was previously assumed not to be. `qualifier`
        # narrows it (a damage type, a colour, a class, a talent, a token slug,
        # a card type); omit it to ask coarsely. `count` is >= N occurrences.
        # These replace 154 hand-rolled private flags across 169 cards, none of
        # which anything ever set.
        event = _norm(params.get("event") or "")
        qualifier = _norm(params.get("qualifier") or params.get("name") or "")
        try:
            need = int(params.get("count", 1) or 1)
        except (TypeError, ValueError):
            need = 1
        who = (params.get("player") or "SELF").upper()
        # "your SECOND non-attack action card each turn" fires ON the second and
        # not on the third. A >= test stays true for every later play, turning
        # "the second" into "the second and every one after".
        exact = bool(params.get("exact"))

        def _event_turn(c, e, s, _ev=event, _q=qualifier, _n=need, _who=who,
                        _exact=exact):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import TURN_EVENT_MARKER
            if not _ev:
                return False
            cid = _controller_id(c)
            pid = (3 - cid) if _who in ("OPPONENT", "ATTACKING", "ATTACKER", "DEFENDING") else cid
            marker = f"{TURN_EVENT_MARKER}{_ev}" + (f":{_q}" if _q else "")
            n = sum(1 for m in s.players[pid].current_turn_effects if m == marker)
            return n == _n if _exact else n >= _n
        return _event_turn

    # NOTE: do NOT alias this as "COMBO". That name is already handled earlier
    # (combo_check over a `names` list), and compile_condition returns on the
    # first match, so an alias here would be dead code — while a card authored
    # as {"type":"COMBO","name":"..."} would silently reach the OTHER handler,
    # whose `names` lookup misses `name` entirely and gates on an empty list.
    if ctype in ("HAND_SIZE_GTE", "HAND_SIZE_LTE", "HAND_SIZE_EQ"):
        # "unless you discard a card" must not be offered to a player with an
        # empty hand: accepting would discard nothing and dodge the penalty for
        # free. There was no hand-size condition of any kind.
        #
        #   {"type":"HAND_SIZE_GTE","amount":1}          — your hand
        #   {"type":"HAND_SIZE_LTE","amount":0,"player":"OPPONENT"}
        try:
            need = int(params.get("amount", params.get("count", 1)) or 0)
        except (TypeError, ValueError):
            need = 0
        who = (params.get("player") or "SELF").upper()

        def _hand_size(c, e, s, _n=need, _who=who, _kind=ctype):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(c)
            pid = (3 - cid) if _who in ("OPPONENT", "DEFENDING", "DEFENDER") else cid
            player = s.players.get(pid)
            if player is None:
                return False
            n = len(player.hand.cards)
            if _kind == "HAND_SIZE_LTE":
                return n <= _n
            if _kind == "HAND_SIZE_EQ":
                return n == _n
            return n >= _n
        return _hand_size

    if ctype in ("BOOST_BANISHED_IS", "ATTACK_BOOST_BANISHED_IS"):
        # "If an ITEM OR EQUIPMENT was banished from boosting this, this gets
        # +1{p}." Distinct from CARD_WAS_BOOSTED, which says only that a boost
        # happened — it cannot tell a boost that banished a weapon from one that
        # banished an action. boost() records the banished cards on the card it
        # boosted, for the same reason it records was_boosted there: a turn
        # marker cannot tell one attack's boost from another's.
        wanted = params.get("types") or params.get("card_types")
        if not wanted:
            wanted = [params.get("type_name") or params.get("card_type") or ""]
        wanted = [_norm(t) for t in wanted if t]
        on_attack = ctype.startswith("ATTACK_")

        def _boost_banished(c, e, s, _w=wanted, _atk=on_attack):
            target = c
            if _atk:
                combat = getattr(s, "combat", None)
                target = getattr(combat, "attack_card", None) if combat else None
            if target is None or not _w:
                return False
            for banished in getattr(target, "boost_banished", None) or []:
                have = {_norm(x) for x in (getattr(banished, "types", None) or [])}
                have |= {_norm(x) for x in (getattr(banished, "subtypes", None) or [])}
                if any(w in have for w in _w):
                    return True
            return False
        return _boost_banished

    if ctype in ("ATTACK_WAS_BOOSTED", "ATTACK_WAS_CHARGED",
                 "CARD_WAS_BOOSTED", "CARD_WAS_CHARGED"):
        # "The next attack you BOOST this turn gets +4{p}", "the next attack you
        # CHARGE to play this turn gets +1{p}". Which ATTACK was boosted or
        # charged cannot come from a turn marker — that records only that the
        # player did it at some point, so it would buff an attack that was
        # never boosted. boost() and charge() mark the card itself.
        attr = "was_boosted" if "BOOSTED" in ctype else "was_charged"
        # ATTACK_* asks about the attack on the chain; CARD_* about this card.
        on_attack = ctype.startswith("ATTACK_")

        def _was(c, e, s, _attr=attr, _atk=on_attack):
            target = c
            if _atk:
                combat = getattr(s, "combat", None)
                target = getattr(combat, "attack_card", None) if combat else None
            return bool(getattr(target, _attr, False))
        return _was

    if ctype in ("AMOUNT_GTE", "AMOUNT_GT", "AMOUNT_LTE", "AMOUNT_LT",
                 "AMOUNT_EQ"):
        # Compare any resolvable AMOUNT against a number:
        #
        #   "If X is 2 or more, this gets go again"          (Sonata Galaxia)
        #     {"type":"AMOUNT_GTE","amount":{"type":"X"},"value":2}
        #   "If this deals MORE THAN 3 damage, it gets go again"  (Surge)
        #     {"type":"AMOUNT_GT","amount":{"type":"LAST_DAMAGE_DEALT"},"value":3}
        #
        # Every existing comparison condition names one specific quantity
        # (HAND_SIZE_GTE, SOUL_COUNT_GTE, CHAIN_HIT_COUNT_GTE, ...), so a card
        # asking about a quantity without its own condition type had nowhere to
        # go -- and both cards above were authored against CHAIN_HIT_COUNT_GTE,
        # which counts something else entirely and made the gate fire on the
        # wrong games. This reuses _resolve_amount, so it can ask about
        # anything an effect can already use as a count.
        #
        # The source card is taken from current_effect_source() where there is
        # one, for the reason CARD_COST_EQ documents: inside an object-target
        # filter the CANDIDATE arrives as `c`, so reading X off it would give 0
        # rather than what the playing card paid.
        from engine.card_effects.dsl.effect_types import _resolve_amount as _ra
        left = params.get("amount", params.get("left"))
        right = params.get("value", params.get("amount2", params.get("right", 0)))
        op = ctype.split("_", 1)[1]

        def _amount_cmp(c, e, s, _l=left, _r=right, _op=op):
            from engine.context import current_effect_source
            source = current_effect_source() or c
            try:
                lhs = int(_ra(_l, s, source))
                rhs = int(_ra(_r, s, source))
            except (TypeError, ValueError):
                return False
            if _op == "GTE":
                return lhs >= rhs
            if _op == "GT":
                return lhs > rhs
            if _op == "LTE":
                return lhs <= rhs
            if _op == "LT":
                return lhs < rhs
            return lhs == rhs
        return _amount_cmp

    if ctype in ("CARD_COST_EQ", "CARD_COST_IS"):
        # "target aura WITH COST X from your graveyard" — an EQUALITY, and one
        # whose right-hand side belongs to the SOURCE card, not the candidate.
        # Writing it as CARD_COST_LTE + CARD_COST_GTE over {"type":"X"} does not
        # work: inside an object-target filter the candidate is passed as the
        # card argument, so _resolve_amount reads x_paid off the CARD BEING
        # TESTED (always 0) instead of the card that paid the X.
        #
        # current_effect_source() is what the interpreter pushes for exactly
        # this kind of question.
        want = params.get("amount", params.get("value", 0))

        def _cost_eq(c, e, s, _w=want):
            from engine.card_effects.dsl.effect_types import _resolve_amount
            from engine.context import current_effect_source
            source = current_effect_source() or c
            cost = getattr(c, "cost", None)
            if cost is None:
                cost = getattr(c, "raw_cost", None)
            try:
                return int(cost) == int(_resolve_amount(_w, s, source))
            except (TypeError, ValueError):
                return False
        return _cost_eq

    if ctype in ("CARD_COST_LTE", "CARD_COST_GTE", "COST_LTE", "COST_GTE",
                 "CARD_COST_LT", "CARD_COST_GT", "COST_LT", "COST_GT"):
        # THIS card's printed cost. The ATTACK_COST_* family asks about the
        # attack on the chain, which for a play-time filter is either absent or
        # a different card entirely.
        #
        # The comparison is derived from the SUFFIX. Spelling it as
        # `cost <= n if kind == "CARD_COST_LTE" else cost >= n` meant the
        # COST_LTE alias -- which is not that one string -- took the >= branch,
        # so urgent_delivery_yellow's "with cost LESS THAN OR EQUAL TO the
        # number of times you've boosted" matched exactly the expensive items
        # the text excludes. An alias that compiles but compares backwards is
        # worse than no alias: the card works, visibly, on the wrong cards.
        # LT/GT are the strict forms ("cost LESS THAN the number of Draconic
        # chain links"), which nothing could previously express.
        limit = params.get("amount", params.get("cost"))
        _op = ctype.rsplit("_", 1)[1]

        def _card_cost(c, e, s, _lim=limit, _op=_op):
            n = _numeric_amount(_lim, s, c)
            if n is None:
                return False
            cost = getattr(c, "raw_cost", None)
            if cost is None:
                cost = getattr(c, "cost", None)
            try:
                cost = int(cost or 0)
            except (TypeError, ValueError):
                cost = 0
            if _op == "LTE":
                return cost <= n
            if _op == "LT":
                return cost < n
            if _op == "GT":
                return cost > n
            return cost >= n
        return _card_cost

    if ctype in ("CARD_HAS_EFFECT", "CARD_DEALS"):
        # "The next card you play this turn WITH AN EFFECT THAT DEALS ARCANE
        # DAMAGE" — the filter is about what the card DOES, which is knowable
        # only from its own JSON. Read from the CardDef, so it holds for any
        # copy and needs no per-card list in engine code.
        #
        #   {"type":"CARD_HAS_EFFECT","effect":"DEAL_ARCANE"}
        want = str(params.get("effect") or params.get("effect_type") or "").upper()

        def _has_effect(c, e, s, _w=want):
            if not _w:
                return False
            from engine.card_effects.dsl.loader import get_card
            card_def = get_card(getattr(c, "slug", "") or "")
            if card_def is None:
                return False
            import json as _json
            for ability in card_def.abilities:
                # Nested effects (CONDITIONAL_EFFECT then/else, MAY blocks) count
                # too: a card that deals arcane damage inside a branch still has
                # an arcane damage effect.
                for eff in ability.effects:
                    if (eff.effect_type or "").upper() == _w:
                        return True
                    if _w in _json.dumps(eff.params or {}).upper():
                        return True
            return False
        return _has_effect

    if ctype in ("CARD_IS_CLASS", "CARD_IS_TALENT", "SELF_IS_CLASS",
                 "CLASS_IN"):
        # Asks about THIS card's class/talent. The ATTACK_* family asks about the
        # attack on the chain, which is a different object — using one where the
        # other is meant silently answers about the wrong card. Needed by the
        # play-time "next card you play" queue, whose filters run against the
        # card being played rather than against combat.
        # Plural spellings too: the cards that reached for CLASS_IN and
        # TalentContainsAny pass `classes` / `talents` LISTS. Reading only the
        # singular left `want` empty, which makes the condition False for every
        # card — a filter that matches nothing rather than one that matches the
        # named class.
        wants = [_norm(v) for v in _as_list(
            params, "card_class", "class", "classes", "class_in",
            "talent", "talents") if v]

        def _is_class(c, e, s, _w=wants):
            if not _w:
                return False
            have = _card_traits(c)
            return any(w in have for w in _w)
        return _is_class

    if ctype in ("CARD_IS_TYPE", "SELF_IS_TYPE", "SUBTYPE_IN", "CARD_TYPE_IN"):
        # Types AND subtypes: "Attack" is a SUBTYPE while "Action" is a type, and
        # a card naming either means the same thing by it.
        # Plural spellings too (SUBTYPE_IN passes `subtypes`). Reading only the
        # singular left `want` empty, and an empty want returns False for every
        # card — a filter matching NOTHING rather than the named type.
        #
        # CARD_TYPE_IN + `types` is the spelling three separately-authored
        # cards reached for, by analogy with ATTACK_TYPE_IN and WEAPON_SUBTYPE_IN
        # which really do exist. It is the natural name, so it is an alias here
        # rather than a correction in three card files: the next author will
        # reach for the same word, and an unknown type does not fail quietly —
        # the whole card refuses to load.
        wants = [_norm(v) for v in _as_list(
            params, "card_type", "type_name", "subtype", "subtypes",
            "card_types", "filter_types", "types") if v]

        def _is_type(c, e, s, _w=wants):
            if not _w:
                return False
            have = {_norm(x) for x in (getattr(c, "types", None) or [])}
            have |= {_norm(x) for x in (getattr(c, "subtypes", None) or [])}
            return any(w in have for w in _w)
        return _is_type

    if ctype in ("CARD_IS_POWER", "CARD_HAS_POWER", "CARD_POWER_IS"):
        # "a card with 1{p}" as a filter over CANDIDATE cards, which is a
        # different question from CARD_IN_ZONE's `power`: that one asks whether
        # such a card EXISTS in a zone (the gate), this one picks which cards
        # qualify (the cost). Rotten Remains needs both — the gate to decide
        # whether the option is offered, the filter to decide what may be
        # banished for it — and without this the filter could only be written
        # over class or type, so "with 1{p}" silently became "any card".
        #
        # Exact and bounded spellings both, because cards say "with 1{p}" as
        # often as "with 6 or more {p}".
        exact = params.get("power")
        want_gte = params.get("power_gte", exact)
        want_lte = params.get("power_lte", exact)

        def _is_power(c, e, s, _gte=want_gte, _lte=want_lte):
            if _gte is None and _lte is None:
                return False
            power = getattr(c, "power", None)
            if power is None:
                power = getattr(c, "base_power", None)
            # A card with no power at all (an equipment, a non-attack action)
            # does not have "1{p}" — it has none, which is not a number to
            # compare. Treating it as 0 would let "with 0{p}" sweep up every
            # such card.
            if power is None:
                return False
            try:
                power = int(power)
            except (TypeError, ValueError):
                return False
            if _gte is not None and power < int(_gte):
                return False
            if _lte is not None and power > int(_lte):
                return False
            return True
        return _is_power

    if ctype in ("CARD_IS_FACE_DOWN", "CARD_IS_FACE_UP"):
        # "a FACE DOWN arrow in your arsenal". The one card that needed this
        # wrote REF_PITCH_IS with pitch "face_up" — a condition about PITCH
        # COLOUR, which is never the string "face_up", so it was false for
        # every card and the filter matched nothing.
        want_down = ctype.endswith("DOWN")

        def _face(c, e, s, _down=want_down):
            down = bool(getattr(c, "face_down", False))
            if not down and getattr(c, "is_public", None) is False:
                # Arsenal and banished-face-down track visibility via is_public;
                # face_down is not set on every path that hides a card.
                down = True
            return down is _down
        return _face

    if ctype in ("REF_HAS_COUNTER", "REF_COUNTER_GTE"):
        # "Sharpen target sword. IF IT HAS 1 or more +1{p} counters, ..." — a
        # counter test on the object a preceding effect stored, not on the
        # source card. HAS_COUNTER reads the source, which for Sharp Incline is
        # the action card itself and never carries power counters, so the gate
        # was false whatever the sword looked like.
        kind = (params.get("counter") or params.get("counter_type")
                or params.get("kind") or "power")
        ref = params.get("ref", "sharpened")
        threshold = params.get("amount", params.get("value", 1))

        def _ref_counter(c, e, s, _ct=kind, _r=ref, _n=threshold):
            from engine.context import get_ref
            target = get_ref(_r)
            if isinstance(target, list):
                target = target[-1] if target else None
            if target is None:
                return False
            have = (getattr(target, "counters", None) or {}).get(_ct, 0) or 0
            try:
                return have >= int(_n)
            except (TypeError, ValueError):
                return False
        return _ref_counter

    if ctype == "HAS_COUNTER":
        # "all equipment they control WITH -1{d} counters" — presence, not a
        # threshold. COUNTER_GTE with amount 1 says the same thing, but the
        # cards say "with X counters" and reading that spelling is what stops
        # the next author inventing a third one.
        kind = (params.get("counter") or params.get("counter_type")
                or params.get("kind") or "")

        def _has_counter(c, e, s, _ct=kind):
            if not _ct:
                return False
            return ((getattr(c, "counters", None) or {}).get(_ct, 0) or 0) > 0
        return _has_counter

    if ctype in ("HAS_BASE_DEFENSE", "NO_BASE_DEFENSE"):
        # "choose a card WITHOUT BASE {d}" — an attack action with no printed
        # defence, not one whose defence is low. BASE_DEFENSE_LTE cannot say it:
        # a card with no {d} has base_defense None, which that condition treats
        # as missing and falls back to the current defence.
        #
        # The one card that needs it wrote ATTACK_HAS_KEYWORD keyword
        # "BASE_DEFENSE" — there is no such keyword, so the test was false for
        # every card in the game.
        want = ctype == "HAS_BASE_DEFENSE"
        if "value" in params:
            want = bool(params.get("value"))

        def _has_base_def(c, e, s, _w=want):
            base = getattr(c, "base_defense", None)
            if base is None:
                base = getattr(c, "raw_defense", None)
            return (base is not None) is _w
        return _has_base_def

    if ctype in ("BASE_DEFENSE_LTE", "BASE_DEFENSE_GTE"):
        # "a Guardian off-hand you control with 2 or less base {d}" — the
        # PRINTED defence, not the current one, so counters already on the card
        # do not change whether it is a legal target.
        #
        # BASE_DEFENSE_LTE was the only invented condition type in the corpus.
        # It went unnoticed because it sat nested inside an effect's "target"
        # dict, where conditions are never compiled — so the type name was
        # never looked up and the usual load-time failure never fired.
        threshold = params.get("amount", params.get("value", 0))
        want_lte = ctype.endswith("LTE")

        def _base_def(c, e, s, _n=threshold, _lte=want_lte):
            from engine.card_effects.dsl.effect_types import _resolve_amount
            base = getattr(c, "base_defense", None)
            if base is None:
                base = getattr(c, "defense", None)
            try:
                base = int(base)
                limit = int(_resolve_amount(_n, s, c))
            except (TypeError, ValueError):
                return False
            return base <= limit if _lte else base >= limit
        return _base_def

    if ctype in ("DEFENSE_LTE", "DEFENSE_GTE"):
        # "When this defends, IF IT HAS 6 OR MORE {d}" — the CURRENT defence,
        # counters and pumps included, which is the whole point of a card whose
        # own text can push it over the line. The card that needed this wrote
        # COUNTER_GTE counter:"DEFENSE" amount:6, which asks for six DEFENCE
        # COUNTERS — a number that is zero on a fresh card and only ever goes
        # up when something DEBUFFS it, so the gate was false exactly when the
        # card is strong and could only become true by being weakened.
        threshold = params.get("amount", params.get("value", 0))
        want_lte = ctype.endswith("LTE")

        def _cur_def(c, e, s, _n=threshold, _lte=want_lte):
            from engine.card_effects.dsl.effect_types import _resolve_amount
            value = getattr(c, "defense", None)
            if value is None:
                value = getattr(c, "base_defense", None)
            try:
                value = int(value)
                limit = int(_resolve_amount(_n, s, c))
            except (TypeError, ValueError):
                return False
            return value <= limit if _lte else value >= limit
        return _cur_def

    if ctype in ("CARD_IS_ATTACK", "SELF_IS_ATTACK"):
        # "the next NON-ATTACK action card you play" — value:false is the whole
        # point of the card, so the flag is read rather than assumed True.
        want = params.get("value", True)

        def _is_attack(c, e, s, _w=want):
            return bool(getattr(c, "is_attack", False)) is bool(_w)
        return _is_attack

    if ctype in ("CARD_IS_COLOR", "CARD_IS_COLOUR", "SELF_IS_COLOR"):
        # "the next BLUE card you play this turn". Colour is pitch value 1/2/3
        # (red/yellow/blue) unless the card carries an explicit colour, and the
        # card's own colour had no condition of its own — CARD_IN_ZONE could
        # filter a ZONE by colour, which is a different question.
        want = _norm(params.get("color") or params.get("colour") or "")
        _PITCH_COLOR = {1: "red", 2: "yellow", 3: "blue"}

        def _is_color(c, e, s, _w=want):
            if not _w:
                return False
            colour = (getattr(c, "color", None)
                      or _PITCH_COLOR.get(getattr(c, "pitch", None)))
            return _norm(colour or "") == _w
        return _is_color

    if ctype in ("WAS_RUNE_GATED", "IS_RUNE_GATED"):
        # CR 8.3.27a — "the next attack action card you RUNE GATE this turn".
        # A property of the card that was played, stamped by play.py, so a
        # next-attack filter can ask it of the attack card it is offered.
        def _rune_gated(c, e, s):
            return bool(getattr(c, "rune_gated", False))
        return _rune_gated

    if ctype == "REACTION_THIS_LINK":
        # "the attacking hero has played or ACTIVATED an attack reaction THIS
        # CHAIN LINK" (Hunted or Hunter). Chain-link scope is the whole point:
        # a turn-scoped record would let a reaction from the first attack of the
        # turn keep answering yes for every later attack.
        #
        #   {"type":"REACTION_THIS_LINK","kind":"attack_reaction","player":"ATTACKING"}
        kind = _norm(params.get("kind") or params.get("reaction") or "")
        who = (params.get("player") or "SELF").upper()

        def _reaction_link(c, e, s, _k=kind, _who=who):
            from engine.card_effects.ability_keywords import _controller_id
            combat = getattr(s, "combat", None)
            if combat is None:
                return False
            cid = _controller_id(c)
            if _who in ("ATTACKING", "ATTACKER"):
                pid = combat.attacker_id
            elif _who in ("DEFENDING", "DEFENDER"):
                pid = 3 - combat.attacker_id
            elif _who == "OPPONENT":
                pid = 3 - cid
            else:
                pid = cid
            for entry_pid, entry_kind in getattr(combat, "reactions_this_link", []):
                if entry_pid != pid:
                    continue
                if _k and _norm(entry_kind) != _k:
                    continue
                return True
            return False
        return _reaction_link

    if ctype in ("TARGET_HERO_CLASS_IN", "OPPOSING_HERO_CLASS_IN"):
        # "When this hits a Runeblade or Wizard HERO" — the class of the hero
        # being attacked, not of the attack. ATTACK_CLASS_IN is the nearest
        # existing condition and reads the ATTACK card's classes, so using it
        # here would ask whether the arrow itself is a Runeblade card.
        #
        #   {"type":"TARGET_HERO_CLASS_IN","classes":["Runeblade","Wizard"]}
        want = [_norm(v) for v in (params.get("classes")
                                   or params.get("class_names") or []) if v]

        def _target_hero_class(c, e, s, _w=want):
            from engine.card_effects.ability_keywords import _controller_id
            if not _w:
                return False
            combat = getattr(s, "combat", None)
            if combat is None:
                return False
            # The hero on the receiving end of the attack.
            defender_id = 3 - combat.attacker_id
            hero = s.players[defender_id].hero if defender_id in s.players else None
            if hero is None:
                return False
            have = {_norm(x) for x in (getattr(hero, "classes", None) or [])}
            have |= {_norm(x) for x in (getattr(hero, "talents", None) or [])}
            return any(w in have for w in _w)
        return _target_hero_class

    if ctype in ("SELF_IN_ZONE", "THIS_IN_ZONE"):
        # "Activate this only while this is face-up in your arsenal."
        # CARD_IN_ZONE counts ANY card in the zone, so it answers "is your
        # arsenal non-empty" — true whenever the card is there, and true just as
        # often when it is not. A restriction on THIS card needs its own check.
        #
        #   {"type":"SELF_IN_ZONE","zone":"arsenal","face_up":true}
        want_zone = _norm(params.get("zone") or "")
        face_up = params.get("face_up")

        def _self_in_zone(c, e, s, _z=want_zone, _fu=face_up):
            if _z and _norm(getattr(c, "zone", "") or "") != _z:
                return False
            if _fu is not None and bool(getattr(c, "is_public", False)) is not bool(_fu):
                return False
            return True
        return _self_in_zone

    if ctype == "MELD_SIDE":
        # CR 8.3.38 Meld: one card, two halves, played as top / bottom / both.
        # The engine already resolves which was chosen and stamps card.meld_side
        # at play; the DSL had no way to ASK, so a meld card's two sides were
        # authored as two unconditional PLAY abilities and both always fired.
        #
        #   {"type":"MELD_SIDE","side":"top"}   — also true when 'both' is played
        want = _norm(params.get("side") or "")

        def _meld_side(c, e, s, _want=want):
            side = _norm(getattr(c, "meld_side", "") or "")
            if not _want:
                return bool(side)
            # Playing "both" plays each half, so each half's ability applies.
            return side == _want or side == "both"
        return _meld_side

    if ctype in ("CARD_IS_NAMED", "CARD_NAME_IN", "SAME_NAME"):
        # The candidate card's own name — the per-card counterpart of
        # ATTACK_NAME_IN, which reads combat.attack_card and so cannot answer
        # "is THIS card a Swift Shot" in a play-time filter. Matches on name or
        # slug, and strips the colour suffix so one entry covers every printing.
        import re as _re
        wants = {_norm(v) for v in _as_list(params, "names", "name", "card_name")
                 if v}

        def _named(c, e, s, _w=wants):
            if not _w:
                return False
            slug = _re.sub(r'_(red|yellow|blue)$', '', getattr(c, 'slug', '') or '')
            return (_norm(slug) in _w
                    or _norm(getattr(c, 'name', '') or '') in _w)
        return _named

    if ctype in ("PLAYED_FROM_ZONE", "PLAYED_FROM"):
        # "You may play Rift Bind from your banished zone. IF YOU DO, it gains
        # +X{p}." The conditional half cannot be a CARD_IN_ZONE check: the card
        # has already left that zone by the time its play ability resolves, so
        # such a check is false for every card in the game. play.py stamps the
        # source zone on the card just before the move.
        #
        #   {"type":"PLAYED_FROM_ZONE","zone":"banished"}
        want = _norm(params.get("zone") or params.get("from_zone") or "")

        def _played_from(c, e, s, _want=want):
            if not _want:
                return False
            if _norm(getattr(c, "played_from_zone", "") or "") == _want:
                return True
            # EQUIPPING is not playing, so play.py never stamps played_from_zone
            # for it — but "when this is equipped from anywhere other than your
            # graveyard" still has to know where it came from. Zone.add keeps
            # prev_zone for every move, which covers equips. Same fallback
            # PLAYED_FROM_ARSENAL uses, and for the same reason.
            return _norm(getattr(c, "prev_zone", "") or "") == _want
        return _played_from

    if ctype == "LAST_CHAIN_ATTACK":
        # "Combo - If Surging Strike was the last attack this combat chain, ...",
        # "If a Draconic attack was the last attack this combat chain, ...",
        # "If the last attack on this combat chain hit, ...".
        #
        #   {"type":"LAST_CHAIN_ATTACK","name":"Surging Strike"}
        #   {"type":"LAST_CHAIN_ATTACK","talent":"Draconic"}
        #   {"type":"LAST_CHAIN_ATTACK","hit":true}
        #
        # ChainLink already captures attack_slug/hit/talents/classes/subtypes at
        # link close, and a link is appended AFTER its damage resolves, so during
        # a new attack chain_links[-1] IS the previous attack. Cards each invented
        # a private flag for this (SURGING_STRIKE_LAST_ATTACK, LEG_TAP_LAST_ATTACK,
        # LAST_ATTACK_WAS_DRACONIC, ...), none of which anything ever set.
        #
        # `name` matches the card NAME as printed, which spans colour variants —
        # "Surging Strike" must match surging_strike_red/yellow/blue — so it is
        # compared against the slug with any colour suffix stripped, and against
        # the resolved card name.
        want_name = _norm(params.get("name") or params.get("card_name") or "")
        want_talent = _norm(params.get("talent") or "")
        want_class = _norm(params.get("class") or params.get("card_class") or "")
        want_subtype = _norm(params.get("subtype") or "")
        want_hit = params.get("hit")

        def _last_chain(c, e, s, _n=want_name, _t=want_talent, _c=want_class,
                        _st=want_subtype, _h=want_hit):
            links = getattr(s, "chain_links", None) or []
            if not links:
                return False
            link = links[-1]
            if _h is not None and bool(link.hit) is not bool(_h):
                return False
            if _t and _t not in {_norm(x) for x in (link.talents or [])}:
                return False
            if _c and _c not in {_norm(x) for x in (link.classes or [])}:
                return False
            if _st and _st not in {_norm(x) for x in (link.subtypes or [])}:
                return False
            if _n:
                slug = str(getattr(link, "attack_slug", "") or "")
                names = {_norm(slug)}
                # Strip a trailing colour so "Surging Strike" matches every
                # printing of the card rather than only the red one.
                base = re.sub(r"_(red|yellow|blue)$", "", slug)
                names.add(_norm(base))
                db = getattr(s, "card_db", None)
                if db is not None:
                    card = db.get(slug)
                    if card is not None and getattr(card, "name", None):
                        names.add(_norm(card.name))
                if _n not in names:
                    return False
            # A bare {"type":"LAST_CHAIN_ATTACK"} asks only that an attack
            # preceded this one on the chain, which the empty-links check above
            # already established.
            return True
        return _last_chain

    if ctype in ("DESTROYED_THIS_TURN", "HAS_DESTROYED_THIS_TURN"):
        # "if you have destroyed a <thing> this turn" — one generic condition
        # taking the thing's name, replacing the per-card flags cards invented
        # (MIGHT_TOKEN_DESTROYED_THIS_TURN, ITEM_DESTROYED_THIS_TURN, ...), none
        # of which anything ever set. The name matches a slug, a type or a
        # subtype: "might", "item", "aura", "lightning flow".
        #
        # `player` picks whose destruction counts — SELF (default), or OPPONENT
        # for "if the attacking hero has destroyed ...".
        want = _norm(params.get("name") or params.get("card_name")
                     or params.get("subtype") or params.get("card_type") or "")
        who = (params.get("player") or "SELF").upper()

        def _dtt(c, e, s, _w=want, _who=who):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import DESTROYED_MARKER
            if not _w:
                return False
            cid = _controller_id(c)
            pid = (3 - cid) if _who in ("OPPONENT", "ATTACKING", "ATTACKER") else cid
            return f"{DESTROYED_MARKER}{_w}" in s.players[pid].current_turn_effects
        return _dtt

    if ctype == "IS_BOOED":
        # True if the controller has been booed this turn.
        def _ib(c, e, s):
            from engine.card_effects.ability_keywords import has_been_booed, _controller_id
            return has_been_booed(s, _controller_id(c))
        return _ib

    if ctype in ("IS_CHEERED", "HAS_BEEN_CHEERED"):
        # "If you've been cheered this turn" — reads the shared cheer state, so
        # a cheer from ANY source counts. Cards used to test their own private
        # SET_FLAG, which only ever saw cheers they caused themselves.
        def _ic(c, e, s):
            from engine.card_effects.ability_keywords import has_been_cheered, _controller_id
            return has_been_cheered(s, _controller_id(c))
        return _ic

    if ctype == "OPPONENT_IS_MARKED":
        # True if the opponent hero is currently marked.
        def _oim(c, e, s):
            from engine.card_effects.ability_keywords import _controller_id
            opp = 3 - _controller_id(c)
            return s.players[opp].class_counters.get("marked", 0) > 0
        return _oim

    if ctype == "CONTROLS_TOKEN_TYPE":
        # True if the controller has >= `amount` permanents of the given token OR
        # permanents that "count as" it (matched via subtype, e.g. Aurum Aegis
        # counts as a Gold). Searches all permanents (a Gold token is an Item
        # sub-zone member, not the Token sub-zone) plus equipment/weapon slots.
        #
        # Cards author the token under EITHER "token" (a slug) or "token_type" (a
        # display name like "Seismic Surge"); previously only "token" was read, so
        # every card using "token_type" (the large majority) had a permanently
        # false condition. Read both and normalise the display name to a slug.
        # Also accepts a "token_types" LIST (match ANY of them).
        _raws = [params.get("token"), params.get("token_type"),
                 params.get("subtype"), params.get("name")]
        _raws += list(params.get("token_types") or [])
        wants = []  # (slug, display) pairs
        for r in _raws:
            if r:
                d = str(r).strip().lower()
                wants.append((d.replace(" ", "_"), d))
        try:
            need = int(params.get("amount", 1))
        except (TypeError, ValueError):
            need = 1
        # "if you control LESS Gold than an opponent" compares the two players'
        # counts instead of a fixed threshold: `opponent` switches to that
        # comparison and `comparison` picks the operator. Both were ignored, so
        # such a card fired whenever it controlled any of the token at all —
        # roughly the opposite of what it says.
        comparison = _norm(params.get("comparison") or "gte")
        vs_opponent = bool(params.get("opponent"))

        def _count_for(player, _wants):
            count = 0
            for zone_name in ('permanents', 'head', 'chest', 'arms', 'legs',
                              'weapon1', 'weapon2'):
                zone = getattr(player, zone_name, None)
                if not zone:
                    continue
                for t in zone.cards:
                    slug = getattr(t, 'slug', '')
                    subs = [st.lower() for st in (getattr(t, 'subtypes', None) or [])]
                    subs_slug = [st.replace(" ", "_") for st in subs]
                    if any(slug == ws or wd in subs or ws in subs_slug
                           for ws, wd in _wants):
                        count += 1
            return count

        _OPS = {
            "gte": lambda a, b: a >= b, "gt": lambda a, b: a > b,
            "lte": lambda a, b: a <= b, "lt": lambda a, b: a < b,
            "eq": lambda a, b: a == b, "neq": lambda a, b: a != b,
        }

        # "while THEY control a Frostbite" — the count is about the OPPONENT,
        # not the source's controller. Without this the only readings available
        # were "I control N" and the vs_opponent comparison.
        _whose = str(_first_present(params, "player", "controller",
                                    default="SELF")).upper()

        def _ctt(c, e, s, _wants=wants, _n=need, _cmp=comparison, _vs=vs_opponent,
                 _w=_whose):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(c)
            if _w in ("OPPONENT", "THEM", "DEFENDING", "DEFENDER"):
                cid = 3 - cid
            mine = _count_for(s.players[cid], _wants)
            other = _count_for(s.players[3 - cid], _wants) if _vs else _n
            return _OPS.get(_cmp, _OPS["gte"])(mine, other)
        return _ctt

    if ctype in ("CONTROLS_FROZEN_PERMANENT", "CONTROLS_FROZEN"):
        # "... or a FROZEN PERMANENT". Frozen-ness lives on the object as a
        # counter, so this is the only way to ask about it; there was no
        # condition for it at all, and the card that needs it had authored
        # CONTROLS_TOKEN_TYPE "FROZEN" — not a token type.
        who = str(_first_present(params, "player", "controller",
                                 default="SELF")).upper()

        def _cfp(c, e, s, _w=who):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.play import CONTINUOUS_FREEZE
            cid = _controller_id(c)
            if _w in ("OPPONENT", "THEM", "DEFENDING", "DEFENDER"):
                cid = 3 - cid
            player = s.players.get(cid)
            if player is None:
                return False
            for obj in player.arena_cards:
                counters = getattr(obj, "counters", None) or {}
                if counters.get("__frozen__", 0) > 0 or counters.get(CONTINUOUS_FREEZE, 0) > 0:
                    return True
            return False
        return _cfp

    if ctype in ("CONTROLS_CHAIN_LINKS", "CHAIN_LINKS_CONTROLLED_GTE"):
        # "control N or more chain links you control", optionally restricted to
        # links whose ATTACK matches a variable `attribute` — a talent, class,
        # subtype, or keyword (case-insensitive), e.g. attribute:"Draconic" for
        # "2 or more Draconic chain links". Omit `attribute` to count every chain
        # link you control. Each ChainLink stores its attack's talents/classes/
        # subtypes/keywords at creation, so no per-link card lookup is needed.
        try:
            amount = int(params.get("amount", 1))
        except (TypeError, ValueError):
            amount = 1
        attribute = (params.get("attribute") or params.get("talent")
                     or params.get("class") or params.get("subtype") or "").lower()
        def _ccl(c, e, s, _n=amount, _attr=attribute):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(c)
            links = [lk for lk in (getattr(s, "chain_links", None) or [])
                     if getattr(lk, "attacker_id", None) == cid]

            # THE ATTACK ON THE CHAIN RIGHT NOW IS A CHAIN LINK TOO. CR 7.0.3a:
            # an attack added to the combat chain becomes the active-attack of
            # chain link N+1, and 7.0.3c gives that link the active-attack's own
            # properties and control. state.chain_links only receives the link
            # AFTER damage resolves, so counting that list alone misses the live
            # attack and every threshold reads one low.
            #
            # phoenix_flame_red is the proof: it is itself Draconic, so "2 or
            # more Draconic chain links" needs one PRIOR Draconic link plus
            # itself. Against the spectator corpus it agreed on 104 of 480
            # attacks, and all 376 disagreements were ours=0 theirs=1 -- one
            # short, every time.
            #
            # Guarded against double counting: once damage has resolved the
            # active attack IS in chain_links, under the same chainlink_id,
            # while state.combat is still set until the chain closes. The guard
            # matches on id AND slug, not id alone -- a reconstructed board can
            # number its links from 1 while the harness gives the live attack
            # link_id 1 too, and on id alone that reads as "already counted"
            # and silently drops the live attack again.
            combat = getattr(s, "combat", None)
            attack_card = getattr(combat, "attack_card", None) if combat else None
            already = any(
                getattr(lk, "chainlink_id", None) == getattr(combat, "link_id", None)
                and getattr(lk, "attack_slug", None) == getattr(attack_card, "slug", None)
                for lk in links) if attack_card is not None else True
            if (attack_card is not None
                    and getattr(combat, "attacker_id", None) == cid
                    and not already):
                links = links + [attack_card]

            if not _attr:
                return len(links) >= _n
            count = 0
            for lk in links:
                attrs = []
                # A ChainLink stores these captured at creation; the live attack
                # is a Card and carries the same field names, so one loop reads
                # both. `keywords` is absent on a Card mid-attack, which is why
                # getattr defaults rather than indexing.
                for fld in ("talents", "classes", "subtypes", "keywords"):
                    attrs += [str(x).lower() for x in (getattr(lk, fld, None) or [])]
                if _attr in attrs:
                    count += 1
            return count >= _n
        return _ccl

    if ctype == "CONTROLS_SUBTYPE":
        # True if the controller controls a permanent with the given subtype
        # (e.g. "an aura you control"). Used to gate a MAY block so a
        # "destroy an aura … if you do …" clause is only offered when there is
        # a legal target.
        want = (params.get("subtype", "") or "").lower()
        # "if you control ANOTHER Illusionist aura" needs all three of these:
        # the class, a count, and — critically — excluding the card asking.
        # Without exclude_self, Sigil of Solitude sees ITSELF and destroys
        # itself at the start of every turn.
        want_class = (params.get("card_class") or params.get("class") or "").lower()
        exclude_self = bool(params.get("exclude_self") or params.get("another"))
        try:
            need = int(params.get("count", 1) or 1)
        except (TypeError, ValueError):
            need = 1

        def _csub(c, e, s, _w=want, _cls=want_class, _x=exclude_self, _n=need):
            from engine.card_effects.ability_keywords import _controller_id
            perms = s.players[_controller_id(c)].permanents.cards
            n = 0
            for p in perms:
                if _x and p is c:
                    continue
                if _w and _w not in [st.lower() for st in (getattr(p, "subtypes", None) or [])]:
                    continue
                if _cls and _cls not in [cl.lower() for cl in (getattr(p, "classes", None) or [])]:
                    continue
                n += 1
            return n >= _n
        return _csub

    if ctype == "ATTACK_HAS_KEYWORD":
        # Normalise separators so "go_again", "go again" and "Go Again" all
        # match — combat.keywords stores the title-cased form ("Go Again") while
        # JSON often writes the snake_case token. Lair of the Spider never fired
        # because "go_again" != "go again" under a plain lower() comparison.
        kw = _norm(params.get("keyword", ""))
        def _ahk(c, e, s, _kw=kw):
            if not s.combat:
                return False
            return _kw in [_norm(k) for k in (s.combat.keywords or [])]
        return _ahk

    # ── boolean combinators ────────────────────────────────────────────────
    # Sub-conditions are authored under "any"/"all" but very often as
    # "conditions" (54 usages). Reading only the former silently produced an
    # EMPTY list, and an empty combinator does not fail loudly — it collapses:
    # any([]) is False, so the OR could never fire and its whole ability was
    # dead; all([]) is True, so the AND removed the gate it was meant to
    # enforce. Reading both is the fix; note the invalid inner types went
    # unvalidated too, because nothing ever compiled them.
    if ctype in ("OR", "AND"):
        specs = (params.get("any" if ctype == "OR" else "all")
                 or params.get("conditions") or [])
        sub_conds = [compile_condition(sc.get("type", "none"), sc) for sc in specs]
        combine = any if ctype == "OR" else all

        def _combine(c, e, s, _subs=sub_conds, _fn=combine):
            if not _subs:
                # An empty combinator is an authoring error, not a truth value.
                # Treat it as no restriction rather than silently killing the
                # ability (OR) or silently passing a gate (AND) — the loader
                # surfaces the real problem via the unknown inner type.
                return True
            return _fn((fn is None or fn(c, e, s)) for fn in _subs)
        return _combine

    if ctype in ("SCRAPPED", "HAS_SCRAPPED"):
        # CR 8.3.32 — "if it scrapped a card". Note "IT", not "you": the check is
        # whether THIS card paid its scrap cost when played, so the marker is
        # keyed by the card's own slug rather than a bare "player scrapped this
        # turn" flag, which would also fire for a different scrap card.
        #
        # `name` overrides the slug for the rare card asking about another
        # ("if it scrapped a Hyper Driver" asks what was scrapped — see
        # speed_demon_red, which needs the SCRAPPED CARD's identity and is not
        # expressible with this alone).
        want = _norm(params.get("name") or params.get("slug") or "")

        def _scrapped(c, e, s, _w=want):
            from engine.card_effects.ability_keywords import _controller_id
            from engine.effect_keywords import TURN_EVENT_MARKER
            ident = _w or _norm(getattr(c, "slug", "") or "")
            if not ident:
                return False
            pid = _controller_id(c)
            return f"{TURN_EVENT_MARKER}scrap:{ident}" in s.players[pid].current_turn_effects
        return _scrapped

    if ctype in ("SOUL_COUNT_GTE", "SOUL_COUNT"):
        # "If the defending hero has 1 or more cards in their soul" (Soul Cleaver).
        # player.soul is a real zone, so this is a count over existing state.
        # `player`: DEFENDING (default here, since that is how the cards word it)
        # / SELF / OPPONENT.
        try:
            need = int(params.get("amount", params.get("count", 1)) or 1)
        except (TypeError, ValueError):
            need = 1
        who = (params.get("player") or "DEFENDING").upper()

        def _soul(c, e, s, _n=need, _who=who):
            from engine.card_effects.ability_keywords import _controller_id
            cid = _controller_id(c)
            pid = (3 - cid) if _who in ("DEFENDING", "OPPONENT", "DEFENDER") else cid
            player = s.players.get(pid)
            if player is None:
                return False
            return len(player.soul.cards) >= _n
        return _soul

    if ctype == "ATTACK_TARGET_IS_HERO":
        # "When this attacks A HERO" — false when the attack was declared
        # against a permanent or ally. combat.attack_target is set only for
        # those, so a hero attack leaves it None.
        # "hero_type" narrows it to a hero of a given class or talent ("when
        # this attacks a Revered hero"); ignoring it fired against any hero.
        hero_type = _norm(params.get("hero_type") or "")

        def _atk_hero(c, e, s, _ht=hero_type):
            combat = s.combat
            if combat is None or getattr(combat, "attack_target", None) is not None:
                return False
            if not _ht:
                return True
            defender = s.players.get(3 - combat.attacker_id)
            hero = getattr(defender, "hero", None)
            return hero is not None and _ht in _card_traits(hero)
        return _atk_hero

    if ctype == "REF_PITCH_IS":
        # Test the pitch value of a card a previous effect stored under "ref".
        # Pitch 1 = red, 2 = yellow, 3 = blue — so "if it's red" becomes a
        # condition on a referenced card rather than something baked into a
        # card-specific effect.
        ref = params.get("ref", "looked")
        # Cards author the COLOUR ("yellow") as readily as the pitch number, and
        # "color" was not read — so those nodes silently fell back to pitch 1
        # and tested red. Colour is the more natural spelling given the text
        # says "if it's a blue card", so it must not be the one that is dropped.
        _COLOR_PITCH = {"red": 1, "yellow": 2, "blue": 3}
        want = params.get("pitch")
        if want is None:
            want = _COLOR_PITCH.get(_norm(params.get("color")
                                          or params.get("colour") or ""), 1)

        def _ref_pitch(c, e, s, _r=ref, _w=want):
            from engine.context import get_ref
            target = get_ref(_r)
            # Refs that name one card are still STORED as a list by the effects
            # that set them (REVEAL_TOP_DECK always stores a list). Refusing a
            # one-element list made "reveal the top card, if it's yellow" answer
            # False no matter what was revealed.
            if isinstance(target, list):
                if len(target) != 1:
                    return False
                target = target[0]
            if target is None:
                return False
            return (getattr(target, "pitch", None) or 0) == _w
        return _ref_pitch

    if ctype == "REF_HAS_KEYWORD":
        # "If THAT CARD has watery grave, this gets overpower" — a question
        # about the card a previous effect stored, not about the source. The
        # REF_* family could already ask a ref's type, cost, power, defense and
        # counters, but not its keywords, so a card whose payoff turns on a
        # printed keyword had no way to ask.
        #
        #   {"type":"REF_HAS_KEYWORD","ref":"burly_card","keyword":"watery grave"}
        #
        # Matching is normalised the way the engine compares keywords
        # everywhere else, so the card DB's "WateryGrave" answers to the
        # printed "watery grave".
        from engine.card_effects.dsl.loader import _kw_key
        ref = params.get("ref", "looked")
        wanted = [_kw_key(str(k)) for k in _as_list(params, "keyword", "keywords")
                  if str(k).strip()]

        def _ref_has_kw(c, e, s, _r=ref, _w=wanted):
            from engine.context import get_ref
            target = get_ref(_r)
            if not target or not _w:
                return False
            for obj in (target if isinstance(target, list) else [target]):
                have = {_kw_key(str(k)) for k in (getattr(obj, "keywords", None) or [])}
                if have & set(_w):
                    return True
            return False
        return _ref_has_kw

    if ctype in ("REF_IS_TYPE", "REF_TYPE_IS"):
        # Test the TYPE of a card a previous effect stored under "ref" —
        # "whenever this banishes a REACTION or INSTANT card", "a NON-ATTACK
        # ACTION card". Types and subtypes both count, as CARD_IS_TYPE does,
        # because "Action" is a type while "Attack" is a subtype and cards use
        # either word for the same idea.
        #
        # `value: false` inverts it, which is what "non-attack" needs; writing
        # that as a NOT around this condition works too, but the cards say
        # "non-X" as one word and reading it here keeps them literal.
        wanted = params.get("types") or params.get("card_types")
        if not wanted:
            wanted = [params.get("type_name") or params.get("card_type")
                      or params.get("subtype") or ""]
        wanted = [_norm(t) for t in wanted if t]
        ref = params.get("ref", "banished")
        want_match = params.get("value", True)

        def _ref_type(c, e, s, _r=ref, _w=wanted, _v=want_match):
            from engine.context import get_ref
            target = get_ref(_r)
            if isinstance(target, list):
                target = target[-1] if len(target) == 1 else (target[-1] if target else None)
            if target is None or not _w:
                return False
            have = {_norm(x) for x in (getattr(target, "types", None) or [])}
            have |= {_norm(x) for x in (getattr(target, "subtypes", None) or [])}
            # "non-attack ACTION" is two claims: it IS an action and is NOT an
            # attack. A bare list would read as "any of these", so the negated
            # form requires every named type to be absent.
            hit = any(w in have for w in _w)
            return hit is bool(_v)
        return _ref_type

    if ctype in ("REF_CONTAINS_TYPE", "REF_ANY_IS_TYPE"):
        # "If you reveal an attack action card AND a non-attack action card this
        # way" — a question about the SET a previous effect stored, not about
        # one card in it.
        #
        # REF_IS_TYPE cannot answer it: handed a list it collapses to the last
        # entry, so on a two-card reveal it tests one card twice and the other
        # never. That is invisible from the card's side, which is how Tome of
        # the Arknight came to gate on two conditions that between them looked
        # at half of what it revealed.
        wanted = params.get("types") or params.get("card_types")
        if not wanted:
            wanted = [params.get("type_name") or params.get("card_type")
                      or params.get("subtype") or ""]
        wanted = [_norm(t) for t in wanted if t]
        ref = params.get("ref", "revealed")
        # value: false asks for a card matching NONE of them — "a non-attack
        # action card" is `types: ["Action"]` plus `not_types: ["Attack"]`,
        # which is two claims about the SAME card and so cannot be two nodes.
        not_types = [_norm(t) for t in (params.get("not_types")
                                        or params.get("not_type")
                                        or ([params["not_subtype"]]
                                            if params.get("not_subtype") else [])
                                        ) if t]

        def _ref_contains(c, e, s, _r=ref, _w=wanted, _n=not_types):
            from engine.context import get_ref
            pool = get_ref(_r)
            if pool is None:
                return False
            if not isinstance(pool, list):
                pool = [pool]
            for obj in pool:
                if obj is None:
                    continue
                have = {_norm(x) for x in (getattr(obj, "types", None) or [])}
                have |= {_norm(x) for x in (getattr(obj, "subtypes", None) or [])}
                if _w and not any(w in have for w in _w):
                    continue
                if _n and any(t in have for t in _n):
                    continue
                return True
            return False
        return _ref_contains

    if ctype in ("REF_POWER_GTE", "REF_POWER_LTE"):
        # "If a card with 6 or more {p} is banished this way" — a power test on
        # what a preceding effect or COST stored, not on the source card. Any
        # entry in a list ref satisfies it, since the text asks whether such a
        # card was among them.
        threshold = params.get("amount", params.get("value", 0))
        ref = params.get("ref", "banished_cards")
        want_gte = ctype.endswith("GTE")

        def _ref_power(c, e, s, _r=ref, _n=threshold, _gte=want_gte):
            from engine.context import get_ref
            found = get_ref(_r)
            if found is None:
                return False
            pool = found if isinstance(found, list) else [found]
            try:
                limit = int(_n)
            except (TypeError, ValueError):
                return False
            for obj in pool:
                power = getattr(obj, "power", None)
                if power is None:
                    power = getattr(obj, "base_power", None)
                if power is None:
                    continue
                if (power >= limit) if _gte else (power <= limit):
                    return True
            return False
        return _ref_power

    if ctype in ("REF_DEFENSE_LTE", "REF_DEFENSE_GTE"):
        # "put a -1{d} counter on an equipment they control. THEN IF IT HAS
        # 0{d}, destroy it." The test is on the object the previous effect acted
        # on, not on the source card — the only card that authored it wrote
        # COUNTER_GTE 0 against the source, which is true for every card at all
        # times, so the destroy half fired unconditionally.
        #
        # Reads the CURRENT {d}, which is where the counter it just took shows
        # up; base_defense is the printed value and would never reach 0.
        threshold = params.get("amount", params.get("value", 0))
        ref = params.get("ref", "countered")
        want_gte = ctype.endswith("GTE")

        def _ref_defense(c, e, s, _r=ref, _n=threshold, _gte=want_gte):
            from engine.context import get_ref
            found = get_ref(_r)
            if found is None:
                return False
            pool = found if isinstance(found, list) else [found]
            try:
                limit = int(_n)
            except (TypeError, ValueError):
                return False
            for obj in pool:
                value = getattr(obj, "defense", None)
                if value is None:
                    continue
                if (value >= limit) if _gte else (value <= limit):
                    return True
            return False
        return _ref_defense

    if ctype in ("SAME_COLOR_AS", "SAME_COLOUR_AS"):
        # "banish a card with THE SAME COLOR AS the banished card" — a
        # comparison against an object a preceding effect stored, not a literal
        # colour. REF_MATCHES_OTHER compares entries WITHIN one ref list, which
        # is a different question.
        ref = _first_present(params, "reference", "ref", default="banished")

        def _same_colour(c, e, s, _r=ref):
            from engine.context import get_ref
            other = get_ref(_r)
            if isinstance(other, list):
                other = other[-1] if other else None
            if other is None:
                return False

            def _col(x):
                return _norm(getattr(x, "color", None)
                             or getattr(x, "base_color", None) or "")
            mine, theirs = _col(c), _col(other)
            return bool(mine) and mine == theirs
        return _same_colour

    if ctype in ("REF_MATCHES_OTHER", "REF_SHARES_WITH_OTHER"):
        # "whenever this banishes a card AND THIS HAS BANISHED ANOTHER card with
        # the same colour / the same name". The list ref accumulates everything
        # the card has banished; this asks whether the most recent one matches
        # any EARLIER entry on the named property.
        #
        # "another" is why the last entry is compared against the others rather
        # than the whole list against itself: a single banished card trivially
        # matches itself, which would make the condition always true.
        ref = params.get("ref", "banished_cards")
        prop = _norm(params.get("property") or params.get("by") or "color")

        def _matches(c, e, s, _r=ref, _p=prop):
            from engine.context import get_ref
            pool = get_ref(_r)
            if not isinstance(pool, list) or len(pool) < 2:
                return False
            latest, earlier = pool[-1], pool[:-1]

            # Pitch 1/2/3 is the colour when the card carries no colour string.
            # Defined here rather than reused from REF_PITCH_IS, whose copy is
            # local to that branch.
            pitch_colour = {1: "red", 2: "yellow", 3: "blue"}

            def _key(card_obj):
                if _p in ("color", "colour", "pitch"):
                    return (getattr(card_obj, "color", None)
                            or pitch_colour.get(getattr(card_obj, "pitch", None)))
                if _p in ("name", "card_name"):
                    return _norm(getattr(card_obj, "name", "") or "")
                return _norm(str(getattr(card_obj, _p, "") or ""))

            key = _key(latest)
            if key in (None, ""):
                return False
            return any(_key(other) == key for other in earlier)
        return _matches

    if ctype == "REF_EXISTS":
        ref = params.get("ref", "looked")
        def _ref_exists(c, e, s, _r=ref):
            from engine.context import get_ref
            target = get_ref(_r)
            return bool(target) if not isinstance(target, list) else len(target) > 0
        return _ref_exists

    if ctype == "NOT":
        # Inner condition may be nested under "condition"/"inner" (a full spec dict)
        # or flattened onto this dict via "inner_type". Never recurse with our own
        # "NOT" type (params.get("type") would re-enter here forever).
        inner_spec = params.get("condition") or params.get("inner")
        if isinstance(inner_spec, dict):
            inner = compile_condition(inner_spec.get("type", "none"), inner_spec)
        else:
            inner_t = params.get("inner_type")
            # A bare "flag" is the flattened FLAG_SET form: {"type":"NOT",
            # "flag":"x"} means "if x is not set". Without this the inner
            # condition is None and _not returns FALSE unconditionally, so the
            # ability can never fire — which is what six once-per-turn gates on
            # the Arakni demi-heroes were doing.
            if not inner_t and params.get("flag"):
                inner_t = "FLAG_SET"
            inner = compile_condition(inner_t, params) if inner_t else None
        def _not(c, e, s, _fn=inner):
            return not (_fn is None or _fn(c, e, s))
        return _not

    # Unknown condition types are authoring errors — fail at JSON load time
    # rather than silently passing (fail-open let bad JSON go unnoticed).
    raise ValueError(f"Unknown DSL condition type: {ctype!r} (params: {params!r})")
