# FAB_Sim — Session Handoff Document
**Date:** 2026-03-16
**Project:** `C:\Users\Joseph\Desktop\FAB_Sim`

---

## What This Project Is

A Flesh and Blood (FAB) TCG reinforcement learning simulator. It:
- Connects to locally-running **Talishar** (PHP game engine) Docker containers as the game backend
- Generates FAB hero decks heuristically via `scripts/generate_heuristic_decks.py`
- Runs self-play PvP games via `scripts/run_talishar_games.py`
- Stores game transitions in `data/talishar_games.db` (SQLite)
- Trains IQL (Implicit Q-Learning) agents on those transitions

---

## Current State

### Docker Setup
- **64 Talishar containers** defined in `third_party/Talishar_official/docker-compose.multi.yml`
- Ports 8080–8143 (instance 0–63), each with web + mysql + redis
- **IMPORTANT:** Running all 64 simultaneously uses ~6 GB RAM via VmmemWSL and causes MySQL crashes
- **Safe limit: 32 parallel workers max** (ports 8080–8111, instances 0–31)
- After reboot, start containers with:
  ```bash
  cd third_party/Talishar_official
  docker compose -f docker-compose.multi.yml up -d
  ```
  Then stop instances 32–63 to save RAM:
  ```bash
  for i in $(seq 32 63); do
    docker stop talishar_official-web-${i}-1 talishar_official-mysql-${i}-1 talishar_official-redis-${i}-1
  done
  ```

### Decks
- **144 generated decks** in `decks/generated/` — freshly generated with all legality fixes applied
- No lite/old decks remain (they were deleted due to bugs)
- Decks pass legality validation (zero violations)

### Database
- `data/talishar_games.db` — contains ~158 games / ~12k transitions from test runs
- Schema: `decks` table (game metadata) + `transitions` table (per-step RL data)

---

## What Was Fixed This Session

### 1. Deck Legality (`rl_agents/fab_constants.py`)
- Expanded `DESCRIPTOR` frozenset to include all card category types (action, attack, aura, ally, dragon, etc.), color keywords (red/yellow/blue), rarity tags (token/young/seasoned/veteran), and subtype tags
- Added `validate_deck_legality()` function

### 2. Deck Generator (`scripts/generate_heuristic_decks.py`)
- Fixed generic armor padding: now checks class legality before assigning generic equipment to a hero (was causing Brute equipment like "Scowling Flesh Bag" to appear in Warrior decks)
- Added pre-write validation via `validate_deck_legality` — warns on any violations before writing deck file
- Added `_is_legal()` filter applied to both deck pool and generic pool before card selection
- Fixed dead SQL clause removal (`AND card_type NOT IN ('token','hero')`)
- Added `rl_agents` stub module to avoid torch import errors

### 3. Deck Search (`rl_agents/deck_search.py`)
- Fixed `_mutate` remove-copy branch: re-adds popped card to unused pool
- Removed dead flex-candidate loop
- Fixed weapon fallback `existing_slugs` to include both weapons and equipment
- Added `_equip_legal()` class check in generic armor padding loop
- Added `validate_pool()` method using `validate_deck_legality`
- Removed dead SQL clause

### 4. Game Engine (`rl_agents/game_backends.py`)
- **Popup/button fix**: Added `_pick_talishar_random_fallback_action` priority block for `playerInputPopUp.active` — picks a popup button immediately instead of skipping
- **Mandatory action acceptance**: `is_mandatory = action.get("type") in ("button", "prompt_button")` — always accepts button/prompt_button submissions even if `_state_changed()` returns False (fixes clash top/bottom decision where state appears unchanged until both players choose)
- Applied to both `_run_talishar_random_game` and `_run_talishar_pvp_game`

---

## Known Remaining Issues

### 1. Games Still Timing Out
The 32-way parallel run (32 games × 32 containers) showed 4/32 completing, 28 timing out at 600s. Root cause is multi-factor:
- MySQL containers crash under heavy parallel load (seen clearly in docker ps)
- Some matchups generate 1600+ actions per game; at 500ms/action under load = 800s > 600s timeout
- The pipeline (run_pipeline.py) runs games in sequential loops (200 games × 5 loops) and had better success
- **Recommendation:** Run games with 8–16 parallel workers at a time, not 32

### 2. High-Action Turns Not Caught
Some decks (Arakni, Ira, Marlynn with action-rich effects) generate 300+ actions per turn, hitting the OPT cap. Some matchups have legitimate 1600+ actions but across many turns. The per-turn cap (300 actions/turn without turn advancement) correctly catches infinite trigger loops, but doesn't help with naturally long games.

### 3. Jarl Starting at 20 HP
`jarl_vetreii` resolves to 20 HP in Talishar even though `slug_index.json` lists health=40. This appears to be correct — Jarl Vetreiði in FAB Classic Constructed starts at 20 HP (he's effectively a young-statted hero without a published adult form). Not a bug.

### 4. Games Classified as "Skipped" But Data Saved
When `_run_with_timeout` times out, it returns None (counted as "skipped"), but the daemon thread continues running and saves transitions to the DB. The DB has more games than the "completed" counter shows. This is fine for data collection but misleading in the summary.

---

## How to Run Games

```bash
cd C:\Users\Joseph\Desktop\FAB_Sim

# 32 games, 32 workers, 32 containers (max safe)
URLS=$(python -c "print(','.join(f'http://localhost:{8080+i}/game' for i in range(32)))")
python -u scripts/run_talishar_games.py \
  --base-url "$URLS" \
  --num-games 32 --workers 32 \
  --mode pvp --seed 12345 \
  --random-decks --game-timeout 600
```

Or run the full pipeline (5 loops × 200 games):
```bash
python scripts/run_pipeline.py
```

---

## Key Files

| File | Purpose |
|------|---------|
| `rl_agents/game_backends.py` | Talishar HTTP client + PvP game loop |
| `rl_agents/fab_constants.py` | DESCRIPTOR frozenset + `validate_deck_legality()` |
| `rl_agents/deck_search.py` | Deck evolution/search for RL deck optimization |
| `scripts/generate_heuristic_decks.py` | Heuristic deck generator (produces `decks/generated/`) |
| `scripts/run_talishar_games.py` | CLI to run N games in parallel |
| `scripts/run_pipeline.py` | Full pipeline: deck gen → game collection → training |
| `data/talishar_games.db` | SQLite DB with game data |
| `card_data/slug_index.json` | FAB card index (by_slug, by_name) |
| `third_party/Talishar_official/docker-compose.multi.yml` | 64-instance Docker Compose |

---

## What To Do Next

1. **After reboot:** Start only 32 containers (instances 0–31), verify MySQL is stable, then run a 32-game test
2. **Investigate high-action matchups:** Which deck combos consistently hit 1600+ actions? Consider adding a per-turn action cap that still lets the turn advance
3. **Pipeline run:** Run `run_pipeline.py` with 32 workers to collect more training data
4. **Re-audit:** The AI/ML re-audit (todo item 9) was deferred — run the three audit agents against the current codebase after confirming game collection is stable
