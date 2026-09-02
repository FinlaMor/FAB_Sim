"""A weapon reading "when THIS hits" was firing on every attack you made.

_dsl_hit_listener broadcast ON_HIT to the attacker's hero and every permanent
they controlled. That is right for "when AN ATTACK YOU CONTROL hits" and wrong
for "when THIS hits", and the corpus is mostly the second: seven weapons say it,
against four cards that mean the broadcast.

Hunter's Klaive reads "When this hits a hero, **mark** them." Attack with
anything else, hit, and the Klaive marked the opponent from inside its weapon
zone.

WHY WEAPONS ARE THE ONES CAUGHT. Activating a weapon to attack creates an
attack-proxy (CR 1.4.3) -- a non-card object representing the weapon, which
inherits its source's properties but not its activated abilities. This engine
models the proxy as a flag on the action and puts the WEAPON itself in
combat.attack_card, so the weapon's own ON_HIT already fires through the
attack-card dispatch, exactly once and only when it is the attack. The broadcast
was pure surplus for them.

The fix is the one this file already made for turns: ON_HIT means "this", and
ON_ANY_HIT is a separate trigger for the broadcast, exactly as START_OF_ANY_TURN
is separate from START_OF_TURN. The comment there records the same reasoning --
23 abilities meaning "your turn" would have started firing twice a round.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import engine.engine as E
from engine.card import CardDB
from engine.card_effects.dsl.loader import load_all_cards, _CARDS
from tests.conftest import _make_combat, _make_state, owned_card

load_all_cards()
DB = CardDB()
IDX = json.loads((ROOT / "card_data" / "slug_index.json")
                 .read_text(encoding="utf-8"))["by_slug"]


class _HitEvent:
    type = "hit"
    target_player_id = 2
    source_player_id = 1
    amount = 3
    data = {"damage": 3}


def _fire_hit(st):
    for handler in st.event_manager.listeners["hit"]:
        handler(_HitEvent(), st)


def _state_with(weapon_slug, attacking):
    """`attacking` selects whether the weapon IS the attack or merely equipped."""
    st = _make_state()
    st.card_db = DB
    E._setup_dsl_listeners(st)
    weapon = copy.deepcopy(DB.get(weapon_slug))
    weapon.owner = weapon.controller = 1
    st.players[1].weapon1.add(weapon)
    if attacking:
        atk = weapon
    else:
        atk = owned_card(1, "unrelated_attack", types=["Action"])
        atk.subtypes = ["Attack"]
    st.combat = _make_combat(attacker_id=1, attack_card=atk)
    st.combat.attack_target = None
    return st, weapon


# --- the defect --------------------------------------------------------------

def test_a_weapon_does_not_mark_when_a_different_attack_hits():
    st, _ = _state_with("hunters_klaive", attacking=False)
    _fire_hit(st)
    assert st.players[2].class_counters.get("marked", 0) == 0, (
        "Hunter's Klaive marked the opponent from inside a weapon zone, on an "
        "attack that was not the Klaive")


def test_a_weapon_still_marks_when_it_is_the_attack():
    """The other half. A fix that silences the weapon entirely is the same bug
    pointing the other way."""
    st, _ = _state_with("hunters_klaive", attacking=True)
    _fire_hit(st)
    assert st.players[2].class_counters.get("marked", 0) == 1, (
        "the Klaive stopped marking on its own attack")


# --- the broadcast cards still work ------------------------------------------

def test_a_card_that_means_the_broadcast_still_fires():
    """Aether Crackers reads "When an attack you control hits a hero" — it must
    fire on an attack that is not itself, which is the whole point of the
    separate trigger."""
    st = _make_state()
    st.card_db = DB
    E._setup_dsl_listeners(st)
    crackers = copy.deepcopy(DB.get("aether_crackers"))
    crackers.owner = crackers.controller = 1
    st.players[1].arms.add(crackers)
    atk = owned_card(1, "unrelated_attack", types=["Action"])
    atk.subtypes = ["Attack"]
    st.combat = _make_combat(attacker_id=1, attack_card=atk)
    st.combat.attack_target = None
    before = st.players[2].life

    _fire_hit(st)

    assert st.players[2].life < before or crackers not in st.players[1].arms.cards, (
        "Aether Crackers did not react to an attack its controller made; the "
        "retrigger to ON_ANY_HIT did not reach it")


# --- corpus guards -----------------------------------------------------------

def _own_text(text):
    """The card's own sentences, with GRANTED abilities removed.

    A granted ability is printed in double quotes, and its "this" refers to
    whatever received it, not to the card doing the granting. Arakni Marionette
    reads: your attacks ... get +1{p} and "When this hits, this gets go again."
    The hero's ability fires when its controller's attack hits — the broadcast
    case — while the quoted "this" is the attack.

    The same pronoun question the gated-keyword sweep ran into, in a different
    place: a sweep over printed text has to know whose sentence it is reading.
    """
    import re
    return re.sub(r'"[^"]*"', " ", text)


def _permanent_zone_cards():
    PERM_TYPES = {"weapon", "equipment", "item", "token"}
    PERM_SUBS = {"aura", "ally", "item", "head", "chest", "arms", "legs"}
    for slug, cd in sorted(_CARDS.items()):
        e = IDX.get(slug) or {}
        types = {str(t).lower() for t in (e.get("types") or [])}
        subs = {str(t).lower() for t in (e.get("subtypes") or [])}
        if types & PERM_TYPES or subs & PERM_SUBS or "Hero" in (e.get("types") or []):
            yield slug, cd, (e.get("functionalText") or "")


def test_no_this_hits_card_uses_the_broadcast_trigger():
    """"When this hits" on ON_ANY_HIT would fire on every attack — the exact
    defect, re-introduced one card at a time."""
    import re
    bad = []
    for slug, cd, text in _permanent_zone_cards():
        if not re.search(r"when(?:ever)? this hits", _own_text(text).lower()):
            continue
        if any((a.trigger or "").upper() == "ON_ANY_HIT" for a in cd.abilities):
            bad.append(slug)
    assert not bad, (
        "these say 'when THIS hits' but listen for any attack: " + ", ".join(bad))


def test_no_any_attack_card_uses_the_self_trigger():
    """The mirror. "When an attack you control hits" on ON_HIT never fires at
    all for a permanent, because ON_HIT reaches only the attack itself — a
    silent no-op rather than an over-trigger."""
    import re
    bad = []
    for slug, cd, text in _permanent_zone_cards():
        if not re.search(r"when(?:ever)? (?:an|a) [\w ]*attack[\w ]* you control hits",
                         _own_text(text).lower()):
            continue
        if any((a.trigger or "").upper() == "ON_HIT" for a in cd.abilities):
            bad.append(slug)
    assert not bad, (
        "these mean 'an attack you control' but only listen for their own hit: "
        + ", ".join(bad))


def test_the_seven_weapons_are_still_on_the_self_trigger():
    """Pins the set that motivated the split, so a later broadening shows up
    here rather than as a card quietly doing more than it says."""
    for slug in ("hunters_klaive", "nerve_scalpel", "beckoning_mistblade",
                 "millers_grindstone", "razor_ring_blue", "scorpio_comet_tail",
                 "jinglewood_smash_hit"):
        cd = _CARDS.get(slug)
        assert cd is not None, slug
        triggers = {(a.trigger or "").upper() for a in cd.abilities}
        assert "ON_HIT" in triggers, "%s: %s" % (slug, triggers)
        assert "ON_ANY_HIT" not in triggers, slug


# --- the other direction: a dagger that "has hit" without attacking ----------

def test_flick_knives_can_reach_a_dagger_attack_action_card():
    """Flick Knives: "Target dagger you control THAT ISN'T ON THE ACTIVE CHAIN
    LINK deals 1 damage to target hero. If damage is dealt this way, THE DAGGER
    HAS HIT."

    A card only needs to say "the dagger has hit" because CR 7.5.5 says a hit
    happens only during the Damage Step, from the active-attack. This is the
    mirror of the broadcast defect: a dagger that did NOT attack is made to have
    hit, on purpose, by name.

    The search was weapon zones only, which excluded every dagger that is an
    ATTACK ACTION CARD. kiss_of_death_red is types ["Action"], subtypes
    ["Attack", "Dagger"] — it lives on the combat chain once played, so it could
    never be found, while graphene_chelicera (a token WEAPON with the Dagger
    subtype) always could. Two daggers, two zones, and only one reachable.
    """
    from engine.card_effects.dsl.effect_types import compile_effect

    st = _make_state()
    st.card_db = DB
    E._setup_dsl_listeners(st)

    kiss = copy.deepcopy(DB.get("kiss_of_death_red"))
    kiss.owner = kiss.controller = 1
    st.combat_chain.add(kiss)                      # played on an earlier link

    active = owned_card(1, "unrelated_attack", types=["Action"])
    active.subtypes = ["Attack"]
    st.combat = _make_combat(attacker_id=1, attack_card=active)
    st.combat.attack_target = None

    knives = owned_card(1, "flick_knives", types=["Equipment"])
    st.players[1].arms.add(knives)
    st.players[1].life = st.players[2].life = 20

    compile_effect("DAGGER_DEALS_DAMAGE_AND_DESTROY", {"amount": 1})(knives, None, st)

    assert st.players[2].life <= 18, (
        "the dagger dealt its 1 damage but its own ON_HIT did not fire, so "
        "'the dagger has hit' reached nothing: life is %s"
        % st.players[2].life)


def test_flick_knives_will_not_target_the_active_attack():
    """"that isn't on the active chain link". The dagger currently attacking is
    not a legal target for its own controller's Flick Knives."""
    from engine.card_effects.dsl.effect_types import compile_effect

    st = _make_state()
    st.card_db = DB
    E._setup_dsl_listeners(st)

    chelicera = copy.deepcopy(DB.get("graphene_chelicera"))
    chelicera.owner = chelicera.controller = 1
    st.players[1].weapon1.add(chelicera)
    st.combat = _make_combat(attacker_id=1, attack_card=chelicera)
    st.combat.attack_target = None

    knives = owned_card(1, "flick_knives", types=["Equipment"])
    st.players[1].arms.add(knives)
    before = st.players[2].life

    compile_effect("DAGGER_DEALS_DAMAGE_AND_DESTROY", {"amount": 1})(knives, None, st)

    assert st.players[2].life == before, (
        "it targeted the dagger that is the active attack")
    assert chelicera in st.players[1].weapon1.cards, "it destroyed the attacker"


# --- a granted trigger lives on the ATTACK, and what that is differs ---------

def _scar_tissue_then_flick(slug, in_weapon_zone):
    """Play Scar Tissue on this dagger's attack, then flick the dagger on a
    LATER chain link. Returns the opponent's marked count."""
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.card_effects.dsl.interpreter import run_ability
    from engine.card_effects.dsl.loader import get_card

    st = _make_state()
    st.card_db = DB
    E._setup_dsl_listeners(st)

    dagger = copy.deepcopy(DB.get(slug))
    dagger.owner = dagger.controller = 1
    (st.players[1].weapon1 if in_weapon_zone else st.combat_chain).add(dagger)

    # The dagger is the active attack; Scar Tissue targets it.
    st.combat = _make_combat(attacker_id=1, attack_card=dagger)
    st.combat.from_weapon = bool(getattr(dagger, "is_weapon", False))
    st.combat.attack_target = None
    run_ability(get_card("scar_tissue_red").abilities[0],
                owned_card(1, "scar_tissue_red"), None, st)

    # A later chain link: something else is attacking, and the dagger is flicked.
    later = owned_card(1, "later_attack", types=["Action"])
    later.subtypes = ["Attack"]
    st.combat = _make_combat(attacker_id=1, attack_card=later)
    st.combat.attack_target = None
    knives = owned_card(1, "flick_knives", types=["Equipment"])
    st.players[1].arms.add(knives)
    compile_effect("DAGGER_DEALS_DAMAGE_AND_DESTROY", {"amount": 1})(knives, None, st)
    return st.players[2].class_counters.get("marked", 0)


def test_a_grant_to_an_attack_action_card_travels_with_the_card():
    """Scar Tissue: "Target dagger attack gets +3{p} and 'When this hits a hero,
    mark them.'"

    Kiss of Death is an attack ACTION CARD, so the attack IS the card and the
    granted trigger is on that object. Flick it later in the chain — making it
    "have hit" without attacking — and the granted trigger fires with it.
    """
    assert _scar_tissue_then_flick("kiss_of_death_red", in_weapon_zone=False) == 1, (
        "the granted on-hit did not travel with the card it was granted to")


def test_a_grant_to_a_weapons_attack_does_not_reach_the_weapon():
    """The same play on a WEAPON. Activating a weapon creates an attack-PROXY
    (CR 1.4.3) — a separate object that ceases to exist when the chain link
    changes (1.4.3c), and effects applying to it do not apply to the weapon
    (1.4.3e). So flicking the weapon afterwards fires only its OWN printed
    on-hit; the Scar Tissue grant went to the proxy and is gone.

    Nerve Scalpel is the subject rather than Hunter's Klaive precisely because
    the Klaive marks by itself — with it, both rulings produce marked=1 and the
    test could not tell them apart.
    """
    assert _scar_tissue_then_flick("nerve_scalpel", in_weapon_zone=True) == 0, (
        "the grant made to a weapon's attack-proxy followed the weapon card")


def test_a_flicked_weapon_still_fires_its_own_on_hit():
    """The other half of the weapon ruling, and the one the marked==0 test
    cannot give: that assertion also passes if NOTHING fired.

    Nerve Scalpel's own on-hit queues a defence penalty on the opponent. Flick
    it and that must still happen — "the dagger has hit" is a real hit for the
    dagger's OWN abilities; it is only the grant made to a proxy that does not
    survive.
    """
    from engine.card_effects.dsl.effect_types import compile_effect

    st = _make_state()
    st.card_db = DB
    E._setup_dsl_listeners(st)

    scalpel = copy.deepcopy(DB.get("nerve_scalpel"))
    scalpel.owner = scalpel.controller = 1
    st.players[1].weapon1.add(scalpel)

    later = owned_card(1, "later_attack", types=["Action"])
    later.subtypes = ["Attack"]
    st.combat = _make_combat(attacker_id=1, attack_card=later)
    st.combat.attack_target = None
    knives = owned_card(1, "flick_knives", types=["Equipment"])
    st.players[1].arms.add(knives)

    compile_effect("DAGGER_DEALS_DAMAGE_AND_DESTROY", {"amount": 1})(knives, None, st)

    assert getattr(st.players[2], "dsl_queued_defense_mods", []), (
        "the flicked Scalpel's OWN on-hit did not fire; splitting ON_HIT off "
        "the broadcast must not silence a dagger that really has hit")


def test_every_granted_on_hit_on_a_flicked_card_fires():
    """"Flick Kiss of Death after playing something like Spike with Bloodrot"
    — Spike targets an attack action card with stealth, which Kiss of Death is,
    and grants it another on-hit.

    spike_with_bloodrot_red is not implemented, so this exercises the mechanic
    rather than the card: TWO granted on-hit triggers plus the card's own must
    all fire when the card is flicked, not just the first. Grants accumulate on
    the object, so a `granted_abilities` list that was overwritten rather than
    appended to would pass every single-grant test above and fail here.
    """
    from engine.card_effects.dsl.effect_types import compile_effect
    from engine.card_effects.dsl.interpreter import run_ability
    from engine.card_effects.dsl.loader import get_card

    st = _make_state()
    st.card_db = DB
    E._setup_dsl_listeners(st)

    kiss = copy.deepcopy(DB.get("kiss_of_death_red"))
    kiss.owner = kiss.controller = 1
    st.combat_chain.add(kiss)
    st.combat = _make_combat(attacker_id=1, attack_card=kiss)
    st.combat.attack_target = None

    # Grant one: Scar Tissue's "when this hits a hero, mark them".
    run_ability(get_card("scar_tissue_red").abilities[0],
                owned_card(1, "scar_tissue_red"), None, st)
    # Grant two: a second on-hit, Spike-with-Bloodrot shaped.
    compile_effect("INJECT_TRIGGER", {
        "trigger": {"trigger_type": "ON_HIT",
                    "conditions": [{"type": "ATTACK_TARGET_IS_HERO"}],
                    "effects": [{"type": "LOSE_LIFE", "amount": 2,
                                 "player": "OPPONENT"}]}})(
        owned_card(1, "spike_shaped_grant"), None, st)

    assert len(getattr(kiss, "granted_abilities", [])) == 2, (
        "grants must accumulate on the object: %s"
        % getattr(kiss, "granted_abilities", None))

    later = owned_card(1, "later_attack", types=["Action"])
    later.subtypes = ["Attack"]
    st.combat = _make_combat(attacker_id=1, attack_card=later)
    st.combat.attack_target = None
    knives = owned_card(1, "flick_knives", types=["Equipment"])
    st.players[1].arms.add(knives)
    st.players[2].life = 20

    compile_effect("DAGGER_DEALS_DAMAGE_AND_DESTROY", {"amount": 1})(knives, None, st)

    assert st.players[2].class_counters.get("marked", 0) == 1, "grant one did not fire"
    # 1 from the flick's damage, 2 from the second grant, 1 from Kiss of Death's
    # own printed on-hit.
    assert st.players[2].life == 16, (
        "not every on-hit fired on the flicked card: life is %s, expected 16"
        % st.players[2].life)
