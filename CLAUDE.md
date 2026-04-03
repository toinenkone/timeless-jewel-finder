# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Instructions for Claude

- After every `git push`, post the **Deployment Instructions** block below to the user.
- When the user asks for deployment instructions, post the **Deployment Instructions** block below.

## Deployment Instructions

After pushing new code, share this with the user:

```
### Deploy latest code on the server

ssh into the server and run:

cd /home/cc/code/timeless-jewel-finder
git pull
sudo systemctl restart jewel-finder

Check it's running:
sudo systemctl status jewel-finder
```

## Running the App

```bash
pip install -r requirements.txt
AUTH_USERNAME=admin AUTH_PASSWORD=yourpassword python app.py
# Open http://localhost:3122/timeless/
```

Credentials default to `admin` / `changeme` if env vars are not set. Always set them explicitly in production.

## Deployment

See the **Deployment** section at the bottom of this file for instructions on deploying to a new server.

## Architecture

Flask web app (`app.py`) backed by `data_loader.py`, serving a single-page HTML UI (`templates/index.html`).

### API Endpoints

All endpoints require HTTP Basic Auth.

| Method | Path | Body / Params | Description |
|--------|------|--------------|-------------|
| GET | `/timeless/` | — | Renders the UI |
| GET | `/timeless/api/jewel_types` | — | Returns list of supported jewel types with seed ranges |
| POST | `/timeless/api/search` | `{"jewel_type": int, "seed": int}` | Returns sockets with duplicate notables |
| POST | `/timeless/api/parse_item` | `{"item_text": string}` | Parses a PoE item tooltip paste, extracts jewel type + seed |
| GET | `/timeless/api/passives` | — | Returns all replacement notables across all jewel types |
| GET | `/timeless/api/passives/<jewel_type>` | — | Returns replacement notables for a specific jewel type |
| GET | `/timeless/api/additions/<jewel_type>` | — | Returns small passive additions for a specific jewel type |
| GET | `/timeless/api/sockets` | — | Returns all 57 jewel socket locations with coordinates |
| GET | `/timeless/api/socket_nodes/<socket_id>` | — | Returns notable nodes within radius of a socket |
| POST | `/timeless/api/search_notable` | `{"jewel_type": int, "notable_name": str, "min_count": int}` | Finds seeds where a named notable appears N+ times in any socket |
| POST | `/timeless/api/search_conversion` | `{"jewel_type": int, "socket_id": int, "conversions": [...]}` | Finds seeds matching specific node-to-notable conversions in a socket |
| POST | `/timeless/api/search_notable_nodes` | `{"jewel_type": int, "node_ids": [...], "socket_id": int, "min_count": int, "target_notable": str}` | Finds seeds where specific nodes convert to a target notable |

`DataLoader` is instantiated once at startup (`app.py` module level); data loads into memory on server start (~3s), searches are instant thereafter. Key fields after init:
- `node_index_map`: `{node_id: {index, size}}` — LUT row index per passive node
- `local_to_global`: `{jewel_type: {local_id: global_id}}` — per-jewel conversion tables
- `passives` / `additions`: 0-indexed lists of `{dn, id, sd, is_keystone}` from LegionPassives.lua
- `tree_nodes`: `{node_id: {name, x, y, is_jewel_socket, is_notable, is_keystone}}`
- `jewel_sockets`: `{socket_id: {name, x, y, label, notable_nodes}}` — precomputed per-socket notable lists
- `lut_cache`: `{jewel_type: bytes}` — decompressed LUT data, loaded on first search per jewel type

### Data Sources

All data is read from the Path of Building installation at `/home/cc/codewithclaude/PathOfBuilding/src/`:

| File | Purpose |
|------|---------|
| `Data/TimelessJewelData/NodeIndexMapping.lua` | Maps passive tree node IDs → LUT index + size; contains `localIdToGlobalId` per jewel type |
| `Data/TimelessJewelData/LegionPassives.lua` | `["nodes"]` = notable/keystone passives (1–182); `["additions"]` = small passives (1–96) |
| `Data/TimelessJewelData/*.zip` | Compressed binary LUT tables; `GloriousVanity` is split into `.zip.part0–4` |
| `TreeData/3_25/tree.lua` | Passive tree: groups (with x/y), nodes (with orbit/orbitIndex/group), and tree constants |

### LUT Format (non-Glorious Vanity)

After `zlib.decompress()`:
- Flat byte array, row-major: `data[node_index * seed_size + seed_offset]`
- `seed_size = seed_max - seed_min + 1`
- `seed_offset = seed - seed_min` (for Elegant Hubris: `seed // 20 - seed_min`)
- Result byte = `local_id` → convert via `localIdToGlobalId[jewel_type][local_id]` → `global_id`
- `global_id >= 96` → replacement notable: `legionNodes[global_id - 96]` (0-indexed)
- `global_id < 96` → small passive addition: `legionAdditions[global_id]` (0-indexed)

Only the first `sizeNotable` (452) node indices in the LUT are notable nodes; the rest are small passives and keystones.

### Node Positions

Computed from tree.lua group coordinates + orbit system:
- `x = group.x + sin(angle) * orbit_radius`
- `y = group.y - cos(angle) * orbit_radius`
- `ORBIT_RADII = [0, 82, 162, 335, 493, 662, 846]`
- Orbit 2 (16 nodes) and orbit 4 (40 nodes) use fixed angle tables; others use `360*i/N`

Large jewel radius = 1800 units (post-3.16 tree).

### Search Logic

`DataLoader.find_duplicate_notables(jewel_type, seed)`:
1. For each of the 57 jewel sockets in the tree
2. Find all notable nodes within radius 1800 that have a LUT entry with `index <= sizeNotable`
3. For each such node, look up `global_id` from the LUT for the given seed
4. Group nodes by their resulting notable name
5. Return sockets where any notable appears 2+ times

### Seed Ranges

| Jewel | Seed range | Notes |
|-------|-----------|-------|
| Glorious Vanity | 100–8000 | Not supported (complex GV format) |
| Lethal Pride | 10000–18000 | |
| Brutal Restraint | 500–8000 | |
| Militant Faith | 2000–10000 | |
| Elegant Hubris | 2000–160000 step 20 | Internally seed/20 maps to 100–8000 |
| Heroic Tragedy | 100–8000 | |

## Deployment

### PoB data files required

The app reads directly from a Path of Building source checkout. You only need these specific files — no full PoB install is required:

```
PathOfBuilding/src/
├── Data/TimelessJewelData/
│   ├── NodeIndexMapping.lua          # ~110 KB
│   ├── LegionPassives.lua            # ~215 KB
│   ├── BrutalRestraint.zip           # ~2.1 MB
│   ├── ElegantHubris.zip             # ~2.4 MB
│   ├── HeroicTragedy.zip             # ~2.1 MB
│   ├── LethalPride.zip               # ~2.2 MB
│   ├── MilitantFaith.zip             # ~839 KB
│   ├── GloriousVanity.zip.part0      # ~5 MB each (5 parts, GV unsupported)
│   ├── GloriousVanity.zip.part1
│   ├── GloriousVanity.zip.part2
│   ├── GloriousVanity.zip.part3
│   └── GloriousVanity.zip.part4
└── TreeData/3_25/
    └── tree.lua                       # ~6 MB
```

The quickest way to get these is a sparse git clone of the PoB repo:

```bash
git clone --depth=1 --filter=blob:none --sparse \
  https://github.com/PathOfBuildingCommunity/PathOfBuilding.git
cd PathOfBuilding
git sparse-checkout set src/Data/TimelessJewelData src/TreeData/3_25
```

### Full deployment steps (Ubuntu/Debian)

```bash
# 1. System deps
sudo apt update && sudo apt install -y python3 python3-pip git

# 2. Clone this repo
git clone https://github.com/toinenkone/timeless-jewel-finder.git
cd timeless-jewel-finder

# 3. Install Python deps
pip3 install flask

# 4. Get PoB data (sparse clone, ~15 MB total)
git clone --depth=1 --filter=blob:none --sparse \
  https://github.com/PathOfBuildingCommunity/PathOfBuilding.git \
  /opt/PathOfBuilding
cd /opt/PathOfBuilding
git sparse-checkout set src/Data/TimelessJewelData src/TreeData/3_25
cd -

# 5. Point app at your PoB data path (edit data_loader.py if not /opt/PathOfBuilding)
#    Default paths in data_loader.py:
#      POB_DATA = "/opt/PathOfBuilding/src/Data/TimelessJewelData"
#      POB_TREE = "/opt/PathOfBuilding/src/TreeData/3_25"
#    Change these two constants to match your install path.

# 6. Set credentials and run
export AUTH_USERNAME=youruser
export AUTH_PASSWORD=yourpassword
python3 app.py
# Listens on 0.0.0.0:3122 — visit http://yourserver:3122/timeless/
```

### Running as a service (systemd)

```ini
# /etc/systemd/system/jewel-finder.service
[Unit]
Description=Timeless Jewel Finder
After=network.target

[Service]
WorkingDirectory=/opt/timeless-jewel-finder
ExecStart=/usr/bin/python3 app.py
Restart=on-failure
User=www-data
Environment=AUTH_USERNAME=youruser
Environment=AUTH_PASSWORD=yourpassword

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now jewel-finder
```

### Reverse proxy (nginx, optional)

```nginx
server {
    listen 80;
    server_name yourserver.example.com;
    location /timeless/ {
        proxy_pass http://127.0.0.1:3122/timeless/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Notes
- Python 3.8+ required (uses `zlib`, `math`, `re` — all stdlib except Flask)
- ~500 MB RAM at runtime (decompressed LUT data cached in memory)
- Data loads at process startup (~3s); subsequent searches are instant
- The `POB_DATA` and `POB_TREE` paths in `data_loader.py` must be updated if PoB is not at the default location
