# Talishar Backend — Operational Pain Points & Costs

**Date:** 2026-03-24
**Subtask:** 1-3 (Data Gathering — Talishar Pain Point Catalog)

---

## 1. Reliability Issues

### 1.1 Massive Game Timeout Rate (87.5%)
- **Evidence:** HANDOFF.md line 79: "32-way parallel run (32 games × 32 containers) showed 4/32 completing, 28 timing out at 600s"
- **Impact:** Only 12.5% of games complete successfully under parallel load. Data collection throughput is severely degraded.

### 1.2 MySQL Container Crashes Under Load
- **Evidence:** HANDOFF.md line 80: "MySQL containers crash under heavy parallel load (seen clearly in docker ps)"
- **Impact:** Game state is stored in MySQL; a crash mid-game kills that game silently. Requires manual container restart.

### 1.3 Silent Action Rejection
- **Evidence:** `game_backends.py` lines 1073, 1291: "Talishar silently rejected this action — remove and retry"
- The game loop must detect rejections by comparing pre/post state hashes (`_state_changed()`, line 835) and retry with different actions. After 10 consecutive rejections, it force-passes (lines 1079-1084, 1296-1301).
- **Impact:** Adds complexity to the game loop, wastes HTTP round-trips, and can cause games to stall.

### 1.4 PHP Fatal Errors in Responses
- **Evidence:** `game_backends.py` line 279: `if "Fatal error" in body or "Cannot redeclare" in body: raise RuntimeError(f"Talishar PHP error in GetNextTurn: {body[:400]}")`
- **Impact:** Unrecoverable errors that terminate the game.

### 1.5 HTML Warning Prefix in JSON Responses
- **Evidence:** `game_backends.py` lines 22-30: `_parse_json()` must strip HTML warning prefixes before parsing JSON: `idx = body.find("{"); if idx > 0: body = body[idx:]`
- **Impact:** PHP warnings are injected into API responses, requiring fragile parsing workarounds.

### 1.6 Timeout Ghost Games (Misleading Metrics)
- **Evidence:** HANDOFF.md line 92: "When `_run_with_timeout` times out, it returns None (counted as 'skipped'), but the daemon thread continues running and saves transitions to the DB."
- **Impact:** Completed/skipped counts are inaccurate. The DB has more games than reported.

---

## 2. Resource Costs

### 2.1 Extreme Memory Consumption
- **Evidence:** HANDOFF.md line 23: "Running all 64 simultaneously uses ~6 GB RAM via VmmemWSL and causes MySQL crashes"
- **Safe limit:** 32 containers = ~3 GB RAM (HANDOFF.md line 24)
- **Per-container cost:** ~94 MB RAM per instance (each is web + MySQL + Redis)
- **Impact:** 3-6 GB RAM consumed just for the game backend, limiting what else can run on the machine.

### 2.2 Three Containers Per Game Instance
- **Evidence:** HANDOFF.md lines 32-34 show each instance requires 3 Docker containers: `talishar_official-web-${i}-1`, `talishar_official-mysql-${i}-1`, `talishar_official-redis-${i}-1`
- 32 usable instances = 96 Docker containers running simultaneously
- **Impact:** Massive container management overhead.

### 2.3 Port Exhaustion
- **Evidence:** HANDOFF.md line 22: "Ports 8080–8143 (instance 0–63)"
- `run_talishar_games.py` line 389: URLs are parsed as comma-separated and round-robin assigned (line 452: `assigned_url = base_urls[i % len(base_urls)]`)
- **Impact:** 64 ports consumed; safe limit is 32 ports (8080-8111).

### 2.4 Slow Game Speed (~500ms/action Under Load)
- **Evidence:** HANDOFF.md line 81: "at 500ms/action under load = 800s > 600s timeout"
- Each action requires 1-2 HTTP round-trips (`game_backends.py` lines 958-959, 1126-1131)
- Even optimized with `returnState=1` fused calls, each action still requires network I/O to a PHP server
- **Impact:** A 1600-action game takes 800s under load, exceeding the 600s timeout.

---

## 3. Setup Complexity

### 3.1 Multi-Step Docker Startup + Manual Pruning
- **Evidence:** HANDOFF.md lines 27-35: After every reboot, must:
  1. `docker compose -f docker-compose.multi.yml up -d` (start all 64)
  2. Manually stop instances 32-63 with a loop to save RAM
- **Impact:** Error-prone manual process after every system restart.

### 3.2 Custom PHP Patches Required
- **Evidence:** `run_talishar_games.py` lines 8-10: "The patched ProcessInput.php with `returnState=1` support (already applied in this repo)"
- `game_backends.py` line 493-494: "Requires the patched ProcessInput.php that honours `returnState=1`. Falls back to None when the server doesn't return JSON (unpatched PHP)."
- **Impact:** The Talishar source must be patched for optimal performance. Upgrades risk breaking the patch.

### 3.3 Elaborate Deck Format Translation
- **Evidence:** `game_backends.py` lines 126-213: `_deck_file_to_talishar_slugs()` — 87 lines of code to translate FAB_Sim deck format to Talishar submission format, including Unicode normalization, HTML entity unescaping, color mapping, slot assignment via `_arena_card_slot()` (lines 97-116).
- **Impact:** Fragile translation layer that can silently produce wrong slugs.

### 3.4 Module Import Workaround
- **Evidence:** `run_talishar_games.py` lines 43-51: Must register a placeholder `rl_agents` module to avoid torch import: "Prevent rl_agents/__init__.py from pulling in torch (not needed here)."
- **Impact:** Import system hacks required to run the game script without pulling in ML dependencies.

---

## 4. Scalability Limits

### 4.1 Hard Cap at 32 Parallel Games
- **Evidence:** HANDOFF.md line 24: "Safe limit: 32 parallel workers max"
- HANDOFF.md line 83: "Recommendation: Run games with 8–16 parallel workers at a time, not 32"
- Effective recommendation is 8-16 concurrent games for stability.
- **Impact:** Data collection speed is bottlenecked by Docker container count.

### 4.2 Degraded Performance Under Parallelism
- **Evidence:** HANDOFF.md lines 79-82: At 32 parallel, 87.5% timeout rate. The pipeline with sequential batching "had better success."
- `run_talishar_games.py` line 357: "Reduce if Talishar Docker is on the same machine."
- **Impact:** Throughput scales inversely as parallelism increases beyond ~8-16 workers.

---

## 5. Debugging Difficulty

### 5.1 Opaque Error Reporting
- **Evidence:** Errors surface as HTTP status codes, PHP fatal error strings (line 279), or silent state non-changes (lines 1073, 1291). No structured error API.
- **Impact:** Debugging requires HTTP logging, PHP log inspection inside containers, and state-diff analysis.

### 5.2 Non-Deterministic Behavior
- **Evidence:** Game state depends on PHP server-side RNG, MySQL state, and HTTP timing. The `_state_changed()` function (line 835) uses full-state hashing as a proxy for action acceptance — an indirect, fallible signal.
- 5ms stall sleeps are scattered through the game loop (lines 1022, 1046, 1217, 1263) to handle timing issues.
- **Impact:** Cannot deterministically replay games or isolate bugs.

### 5.3 No Direct State Inspection
- **Evidence:** State is fetched via HTTP (`get_state()` at line 271) and must be parsed from JSON with HTML-prefix stripping. The state format is dictated by Talishar's PHP, not the Python codebase.
- **Impact:** Cannot set breakpoints in the game engine, inspect internal state, or step through logic.

---

## 6. Maintenance Burden

### 6.1 PHP Codebase We Don't Control
- **Evidence:** Talishar is a third-party PHP application in `third_party/Talishar_official/`. The Python side is an HTTP client adapter (`TalisharClient` class, 150+ lines at lines 216-594).
- **Impact:** Bug fixes require PHP knowledge and patching a codebase we don't maintain.

### 6.2 Complex HTTP Protocol Adaptation
- **Evidence:** `TalisharClient` has 12+ methods for HTTP interaction: `create_game`, `join_game`, `start_game`, `get_state`, `process_input`, `process_input_fused`, `submit_opt`, `submit_trigger_order`, `submit_action`, `submit_action_fused`, `parallel_get_states` — totaling ~380 lines.
- `_run_talishar_random_game` (lines 946-1106) and `_run_talishar_pvp_game` (lines 1109-1347) each have ~160-240 lines of game loop logic managing stalls, retries, rejections, and timeouts.
- **Impact:** ~780 lines of code dedicated purely to working around Talishar's HTTP interface.

### 6.3 Action Selection Workarounds
- **Evidence:** `_pick_talishar_random_fallback_action` (line 843) — 100+ lines of priority-based action selection with special cases for popups, OPT, trigger ordering, and zone selections that exist only because of Talishar's UI-oriented state format.
- `get_available_actions` (line 325) — 130+ lines parsing Talishar-specific zone fields (`playerHand`, `playerEquipment`, `playerArse`, `playerInputPopUp`, etc.)
- **Impact:** Agent code must understand Talishar's UI state model rather than clean game semantics.

---

## Summary Table

| Category | Pain Point | Severity | Evidence |
|----------|-----------|----------|----------|
| Reliability | 87.5% timeout rate | **Critical** | HANDOFF.md:79 — 28/32 games timeout |
| Reliability | MySQL crashes | **Critical** | HANDOFF.md:80 |
| Reliability | Silent action rejection | High | game_backends.py:1073,1291 |
| Reliability | PHP fatal errors | High | game_backends.py:279 |
| Reliability | HTML in JSON responses | Medium | game_backends.py:22-30 |
| Resource | 3-6 GB RAM for backend | High | HANDOFF.md:23 |
| Resource | 96 Docker containers (32 instances) | High | HANDOFF.md:32-34 |
| Resource | ~500ms/action under load | High | HANDOFF.md:81 |
| Setup | Manual post-reboot process | Medium | HANDOFF.md:27-35 |
| Setup | Custom PHP patches | Medium | run_talishar_games.py:8-10 |
| Setup | 87-line deck format translator | Medium | game_backends.py:126-213 |
| Scalability | Hard cap at 32 games | High | HANDOFF.md:24 |
| Scalability | Performance degrades >8 workers | High | HANDOFF.md:83 |
| Debugging | Opaque HTTP errors | High | game_backends.py:279 |
| Debugging | Non-deterministic | High | game_backends.py:835 |
| Maintenance | ~780 lines of HTTP adapter code | Medium | game_backends.py:216-1347 |
| Maintenance | Third-party PHP codebase | Medium | third_party/Talishar_official/ |
