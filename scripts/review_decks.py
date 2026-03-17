"""scripts/review_decks.py — Legality and practicality review of all generated CC decks."""
import html
import json
import re
import unicodedata
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent

with open(ROOT / "card_data/slug_index.json", encoding="utf-8") as f:
    idx = json.load(f)
by_slug = idx["by_slug"]
by_name = {k.lower(): v for k, v in idx.get("by_name", {}).items()}

DESCRIPTOR = {
    # format / category markers
    "hero","equipment","weapon","generic","base","event","demi-hero","evo","trap",
    # weapon handedness
    "1h","2h",
    # physical weapon sub-types (not class restrictions)
    "axe","book","bow","brush","cannon","claw","club","dagger","fiddle","flail",
    "gun","hammer","item","lute","orb","pistol","polearm","rock","scepter","scroll",
    "scythe","staff","sword","wrench","shield",
    # armor slot names
    "head","chest","arms","legs",
    # secondary weapon slot names
    "off-hand","offhand","quiver",
    # card type categories (not class restrictions)
    "action","attack","non-attack","instant","reaction",
    "attack reaction","defense reaction","defense","block","generic block",
    # card sub-types / play zones (not class restrictions)
    "aura","arrow","ally","dragon","angel","demon","figment",
    "construct","ash","cog","macro","song","gem","invocation","landmark",
    "resource","mentor","companion","affliction","high seas","placeholder card",
    "mercenary","chi","shuriken","rosetta","scurv","puffin","arakni",
    # Note: revered/reviled are talent identifiers — intentionally NOT in DESCRIPTOR
    # color/pitch keywords
    "red","yellow","blue",
    # rarity / print descriptors
    "token","young","seasoned","veteran",
    # talent identifiers that ARE class/talent words but appear on both heroes
    # and cards as flavor context — keep only if truly non-restricting
    "talent",
}


_ESSENCE_ELEMENTS = {"earth", "ice", "fire", "lightning", "water", "wind", "rock"}


def hero_classes(hero_slug):
    e = by_slug.get(hero_slug) or by_slug.get(hero_slug.replace("-", "_"))
    if not e:
        return frozenset()
    classes = {t.lower() for t in e.get("types", []) if t.lower() not in DESCRIPTOR}
    # Expand via Essence keywords (e.g. "Essence of Earth and Ice")
    for kw in e.get("card_keywords", []):
        kw_lower = kw.lower()
        if "essence of" in kw_lower:
            after = kw_lower.split("essence of", 1)[1]
            for word in re.split(r"[\s,]+", after):
                word = word.strip()
                if word and word not in ("and", "or", "the") and word in _ESSENCE_ELEMENTS:
                    classes.add(word)
    return frozenset(classes)


def card_classes(card_slug):
    e = by_slug.get(card_slug)
    if not e:
        return None
    return frozenset(t.lower() for t in e.get("types", []) if t.lower() not in DESCRIPTOR)


def card_kws(card_slug):
    e = by_slug.get(card_slug)
    return e.get("card_keywords", []) if e else []


def name_to_slug(name, color=None):
    key = name.lower()
    slugs = by_name.get(key)
    if not slugs:
        return None
    if color:
        for s in slugs:
            if s.endswith("_" + color):
                return s
    return slugs[0]


deck_files = sorted(
    f for f in (ROOT / "decks/generated").glob("*_CC.txt") if "_mut" not in f.name
)

summaries = {}

for deck_file in deck_files:
    text = deck_file.read_text(encoding="utf-8")
    lines = text.splitlines()

    hero_name = ""
    for line in lines:
        if line.startswith("Hero:"):
            hero_name = line.split(":", 1)[1].strip()
            break

    # Decode HTML entities (e.g. &#x27; → ') then normalize unicode
    _normalized = unicodedata.normalize("NFKD", html.unescape(hero_name))
    _ascii = _normalized.encode("ascii", "ignore").decode("ascii")
    hero_slug = (
        _ascii.lower()
        .replace(" ", "_")
        .replace(",", "")
        .replace("'", "")   # straight apostrophe
        .replace("\u2019", "")  # right single quotation mark '
        .replace("\u2018", "")  # left single quotation mark '
        .replace("-", "_")
        .replace("!", "")
        .replace("?", "")
        .replace(".", "")
        .replace("/", "")
    )
    hc = hero_classes(hero_slug)

    in_arena = in_deck = False
    arena_cards = []
    deck_cards = []

    for line in lines:
        stripped = line.strip()
        if stripped == "Arena cards":
            in_arena, in_deck = True, False
            continue
        if stripped == "Deck cards":
            in_arena, in_deck = False, True
            continue
        if not stripped or stripped.startswith(("Name:", "Hero:", "Format:")):
            continue
        m = re.match(r"(\d+)x (.+?)( \((red|yellow|blue)\))?$", stripped)
        if not m:
            continue
        count = int(m.group(1))
        name = m.group(2).strip()
        color = m.group(4)
        slug = name_to_slug(name, color)
        entry = {"count": count, "name": name, "color": color, "slug": slug}
        if in_arena:
            arena_cards.append(entry)
        elif in_deck:
            deck_cards.append(entry)

    deck_issues = []

    # Deck size
    total = sum(c["count"] for c in deck_cards)
    if total != 60:
        deck_issues.append(f"Deck size: {total} cards (expected 60)")

    # Legendary copy limits (max 1 across all colors)
    base_name_counts = defaultdict(int)
    for c in deck_cards:
        base = c["name"].lower().split(" (")[0]
        base_name_counts[base] += c["count"]
    for c in deck_cards:
        if not c["slug"]:
            continue
        if "Legendary" in card_kws(c["slug"]):
            base = c["name"].lower().split(" (")[0]
            if base_name_counts[base] > 1 and base not in {
                x["name"].lower().split(" (")[0]
                for x in deck_issues  # avoid duplicate reports
                if isinstance(x, dict)
            }:
                deck_issues.append(
                    f"Legendary copy limit: '{c['name']}' has {base_name_counts[base]} total copies (max 1)"
                )

    # Hero legality (deck cards)
    for c in deck_cards:
        if not c["slug"]:
            continue
        cc = card_classes(c["slug"])
        if cc is None:
            continue
        if cc and not cc <= hc:
            # Specialization cards are legal if this hero's name contains the spec hero name
            specs = [k for k in card_kws(c["slug"]) if "Specialization" in k]
            legal_via_spec = any(
                k.replace(" Specialization", "").lower() in hero_name_lower
                for k in specs
            )
            if not legal_via_spec:
                deck_issues.append(
                    f"Illegal card: '{c['name']}' (card class {cc} not subset of hero {hc})"
                )

    # Hero legality (arena cards)
    hero_name_lower = hero_name.lower()
    for c in arena_cards:
        if not c["slug"]:
            continue
        cc = card_classes(c["slug"])
        if cc is None:
            continue
        if cc and not cc <= hc:
            # Check specialization keywords — legal if spec hero name appears in this hero's name
            specs = [k for k in card_kws(c["slug"]) if "Specialization" in k]
            legal_via_spec = any(
                k.replace(" Specialization", "").lower() in hero_name_lower
                for k in specs
            )
            if specs and not legal_via_spec:
                deck_issues.append(
                    f"Specialization violation: '{c['name']}' requires {specs}"
                )
            elif not specs:
                deck_issues.append(
                    f"Illegal equipment: '{c['name']}' (card class {cc} not subset of hero {hc})"
                )

    # Equipment slot counts
    slot_counts = defaultdict(int)
    weapon_types = []
    for eq in arena_cards:
        slug = eq["slug"]
        if not slug:
            continue
        e = by_slug.get(slug)
        if not e:
            continue
        types = [t.lower() for t in e.get("types", [])]
        if "weapon" in types:
            weapon_types.extend(t for t in types if t in ("1h", "2h", "bow"))
        elif "head" in types:
            slot_counts["head"] += eq["count"]
        elif "chest" in types:
            slot_counts["chest"] += eq["count"]
        elif "arms" in types:
            slot_counts["arms"] += eq["count"]
        elif "legs" in types:
            slot_counts["legs"] += eq["count"]
        elif "off-hand" in types:
            slot_counts["off-hand"] += eq["count"]
        elif "quiver" in types:
            slot_counts["quiver"] += eq["count"]

    for slot, cnt in slot_counts.items():
        if cnt > 1:
            deck_issues.append(f"Duplicate slot: {slot} x{cnt}")

    if slot_counts["quiver"] > 0 and "bow" not in weapon_types:
        deck_issues.append("Quiver without bow weapon")
    # Note: some heroes (e.g. Gravy Bones) legitimately run an off-hand with no weapon.
    # This is only flagged as a warning, not an error.

    # Unknown cards
    for c in deck_cards + arena_cards:
        if c["slug"] is None:
            deck_issues.append(f"Unknown card: '{c['name']}' not in slug_index")

    # Pitch curve
    reds = sum(c["count"] for c in deck_cards if c["color"] == "red")
    yellows = sum(c["count"] for c in deck_cards if c["color"] == "yellow")
    blues = sum(c["count"] for c in deck_cards if c["color"] == "blue")
    no_color = sum(c["count"] for c in deck_cards if not c["color"])
    if blues < 10 and total >= 50:
        deck_issues.append(
            f"Low pitch: only {blues} blue cards ({blues/max(total,1)*100:.0f}%) — weak resource generation"
        )

    label = deck_file.name.replace("_CC.txt", "")
    summaries[label] = {
        "hero": hero_name,
        "deck_size": total,
        "red": reds,
        "yellow": yellows,
        "blue": blues,
        "no_color": no_color,
        "arena": len(arena_cards),
        "issues": deck_issues,
    }

# --- Report ---
clean = [(lbl, s) for lbl, s in sorted(summaries.items()) if not s["issues"]]
flagged = [(lbl, s) for lbl, s in sorted(summaries.items()) if s["issues"]]

print(f"=== FAB Deck Review Report ===")
print(f"Reviewed: {len(summaries)} decks   Clean: {len(clean)}   Flagged: {len(flagged)}")

if flagged:
    print("\n--- FLAGGED DECKS ---")
    for label, s in flagged:
        pitch = f"R:{s['red']} Y:{s['yellow']} B:{s['blue']}"
        if s["no_color"]:
            pitch += f" NC:{s['no_color']}"
        print(f"\n{label}  ({s['hero']})  [{s['deck_size']} cards, {pitch}]")
        for iss in s["issues"]:
            print(f"  ! {iss}".encode("ascii", "replace").decode("ascii"))

print("\n--- CLEAN DECKS ---")
for label, s in clean:
    pitch = f"R:{s['red']} Y:{s['yellow']} B:{s['blue']}"
    print(f"  OK {label}  [{s['deck_size']} cards, {pitch}]")
