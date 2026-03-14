"""
Loads and parses Path of Building data for Timeless Jewel lookups.
"""
import re
import os
import zlib
import math
from collections import defaultdict

POB_DATA = "/opt/PathOfBuilding/src/Data/TimelessJewelData"
POB_TREE = "/opt/PathOfBuilding/src/TreeData/3_25"

JEWEL_TYPES = {
    1: {"name": "Glorious Vanity",  "file": "GloriousVanity",  "seed_min": 100,   "seed_max": 8000,   "seed_step": 1},
    2: {"name": "Lethal Pride",     "file": "LethalPride",     "seed_min": 10000, "seed_max": 18000,  "seed_step": 1},
    3: {"name": "Brutal Restraint", "file": "BrutalRestraint", "seed_min": 500,   "seed_max": 8000,   "seed_step": 1},
    4: {"name": "Militant Faith",   "file": "MilitantFaith",   "seed_min": 2000,  "seed_max": 10000,  "seed_step": 1},
    5: {"name": "Elegant Hubris",   "file": "ElegantHubris",   "seed_min": 2000,  "seed_max": 160000, "seed_step": 20},
    6: {"name": "Heroic Tragedy",   "file": "HeroicTragedy",   "seed_min": 100,   "seed_max": 8000,   "seed_step": 1},
}

# LUT seed ranges (internal, after EH /20)
LUT_SEED_MIN = {1: 100, 2: 10000, 3: 500, 4: 2000, 5: 100, 6: 100}
LUT_SEED_MAX = {1: 8000, 2: 18000, 3: 8000, 4: 10000, 5: 8000, 6: 8000}

TIMELESS_JEWEL_ADDITIONS = 96

# Orbit system (from tree constants)
ORBIT_RADII = [0, 82, 162, 335, 493, 662, 846]
SKILLS_PER_ORBIT = [1, 6, 16, 16, 40, 72, 72]

# Large jewel radius (post-3.16 tree)
LARGE_RADIUS = 1800


def _calc_orbit_angles(skills_in_orbit):
    if skills_in_orbit == 16:
        degrees = [0, 30, 45, 60, 90, 120, 135, 150, 180, 210, 225, 240, 270, 300, 315, 330]
    elif skills_in_orbit == 40:
        degrees = [0, 10, 20, 30, 40, 45, 50, 60, 70, 80, 90, 100, 110, 120, 130, 135,
                   140, 150, 160, 170, 180, 190, 200, 210, 220, 225, 230, 240, 250, 260,
                   270, 280, 290, 300, 310, 315, 320, 330, 340, 350]
    else:
        degrees = [360 * i / skills_in_orbit for i in range(skills_in_orbit)]
    return [math.radians(d) for d in degrees]


# Precompute orbit angles for each orbit level
ORBIT_ANGLES = [_calc_orbit_angles(n) for n in SKILLS_PER_ORBIT]


class DataLoader:
    def __init__(self):
        print("Loading data...")
        self.node_index_map = {}    # node_id -> {index, size}
        self.size_notable = 0
        self.local_to_global = {}   # jewel_type -> {local_id -> global_id}
        self.passives = []          # 0-indexed list of {dn, id}
        self.additions = []         # 0-indexed list of {dn, id}
        self.tree_nodes = {}        # node_id -> {name, x, y, is_jewel_socket, is_notable, is_keystone, ascendancy}
        self.jewel_sockets = {}     # socket_id -> {name, x, y, label, notable_nodes}
        self.lut_cache = {}         # jewel_type -> bytes

        self._load_node_index_mapping()
        self._load_legion_passives()
        self._load_tree()
        print("Data loaded.")

    def _load_node_index_mapping(self):
        path = os.path.join(POB_DATA, "NodeIndexMapping.lua")
        with open(path, "r") as f:
            content = f.read()

        # size and sizeNotable
        m = re.search(r'nodeIDList\["size"\]\s*=\s*(\d+)', content)
        if m:
            self.size = int(m.group(1))
        m = re.search(r'nodeIDList\["sizeNotable"\]\s*=\s*(\d+)', content)
        if m:
            self.size_notable = int(m.group(1))

        # node entries: nodeIDList[ID] = { index = I, size = S }
        for m in re.finditer(r'nodeIDList\[(\d+)\]\s*=\s*\{\s*index\s*=\s*(\d+),\s*size\s*=\s*(\d+)\s*\}', content):
            node_id = int(m.group(1))
            index = int(m.group(2))
            size = int(m.group(3))
            self.node_index_map[node_id] = {"index": index, "size": size}

        # localIdToGlobalId mappings
        for m in re.finditer(r'nodeIDList\["localIdToGlobalId"\]\[(\d+)\]\[(\d+)\]\s*=\s*(\d+)', content):
            jtype = int(m.group(1))
            local_id = int(m.group(2))
            global_id = int(m.group(3))
            if jtype not in self.local_to_global:
                self.local_to_global[jtype] = {}
            self.local_to_global[jtype][local_id] = global_id

    def _load_legion_passives(self):
        path = os.path.join(POB_DATA, "LegionPassives.lua")
        with open(path, "r") as f:
            content = f.read()

        # Find additions section
        add_start = content.index('["additions"]')
        groups_start = content.index('["groups"]')
        pass_start = content.index('["nodes"]')

        additions_text = content[add_start:groups_start]
        passives_text = content[pass_start:]

        def extract_entries(text):
            entries = []
            # Find each numbered entry [N] = { ... }
            # Extract index and dn from each block
            # We use a simple scan: find [N] = { then scan for ["dn"] = "..."
            entry_pattern = re.compile(r'\[(\d+)\]\s*=\s*\{')
            dn_pattern = re.compile(r'\["dn"\]\s*=\s*"([^"]*)"')
            id_pattern = re.compile(r'\["id"\]\s*=\s*"([^"]*)"')

            pos = 0
            while True:
                m = entry_pattern.search(text, pos)
                if not m:
                    break
                idx = int(m.group(1))
                # Find end of this entry - scan for matching brace
                brace_start = m.end() - 1
                depth = 0
                end = brace_start
                for i in range(brace_start, len(text)):
                    if text[i] == '{':
                        depth += 1
                    elif text[i] == '}':
                        depth -= 1
                        if depth == 0:
                            end = i
                            break
                block = text[m.start():end + 1]
                dn_m = dn_pattern.search(block)
                id_m = id_pattern.search(block)
                entries.append({
                    "idx": idx,
                    "dn": dn_m.group(1) if dn_m else "Unknown",
                    "id": id_m.group(1) if id_m else "",
                })
                pos = end + 1

            # Sort by index and return as list
            entries.sort(key=lambda e: e["idx"])
            return entries

        self.additions = extract_entries(additions_text)
        self.passives = extract_entries(passives_text)

    def _load_tree(self):
        path = os.path.join(POB_TREE, "tree.lua")
        with open(path, "r") as f:
            lines = f.readlines()

        groups = {}   # group_id -> {x, y}
        raw_nodes = {}  # node_id -> {...}

        # State machine
        section = None   # 'groups', 'nodes', None
        current_id = None
        current_obj = None
        depth_stack = []

        # Regex patterns
        re_groups_start = re.compile(r'^\s{4}\["groups"\]=\s*\{')
        re_nodes_start = re.compile(r'^\s{4}\["nodes"\]=\s*\{')
        re_constants_start = re.compile(r'^\s{4}\["constants"\]=\s*\{')
        re_entry = re.compile(r'^\s{8}\[(\d+)\]=\s*\{')
        re_field_int = re.compile(r'^\s+\["(\w+)"\]=\s*(-?\d+),?$')
        re_field_float = re.compile(r'^\s+\["(\w+)"\]=\s*(-?[\d.]+),?$')
        re_field_str = re.compile(r'^\s+\["(\w+)"\]=\s*"([^"]*)",?$')
        re_field_bool = re.compile(r'^\s+\["(\w+)"\]=\s*(true|false),?$')

        for line in lines:
            stripped = line.rstrip()

            if section is None:
                if re_groups_start.match(stripped):
                    section = 'groups'
                    continue
                if re_nodes_start.match(stripped):
                    section = 'nodes'
                    continue
                continue

            if re_constants_start.match(stripped):
                break  # Done

            if section == 'groups':
                if re_nodes_start.match(stripped):
                    section = 'nodes'
                    current_id = None
                    current_obj = None
                    continue

                m = re_entry.match(stripped)
                if m:
                    current_id = int(m.group(1))
                    current_obj = {}
                    groups[current_id] = current_obj
                    continue

                if current_obj is not None:
                    m = re_field_float.match(stripped)
                    if m and m.group(1) in ('x', 'y'):
                        current_obj[m.group(1)] = float(m.group(2))
                    m2 = re_field_int.match(stripped)
                    if m2 and m2.group(1) in ('x', 'y'):
                        current_obj[m2.group(1)] = float(m2.group(2))

            elif section == 'nodes':
                m = re_entry.match(stripped)
                if m:
                    current_id = int(m.group(1))
                    current_obj = {'id': current_id}
                    raw_nodes[current_id] = current_obj
                    continue

                if current_obj is not None:
                    # String field
                    m = re_field_str.match(stripped)
                    if m:
                        key, val = m.group(1), m.group(2)
                        if key == 'name':
                            current_obj['name'] = val
                        elif key == 'ascendancyName':
                            current_obj['ascendancy'] = val
                        continue

                    # Int field
                    m = re_field_int.match(stripped)
                    if m:
                        key, val = m.group(1), int(m.group(2))
                        if key in ('group', 'orbit', 'orbitIndex'):
                            current_obj[key] = val
                        continue

                    # Bool field
                    m = re_field_bool.match(stripped)
                    if m:
                        key, val = m.group(1), m.group(2) == 'true'
                        if val and key in ('isJewelSocket', 'isNotable', 'isKeystone'):
                            current_obj[key] = True
                        continue

        # Compute node positions
        for node_id, node in raw_nodes.items():
            g = node.get('group')
            o = node.get('orbit', 0)
            oidx = node.get('orbitIndex', 0)
            if g and g in groups:
                gx = groups[g].get('x', 0)
                gy = groups[g].get('y', 0)
                if o < len(ORBIT_RADII) and o < len(ORBIT_ANGLES):
                    angles = ORBIT_ANGLES[o]
                    if oidx < len(angles):
                        angle = angles[oidx]
                    else:
                        angle = 0
                    radius = ORBIT_RADII[o]
                    node['x'] = gx + math.sin(angle) * radius
                    node['y'] = gy - math.cos(angle) * radius

        # Build final tree_nodes
        for node_id, node in raw_nodes.items():
            # Skip ascendancy nodes (they have an ascendancy field)
            if 'ascendancy' in node:
                continue
            self.tree_nodes[node_id] = {
                'name': node.get('name', str(node_id)),
                'x': node.get('x', 0),
                'y': node.get('y', 0),
                'is_jewel_socket': node.get('isJewelSocket', False),
                'is_notable': node.get('isNotable', False),
                'is_keystone': node.get('isKeystone', False),
            }

        # Build jewel sockets with their nearby notable nodes
        self._build_jewel_sockets()

    def _build_jewel_sockets(self):
        LARGE_R_SQ = LARGE_RADIUS * LARGE_RADIUS

        # Find keystone nodes for socket labeling
        keystones = {nid: n for nid, n in self.tree_nodes.items() if n['is_keystone']}

        # Special socket labels from PoB TreeTab
        special_labels = {26725: "Marauder", 54127: "Duelist", 7960: "Templar/Witch"}

        for socket_id, socket in self.tree_nodes.items():
            if not socket['is_jewel_socket']:
                continue

            sx, sy = socket['x'], socket['y']

            # Find label (nearest keystone)
            label = special_labels.get(socket_id)
            if label is None:
                min_dist = float('inf')
                for kid, ks in keystones.items():
                    dx = ks['x'] - sx
                    dy = ks['y'] - sy
                    dist = dx * dx + dy * dy
                    if dist < min_dist:
                        min_dist = dist
                        label = ks['name']
            if label is None:
                label = f"Socket {socket_id}"

            # Find notable nodes in large radius that have LUT entries
            notable_nodes = []
            for nid, node in self.tree_nodes.items():
                if nid == socket_id:
                    continue
                if not node['is_notable']:
                    continue
                # Must have a LUT entry with index <= sizeNotable
                lut_entry = self.node_index_map.get(nid)
                if lut_entry is None:
                    continue
                if lut_entry['index'] > self.size_notable:
                    continue
                # Check distance
                dx = node['x'] - sx
                dy = node['y'] - sy
                if dx * dx + dy * dy <= LARGE_R_SQ:
                    notable_nodes.append(nid)

            self.jewel_sockets[socket_id] = {
                'id': socket_id,
                'x': sx,
                'y': sy,
                'label': f"{label}: {socket_id}",
                'keystone': label,
                'notable_nodes': notable_nodes,
            }

    def _load_lut(self, jewel_type):
        if jewel_type in self.lut_cache:
            return self.lut_cache[jewel_type]

        if jewel_type == 1:
            # GV uses split zip files
            parts = []
            for i in range(5):
                path = os.path.join(POB_DATA, f"GloriousVanity.zip.part{i}")
                if os.path.exists(path):
                    with open(path, 'rb') as f:
                        parts.append(f.read())
            raw = b''.join(parts)
        else:
            fname = JEWEL_TYPES[jewel_type]['file']
            path = os.path.join(POB_DATA, f"{fname}.zip")
            with open(path, 'rb') as f:
                raw = f.read()

        data = zlib.decompress(raw)
        self.lut_cache[jewel_type] = data
        return data

    def _convert_local_to_global(self, jewel_type, local_id):
        mapping = self.local_to_global.get(jewel_type, {})
        return mapping.get(local_id, local_id)

    def read_lut(self, seed, node_id, jewel_type):
        """Returns global_id for a given seed/node/jewel_type. Returns None if not found."""
        if jewel_type == 1:
            return None  # GV not supported (complex format)

        lut_data = self._load_lut(jewel_type)
        if not lut_data:
            return None

        lut_entry = self.node_index_map.get(node_id)
        if lut_entry is None:
            return None

        index = lut_entry['index']
        if index > self.size_notable:
            return None  # Not a notable node in the LUT

        # For Elegant Hubris, divide seed by 20
        lut_seed = seed // 20 if jewel_type == 5 else seed

        seed_min = LUT_SEED_MIN[jewel_type]
        seed_max = LUT_SEED_MAX[jewel_type]
        seed_size = seed_max - seed_min + 1
        seed_offset = lut_seed - seed_min

        if seed_offset < 0 or seed_offset >= seed_size:
            return None

        byte_pos = index * seed_size + seed_offset
        if byte_pos >= len(lut_data):
            return None

        local_id = lut_data[byte_pos]
        global_id = self._convert_local_to_global(jewel_type, local_id)
        return global_id

    def global_id_to_name(self, global_id):
        """Convert global_id to (name, is_replacement) tuple."""
        if global_id is None:
            return None, False
        if global_id >= TIMELESS_JEWEL_ADDITIONS:
            # Replacement notable
            passive_idx = global_id - TIMELESS_JEWEL_ADDITIONS  # 0-indexed
            if passive_idx < len(self.passives):
                return self.passives[passive_idx]['dn'], True
        else:
            # Addition (small passive)
            if global_id < len(self.additions):
                return self.additions[global_id]['dn'], False
        return None, False

    def find_duplicate_notables(self, jewel_type, seed):
        """
        For the given jewel type and seed, find all jewel sockets that have
        2+ notable nodes converting to the same replacement notable.
        Returns a sorted list of results.
        """
        if jewel_type not in JEWEL_TYPES:
            return {"error": "Invalid jewel type"}
        if jewel_type == 1:
            return {"error": "Glorious Vanity is not supported yet"}

        jt = JEWEL_TYPES[jewel_type]
        seed_min = jt['seed_min']
        seed_max = jt['seed_max']
        if not (seed_min <= seed <= seed_max):
            return {"error": f"Seed must be between {seed_min} and {seed_max}"}
        if jt['seed_step'] > 1 and seed % jt['seed_step'] != 0:
            return {"error": f"Seed must be a multiple of {jt['seed_step']}"}

        results = []

        for socket_id, socket in self.jewel_sockets.items():
            notable_nodes = socket['notable_nodes']
            if not notable_nodes:
                continue

            # For each notable node, get what it becomes
            by_name = defaultdict(list)
            for nid in notable_nodes:
                global_id = self.read_lut(seed, nid, jewel_type)
                name, is_replacement = self.global_id_to_name(global_id)
                if name and is_replacement:
                    by_name[name].append({
                        'node_id': nid,
                        'node_name': self.tree_nodes[nid]['name'],
                    })

            # Find cases with 2+ occurrences
            matches = []
            for notable_name, nodes in by_name.items():
                if len(nodes) >= 2:
                    matches.append({
                        'notable': notable_name,
                        'count': len(nodes),
                        'nodes': nodes,
                    })

            if matches:
                matches.sort(key=lambda m: -m['count'])
                results.append({
                    'socket_id': socket_id,
                    'label': socket['label'],
                    'keystone': socket['keystone'],
                    'total_notables_in_radius': len(notable_nodes),
                    'matches': matches,
                })

        results.sort(key=lambda r: -max(m['count'] for m in r['matches']))
        return {"results": results, "jewel_type": jt['name'], "seed": seed}

    def parse_item_text(self, text):
        """Parse a PoE item text paste and extract jewel type and seed."""
        jewel_type = None
        seed = None

        for jtype, jinfo in JEWEL_TYPES.items():
            if jinfo['name'] in text:
                jewel_type = jtype
                break

        if jewel_type is None:
            return {"error": "No timeless jewel type found in text"}

        jt = JEWEL_TYPES[jewel_type]
        seed_min = jt['seed_min']
        seed_max = jt['seed_max']
        step = jt['seed_step']

        # Look for a number in the valid seed range
        for m in re.finditer(r'\b(\d+)\b', text):
            val = int(m.group(1))
            if seed_min <= val <= seed_max:
                if step == 1 or val % step == 0:
                    seed = val
                    break

        if seed is None:
            return {"error": "Could not find valid seed in item text", "jewel_type": jtype}

        return {"jewel_type": jewel_type, "seed": seed}
