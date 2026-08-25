"""Build card_data/release_notes.json from the official release notes.

The card database carries printed text and stats and no rulings field at all,
so without this the notes exist nowhere the engine or the drafting pass can see
them. They are worth having because printed text says WHAT a card does and the
notes routinely settle WHEN it is checked -- which decides whether an ability is
static or triggered, and is usually not recoverable from the text. Aggressive
Pounce is the case that prompted this: a drafting run made it a TRIGGERED
ON_ATTACK, and the note says the condition is "always checking".

Source: https://fabtcg.com/rules-and-policy-center/release-notes/
robots.txt allows all agents (`Disallow:` empty). The site 403s a non-browser
User-Agent, so one is set; pages are cached under --cache and requests are
spaced by --delay so a re-run costs the site nothing.

Page shape, per card:

    <p class="wp-block-paragraph"><strong>Full Name | Short</strong></p>
    <p …>type line</p>  <p …>stats</p>  <p …>printed text</p>
    <ul class="wp-block-list"><li>ruling</li><li>ruling</li></ul>

so a <strong> inside a block paragraph opens a card and the <li>s before the
next one are its notes.

NAMES, NOT SLUGS. A release note is written once for a card and applies to
every colour printing of it, which is exactly right: the rulings are about the
ability, and the printings differ only in numbers. Names are matched against
slug_index; one entry is stored per card and the other printings point at it
with `same_as`.

    python scripts/scrape_release_notes.py            # fetch, parse, write
    python scripts/scrape_release_notes.py --offline  # re-parse the cache only
"""
from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "card_data" / "release_notes.json"
SLUG_INDEX = ROOT / "card_data" / "slug_index.json"
INDEX_URL = "https://fabtcg.com/rules-and-policy-center/release-notes/"
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/120.0 Safari/537.36")}

#: The game symbols are <img alt="…"> in the HTML and {x} tokens in the card
#: text this project already stores. Matching the existing convention means a
#: note reads the same way the printed text does.
SYMBOL = {"power": "{p}", "resource": "{r}", "life": "{h}", "health": "{h}",
          "defense": "{d}", "defence": "{d}", "intellect": "{i}",
          "chi": "{chi}"}


def _fetch(url: str, cache: Path, delay: float, offline: bool) -> str:
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    if offline:
        return ""
    time.sleep(delay)
    raw = urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=60
    ).read().decode("utf-8", "replace")
    cache.write_text(raw, encoding="utf-8")
    return raw


def _text(fragment: str) -> str:
    """HTML fragment -> the text a person would read, symbols included."""
    def _img(m):
        alt = (re.search(r'alt="([^"]*)"', m.group(0)) or [None, ""])[1]
        return SYMBOL.get(alt.strip().lower(), "")
    fragment = re.sub(r"<img\b[^>]*>", _img, fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    fragment = html.unescape(fragment)
    # The pages use U+FFFD where an apostrophe should be, often enough that
    # leaving it makes the notes unpleasant to read and hard to grep.
    fragment = fragment.replace("\ufffd", "'").replace("\u2019", "'")
    return re.sub(r"\s+", " ", fragment).strip()


def _parse(page: str) -> dict[str, list[str]]:
    """Card name -> its notes, in document order."""
    out: dict[str, list[str]] = {}
    current = None
    # TWO LAYOUTS. Newer set pages open a card with
    #   <p class="wp-block-paragraph"><strong>Name | Short</strong></p>
    # and older ones (Welcome to Rathe, Arcane Rising, Crucible, Monarch,
    # Tales of Aria) use <h4>Name</h4>. Reading only the first left the older
    # pages with no card boundaries at all, so every <strong> inside body text
    # became a "card" and swallowed the rest of the section: single entries
    # thousands of characters long containing a dozen cards' notes. The
    # giveaway was the card counts -- 19 for a whole set where a comparable one
    # had 229.
    token = re.compile(
        r'<h[34][^>]*>(.*?)</h[34]>'
        r'|<p class="wp-block-paragraph"><strong>(.*?)</strong></p>'
        r'|<li>(.*?)</li>', re.S)
    for m in token.finditer(page):
        raw_name = m.group(1) if m.group(1) is not None else m.group(2)
        if raw_name is not None:
            name = _text(raw_name)
            # "Full Name | Short" -- section headings ("New Keywords") carry no
            # pipe and no notes, so they collect nothing and drop out below.
            name = name.split("|")[0].strip()
            # A card name is SHORT. Anything long is body text that happened to
            # be bold, and treating it as a name is exactly how one entry ends
            # up holding a whole section.
            if len(name) > 80:
                name = ""
            current = name or None
            if current:
                out.setdefault(current, [])
        elif current:
            note = _text(m.group(3))
            if note:
                out[current].append(note)
    return {k: v for k, v in out.items() if v}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", default="C:/tmp/rn", help="page cache directory")
    ap.add_argument("--delay", type=float, default=2.0,
                    help="seconds between requests (be polite)")
    ap.add_argument("--offline", action="store_true",
                    help="parse the cache only, fetch nothing")
    args = ap.parse_args()
    cache = Path(args.cache)

    index = _fetch(INDEX_URL, cache / "_index.html", args.delay, args.offline)
    urls = sorted(set(re.findall(
        r'href="(https://fabtcg\.com/rules-and-policy-center/release-notes/[a-z0-9-]+/)"',
        index)))
    urls = [u for u in urls if u.rstrip("/") != INDEX_URL.rstrip("/")]
    print(f"{len(urls)} set pages")

    notes: dict[str, list[str]] = {}
    for url in urls:
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        page = _fetch(url, cache / f"{slug}.html", args.delay, args.offline)
        if not page:
            print(f"  {slug:44} (not cached, skipped)")
            continue
        found = _parse(page)
        for name, items in found.items():
            notes.setdefault(name, [])
            for it in items:
                if it not in notes[name]:
                    notes[name].append(it)
        print(f"  {slug:44} {len(found):4} cards")

    # names -> slugs (needed by the contents filter below as well)
    idx = json.loads(SLUG_INDEX.read_text(encoding="utf-8"))["by_slug"]
    by_name: dict[str, list[str]] = {}
    for slug, card in idx.items():
        nm = (card.get("name") or "").strip().lower()
        if nm:
            by_name.setdefault(nm, []).append(slug)

    # A SET PAGE'S TABLE OF CONTENTS IS A LIST OF <li> CARD NAMES, and several
    # set names are also card names ("Uprising"), so the page heading opened a
    # card block and collected the whole index as its "rulings". A real ruling
    # is a sentence; a bare card name is navigation. Dropping any note that IS
    # a card name removes the contents lists without touching real notes, none
    # of which are a bare name.
    all_names = {n for n in by_name}

    def _is_navigation(note: str) -> bool:
        # A contents entry is a card NAME, sometimes with a colour marker
        # appended ("Trade In (red/yel/blu)"), sometimes a keyword section
        # heading ("Material"). A real ruling is a SENTENCE, so anything short
        # that does not end in a full stop is not one.
        base = re.sub(r"\s*\([^)]*\)\s*$", "", note).strip().lower()
        if base in all_names:
            return True
        return len(note) < 60 and not note.rstrip().endswith(".")

    cleaned: dict[str, list[str]] = {}
    for name, items in notes.items():
        keep = [it for it in items if not _is_navigation(it)]
        if keep:
            cleaned[name] = keep
    dropped = sum(len(v) for v in notes.values()) - sum(len(v) for v in cleaned.values())
    print(f"dropped {dropped} table-of-contents entries")
    notes = cleaned

    by_slug: dict[str, dict] = {}
    matched = unmatched = 0
    for name, items in sorted(notes.items()):
        slugs = sorted(by_name.get(name.strip().lower(), []))
        if not slugs:
            unmatched += 1
            continue
        matched += 1
        primary = slugs[0]
        by_slug[primary] = {
            "name": name,
            "printed": idx[primary].get("functionalText"),
            "notes": items,
            "source": "fabtcg.com release notes",
        }
        for other in slugs[1:]:
            by_slug[other] = {"same_as": primary}

    about = json.loads(OUT.read_text(encoding="utf-8"))["_about"] if OUT.exists() else []
    OUT.write_text(json.dumps({"_about": about, "by_slug": by_slug},
                              indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"\ncards with notes : {len(notes)}")
    print(f"matched to slugs : {matched}  ({len(by_slug)} slugs incl. printings)")
    print(f"unmatched names  : {unmatched}")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
