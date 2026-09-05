#!/usr/bin/env python3
"""Build a Talishar game state to order, instead of playing a game into one.

Every earlier way of getting an oracle state for a card was a SEARCH. The
spectator corpus answers "no evidence" for any card nobody happened to play,
which is most of them. The local generator answered that by stacking twelve
copies into a deck and grinding whole games until one was drawn -- minutes per
card, no control over the board, and the stacking itself evicts cards: it
replaces the most-duplicated *other* card, which for whelming_gustwave is
Surging Strike, the one card the combo needs.

The state is just a file. Talishar's ParseGamestate() reads gamestate.txt into
globals and WriteGamestate.php writes them back, so the adapter's POST
/scenario boots a legal game, patches the globals, and writes. Talishar does
the serialization, so the field layouts cannot drift from the ones it reads.

    from scripts.talishar_scenario import Scenario, build
    r = build(Scenario(card="whelming_gustwave_red",
                       hand=["whelming_gustwave_red"],
                       chain_links=["surging_strike_red"]))
    r.play("whelming_gustwave_red")   # -> state after the card is played

WHAT THE ADAPTER GUARANTEES, AND WHAT IT DOES NOT. /scenario re-reads the state
it wrote and diffs it against the request; a mismatch comes back as HTTP 409 and
`build` raises. That catches a field that did not land. It does NOT catch a
field that was never asked for -- setting a chain link without its summary row
produced a chain that was visible in the state and invisible to every combo
card, which looked exactly like success. So: assert on the OUTCOME (the power,
the damage), never on the scenario echo alone.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADLESS = Path("C:/Users/Joseph/Desktop/FAB_Sim_Headless")
ADAPTER = "http://localhost:8000"
DECK_TEMPLATES = HEADLESS / "decks" / "_cc_games"
GEN_DIR = HEADLESS / "decks" / "_generated"


class ScenarioError(RuntimeError):
    """The adapter refused to build the state, or it did not round-trip."""


@dataclass
class Scenario:
    """One made-to-order board.

    Only `card` is required; everything else defaults to a quiet board with the
    card in hand, which is the situation most cards need. Zones take plain
    slugs; the adapter fills in the per-zone record fields (unique ids, facing,
    counters) from Talishar's own layouts.
    """

    card: str
    hand: list[str] | None = None
    #: Previous links on the CURRENT combat chain, oldest first. The last one
    #: is what "Combo - if X was the last attack this combat chain" reads.
    chain_links: list[str] = field(default_factory=list)
    arsenal: list[str] = field(default_factory=list)
    discard: list[str] = field(default_factory=list)
    banish: list[str] = field(default_factory=list)
    pitch: list[str] = field(default_factory=list)
    deck_top: list[str] = field(default_factory=list)
    #: Resources already floating. Talishar does not gate legality on cost -- it
    #: offers the play and then drops into the phase-P pitch prompt to collect
    #: payment. Pre-paying skips that prompt, so the card goes straight onto the
    #: chain and the measurement is not navigating a pitch decision that has
    #: nothing to do with the effect under test. At 0 the same play lands in
    #: phase P instead of phase B.
    resources: int = 3
    health: int = 20
    opp_health: int = 20
    opp_hand: list[str] | None = None
    opp_arsenal: list[str] = field(default_factory=list)
    #: The opponent's graveyard and banished zone. Needed by any cost that
    #: reaches across the table -- rotten_remains banishes "a card with 1{p}
    #: from EACH hero's graveyard", so with only our side stocked Talishar never
    #: offers the choice and the paid branch cannot be built at all.
    opp_discard: list[str] = field(default_factory=list)
    opp_banish: list[str] = field(default_factory=list)
    current_turn_effects: list[dict] = field(default_factory=list)
    action_points: int = 1
    #: Which seat holds the card and has priority. Seat 2 is what a defence
    #: reaction needs -- the card can only be played while the OTHER player is
    #: attacking -- so the whole card class is unreachable without it.
    actor: int = 1
    seed: int = 909
    #: Label carried through to the recorded rows so a disagreement can be
    #: traced back to the situation that produced it.
    label: str = "baseline"
    #: Answer Talishar's optional-cost prompts by PAYING rather than passing.
    #: Only meaningful once the zone the cost draws from is stocked -- Talishar
    #: does not offer Decompose at all with an empty graveyard -- which is what
    #: zone_requirements() is for.
    take_optional: bool = False

    def patch(self) -> dict:
        me: dict = {
            "hand": list(self.hand if self.hand is not None else [self.card]),
            "health": self.health,
            "resources": self.resources,
        }
        for zone in ("arsenal", "discard", "banish", "pitch", "deck_top"):
            value = getattr(self, zone)
            if value:
                me[zone] = list(value)
        them: dict = {"health": self.opp_health}
        if self.opp_hand is not None:
            them["hand"] = list(self.opp_hand)
        for zone, value in (("arsenal", self.opp_arsenal),
                            ("discard", self.opp_discard),
                            ("banish", self.opp_banish)):
            if value:
                them[zone] = list(value)

        actor = 2 if int(self.actor) == 2 else 1
        out = {
            "phase": "M",
            "main_player": actor,
            "current_player": actor,
            "action_points": self.action_points,
            "in_game_status": 1,
            "players": {str(actor): me, str(3 - actor): them},
        }
        if self.chain_links:
            # Name the player explicitly: a bare slug defaults to seat 1 on the
            # adapter side, so a seat-2 scenario would build a chain whose links
            # belonged to the opponent.
            out["chain_links"] = [{"card": c, "player": actor}
                                  for c in self.chain_links]
        if self.current_turn_effects:
            out["current_turn_effects"] = list(self.current_turn_effects)
        return out


class Built:
    """A built scenario, and the handful of moves worth making on it."""

    def __init__(self, adapter: str, payload: dict, scenario: Scenario):
        self.adapter = adapter
        self.game_id = payload["game_id"]
        self.state = payload["state"]
        self.legal_actions = payload.get("legal_actions") or []
        self.scenario = scenario
        self.applied = (payload.get("scenario") or {}).get("applied") or {}
        self.warnings = (payload.get("scenario") or {}).get("warnings") or []

    def action_for(self, slug: str, kind: str = "PLAY_FROM_HAND"):
        for a in self.legal_actions:
            if a.get("card_id") == slug and a.get("type") == kind:
                return a
        return None

    def step(self, action_id: int) -> dict:
        return _post(self.adapter, "/step",
                     {"game_id": self.game_id, "action_id": int(action_id)})

    def play(self, slug: str) -> dict | None:
        """Play `slug` from hand. None when the engine will not allow it.

        A None here is a finding, not a glitch: it means Talishar considers the
        card unplayable in the state we asked for, and that is worth reporting
        rather than silently skipping.
        """
        action = self.action_for(slug)
        if action is None:
            return None
        return self.step(action["action_id"])

    def state_now(self) -> dict:
        return _get(self.adapter, "/state?game_id=%s" % self.game_id)["state"]


def _post(adapter: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(
        adapter + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as fh:
            return json.load(fh)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise ScenarioError("POST %s -> HTTP %d: %s" % (path, exc.code, detail[:1500]))
    except OSError as exc:
        raise ScenarioError(
            "adapter unreachable at %s (%r). Start it:\n"
            "  cd FAB_Sim_Headless && ADAPTER_MODE=real docker compose up -d adapter"
            % (adapter, exc))


def _get(adapter: str, path: str) -> dict:
    try:
        with urllib.request.urlopen(adapter + path, timeout=180) as fh:
            return json.load(fh)
    except urllib.error.HTTPError as exc:
        raise ScenarioError("GET %s -> HTTP %d" % (path, exc.code))


def slug_index() -> dict:
    return json.loads((ROOT / "card_data" / "slug_index.json")
                      .read_text(encoding="utf-8"))["by_slug"]


def pick_template(slug: str, index: dict):
    """A real CC deck whose hero can legally play this card.

    Talishar enforces deck legality at game start, and a deck assembled from
    "cards that name this hero" fails that in tedious, uninformative ways.
    decks/_cc_games holds real hero-vs-hero decks; we borrow one wholesale.
    Unlike the old generator we do NOT modify it -- the card arrives via the
    scenario patch, so the deck's own contents (including a combo partner) stay
    intact.
    """
    entry = index.get(slug) or {}
    legal = {h.lower() for h in (entry.get("legalHeroes") or [])}
    best = None
    for path in sorted(DECK_TEMPLATES.glob("*.json")):
        try:
            deck = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        hero = str(deck.get("hero") or "")
        # legalHeroes are display names ("Katsu"); deck heroes are slugs
        # ("katsu_the_wanderer"), so match on the leading name.
        if legal and not any(hero.startswith(h) for h in legal):
            continue
        if slug in (deck.get("deck") or []):
            return path, deck, True
        if best is None:
            best = (path, deck, False)
    return best if best else (None, None, False)


def validate(scenario: Scenario, index: dict) -> None:
    """Reject slugs that are not real cards, before the adapter sees them.

    Talishar does NOT reject an unknown card id: it puts it in the zone and
    then offers it as a legal play. A typo would therefore produce a board with
    a phantom card in it, no error anywhere, and a comparison quietly answering
    a question about a game that could not exist. The adapter's round-trip check
    cannot catch this either -- the field lands exactly as requested.
    """
    unknown = []
    for zone in ("hand", "chain_links", "arsenal", "discard", "banish", "pitch",
                 "deck_top", "opp_hand", "opp_arsenal", "opp_discard",
                 "opp_banish"):
        for slug in (getattr(scenario, zone) or []):
            if slug not in index:
                unknown.append("%s:%s" % (zone, slug))
    if scenario.card not in index:
        unknown.append("card:%s" % scenario.card)
    if unknown:
        raise ScenarioError("unknown card slug(s): %s" % ", ".join(sorted(set(unknown))))


def build(scenario: Scenario, adapter: str = ADAPTER, index: dict | None = None,
          format_: str = "cc") -> Built:
    """Create the game and patch it into `scenario`. Raises on a bad round trip."""
    index = index if index is not None else slug_index()
    validate(scenario, index)
    path, template, _runs_it = pick_template(scenario.card, index)
    if template is None:
        raise ScenarioError(
            "no CC template deck for a hero that can legally play %s" % scenario.card)

    # The adapter reads decks from a read-only bind mount under decks/, so both
    # seats' deck files have to live there even though neither is modified.
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    seat0 = GEN_DIR / ("%s_seat0.json" % scenario.card)
    seat1 = GEN_DIR / ("%s_seat1.json" % scenario.card)
    body = json.dumps(template, indent=1)
    seat0.write_text(body, encoding="utf-8")
    seat1.write_text(body, encoding="utf-8")

    payload = _post(adapter, "/scenario", {
        "hero1": template["hero"], "hero2": template["hero"],
        "deck1": "decks/_generated/%s" % seat0.name,
        "deck2": "decks/_generated/%s" % seat1.name,
        "seed": scenario.seed, "format": format_,
        "patch": scenario.patch(),
    })
    return Built(adapter, payload, scenario)


def combo_partners(slug: str, index: dict | None = None) -> list[str]:
    """Cards this card's own text names, as slugs.

    Read out of the card text rather than kept in a table, so it covers every
    "Combo - if <Card> was the last attack" without a per-card entry here (the
    project keeps card-specific knowledge in engine/card_effects/, not in
    tooling). Names are matched against the printed names in slug_index, longest
    first so "Surging Strike" wins over a card merely called "Strike".
    """
    index = index if index is not None else slug_index()
    text = str((index.get(slug) or {}).get("functionalText") or "")
    if not text:
        return []
    self_name = str((index.get(slug) or {}).get("name") or "")
    by_name: dict[str, str] = {}
    for other, entry in index.items():
        name = str(entry.get("name") or "")
        # Attacks only: a chain link is an attack, and matching every noun in
        # the text against the whole card pool produces nonsense links.
        if not name or name == self_name:
            continue
        if "Attack" not in (entry.get("subtypes") or []):
            continue
        by_name.setdefault(name, other)
    found: list[str] = []
    for name in sorted(by_name, key=len, reverse=True):
        if name in text and by_name[name] not in found:
            found.append(by_name[name])
    return found


#: CARD_IN_ZONE zone names -> the Scenario field that stocks that zone. The DSL
#: spells zones both ways ("GRAVEYARD" and "graveyard"), so lookups lowercase.
_ZONE_TO_FIELD = {
    "graveyard": "discard",
    "hero_graveyard": "discard",
    "discard": "discard",
    "banished": "banish",
    "banish": "banish",
    "pitch": "pitch",
    "arsenal": "arsenal",
    "soul": "soul",
}


def _card_matches(entry: dict, spec: dict) -> bool:
    """Does this slug_index entry satisfy one CARD_IN_ZONE's trait filters?

    Mirrors the DSL's own matching loosely rather than exactly: `card_class`,
    `talent` and `subtype` are all checked against classes + talents + subtypes
    together, because condition_types._card_traits pools them and a card
    authored "Earth" may carry it as a talent, a class, or neither.
    """
    traits = set()
    for key in ("classes", "talents", "subtypes", "types"):
        traits.update(str(v) for v in (entry.get(key) or []))

    for key in ("card_class", "talent", "subtype", "card_type"):
        want = spec.get(key)
        if want and str(want) not in traits:
            return False
    for want in (spec.get("filter_types") or []):
        if str(want) not in traits:
            return False
    if spec.get("color") and not str(entry.get("color") or "").lower().startswith(
            str(spec["color"]).lower()[:1]):
        return False

    power = entry.get("power")
    try:
        power = int(power)
    except (TypeError, ValueError):
        power = None
    if spec.get("power") is not None:
        if power != int(spec["power"]):
            return False
    if spec.get("power_gte") is not None:
        if power is None or power < int(spec["power_gte"]):
            return False
    return True


def zone_requirements(slug: str, index: dict | None = None) -> dict[str, list[str]]:
    """Real cards to stock so this card's zone-gated abilities can fire.

    Read out of the card's own DSL, not a table: every CARD_IN_ZONE condition
    anywhere in its abilities says "this ability needs N cards matching X in
    zone Z", which is exactly a shopping list. An empty board answers only half
    of what a card does -- Cadaverous Tilling's Decompose needs 2 Earth cards
    and an action in the graveyard before Talishar will even OFFER the choice,
    so on a bare board the whole clause is unreachable and "the scenario agrees"
    means nothing about it.

    Conditions wanting a zone EMPTY (count_eq/amount 0) are skipped: that is
    already the default board.
    """
    index = index if index is not None else slug_index()
    card_def = _card_json(slug)
    if not card_def:
        return {}

    wants: list[tuple[str, int, dict]] = []

    def walk(node):
        if isinstance(node, dict):
            if str(node.get("type") or "") == "CARD_IN_ZONE":
                zone = str(node.get("zone") or "").lower()
                field = _ZONE_TO_FIELD.get(zone)
                count = node.get("count_gte", node.get("amount", 1))
                try:
                    count = int(count)
                except (TypeError, ValueError):
                    count = 1
                # count_eq 0 / amount 0 mean "this zone must be EMPTY".
                if field and count > 0 and node.get("count_eq") != 0:
                    wants.append((field, count, node))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(card_def.get("abilities") or [])
    if not wants:
        return {}

    # Prefer cards the same heroes can play, so the board stays plausible.
    legal = {h.lower() for h in ((index.get(slug) or {}).get("legalHeroes") or [])}

    out: dict[str, list[str]] = {}
    for field, count, spec in wants:
        # "hero_graveyard" is Talishar's name for a zone read across BOTH
        # players ("banish a card from each hero's graveyard"). Stocking only
        # our side means the cost is never payable and Talishar never offers
        # the choice, so the paid branch cannot be built.
        both_sides = str(spec.get("zone") or "").lower().startswith("hero_")
        picked: list[str] = []
        for pool_pass in (True, False):
            if len(picked) >= count:
                break
            for other, entry in index.items():
                if len(picked) >= count:
                    break
                if other == slug or other in picked:
                    continue
                if pool_pass and legal:
                    others = {h.lower() for h in (entry.get("legalHeroes") or [])}
                    if not (others & legal):
                        continue
                if _card_matches(entry, spec):
                    picked.append(other)
        # Requirements on the same zone accumulate: Decompose needs 2 Earth
        # cards AND an action card, which is two conditions and three cards.
        targets = [field, "opp_" + field] if both_sides else [field]
        for target in targets:
            out.setdefault(target, [])
            out[target].extend(p for p in picked if p not in out[target])
    return out


_CARD_JSON_CACHE: dict[str, dict] = {}


def _card_json(slug: str) -> dict:
    """The card's DSL definition, or {} when it has none.

    Never a bare rglob over the card tree -- the pipeline leaves drafts and
    review artifacts in there, and picking one up silently reads a card that is
    not the implemented one.
    """
    if not _CARD_JSON_CACHE:
        root = ROOT / "engine" / "card_effects" / "json"
        for path in root.rglob("*.json"):
            if "needs_review" in path.parts or "batch" in path.parts:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict) and data.get("slug") and "abilities" in data:
                _CARD_JSON_CACHE.setdefault(str(data["slug"]), data)
    return _CARD_JSON_CACHE.get(slug) or {}


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--card", required=True)
    ap.add_argument("--chain-link", action="append", default=[],
                    help="Card on a previous link of the current combat chain.")
    ap.add_argument("--hand", action="append", default=[])
    ap.add_argument("--adapter", default=ADAPTER)
    ap.add_argument("--play", action="store_true",
                    help="Play the card and report the resulting attack.")
    args = ap.parse_args()

    sc = Scenario(card=args.card,
                  hand=(args.hand or None),
                  chain_links=args.chain_link)
    built = build(sc, adapter=args.adapter)
    print("game %s built; warnings=%s" % (built.game_id, built.warnings or "none"))
    for p in built.state["players"]:
        print("  p%s hp=%s hand=%s" % (p["player_id"], p["health"], p.get("hand")))
    print("  chain links: %s" % [l[0] if isinstance(l, list) else l
                                 for l in (built.state.get("links") or [])])
    print("  legal: %s" % [(a["type"], a.get("card_id")) for a in built.legal_actions])
    if args.play:
        after = built.play(args.card)
        if after is None:
            print("  Talishar will not let %s be played here" % args.card)
            return 1
        combat = after["state"]["combat"]
        print("  after play: attack_power=%s pending_damage=%s"
              % (combat.get("attack_power"), combat.get("pending_damage")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
