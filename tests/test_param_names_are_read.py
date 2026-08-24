"""A parameter the compiler never reads fails silently.

audit_run.py checks a node's TYPE is real. It cannot see this:

    {"type": "WEAPON_SUBTYPE_IN", "subtypes": ["sword"]}

WEAPON_SUBTYPE_IN read `values`. Three of the five cards using it authored
`subtypes` — the natural name given what the condition is called — so they
filtered on an empty list, matched nothing, and could never fire. To a type-name
audit those three cards look perfect.

The corpus had 242 cards with at least one such key. They fell into families,
and the fix for a family is to read every spelling in the compiler rather than
to edit dozens of cards: `class`/`classes`, `subtype`/`subtypes`,
`token`/`token_type`, `zone`/`from_zones`, `counter`/`counter_type`,
`duration`/`scope`. This pins those families shut.

Three of them were worse than a dropped filter:
  * CARD_IN_ZONE dropping a type filter did not disable the condition, it made
    it TOO PERMISSIVE — "an instant in your graveyard" became "any card".
  * MODIFY_DEFENSE_VALUE ignored `mod`, so "subtract" ADDED.
  * SET_FLAG ignored `value: false`, so "clear this" SET it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import audit_params as A

INDEX = A.build_index()


def test_the_detector_sees_the_compilers():
    # Guards the guard. If the AST walk goes stale every check below passes
    # vacuously, which is how a broken audit certifies a broken corpus.
    assert len(INDEX) > 150, f"only {len(INDEX)} types extracted from the compilers"


@pytest.mark.parametrize("type_name,key", [
    # singular/plural — an unread list key leaves the filter EMPTY, so the
    # condition matches nothing and the ability can never fire
    ("ATTACK_CLASS_IN", "class"),
    ("ATTACK_SUBTYPE_IN", "subtype"),
    ("WEAPON_SUBTYPE_IN", "subtypes"),
    ("ATTACK_TYPE_IN", "values"),
    ("CARD_IN_ZONE", "keyword"),
    # unread filter on CARD_IN_ZONE makes the condition too PERMISSIVE
    ("CARD_IN_ZONE", "card_type"),
    ("CARD_IN_ZONE", "subtype"),
    ("CARD_IN_ZONE", "subtypes"),
    ("CARD_IN_ZONE", "player"),
    # a token named under the wrong key is the empty slug: destroys/creates nothing
    ("DESTROY_TOKEN", "token_type"),
    ("CREATE_TOKEN", "token_slug"),
    ("CREATE_TOKEN", "zone"),
    ("CONTROLS_TOKEN_TYPE", "subtype"),
    # wrong zone is worse than no zone: PUT_CARDS_BOTTOM defaulted to
    # hand+arsenal, so a card meant to bottom its revealed cards emptied the hand
    ("PUT_CARDS_BOTTOM", "zone"),
    ("MOVE_REF", "to"),
    # these two INVERT the effect rather than weaken it
    ("MODIFY_DEFENSE_VALUE", "mod"),
    ("SET_FLAG", "value"),
    ("SET_FLAG", "duration"),
    # restriction silently doing nothing: fired on both players' turns
    ("DURING_TURN", "player"),
    # cost could never be paid, so the ability was unusable
    ("REMOVE_COUNTERS", "counter"),
    # fell back to pitch 1 (red) whatever colour the card named
    ("REF_PITCH_IS", "color"),
])
def test_known_defect_family_is_read(type_name, key):
    known = INDEX.get(type_name)
    assert known is not None, f"{type_name} is not a registered type any more"
    assert key in known, (
        f"{type_name} no longer reads {key!r}. Cards author that spelling, and a "
        "key the compiler ignores is dropped in silence — the ability fails "
        "exactly as if its type were invented, but no type-name audit can see it."
    )


def test_not_with_a_bare_flag_is_not_always_false():
    # {"type":"NOT","flag":"x"} compiled its inner condition to None, and
    # `not (None is None or ...)` is False UNCONDITIONALLY — so six once-per-turn
    # gates on the Arakni demi-heroes could never fire.
    from engine.card_effects.dsl.condition_types import compile_condition
    fn = compile_condition("NOT", {"flag": "some_flag"})
    assert fn is not None

    class _P:
        current_turn_effects: list = []

    class _S:
        players = {1: _P(), 2: _P()}

    class _C:
        owner = controller = 1
        slug = "x"

    assert fn(_C(), None, _S()) is True, \
        "NOT over an unset flag must be True; it was False for every input"


def test_inert_rules_name_a_real_type_and_key():
    # Every INERT entry is a CLAIM that honouring a key would change nothing.
    # A wrong one hides a broken card forever, which is exactly how ENGINE_FLAGS
    # certified "die_rolled_six". At minimum the type must still exist — an
    # entry for a type that has been renamed silently protects nothing and
    # would go unnoticed.
    for (type_name, key), (values, why) in A.INERT.items():
        assert type_name in INDEX, (
            f"INERT names {type_name}, which is no longer a registered type — "
            "the rule now suppresses nothing and hides its own staleness")
        assert values, f"INERT[{type_name}.{key}] allows no values"
        assert why, f"INERT[{type_name}.{key}] gives no reason"


def test_inert_only_covers_values_that_match_the_default():
    # The severity split is only trustworthy if "inert" means the value the code
    # already uses. A non-default value on the same key must still be ACTIVE —
    # "player": "OPPONENT" is a real defect even though "player": "SELF" is not.
    assert A.severity("CHOOSE", "player", "SELF") == "inert"
    assert A.severity("CHOOSE", "player", "OPPONENT") == "active"
    assert A.severity("SEARCH_DECK", "shuffle", True) == "inert"
    assert A.severity("SEARCH_DECK", "shuffle", False) == "active"
    # A key with no rule is never inert.
    assert A.severity("CHOOSE", "totally_made_up", "SELF") == "active"


def test_regression_count_does_not_grow():
    # The remaining unread keys are one-off inventions on individual cards, not
    # families — each needs its own judgement, so this pins the number rather
    # than claiming zero. Lower it when cards are fixed; a rise means a new
    # family appeared and should be closed in the compiler instead.
    findings = 0
    for path in A.card_files():
        import json
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        hits: list[str] = []
        A.walk(raw.get("abilities", []),
               lambda n: hits.extend(A.audit_node(n, INDEX)))
        if hits:
            findings += 1
    # ACTIVE findings only: a key whose value is the default anyway is redundant,
    # not broken, and counting those invites churning correct cards.
    #
    # This ceiling went 77 -> 163 without a single card getting worse. The audit
    # kept ONE flat STRUCTURAL_KEYS list of "keys the loader consumes", and
    # "target" was in it — but at effect level the loader pops only
    # "conditions". So every effect naming a target was exempt from the one
    # check that would have caught it, and the number this pins was measuring
    # the detector's blind spot as much as the corpus.
    #
    # Raising a threshold to make a test pass is normally how a regression gets
    # laundered into the baseline. It is the right move ONLY here, where the
    # rise is the detector seeing more, and the evidence is that BANISH's
    # unread target was milling its own controller's deck on 17 cards. Do not
    # raise it again without that kind of evidence: a rise from a corpus change
    # is a new family, and belongs in the compiler where it closes every card
    # at once.
    #
    # 163 -> 153: the counter effects (PUT_COUNTER / REMOVE_COUNTER /
    # REMOVE_COUNTERS) now read their target, closing twelve cards that were
    # putting their counters on the source card.
    # 153 -> 148: LOOK_AT now reads its target through the same parser BANISH
    # uses, closing twelve more -- five of which were reading the OPPONENT's
    # deck where the card says "your deck".
    # 148 -> 142: DESTROY_TOKEN was standing in for six different destroy
    # effects; the eight cards now use DESTROY_PERMANENT, DESTROY_MATCHING or
    # DESTROY_DEFENDING as their text requires.
    # 142 -> 132: DESTROY_REF/BANISH_REF nodes handed a "target" acted on a ref
    # no earlier effect in the ability ever set, so all ten did nothing at all.
    # 132 -> 120: DISCARD / SET_FLAG / PUT_CARDS_BOTTOM named the OPPONENT under
    # "target" and did it to the caster. PUT_CARDS_BOTTOM had no `player` param
    # at all and moved the whole zone.
    # 120 -> 106: the clash cycle, plus INTIMIDATE/PREVENT_DAMAGE targets
    # declared INERT (they always hit the opposing hero / shield the
    # controller, so naming it changes nothing).
    # 106 -> 96: effects that name ONE card. SEARCH_DECK gained name/keyword
    # filters, RETURN_TO_HAND gained a target/ref (it returned the SOURCE), and
    # the BANISH_FROM_GRAVEYARD cost gained a name.
    # 96 -> 94: MAY now reads its `cost`. It did not, so "you may pay {r}. If
    # you do, +1{p}" was free and unconditional -- the card strictly stronger
    # than printed.
    # 82 -> 73: the targeting tail. TAP, FLIP_REF and MODIFY_DEFENSE_VALUE now
    # take the canonical object target, and that target grew "ref" and
    # "record_as" so "put a counter on IT" can name the object the previous
    # effect acted on instead of repeating the search. PUT_ARSENAL_BOTTOM read
    # neither its face_up filter nor, on four cards, the fact that it defaults
    # to the OPPONENT's arsenal and moves cards the wrong way -- those now use
    # the new PUT_INTO_ARSENAL.
    # 73 -> 69: the deck-bottom family. PUT_HAND_CARD_BOTTOM now reads
    # "position" (a card saying ON TOP put its card on the BOTTOM) and records
    # what it moved, so "if you do, draw a card" -- absent entirely on Sink
    # Below -- can be gated on it. The rest were the wrong effect: "the
    # ATTACKING hero puts a card" fell back to SELF, and "your revealed card"
    # meant the CLASH reveal, not a card in hand.
    # 69 -> 64: the discard family. DISCARD read no filter at all and
    # DISCARD_CARD read only type_filter/class_filter, so "discard a YELLOW
    # card" / "an INSTANT card" / "a Phoenix Flame" all discarded hand position
    # 0 -- effect_discard took cards[0] with no choice offered to anyone. On the
    # COST side an unread filter also made can_pay say yes on any non-empty
    # hand, so cards were playable when their cost could not be paid. One
    # vocabulary now serves both (_hand_card_filter).
    #
    # Part of that drop is the AUDIT seeing more, not the corpus changing:
    # a block that hands `params` to a shared helper now gets credited with the
    # keys the HELPER reads, including across a module boundary. Without it the
    # scan went blind exactly where the compiler was factored properly, and
    # reported 8 correct cards.
    # 64 -> 59: CARD_IN_ZONE. It counts cards and defaults to "at least one",
    # so a filter it does not read does not disable the gate -- it widens the
    # question to "is this zone non-empty". It now reads the exact spellings
    # (cost, power), face_up, a card NAME, a nested `filter` dict, and
    # player: ANY for "in any arsenal" / "each hero's graveyard".
    # 59 -> 55: "put IT on the bottom" cannot be spelled as a zone.
    # PUT_CARDS_BOTTOM knew only how to name a zone and move everything in it,
    # so seerstone fell through to the hand+arsenal DEFAULT (bottoming a card
    # from each), right_behind_you named "top_deck" -- not a Player attribute --
    # and bottomed nothing, and phantasmaclasm hid the whole thing inside a
    # SELECT_FROM_REF `effects` list it does not read. It now takes a `ref` and
    # honours `optional`.
    # 55 -> 51: DESTROY_PERMANENT exists as both an effect and a cost, and the
    # two read DIFFERENT subsets of one vocabulary -- the effect knew `subtype`,
    # the cost knew `slug`/`permanent_type`, and NEITHER knew `asset`, which is
    # what both cards needing it say. They now share _permanent_filter.
    # DESTROY_TOKEN gained max_destroy and records what it took, so "for each
    # destroyed this way" can count it instead of assuming the maximum.
    # 51 -> 48: SEARCH_DECK now reads a nested `filter` dict and the plain
    # "card_type" spelling, so a search that names what it wants stops matching
    # ANY card. Two deeper bugs came out with them: "deck_top" is not a ZONE, so
    # every "put it on top" silently left the card where it was; and the shuffle
    # ran AFTER the placement, randomising the card back into the deck.
    # 48 -> 44: CHOOSE_VALUE. CHOOSE picks between EFFECT OPTIONS; two cards
    # used it to mean "pick an abstract VALUE and remember it" and, with no
    # `options` list, the handler returned immediately so neither card did
    # anything. MARK also gained a hero name -- it always marks the opposing
    # hero, which is right for the nine cards saying "target opposing hero" and
    # wrong for the one that names WHICH hero.
    # 44 -> 42: GAIN resolved every asset to the CONTROLLER, so "THEY gain {r}"
    # handed the resource to the card's own controller -- an inversion. It also
    # had no intellect asset (the card that needs it used the KEYWORD branch,
    # which grants to the combat's keyword list) and no duration, so an
    # until-end-of-turn intellect gain would have been permanent. BANISH gained
    # the "if you do" payoff its one user had authored under a key it does not
    # read.
    # 42 -> 38: four cards selected from refs nothing anywhere sets
    # ("MYGRAVEYARD", "MYHAND", "arsenal", "REVEALED"), so every one did nothing.
    # What they need is an object target over a zone. ADD_DEFEND gained one (it
    # could only add the SOURCE card), SEARCH_DECK gained `player` (no way to
    # say WHOSE deck, so a card raiding the opponent's raided its own), and
    # COUNT_REF's card_type now checks subtypes as CARD_IS_TYPE does.
    # 38 -> 34: the modal/target batch. BANISH_REF and REVEAL_TOP_DECK were the
    # wrong effects for "banish target X from an opposing graveyard" and "turn a
    # card in their arsenal face up"; MAY_DESTROY_SILVERS_TO_EQUIP is a bespoke
    # effect for a different card entirely.
    # 34 -> 33: arc_bending_red's Lightning Bond was an ACTIVATE ability with a
    # PITCH cost -- an ability you activate by pitching, which is not what a
    # bond is. A bond is a condition ON PLAY about what paid for the card, and
    # PITCHED_FOR_THIS now reads a class/talent as well as a subtype.
    # 33 -> 28: TRANSFORM_HERO is Arakni's "you become an Agent of Chaos" and
    # reads only `mode`. invoke_azvolai_red put "Ash" in `target` meaning the
    # PERMANENT transform, so it left the ash alone and turned the CONTROLLER'S
    # HERO into an Agent of Chaos -- the fourth card to confuse the two, so an
    # unrecognised mode now raises at load. Alongside it, DEAL_ARCANE resolved
    # every target spelling except "OPPONENT" to the CONTROLLER, so "target
    # hero" (3 cards) and zap_clappers' "the ATTACKING hero" burned their own
    # side; that vocabulary is now one shared resolver, because DEAL_GENERIC
    # held a second copy of it.
    # 28 -> 27: a FALSE POSITIVE, not a fix. NOT's flattened form hands the
    # WHOLE params dict to compile_condition(inner_type, params), so the keys
    # belong to the INNER type. The scan only recognised forwarding when
    # `params` was the FIRST argument, so fyendals_spring_tunic's
    # counter_type/min read as dead on a card that demonstrably works. A false
    # positive in a report this long is how someone learns to stop believing it.
    # 27 -> 26: mounting_anger_red. "You may banish an attack action card from
    # your hand with cost LESS THAN your Draconic chain links. If you do, it
    # gains +1{p} and you may play it this turn." MODIFY_ATTACK reads no
    # target, and SET_FLAG appends a STRING to current_turn_effects that
    # nothing reads -- play.py consults player.playable_from_banished -- so
    # neither payoff half reached the game state, and both re-filtered the
    # WHOLE banished zone rather than the card just banished.
    # 26 -> 23: "self" is not a REF. The ref family resolves its object from a
    # named ref an earlier effect stored, and three cards wrote
    # `"target": "self"` for wordings whose object is the source card --
    # "turn IT face-down", "put IT into your hero's soul". The lookup was
    # skipped and the ref fell back to a default nothing had set, so each card
    # did nothing at all. patch_the_hole was worse than nothing: with no ref
    # and no target, RETURN_TO_HAND fell through to "return THIS card", so
    # "return a card from your ARSENAL" bounced the equipment it had just
    # destroyed as a cost and left the arsenal untouched.
    # 23 -> 19: graveyard searches that could only ever reach HAND. Two search
    # effects each carried their OWN types-only copy of the type filter, so
    # "an ALLY" -- a SUBTYPE -- matched nothing in the game. bone_puppetry's
    # "return an ally from your graveyard TO THE ARENA" was
    # RETURN_DR_FROM_GRAVEYARD (a DEFENSE REACTION, to HAND), and
    # ominous_excavation_blue's "shuffle an instant into your deck" was a
    # banish-a-trap-and-make-it-playable. looking_for_a_scrap_blue's unread
    # pitch_power let ANY graveyard card pay a cost only a 1-power card can
    # pay -- on the COST side that legalises an unplayable play.
    # 19 -> 17: step_between_red's "{p} damage CAN'T BE PREVENTED this combat
    # chain" was authored as WARD -- which PREVENTS damage. The clause helped
    # the DEFENDER against the very attack it exists to push through.
    # DamageEvent.unpreventable and effects.py's refusal to let Ward touch it
    # both already existed; MAKE_NEXT_DAMAGE_UNPREVENTABLE was one-shot and
    # untyped, so it gained a scope and a damage_type. DESTROY_ARSENAL now
    # reads `target` as the spelling of WHOSE arsenal -- it named the default
    # on the one card using it, but "self" would have hit the opponent.
    # 17 -> 14: two wrong-effect defects.
    # v_for_valor_yellow reads "{r}, destroy this, CHARGE your hero's soul:" --
    # the charge is a COST. As an ON_PLAY effect the reaction was legal with an
    # EMPTY HAND: it resolved, the attack got +2{p}, and the cost was never
    # paid. CHARGE also took hand position 0 with nobody choosing.
    # Both Promise of Plenty variants sat on
    # EACH_HERO_ARSENAL_FROM_ZONE_THEN_DISCARD, whose tail makes each hero
    # discard AT RANDOM. Their text never mentions discarding, so the card
    # inflicted a symmetric invented downside that hurt the caster too. The
    # discard is now opt-out (Codex of Frailty and Inertia do say it).
    assert findings <= 14, (
        f"{findings} cards have an ACTIVE parameter the compiler never reads (was 14). "
        "A new one usually means a new spelling of an existing family — fix it "
        "in the compiler, where it closes every card at once."
    )


# --- the NOT exemption has to be EARNED --------------------------------------

def test_a_flattened_NOT_really_forwards_its_params_to_the_inner_condition():
    """audit_params stops reporting NOT's keys because the handler forwards
    `params` wholesale. That exemption is only honest if the forwarding works:
    an exemption granted to a handler that DROPS the keys would hide exactly
    the defect the audit exists to find.

    fyendals_spring_tunic: "at the start of your turn, if this has FEWER THAN 3
    energy counters". Drop counter_type/min and the gate answers about the
    wrong counter, or about none.
    """
    import copy

    from engine.card import CardDB
    from engine.card_effects.dsl.condition_types import compile_condition
    from engine.card_effects.dsl.loader import load_all_cards
    from tests.conftest import _make_state

    load_all_cards()
    db = CardDB()
    state = _make_state()
    state.card_db = db
    tunic = copy.deepcopy(db.get("fyendals_spring_tunic"))
    tunic.owner = tunic.controller = 1

    fn = compile_condition("NOT", {"inner_type": "COUNTER_GTE",
                                   "counter_type": "energy", "min": 3})

    assert fn(tunic, None, state) is True, "an empty tunic did not satisfy it"
    tunic.counters["energy"] = 2
    assert fn(tunic, None, state) is True, "2 is fewer than 3"
    tunic.counters["energy"] = 3
    assert fn(tunic, None, state) is False, (
        "3 energy counters still read as \"fewer than 3\" — the inner "
        "condition never saw counter_type/min")


def test_the_forwarding_is_detected_from_the_source_not_hardcoded():
    """A hand-written allowlist of forwarding types goes stale silently. The
    scan derives them, so this pins that NOT is derived rather than named."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import audit_params as A

    index = A.build_index()
    assert A.WHOLESALE in index.get("NOT", set())
    src = (Path(__file__).resolve().parent.parent / "scripts"
           / "audit_params.py").read_text(encoding="utf-8")
    assert '"NOT"' not in src, (
        "the forwarding list is hardcoded; it will go stale silently")
