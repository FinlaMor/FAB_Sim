#!/usr/bin/env python3
"""Build a visual HTML replay of a game — card images moving around a board.

Either record a fresh game:
  python scripts/make_replay.py --deck1 decks/victor_goldmane_high_and_mighty_CC_lite.txt --deck2 decks/kayo_underhanded_cheat_CC_lite.txt --seed 11 -o recordings/replay.html

or build from an existing JSONL recording that contains snapshots
(record it with MemoryRecorder/JsonlRecorder snapshot_on={"decision","action_applied"}):
  python scripts/make_replay.py --from-recording recordings/game.jsonl -o replay.html

Open the output file in any browser. Card images stream from
images.talishar.net; cards without an image fall back to a text tile.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SNAPSHOT_KINDS = {"decision", "action_applied"}


def record_game(deck1: str, deck2: str, seed: int, max_turns: int) -> list[dict]:
    import random
    from engine.card import CardDB
    from engine.engine import new_game
    from engine.recorder import MemoryRecorder
    from rl_agents.random_agent import RandomAgent

    random.seed(seed)  # engine-internal randomness (random discards, …)
    rec = MemoryRecorder(snapshot_on=SNAPSHOT_KINDS)
    new_game(deck1, deck2, RandomAgent(seed=seed), RandomAgent(seed=seed + 1),
             CardDB(), p1_seed=seed, p2_seed=seed + 1, max_turns=max_turns,
             recorders=[rec])
    return rec.records


def load_recording(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def _norm_combat(combat) -> dict | None:
    if not combat:
        return None
    return {
        "attack": combat.get("attack_slug") or combat.get("attack_card"),
        "power": combat.get("attack_power"),
        "defense": combat.get("total_defense"),
        "defending": combat.get("defending_slugs") or combat.get("defending") or [],
        "keywords": combat.get("keywords") or combat.get("keyword_effects") or [],
    }


def build_frames(records: list[dict]) -> list[dict]:
    """One frame per snapshot-bearing record; events since the previous
    snapshot become the frame's log."""
    frames: list[dict] = []
    pending_log: list[str] = []

    for r in records:
        kind = r["kind"]
        if kind == "event":
            ev = r["event"]
            data = ev.get("data") or {}
            bits = [ev["type"]]
            if ev.get("card"):
                bits.append(str(ev["card"]))
            extras = {k: v for k, v in data.items()
                      if k in ("damage", "amount", "player_id", "target", "slug", "count")}
            if extras:
                bits.append(json.dumps(extras))
            pending_log.append(" ".join(bits))
            continue
        if kind == "step_change":
            pending_log.append(f"step: {r['from']} -> {r['to']}")
            continue
        if kind == "layer_resolved":
            pending_log.append(f"layer resolved: {r.get('card')}")
            continue

        snap = r.get("snapshot")
        if snap is None:
            if kind == "action_applied":
                pending_log.append(f"action: {json.dumps(r.get('action'))}")
            continue

        frame = {
            "kind": kind,
            "turn": r.get("turn"),
            "step": r.get("step"),
            "log": pending_log,
            "snapshot": {
                **snap,
                "combat": _norm_combat(snap.get("combat")),
            },
        }
        if kind == "decision":
            frame["decision"] = {
                "player_id": r.get("player_id"),
                "context": r.get("context"),
                "options": r.get("options"),
                "chosen": r.get("chosen"),
                "chosen_index": r.get("chosen_index"),
            }
        elif kind == "action_applied":
            frame["action"] = r.get("action")
        elif kind == "game_end":
            frame["result"] = {"winner": r.get("winner"),
                               "turns": r.get("individual_turns")}
        frames.append(frame)
        pending_log = []

    if pending_log and frames:
        frames[-1]["log"] = frames[-1]["log"] + pending_log
    return frames


def collect_slugs(frames: list[dict]) -> set[str]:
    slugs: set[str] = set()

    def walk(obj):
        if isinstance(obj, str):
            slugs.add(obj)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)

    for f in frames:
        snap = f["snapshot"]
        for p in snap["players"].values():
            for key in ("hand", "graveyard", "pitch", "arsenal", "banished",
                        "permanents", "items", "auras", "allies", "tokens"):
                walk(p.get(key) or [])
            walk(p.get("equipment") or {})
            slugs.add(p.get("hero") or "")
        combat = snap.get("combat")
        if combat:
            slugs.add(str(combat.get("attack")))
            walk(combat.get("defending") or [])
        walk(snap.get("stack") or [])
    slugs.discard("")
    return slugs


_COLOR_SUFFIX = re.compile(r"_(red|yellow|blue)$")


# Some cards' base print ID isn't hosted, but a foiling variant is (the only
# hosted image for Ironfist Revelation is SUP168-RF). Try the base ID, then
# rainbow/cold-foil variants. The viewer tries each candidate against both CDNs.
_FOIL_SUFFIXES = ("", "-RF", "-CF")


def image_map(slugs: set[str]) -> dict[str, list[str]]:
    """slug -> ordered list of candidate image IDs. The viewer tries each ID
    against both CDNs (Talishar hosts recent sets, the fab-cube cloudfront
    hosts promo/reprint sets) and falls back to a text tile when none loads.
    Game slugs carry a color suffix the index sometimes lacks
    (ironfist_revelation_red -> ironfist_revelation)."""
    with open(ROOT / "card_data" / "slug_index.json", encoding="utf-8") as f:
        index = json.load(f).get("by_slug")
    out: dict[str, list[str]] = {}
    for s in slugs:
        entry = index.get(s) or index.get(_COLOR_SUFFIX.sub("", s))
        if not entry:
            continue
        base_ids: list[str] = []
        for cid in [entry.get("defaultImage"),
                    *(entry.get("setIdentifiers") or []),
                    entry.get("specialImage")]:
            if cid and cid not in base_ids:
                base_ids.append(cid)
        candidates: list[str] = []
        for cid in base_ids:
            for suf in _FOIL_SUFFIXES:
                variant = cid + suf
                if variant not in candidates:
                    candidates.append(variant)
        if candidates:
            out[s] = candidates
    return out


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>FAB replay — __TITLE__</title>
<style>
  :root { --bg:#141a21; --panel:#1d2530; --line:#2c3949; --text:#d8e0ea; --dim:#8395a9; --accent:#e0a54c; }
  * { box-sizing:border-box; margin:0; }
  body { background:var(--bg); color:var(--text); font:13px/1.45 "Segoe UI",system-ui,sans-serif; }
  .app { display:grid; grid-template-columns:1fr 330px; grid-template-rows:auto 1fr; height:100vh; }
  header { grid-column:1/3; display:flex; align-items:center; gap:12px; padding:8px 14px;
           background:var(--panel); border-bottom:1px solid var(--line); }
  header h1 { font-size:15px; font-weight:600; margin-right:8px; }
  header button { background:#2a3646; color:var(--text); border:1px solid var(--line);
                  border-radius:6px; padding:4px 12px; cursor:pointer; font-size:13px; }
  header button:hover { background:#35455c; }
  #slider { flex:1; accent-color:var(--accent); }
  #framelabel { color:var(--dim); white-space:nowrap; }
  .board { overflow:auto; padding:10px 14px; display:flex; flex-direction:column; gap:6px; }
  .side { border:1px solid var(--line); border-radius:10px; background:var(--panel); padding:8px 10px; }
  .side h2 { font-size:13px; color:var(--accent); margin-bottom:6px; display:flex; gap:14px; align-items:baseline; }
  .side h2 .stat { color:var(--text); font-weight:400; } .side h2 .stat b { color:#fff; }
  .zones { display:flex; flex-wrap:wrap; gap:10px; }
  .sidegrid { display:grid; grid-template-columns:auto 1fr auto; gap:16px; align-items:start; }
  .equip { display:flex; flex-direction:column; gap:4px; }
  .equiprow { display:flex; gap:8px; }
  .centercol { display:flex; flex-direction:column; gap:8px; }
  .piles { display:grid; gap:4px 8px; align-items:end;
           grid-template-areas: ". grave" "pitch deck" ". banish"; }
  .zone { min-width:64px; }
  .zone .zl { color:var(--dim); font-size:10px; text-transform:uppercase; letter-spacing:.06em; margin-bottom:3px; }
  .cards { display:flex; flex-wrap:wrap; gap:4px; min-height:72px; }
  .card { width:52px; height:72px; border-radius:4px; background:#26303d; border:1px solid var(--line);
          overflow:hidden; position:relative; flex:none; transition:transform .08s; }
  .card img { width:100%; height:100%; object-fit:cover; display:block; }
  .card .nm { position:absolute; inset:0; padding:3px; font-size:8.5px; color:var(--text);
              overflow:hidden; display:none; }
  .card.noimg .nm { display:block; } .card.noimg img { display:none; }
  .card:hover { transform:scale(2.6); z-index:50; box-shadow:0 4px 18px #000c; }
  .pile { width:52px; height:72px; border-radius:4px; border:1px dashed var(--line); color:var(--dim);
          display:flex; align-items:center; justify-content:center; font-size:15px; flex:none; }
  .combat { border:1px solid #5c3a2c; border-radius:10px; background:#221a16; padding:8px 10px; }
  .combat h2 { font-size:13px; color:#e0764c; margin-bottom:6px; }
  .combat .row { display:flex; align-items:center; gap:14px; }
  .vs { font-size:18px; color:var(--dim); }
  .combat .pw { font-size:15px; } .combat .pw b { color:#e0764c; font-size:19px; }
  aside { border-left:1px solid var(--line); background:var(--panel); overflow-y:auto; padding:10px 12px;
          display:flex; flex-direction:column; gap:10px; }
  aside h3 { font-size:12px; color:var(--accent); text-transform:uppercase; letter-spacing:.06em; }
  .decision { border:1px solid var(--line); border-radius:8px; padding:8px; background:#232d3a; }
  .decision .ctx { color:var(--dim); margin-bottom:6px; }
  .opt { padding:4px 6px; border-radius:5px; margin-bottom:3px; background:#1a2230; font-family:Consolas,monospace;
         font-size:11px; word-break:break-all; }
  .opt.chosen { background:#3d3117; border:1px solid var(--accent); }
  #log { font-family:Consolas,monospace; font-size:11px; color:var(--dim); white-space:pre-wrap; word-break:break-all; }
  #log .hit { color:#e0764c; } #log .step { color:#5f7d9c; }
  kbd { background:#2a3646; border-radius:3px; padding:0 5px; border:1px solid var(--line); }
</style></head><body>
<div class="app">
  <header>
    <h1>__TITLE__</h1>
    <button id="prev">&#9664;</button>
    <button id="next">&#9654;</button>
    <input type="range" id="slider" min="0" value="0">
    <span id="framelabel"></span>
    <span style="color:var(--dim)">keys: <kbd>&#8592;</kbd><kbd>&#8594;</kbd></span>
  </header>
  <div class="board">
    <div class="side" id="p2side"></div>
    <div class="combat" id="combat"></div>
    <div class="side" id="p1side"></div>
  </div>
  <aside>
    <div id="decisionbox"></div>
    <h3>Events since last frame</h3>
    <div id="log"></div>
  </aside>
</div>
<script>
const FRAMES = __FRAMES__;
const IMAGES = __IMAGES__;
// Neither CDN is complete: Talishar hosts recent sets (UPR, HVY, MST…),
// the fab-cube cloudfront hosts promo/reprint sets (SUP, PEN, MPG, SEA…).
// Try every printing ID against both hosts before falling back to a tile.
const IMG_HOSTS = [
  "https://images.talishar.net/public/cardimages/english/",
  "https://d2wlb52bya4y8z.cloudfront.net/media/cards/large/",
];

function cardEl(slug){
  const d = document.createElement('div');
  d.className = 'card'; d.title = slug;
  const img = document.createElement('img');
  const nm = document.createElement('div'); nm.className='nm'; nm.textContent = slug.replaceAll('_',' ');
  // Build id × host url list.
  const urls = [];
  for (const id of (IMAGES[slug] || []))
    for (const host of IMG_HOSTS) urls.push(host + id + '.webp');
  let i = 0;
  if (urls.length){
    img.src = urls[0];
    img.onerror = () => {
      i += 1;
      if (i < urls.length) img.src = urls[i];
      else d.classList.add('noimg');
    };
  }
  else d.classList.add('noimg');
  d.append(img, nm);
  return d;
}
function zone(label, slugs, opts={}){
  const z = document.createElement('div'); z.className='zone';
  const zl = document.createElement('div'); zl.className='zl'; zl.textContent = label; z.append(zl);
  const cs = document.createElement('div'); cs.className='cards';
  if (opts.pile !== undefined){
    const p = document.createElement('div'); p.className='pile'; p.textContent = opts.pile; cs.append(p);
  }
  (slugs||[]).forEach(s => cs.append(cardEl(s)));
  z.append(cs);
  return z;
}
function renderSide(el, pid, p){
  el.innerHTML = '';
  const h = document.createElement('h2');
  h.innerHTML = `P${pid} &mdash; ${(p.hero||'').replaceAll('_',' ')}
    <span class="stat">life <b>${p.life}</b></span>
    <span class="stat">res <b>${p.resources}</b></span>
    <span class="stat">AP <b>${p.action_points}</b></span>`;
  el.append(h);

  const grid = document.createElement('div'); grid.className='sidegrid';

  // LEFT — equipment cross: head / chest+arms / legs (FaB board layout)
  const eq = document.createElement('div'); eq.className='equip';
  const eqz = p.equipment || {};
  eq.append(zone('Head',  eqz.head  || []));
  const mid = document.createElement('div'); mid.className='equiprow';
  mid.append(zone('Chest', eqz.chest || []));
  mid.append(zone('Arms',  eqz.arms  || []));
  eq.append(mid);
  eq.append(zone('Legs',  eqz.legs  || []));
  grid.append(eq);

  // CENTER — hero + weapons + arena permanents; hand + arsenal below
  const mid2 = document.createElement('div'); mid2.className='centercol';
  const top = document.createElement('div'); top.className='zones';
  top.append(zone('Hero', [p.hero].filter(Boolean)));
  const weapons = [...(eqz.weapon1||[]), ...(eqz.weapon2||[])];
  if (weapons.length) top.append(zone('Weapons', weapons));
  const arena = [...(p.items||[]), ...(p.auras||[]), ...(p.allies||[]), ...(p.tokens||[]), ...(p.permanents||[])];
  if (arena.length) top.append(zone('Arena', arena));
  mid2.append(top);
  // Hand sits in its own row ABOVE the arsenal (arsenal is the front row).
  const handrow = document.createElement('div'); handrow.className='zones';
  handrow.append(zone('Hand', p.hand));
  mid2.append(handrow);
  const arsrow = document.createElement('div'); arsrow.className='zones';
  arsrow.append(zone('Arsenal', p.arsenal));
  mid2.append(arsrow);
  grid.append(mid2);

  // RIGHT — piles: graveyard above deck, banish below, pitch left of deck
  const piles = document.createElement('div'); piles.className='piles';
  const grave = zone('Graveyard', p.graveyard.slice(-2), {pile: p.graveyard.length}); grave.style.gridArea='grave';
  const pitch = zone('Pitch', p.pitch); pitch.style.gridArea='pitch';
  const deck  = zone('Deck', [], {pile: p.deck_count}); deck.style.gridArea='deck';
  const ban   = zone('Banished', p.banished || []); ban.style.gridArea='banish';
  piles.append(grave, pitch, deck, ban);
  grid.append(piles);

  el.append(grid);
}
function renderCombat(el, c, stack){
  el.innerHTML = '<h2>Combat / Stack</h2>';
  const row = document.createElement('div'); row.className='row';
  if (c && c.attack){
    row.append(cardEl(String(c.attack)));
    const pw = document.createElement('div'); pw.className='pw';
    pw.innerHTML = `<b>${c.power??'?'}</b> power &nbsp;vs&nbsp; <b>${c.defense??0}</b> defense
      ${c.keywords && c.keywords.length ? '<br><span style="color:#8395a9">'+c.keywords.join(', ')+'</span>':''}`;
    row.append(pw);
    if ((c.defending||[]).length){
      const vs = document.createElement('div'); vs.className='vs'; vs.textContent='&#128737;'; vs.innerHTML='&#128737;';
      row.append(vs);
      c.defending.forEach(s => row.append(cardEl(String(s))));
    }
  } else {
    const idle = document.createElement('span'); idle.style.color='var(--dim)';
    idle.textContent = 'no combat';
    row.append(idle);
  }
  if ((stack||[]).length){
    const st = document.createElement('div'); st.style.marginLeft='24px';
    st.innerHTML = '<span style="color:#8395a9">stack:</span>';
    const cs = document.createElement('span'); cs.style.display='inline-flex'; cs.style.gap='4px'; cs.style.marginLeft='6px';
    stack.forEach(s => cs.append(cardEl(s)));
    st.append(cs); row.append(st);
  }
  el.append(row);
}
function renderDecision(el, frame){
  el.innerHTML = '';
  if (!frame.decision){
    if (frame.action){
      el.innerHTML = `<h3>Action applied</h3><div class="decision"><div class="opt chosen">${JSON.stringify(frame.action)}</div></div>`;
    } else if (frame.result){
      el.innerHTML = `<h3>Game over</h3><div class="decision">Winner: P${frame.result.winner} after ${frame.result.turns} turns</div>`;
    }
    return;
  }
  const d = frame.decision;
  el.innerHTML = `<h3>Decision &mdash; P${d.player_id}</h3>`;
  const box = document.createElement('div'); box.className='decision';
  box.innerHTML = `<div class="ctx">${d.context||''}</div>`;
  (d.options||[]).forEach((o,i)=>{
    const div = document.createElement('div');
    div.className = 'opt' + (i===d.chosen_index ? ' chosen':'');
    div.textContent = typeof o==='object' ? JSON.stringify(o) : String(o);
    box.append(div);
  });
  if (d.chosen_index===null || d.chosen_index===undefined){
    const div = document.createElement('div'); div.className='opt chosen';
    div.textContent = 'chosen: ' + (typeof d.chosen==='object'?JSON.stringify(d.chosen):String(d.chosen));
    box.append(div);
  }
  el.append(box);
}
function show(i){
  i = Math.max(0, Math.min(FRAMES.length-1, i));
  cur = i;
  const f = FRAMES[i];
  slider.value = i;
  framelabel.textContent = `frame ${i+1}/${FRAMES.length} — turn ${f.turn} · ${f.step} · ${f.kind}`;
  const snap = f.snapshot;
  renderSide(document.getElementById('p1side'), 1, snap.players["1"] || snap.players[1]);
  renderSide(document.getElementById('p2side'), 2, snap.players["2"] || snap.players[2]);
  renderCombat(document.getElementById('combat'), snap.combat, snap.stack);
  renderDecision(document.getElementById('decisionbox'), f);
  document.getElementById('log').innerHTML =
    (f.log||[]).map(l => `<div class="${l.startsWith('hit')?'hit':(l.startsWith('step')?'step':'')}">${l}</div>`).join('');
}
let cur = 0;
const slider = document.getElementById('slider');
const framelabel = document.getElementById('framelabel');
slider.max = FRAMES.length-1;
document.getElementById('prev').onclick = () => show(cur-1);
document.getElementById('next').onclick = () => show(cur+1);
slider.oninput = e => show(+e.target.value);
document.addEventListener('keydown', e => {
  if (e.key==='ArrowLeft') show(cur-1);
  if (e.key==='ArrowRight') show(cur+1);
});
show(0);
</script></body></html>
"""


def build_html(frames: list[dict], title: str) -> str:
    images = image_map(collect_slugs(frames))
    html = HTML_TEMPLATE
    html = html.replace("__TITLE__", title)
    html = html.replace("__FRAMES__", json.dumps(frames))
    html = html.replace("__IMAGES__", json.dumps(images))
    return html


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--deck1", default="decks/victor_goldmane_high_and_mighty_CC_lite.txt")
    ap.add_argument("--deck2", default="decks/kayo_underhanded_cheat_CC_lite.txt")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--max-turns", type=int, default=60)
    ap.add_argument("--from-recording", help="build from an existing snapshot-bearing JSONL")
    ap.add_argument("-o", "--out", default="recordings/replay.html")
    args = ap.parse_args()

    if args.from_recording:
        records = load_recording(args.from_recording)
        title = Path(args.from_recording).stem
    else:
        records = record_game(args.deck1, args.deck2, args.seed, args.max_turns)
        title = f"{Path(args.deck1).stem} vs {Path(args.deck2).stem} (seed {args.seed})"

    frames = build_frames(records)
    if not frames:
        print("No snapshot-bearing records found — record with "
              "snapshot_on={'decision','action_applied'}.")
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(frames, title), encoding="utf-8")
    print(f"Wrote {out} ({len(frames)} frames, {out.stat().st_size//1024} KB) — open it in a browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
