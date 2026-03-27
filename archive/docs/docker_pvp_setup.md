# Running PvP Games via Talishar Docker Backend

This guide walks through spinning up the Talishar PHP backend in Docker and running
automated PvP games through it using `scripts/run_talishar_games.py`.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Engine + Compose. Enable WSL2 integration on Windows. |
| Python 3.10+ | For the FAB_Sim scripts. |
| FAB_Sim repo cloned | Talishar backend lives in `third_party/Talishar_official/`. |

---

## Step 1 — Clone the Talishar submodule (if not already done)

The backend is tracked as a Git submodule. From the repo root:

```bash
git submodule update --init --recursive
```

After this, `third_party/Talishar_official/` should be populated with PHP files.

---

## Step 2 — Build and start the Docker stack

```bash
cd third_party/Talishar_official
bash start.sh
```

`start.sh` does the following:
- Copies `HostFiles/RedirectorTemplate.php` → `HostFiles/Redirector.php` (if missing)
- Creates `HostFiles/GameIDCounter.txt` initialized to `1`
- Creates `Games/` directory with open permissions
- Runs `docker compose up -d`

**Services that come up:**

| Service | Host port | Purpose |
|---|---|---|
| `web-server` | **8080** | Apache + PHP 8.3 game backend |
| `mysql-server` | (internal) | FAB Online database (`fabonline`) |
| `phpmyadmin` | **5001** | DB admin UI |
| `redis` | **6382** | Session/state cache |

Wait ~15–30 seconds for the database to initialize on first run (MySQL is importing
the schema from `Database/`).

### Verify the stack is healthy

```bash
docker compose ps                        # all services should show "Up"
curl http://localhost:8080/game/GetNextTurn.php   # expect a JSON or PHP error (not a connection error)
```

---

## Step 3 — Set up the Python environment

From the repo root:

```bash
python -m venv .venv

.venv\Scripts\activate

pip install requests
```

> The script intentionally avoids importing PyTorch so no GPU setup is needed for
> running games — only `requests` is required.

---

## Step 4 — Run a PvP game

All commands are run from the **repo root** with the virtual environment active.

### Single game (both players random agents)

```bash
python scripts/run_talishar_games.py
```

Default: Oscillio (P1) vs Kayo (P2), max 50 turns, verbose output.

### Single game with specific decks

```bash
python scripts/run_talishar_games.py \
    --p1-deck decks/oscillio_constella_intelligence_CC_lite.txt \
    --p2-deck decks/kayo_underhanded_cheat_CC_lite.txt \
    --max-turns 30
```

### Random deck pairing

```bash
python scripts/run_talishar_games.py --random-decks
```

Available decks in `decks/`:

| File | Hero |
|---|---|
| `oscillio_constella_intelligence_CC_lite.txt` | Oscillio |
| `kayo_underhanded_cheat_CC_lite.txt` | Kayo |
| `marlynn_treasure_hunter_CC_lite.txt` | Marlynn |
| `arakni_marionette_CC_lite.txt` | Arakni |
| `ser_boltyn_breaker_of_dawn_CC.txt` | Boltyn |
| `tuffnut_bumbling_hulkster_CC.txt` | Tuffnut |
| `valda_seismic_impact_CC.txt` | Valda |

### Multiple parallel games (single container)

```bash
# 10 games, up to 4 parallel workers, benchmark output only
python scripts/run_talishar_games.py --num-games 10 --benchmark

# 10 random pairings
python scripts/run_talishar_games.py --random-decks --num-games 10 --benchmark
```

### Multiple parallel games (multi-container — recommended for large runs)

Run multiple Talishar Docker containers on different ports for higher throughput.
Each container handles 1 game at a time, eliminating PHP CPU contention.

```bash
# Start additional containers (see "Multi-Container Setup" below)
# Then distribute games across them with comma-separated --base-url:
python scripts/run_talishar_games.py --base-url "http://localhost:8080/game,http://localhost:8081/game,http://localhost:8082/game,http://localhost:8083/game" --num-games 200 --workers 4 --random-decks --max-turns 30 --game-timeout 600
```

Games are distributed round-robin across containers (game 1 → port 8080,
game 2 → port 8081, etc.). Match `--workers` to the number of containers.

### vs Practice Dummy (single-agent mode)

```bash
python scripts/run_talishar_games.py --mode dummy --num-games 4
```

---

## CLI Reference

```
python scripts/run_talishar_games.py [OPTIONS]

  --base-url URL        Talishar server URL  (default: http://localhost:8080/game)
                        For multi-container setups, comma-separate URLs:
                        "http://localhost:8080/game,http://localhost:8081/game,..."
  --mode {pvp,dummy}    pvp = control both seats; dummy = vs Practice Dummy
  --p1-deck PATH        P1 deck file
  --p2-deck PATH        P2 deck file
  --random-decks        Pick random decks from decks/ for each game
  --max-turns N         Turn cap per game  (default: 50)
  --max-actions N       Action iteration cap per game; 0 = max_turns*60  (default: 0)
  --seed N              Global RNG seed
  --num-games N         Number of games; >1 runs in parallel
  --workers N           Max parallel threads  (default: 4)
  --game-timeout S      Per-game wall-clock timeout in seconds  (default: 600)
  --benchmark           Suppress per-action output; print summary only
  --db PATH             SQLite database path  (default: data/talishar_games.db)
  --no-save             Disable saving game data to SQLite
  --info                Print HTTP optimisation details and exit
```

---

## HTTP Optimisations (already applied)

The patched `ProcessInput.php` in this repo supports `?returnState=1`, which fuses
the submit-action and get-state calls into one HTTP round-trip.

| Mode | Before (calls/action) | After (calls/action) | Speedup |
|---|---|---|---|
| PvP | 3 | 1–2 | ~2–3× |
| Dummy | 2 | 1 | ~2× |

---

## Multi-Container Setup (for large data collection runs)

A single Talishar Docker container can only handle ~1-2 concurrent games before
PHP CPU contention causes requests to slow down and games to timeout. For bulk
data collection, run multiple independent containers on different ports.

### Starting additional containers

Each additional container needs its own port mapping. From the repo root:

```bash
cd third_party/Talishar_official

# Container 1 is already running on port 8080 via start.sh

# Start containers 2-4 on ports 8081-8083:
for PORT in 8081 8082 8083; do
    docker compose -p talishar_${PORT} \
        -f docker-compose.yml \
        up -d \
        --build
    # Remap the web-server port (edit docker-compose.yml or use --scale)
done
```

Alternatively, create a `docker-compose.multi.yml` that defines separate services
for each port, or simply duplicate the stack with different project names and port
overrides.

**Quick manual approach** — duplicate the web-server on a new port:

```bash
# Clone the container with a different host port
docker run -d --name talishar_8081 \
    -p 8081:80 \
    -v "$(pwd)/HostFiles:/var/www/html/HostFiles" \
    -v "$(pwd)/Games:/var/www/html/Games" \
    talishar_official-web-server

docker run -d --name talishar_8082 \
    -p 8082:80 \
    -v "$(pwd)/HostFiles:/var/www/html/HostFiles" \
    -v "$(pwd)/Games:/var/www/html/Games" \
    talishar_official-web-server
```

> **Note:** Each container shares the same `Games/` directory for game state files.
> This is fine because each game gets a unique `gameName` ID — there is no conflict
> between containers.

### Throughput guidelines

| Containers | Workers | Games/container | Expected games/hour |
|-----------|---------|----------------|---------------------|
| 1         | 1       | 1              | 15-20               |
| 1         | 2       | 2              | 20-30               |
| 4         | 4       | 1              | 60-80               |
| 4         | 4       | 1 (max-turns 30) | 100-130           |

### Tuning WSL2 resources (Windows)

Docker Desktop on Windows runs inside WSL2. Give it more CPU/RAM by creating
or editing `%USERPROFILE%\.wslconfig`:

```ini
[wsl2]
memory=12GB
processors=6
swap=4GB
```

Then restart: `wsl --shutdown` and reopen Docker Desktop.

---

## Stopping the Stack

```bash
cd third_party/Talishar_official
bash stop.sh          # docker compose down
```

To also wipe the database volume:

```bash
docker compose down -v
```

---

## Troubleshooting

**`ERROR: Cannot reach Talishar at http://localhost:8080/game`**
- Run `docker compose ps` in `third_party/Talishar_official/` — all services must show `Up`.
- Check logs: `docker compose logs web-server`.

**`docker compose up` fails with port conflict**
- Another process is using port 8080. Change the host port in `docker-compose.yml`:
  `"8181:80"` then pass `--base-url http://localhost:8181/game` to the script.

**MySQL keeps restarting on first boot**
- The schema import from `Database/` can take 30–60 seconds. Wait and re-check with
  `docker compose ps`.

**Games hang and hit the timeout**
- Reduce `--workers` to match or stay below the number of containers (1 worker per container).
- Lower `--max-turns` (30 is usually enough for decisive games).
- Use `--max-actions 1500` to hard-cap iterations per game.
- Increase `--game-timeout` if games are completing but slowly.
- Check `docker compose logs web-server` for PHP errors.

**Most games skipped in parallel runs (e.g., 28/2000)**
- Too many workers hitting one container. Use multi-container setup (see above).
- Rule of thumb: never exceed 2 workers per container.

**`ModuleNotFoundError: No module named 'requests'`**
- Make sure the virtual environment is active and `pip install requests` has been run.
