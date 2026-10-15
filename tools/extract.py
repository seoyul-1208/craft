"""마인크래프트 클라이언트 jar에서 레시피·이름·아이콘을 뽑아 site/data.js 와 site/icons/ 를 만든다.

사용법:  python tools/extract.py [버전]      (기본값: 26.3)
"""
import io
import json
import os
import shutil
import sys
import zipfile
from collections import OrderedDict

import numpy as np
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
VERSION = sys.argv[1] if len(sys.argv) > 1 else "26.3"
MC = os.path.expandvars(r"%APPDATA%\.minecraft")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")

COLORS = ["white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray",
          "light_gray", "cyan", "purple", "blue", "brown", "green", "red", "black"]

# 섞어서 만드는 염료 (기본 염료로 분해한다)
MIXED_DYES = ["orange", "magenta", "light_blue", "lime", "pink", "gray", "light_gray", "cyan", "purple"]
BASE_DYES = [c for c in COLORS if c not in MIXED_DYES]

# 월드에서 그대로 얻을 수 있어서 레시피가 있어도 더 분해하지 않는 기본 원재료
# (돌은 조약돌로, 색깔 양털은 하얀색 양털 + 염료로, 점토·벽돌·진흙은 흙으로 계산한다)
NATURAL_RAW = [
    "cobblestone", "deepslate", "sandstone", "red_sandstone", "terracotta", "coarse_dirt",
    "packed_ice", "blue_ice", "snow_block", "melon", "glowstone", "magma_block",
    "nether_wart_block", "dripstone_block", "amethyst_block", "leather", "honey_bottle",
    "iron_ingot", "gold_ingot", "copper_ingot", "diamond", "emerald",
    "lapis_lazuli", "redstone", "coal", "quartz",
    "white_wool",
] + [f"{c}_dye" for c in BASE_DYES]

# 서바이벌에서 얻을 수 없는 아이템 (생성 알, 벌레 먹은 블록과 함께 목록에서 뺀다)
CREATIVE_ONLY = {
    "trial_spawner", "spawner", "vault", "reinforced_deepslate", "budding_amethyst", "bedrock",
    "end_portal_frame", "petrified_oak_slab", "farmland", "dirt_path", "frogspawn", "player_head",
    "suspicious_sand", "suspicious_gravel", "command_block", "chain_command_block",
    "repeating_command_block", "command_block_minecart", "structure_block", "structure_void", "jigsaw",
    "barrier", "light", "debug_stick", "knowledge_book", "test_block", "test_instance_block",
}

jar = zipfile.ZipFile(os.path.join(MC, "versions", VERSION, f"{VERSION}.jar"))
names = set(jar.namelist())


def read_json(path):
    return json.loads(jar.read(path))


def strip(i):
    return i.split(":", 1)[1] if ":" in i else i


# ---------- 언어 ----------
en = read_json("assets/minecraft/lang/en_us.json")
ver_json = json.load(open(os.path.join(MC, "versions", VERSION, f"{VERSION}.json"), encoding="utf-8"))
index = json.load(open(os.path.join(MC, "assets", "indexes", ver_json["assetIndex"]["id"] + ".json"), encoding="utf-8"))
h = index["objects"]["minecraft/lang/ko_kr.json"]["hash"]
ko = json.load(open(os.path.join(MC, "assets", "objects", h[:2], h), encoding="utf-8"))


def lang_name(lang, item):
    return lang.get(f"item.minecraft.{item}") or lang.get(f"block.minecraft.{item}")


# ---------- 태그 ----------
tag_cache = {}


def expand_tag(tag):
    tag = strip(tag)
    if tag in tag_cache:
        return tag_cache[tag]
    tag_cache[tag] = []
    out = []
    for v in read_json(f"data/minecraft/tags/item/{tag}.json")["values"]:
        v = v["id"] if isinstance(v, dict) else v
        out += expand_tag(v[1:]) if v.startswith("#") else [strip(v)]
    tag_cache[tag] = list(OrderedDict.fromkeys(out))
    return tag_cache[tag]


def alts(ing):
    if isinstance(ing, list):
        out = []
        for x in ing:
            out += alts(x)
        return list(OrderedDict.fromkeys(out))
    if isinstance(ing, dict):
        ing = ing.get("item") or ing.get("tag")
    return expand_tag(ing[1:]) if ing.startswith("#") else [strip(ing)]


# ---------- 레시피 ----------
recipes = []


def add(rtype, result, count, cells, keys, w=None):
    """cells: 칸마다 재료 키(또는 None), keys: 키 -> 대체 아이템 목록"""
    if not result:
        return
    key_order = list(OrderedDict.fromkeys(k for k in cells if k is not None))
    slots = []
    for k in key_order:
        a = [x for x in keys[k] if x != result]  # 자기 자신을 재료로 쓰는 경우 제외
        if not a:
            return
        slots.append(a)
    rec = {"t": rtype, "r": result, "c": count,
           "s": slots,
           "n": [cells.count(k) for k in key_order],
           "g": [key_order.index(k) if k is not None else -1 for k in cells]}
    if w:
        rec["w"] = w
    recipes.append(rec)


for path in sorted(n for n in names if n.startswith("data/minecraft/recipe/") and n.endswith(".json")):
    r = read_json(path)
    t = strip(r["type"])
    res = r.get("result", {})
    out, cnt = strip(res.get("id", "")), res.get("count", 1)
    if t == "crafting_shaped":
        rows = r["pattern"]
        w = max(len(x) for x in rows)
        cells = [(c if c != " " else None) for row in rows for c in row.ljust(w)]
        add("craft", out, cnt, cells, {k: alts(v) for k, v in r["key"].items()}, w)
    elif t == "crafting_shapeless":
        ings = r["ingredients"]
        add("craft", out, cnt, [f"i{json.dumps(i)}" for i in ings],
            {f"i{json.dumps(i)}": alts(i) for i in ings})
    elif t == "crafting_transmute":
        add("craft", out, cnt, ["a", "b"], {"a": alts(r["input"]), "b": alts(r["material"])})
    elif t == "crafting_decorated_pot":
        add("craft", out, cnt, [None, "p", None, "p", None, "p", None, "p", None],
            {"p": alts(r["back"])}, 3)
    elif t == "crafting_special_firework_star":
        # 모양·효과 재료는 넣지 않은 가장 기본 조합
        add("craft", out, cnt, ["f", "d"], {"f": alts(r["fuel"]), "d": alts(r["dye"])})
    elif t == "smelting":
        add("smelt", out, cnt, ["a"], {"a": alts(r["ingredient"])})
    elif t == "stonecutting":
        add("cut", out, cnt, ["a"], {"a": alts(r["ingredient"])})
    elif t == "smithing_transform":
        add("smith", out, cnt, ["a", "b", "c"],
            {"a": alts(r["template"]), "b": alts(r["base"]), "c": alts(r["addition"])})
    # 나머지(염색 복사, 특수 제작, 훈연기/용광로 중복 등)는 계산에 쓰지 않는다

# 콘크리트 가루는 물에 닿으면 콘크리트가 된다 (레시피 파일이 없음)
for c in COLORS:
    add("water", f"{c}_concrete", 1, ["a"], {"a": [f"{c}_concrete_powder"]})
# 흙 → 진흙(물병) → 점토(뾰족한 점적석 위에서 마름) → 점토 덩이 4개(부수기)
add("mud", "mud", 1, ["a"], {"a": ["dirt"]})
add("drip", "clay", 1, ["a"], {"a": ["mud"]})
add("break", "clay_ball", 4, ["a"], {"a": ["clay"]})
# 구리 골렘: 구리 블록 위에 조각한 호박 → 완전히 산화되면 동상 → 도끼로 벗겨 산화 단계를 낮춘다
add("build", "copper_golem", 1, ["p", "b"], {"p": ["carved_pumpkin"], "b": ["copper_block"]}, 1)
add("statue", "oxidized_copper_golem_statue", 1, ["a"], {"a": ["copper_golem"]})
for lower, higher in [("weathered", "oxidized"), ("exposed", "weathered"), ("", "exposed")]:
    add("scrape", f"{lower + '_' if lower else ''}copper_golem_statue", 1, ["a"], {"a": [f"{higher}_copper_golem_statue"]})

DYE_IDS = {f"{c}_dye" for c in COLORS}
COLORED_WOOL = {f"{c}_wool" for c in COLORS if c != "white"}
kept = []
for rec in recipes:
    if rec["r"] in {f"{c}_dye" for c in MIXED_DYES}:
        # 섞는 염료는 염료끼리 섞는 레시피만 쓴다 (꽃 레시피 제외)
        if not all(set(sl) <= DYE_IDS for sl in rec["s"]):
            continue
    if rec["r"] in COLORED_WOOL:
        # 색깔 양털은 하얀색 양털 + 염료
        if not any("white_wool" in sl for sl in rec["s"]):
            continue
        rec["s"] = [["white_wool"] if "white_wool" in sl else sl for sl in rec["s"]]
        rec["t"] = "dye"
    kept.append(rec)
recipes = kept

# ---------- 9개 <-> 블록 1개 짝 (주괴/블록 등) ----------
compress = {}
for rec in recipes:
    if rec["t"] == "craft" and rec["c"] == 1 and len(rec["s"]) == 1 and rec["n"][0] == 9 and len(rec["s"][0]) == 1:
        compress[(rec["s"][0][0], rec["r"])] = True
storage = {}  # 재료 -> 블록
for rec in recipes:
    if rec["t"] == "craft" and rec["c"] == 9 and len(rec["s"]) == 1 and rec["n"][0] == 1 and len(rec["s"][0]) == 1:
        block, base = rec["s"][0][0], rec["r"]
        if (base, block) in compress:
            storage[base] = block

# 블록 짝이 있어도 다른 재료로 만드는 아이템 (네더라이트 주괴 = 네더라이트 파편 4 + 금 주괴 4)
CRAFTED = {"netherite_ingot"}
raw = set(NATURAL_RAW)
for base, block in storage.items():
    if block not in raw and base not in CRAFTED:
        raw.add(base)  # 블록은 재료 9개로 분해하고, 재료 쪽을 원재료로 본다
# 원재료를 다시 만드는 레시피(블록→주괴, 실→양털 등)는 계산에서 쓸 일이 없지만 그대로 둔다.

# ---------- 아이콘 ----------
used = set()
for rec in recipes:
    used.add(rec["r"])
    for s in rec["s"]:
        used.update(s)
used |= raw
# 레시피와 상관없는 아이템(마른 덤불, 묘목 등)도 입력할 수 있게 전체 아이템을 넣는다
for n in names:
    if n.startswith("assets/minecraft/items/") and n.endswith(".json"):
        i = n[len("assets/minecraft/items/"):-5]
        if i != "air" and i not in CREATIVE_ONLY and not i.startswith("infested_") and not i.endswith("_spawn_egg") \
                and (lang_name(ko, i) or lang_name(en, i)):
            used.add(i)

TEX_PRIORITY = ["layer0", "all", "side", "front", "texture", "top", "end", "cross", "plant",
                "pattern", "wool", "particle"]


def find_model(node):
    if isinstance(node, dict):
        if node.get("type") in ("minecraft:model", "model") and isinstance(node.get("model"), str):
            return node["model"]
        if node.get("type") in ("minecraft:special", "special") and isinstance(node.get("base"), str):
            return node["base"]
        for k in ("fallback", "on_false", "model", "models", "cases", "entries"):
            if k in node:
                m = find_model(node[k])
                if m:
                    return m
        for v in node.values():
            m = find_model(v)
            if m:
                return m
    elif isinstance(node, list):
        for v in node:
            m = find_model(v)
            if m:
                return m
    return None


def model_textures(model):
    tex = {}
    while model:
        p = f"assets/minecraft/models/{strip(model)}.json"
        if p not in names:
            break
        m = read_json(p)
        for k, v in m.get("textures", {}).items():
            tex.setdefault(k, v.get("sprite") if isinstance(v, dict) else v)
        model = m.get("parent")
    return tex


# 유리판은 아이콘 그림이 유리와 같은 평평한 텍스처라서 좁게 잘라 판 모양으로 보여준다
def shape_for(item):
    return "pane" if item.endswith("_pane") else None


# 재료순 정렬 그룹: 0 나무, 1 돌, 2 흙, 3 기타 블록, 4 아이템
STONE = {"cobblestone", "stone", "cobbled_deepslate", "deepslate", "andesite", "diorite", "granite",
         "tuff", "calcite", "blackstone", "basalt", "smooth_basalt", "netherrack", "end_stone",
         "sandstone", "red_sandstone", "dripstone_block", "obsidian", "crying_obsidian",
         "mossy_cobblestone", "smooth_stone"}
SOIL = {"dirt", "coarse_dirt", "rooted_dirt", "podzol", "mycelium", "grass_block", "mud", "clay",
        "sand", "red_sand", "gravel", "soul_sand", "soul_soil", "moss_block", "pale_moss_block"}
WOOD = set(expand_tag("logs")) | set(expand_tag("planks")) | {"bamboo_block", "stripped_bamboo_block", "bamboo"}


def group_for(item):
    if item in WOOD:
        return 0
    if item in STONE:
        return 1
    if item in SOIL:
        return 2
    return 3 if f"block.minecraft.{item}" in en else 4


def texture_for(item):
    p = f"assets/minecraft/items/{item}.json"
    if p not in names:
        return None
    model = find_model(read_json(p))
    if not model:
        return None
    tex = model_textures(model)
    for key in TEX_PRIORITY:
        v = tex.get(key)
        depth = 0
        while v and v.startswith("#") and depth < 10:
            v = tex.get(v[1:])
            depth += 1
        if v and not v.startswith("#"):
            path = f"assets/minecraft/textures/{strip(v)}.png"
            if path in names:
                return path
    return None


# 구리 골렘 동상은 특수 모델이라 엔티티 텍스처에서 앞모습을 잘라 붙여 아이콘을 만든다 (산화 단계별로 다름)
# (텍스처 u, v, 너비, 높이) 앞면 -> 24x24 캔버스 x, y
GOLEM_PARTS = [
    ((41, 4, 4, 4), (10, 0)),    # 안테나 끝
    ((39, 10, 2, 4), (11, 4)),   # 안테나
    ((10, 10, 8, 5), (8, 8)),    # 머리
    ((6, 21, 8, 6), (8, 13)),    # 몸
    ((4, 31, 4, 5), (8, 19)),    # 오른다리
    ((20, 31, 4, 5), (12, 19)),  # 왼다리
    ((40, 20, 3, 10), (5, 13)),  # 오른팔
    ((54, 20, 3, 10), (16, 13)), # 왼팔
    ((58, 2, 2, 3), (11, 11)),   # 코
]


def golem_texture(node):
    if isinstance(node, dict):
        if strip(node.get("type", "")) == "copper_golem_statue" and isinstance(node.get("texture"), str):
            return f"assets/minecraft/{strip(node['texture'])}"
        node = list(node.values())
    if isinstance(node, list):
        for v in node:
            t = golem_texture(v)
            if t:
                return t
    return None


def write_golem_icon(tp, dst):
    tex = Image.open(io.BytesIO(jar.read(tp))).convert("RGBA")
    out = Image.new("RGBA", (24, 24))
    for (u, v, w, h), (x, y) in GOLEM_PARTS:
        out.alpha_composite(tex.crop((u, v, u + w, v + h)), (x, y))
    out.save(dst)


# ---------- 블록 아이콘: 블록 모델을 게임 인벤토리처럼 비스듬히 그린다 ----------
RENDER = 64   # 저장 크기
SUPER = 4     # 계단 현상을 줄이려고 크게 그린 뒤 줄인다


def model_info(model):
    """모델 상속을 따라가며 텍스처, 요소(elements), 인벤토리(gui) 표시 방식을 모은다"""
    tex, elements, gui = {}, None, None
    while model:
        if strip(model) in ("builtin/generated", "item/generated"):
            return None  # 평평한 아이템 그림
        p = f"assets/minecraft/models/{strip(model)}.json"
        if p not in names:
            return None
        m = read_json(p)
        for k, v in m.get("textures", {}).items():
            tex.setdefault(k, v.get("sprite") if isinstance(v, dict) else v)
        if elements is None and "elements" in m:
            elements = m["elements"]
        gui = gui or m.get("display", {}).get("gui")
        model = m.get("parent")
    if not elements:
        return None
    return tex, elements, gui or {"rotation": [30, 225, 0], "scale": [0.625] * 3}


tex_cache = {}


def load_tex(ref, tex):
    depth = 0
    while ref and ref.startswith("#") and depth < 10:
        ref = tex.get(ref[1:])
        depth += 1
    if not ref or ref.startswith("#"):
        return None
    path = f"assets/minecraft/textures/{strip(ref)}.png"
    if path not in names:
        return None
    if path not in tex_cache:
        im = Image.open(io.BytesIO(jar.read(path))).convert("RGBA")
        im = im.crop((0, 0, im.width, im.width))  # 움직이는 텍스처는 첫 장면만
        tex_cache[path] = np.asarray(im, dtype=np.float32) / 255
    return tex_cache[path]


def tint_rgb(t):
    kind = strip(t.get("type", ""))
    if kind == "grass":
        cm = Image.open(io.BytesIO(jar.read("assets/minecraft/textures/colormap/grass.png"))).convert("RGB")
        temp = min(max(t.get("temperature", 0.5), 0), 1)
        rain = min(max(t.get("downfall", 1), 0), 1) * temp
        return np.array(cm.getpixel((int((1 - temp) * 255), int((1 - rain) * 255))), dtype=np.float32) / 255
    v = t.get("value") if kind == "constant" else t.get("default")
    if not isinstance(v, int):
        return None
    return np.array([(v >> 16) & 255, (v >> 8) & 255, v & 255], dtype=np.float32) / 255


def rot3(axis, deg):
    a = np.radians(deg)
    c, s_ = np.cos(a), np.sin(a)
    return {"x": np.array([[1, 0, 0], [0, c, -s_], [0, s_, c]]),
            "y": np.array([[c, 0, s_], [0, 1, 0], [-s_, 0, c]]),
            "z": np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]])}[axis]


# 면마다 바깥에서 본 왼쪽 위, 오른쪽 위, 오른쪽 아래, 왼쪽 아래 꼭짓점 (a=from, b=to)
FACE_CORNERS = {
    "north": lambda a, b: [(b[0], b[1], a[2]), (a[0], b[1], a[2]), (a[0], a[1], a[2]), (b[0], a[1], a[2])],
    "south": lambda a, b: [(a[0], b[1], b[2]), (b[0], b[1], b[2]), (b[0], a[1], b[2]), (a[0], a[1], b[2])],
    "west": lambda a, b: [(a[0], b[1], a[2]), (a[0], b[1], b[2]), (a[0], a[1], b[2]), (a[0], a[1], a[2])],
    "east": lambda a, b: [(b[0], b[1], b[2]), (b[0], b[1], a[2]), (b[0], a[1], a[2]), (b[0], a[1], b[2])],
    "up": lambda a, b: [(a[0], b[1], a[2]), (b[0], b[1], a[2]), (b[0], b[1], b[2]), (a[0], b[1], b[2])],
    "down": lambda a, b: [(a[0], a[1], b[2]), (b[0], a[1], b[2]), (b[0], a[1], a[2]), (a[0], a[1], a[2])],
}
DEFAULT_UV = {
    "down": lambda a, b: [a[0], 16 - b[2], b[0], 16 - a[2]],
    "up": lambda a, b: [a[0], a[2], b[0], b[2]],
    "north": lambda a, b: [16 - b[0], 16 - b[1], 16 - a[0], 16 - a[1]],
    "south": lambda a, b: [a[0], 16 - b[1], b[0], 16 - a[1]],
    "west": lambda a, b: [a[2], 16 - b[1], b[2], 16 - a[1]],
    "east": lambda a, b: [16 - b[2], 16 - b[1], 16 - a[2], 16 - a[1]],
}


def render_block(info, tints, fit=None):
    """fit: 그림 크기에 대한 비율. 주면 모델 크기와 상관없이 가운데에 그 크기로 맞춘다"""
    tex, elements, gui = info
    N = RENDER * SUPER
    rx, ry, rz = gui.get("rotation", [0, 0, 0])
    R = rot3("x", rx) @ rot3("y", ry) @ rot3("z", rz)
    scale = np.array(gui.get("scale", [1, 1, 1]), dtype=float)
    trans = np.array(gui.get("translation", [0, 0, 0]), dtype=float) / 16

    faces = []
    for el in elements:
        a, b = el["from"], el["to"]
        er = el.get("rotation")
        for fname, f in el.get("faces", {}).items():
            img = f["img"] if "img" in f else load_tex(f.get("texture", ""), tex)
            if img is None:
                continue
            pts = np.array(FACE_CORNERS[fname](a, b), dtype=float)
            if er:
                o = np.array(er["origin"], dtype=float)
                if "axis" in er:
                    M = rot3(er["axis"], er["angle"])
                else:
                    M = rot3("x", er.get("x", 0)) @ rot3("y", er.get("y", 0)) @ rot3("z", er.get("z", 0))
                pts = (pts - o) @ M.T + o
            v = ((pts / 16 - 0.5) * scale) @ R.T + trans
            normal = np.cross(v[1] - v[0], v[0] - v[3])
            if normal[2] <= 1e-9:
                continue  # 뒷면
            n = normal / np.linalg.norm(normal)
            shade = 1.0 if (el.get("shade", True) is False or n[1] > 0.7) else (0.8 if n[0] < 0 else 0.6)
            u1, v1, u2, v2 = f.get("uv") or DEFAULT_UV[fname](a, b)
            uvs = [(u1, v1), (u2, v1), (u2, v2), (u1, v2)]
            k = (f.get("rotation", 0) // 90) % 4
            uvs = [uvs[(i - k) % 4] for i in range(4)]
            color = None
            ti = f.get("tintindex")
            if ti is not None and 0 <= ti < len(tints):
                color = tint_rgb(tints[ti])
            faces.append((v, np.array(uvs, dtype=float), img, shade, color))

    cx = cy = 0.0
    k = 1.0
    if fit and faces:
        allv = np.concatenate([f[0] for f in faces])
        lo, hi = allv[:, :2].min(axis=0), allv[:, :2].max(axis=0)
        k = fit / max(hi - lo)
        cx, cy = (lo + hi) / 2
    faces = [(v[:, 2].mean(), np.stack([N / 2 + (v[:, 0] - cx) * k * N, N / 2 - (v[:, 1] - cy) * k * N, v[:, 2]], axis=1),
              uvs, img, shade, color) for v, uvs, img, shade, color in faces]

    rgb = np.zeros((N, N, 3), dtype=np.float32)   # 미리 곱한 알파
    alpha = np.zeros((N, N), dtype=np.float32)
    zbuf = np.full((N, N), -np.inf, dtype=np.float32)
    for _, scr, uv, img, shade, color in sorted(faces, key=lambda f: f[0]):  # 먼 면부터
        p0, e1, e2 = scr[0, :2], scr[1, :2] - scr[0, :2], scr[3, :2] - scr[0, :2]
        det = e1[0] * e2[1] - e1[1] * e2[0]
        if abs(det) < 1e-6:
            continue
        x0, x1 = int(max(0, np.floor(scr[:, 0].min()))), int(min(N, np.ceil(scr[:, 0].max())))
        y0, y1 = int(max(0, np.floor(scr[:, 1].min()))), int(min(N, np.ceil(scr[:, 1].max())))
        if x0 >= x1 or y0 >= y1:
            continue
        ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32) + 0.5
        dx, dy = xs - p0[0], ys - p0[1]
        fa = (dx * e2[1] - dy * e2[0]) / det
        fb = (e1[0] * dy - e1[1] * dx) / det
        inside = (fa >= 0) & (fa < 1) & (fb >= 0) & (fb < 1)
        if not inside.any():
            continue
        th, tw = img.shape[:2]
        u = uv[0, 0] + fa * (uv[1, 0] - uv[0, 0]) + fb * (uv[3, 0] - uv[0, 0])
        w = uv[0, 1] + fa * (uv[1, 1] - uv[0, 1]) + fb * (uv[3, 1] - uv[0, 1])
        tx = np.clip(np.floor(u / 16 * tw), 0, tw - 1).astype(int)
        ty = np.clip(np.floor(w / 16 * th), 0, th - 1).astype(int)
        texel = img[ty, tx]
        c = texel[..., :3] * shade
        if color is not None:
            c = c * color
        ta = texel[..., 3]
        depth = scr[0, 2] + fa * (scr[1, 2] - scr[0, 2]) + fb * (scr[3, 2] - scr[0, 2])
        zb, rb, ab = zbuf[y0:y1, x0:x1], rgb[y0:y1, x0:x1], alpha[y0:y1, x0:x1]
        draw = inside & (ta > 0.01) & (depth > zb)
        opaque = draw & (ta > 0.98)
        rb[opaque] = c[opaque]
        ab[opaque] = 1
        zb[opaque] = depth[opaque]
        glass = draw & ~opaque
        ga = ta[glass][:, None]
        rb[glass] = c[glass] * ga + rb[glass] * (1 - ga)
        ab[glass] = ta[glass] + ab[glass] * (1 - ta[glass])

    # 줄이기 (미리 곱한 알파로 평균내야 가장자리가 어두워지지 않는다)
    rgb = rgb.reshape(RENDER, SUPER, RENDER, SUPER, 3).mean(axis=(1, 3))
    alpha = alpha.reshape(RENDER, SUPER, RENDER, SUPER).mean(axis=(1, 3))
    out = np.zeros((RENDER, RENDER, 4), dtype=np.float32)
    out[..., :3] = np.where(alpha[..., None] > 0, rgb / np.maximum(alpha[..., None], 1e-6), 0)
    out[..., 3] = alpha
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")


def block_render(item):
    """블록 모델로 그린 아이콘 파일 이름. 평평한 아이템이면 None"""
    p = f"assets/minecraft/items/{item}.json"
    if p not in names:
        return None
    root = read_json(p)
    model = find_model(root)
    if not model:
        return None
    info = model_info(model)
    if not info:
        return None
    tints = root["model"].get("tints", []) if isinstance(root.get("model"), dict) else []
    tag = "".join(f"__{tint_key(t)}" for t in tints)
    icon = "render__" + strip(model).replace("/", "__") + tag + ".png"
    dst = os.path.join(icons_dir, icon)
    if not os.path.exists(dst):
        render_block(info, tints).save(dst)
    return icon


def tint_key(t):
    c = tint_rgb(t)
    return "x" if c is None else "%02x%02x%02x" % tuple(int(x * 255 + 0.5) for x in c)


# ---------- 몹 머리: 엔티티 텍스처의 머리 부분으로 상자를 만들어 그린다 ----------
def entity_tex(path):
    im = Image.open(io.BytesIO(jar.read(f"assets/minecraft/textures/entity/{path}.png"))).convert("RGBA")
    return np.asarray(im, dtype=np.float32) / 255


def ebox(img, u, v, x, y, z, w, h, d, grow=0.0, pivot=(0, 0, 0), zrot=0):
    """엔티티 모델 상자(y가 아래, 앞이 -z) 하나를 블록 모델 요소(y가 위, 앞이 남쪽)로 바꾼다"""
    px, py, pz = pivot
    x0, x1 = px + x - grow, px + x + w + grow
    y0, y1 = py + y - grow, py + y + h + grow
    z0, z1 = pz + z - grow, pz + z + d + grow
    regions = {"up": (u + d, v, w, d), "down": (u + d + w, v, w, d),
               "west": (u, v + d, d, h), "south": (u + d, v + d, w, h),
               "east": (u + d + w, v + d, d, h), "north": (u + 2 * d + w, v + d, w, h)}
    faces = {}
    for name_, (fx, fy, fw, fh) in regions.items():
        part = img[fy:fy + fh, fx:fx + fw]
        if part.size:
            faces[name_] = {"img": part, "uv": [0, 0, 16, 16]}
    el = {"from": [x0 + 8, -y1, 8 - z1], "to": [x1 + 8, -y0, 8 - z0], "faces": faces}
    if zrot:
        el["rotation"] = {"origin": [px + 8, -py, 8 - pz], "axis": "z", "angle": -zrot}
    return el


def humanoid_head(path, hat):
    img = entity_tex(path)
    els = [ebox(img, 0, 0, -4, -8, -4, 8, 8, 8)]
    if hat:
        els.append(ebox(img, 32, 0, -4, -8, -4, 8, 8, 8, grow=0.25))
    return els


def piglin_head():
    img = entity_tex("piglin/piglin")
    return [ebox(img, 0, 0, -5, -8, -4, 10, 8, 8),
            ebox(img, 31, 1, -2, -4, -5, 4, 4, 1),
            ebox(img, 2, 4, 2, -2, -5, 1, 2, 1),
            ebox(img, 2, 0, -3, -2, -5, 1, 2, 1),
            ebox(img, 51, 6, 0, 0, -2, 1, 5, 4, pivot=(4.5, -6, 0), zrot=-30),
            ebox(img, 39, 6, -1, 0, -2, 1, 5, 4, pivot=(-4.5, -6, 0), zrot=30)]


def dragon_head():
    img = entity_tex("enderdragon/dragon")
    return [ebox(img, 112, 30, -8, -8, -10, 16, 16, 16),
            ebox(img, 176, 44, -6, -1, -24, 12, 5, 16),
            ebox(img, 0, 0, -5, -12, -4, 2, 4, 6),
            ebox(img, 0, 0, 3, -12, -4, 2, 4, 6),
            ebox(img, 112, 0, -5, -3, -22, 2, 2, 4),
            ebox(img, 112, 0, 3, -3, -22, 2, 2, 4),
            ebox(img, 176, 65, -6, 0, -16, 12, 4, 16, pivot=(0, 4, -8))]


HEADS = {
    "skeleton_skull": lambda: humanoid_head("skeleton/skeleton", False),
    "wither_skeleton_skull": lambda: humanoid_head("skeleton/wither_skeleton", False),
    "zombie_head": lambda: humanoid_head("zombie/zombie", True),
    "player_head": lambda: humanoid_head("player/wide/steve", True),
    "creeper_head": lambda: humanoid_head("creeper/creeper", False),
    "piglin_head": piglin_head,
    "dragon_head": dragon_head,
}
HEAD_GUI = {"rotation": [30, -45, 0]}  # 얼굴이 왼쪽 앞을 보는 인벤토리 각도


def chest_texture(node):
    """아이템 정의에서 상자 텍스처 이름을 찾는다 (크리스마스용은 건너뜀)"""
    if isinstance(node, dict):
        if strip(node.get("type", "")) == "chest" and strip(node.get("texture", "")) != "christmas":
            return strip(node["texture"])
        node = list(node.values())
    if isinstance(node, list):
        for v in node:
            t = chest_texture(v)
            if t:
                return t
    return None


def flat_box(frm, to, regions, img):
    """블록 모델 좌표의 상자. regions: 면 -> 텍스처 영역 (상자 텍스처는 위아래가 뒤집혀 저장되어 있다)"""
    faces = {}
    for face, (x, y, w, h) in regions.items():
        faces[face] = {"img": img[y:y + h, x:x + w][::-1], "uv": [0, 0, 16, 16]}
    return {"from": frm, "to": to, "faces": faces}


def chest_elements(name_):
    img = entity_tex(f"chest/{name_}")
    # 텍스처에서 앞면(자물쇠 자국)은 띠의 네 번째 칸이다
    return [
        flat_box([1, 0, 1], [15, 10, 15], {"south": (42, 33, 14, 10), "west": (0, 33, 14, 10),
                                           "east": (28, 33, 14, 10), "north": (14, 33, 14, 10)}, img),
        flat_box([1, 9, 1], [15, 14, 15], {"south": (42, 14, 14, 5), "west": (0, 14, 14, 5),
                                           "east": (28, 14, 14, 5), "north": (14, 14, 14, 5),
                                           "up": (28, 0, 14, 14)}, img),
        flat_box([7, 7, 15], [9, 11, 16], {"south": (1, 1, 2, 4), "west": (0, 1, 1, 4),
                                           "east": (3, 1, 1, 4), "up": (1, 0, 2, 1)}, img),
    ]


def shield_elements():
    img = entity_tex("shield/shield_base_nopattern")
    return [ebox(img, 0, 0, -6, -11, -2, 12, 22, 1), ebox(img, 26, 0, -1, -3, -1, 2, 6, 6)]


def special_render(item):
    """특수 렌더러를 쓰는 아이템(머리, 상자, 방패)의 아이콘. 해당 없으면 None"""
    if item in HEADS:
        return head_render(item)
    if item == "shield":
        icon = "special__shield.png"
        dst = os.path.join(icons_dir, icon)
        if not os.path.exists(dst):
            render_block(({}, shield_elements(), {"rotation": [15, -25, -5]}), [], fit=0.9).save(dst)
        return icon
    p = f"assets/minecraft/items/{item}.json"
    tex = chest_texture(read_json(p)) if p in names else None
    if not tex:
        return None
    icon = f"special__chest_{tex}.png"
    dst = os.path.join(icons_dir, icon)
    if not os.path.exists(dst):
        gui = {"rotation": HEAD_GUI["rotation"], "scale": [0.625] * 3}
        render_block(({}, chest_elements(tex), gui), []).save(dst)
    return icon


def head_render(item):
    icon = f"head__{item}.png"
    dst = os.path.join(icons_dir, icon)
    if not os.path.exists(dst):
        render_block(({}, HEADS[item](), HEAD_GUI), [], fit=0.8 if item == "dragon_head" else 0.66).save(dst)
    return icon


icons_dir = os.path.join(SITE, "icons")
shutil.rmtree(icons_dir, ignore_errors=True)
os.makedirs(icons_dir)
items = {}
for item in sorted(used):
    tp = texture_for(item)
    icon = None
    gp = f"assets/minecraft/items/{item}.json"
    gt = golem_texture(read_json(gp)) if gp in names else None
    rendered = special_render(item) or (None if gt in names else block_render(item))
    if rendered:
        icon = rendered
    elif gt in names:
        icon = "statue__" + os.path.basename(gt)
        dst = os.path.join(icons_dir, icon)
        if not os.path.exists(dst):
            write_golem_icon(gt, dst)
    elif tp:
        icon = tp[len("assets/minecraft/textures/"):].replace("/", "__")
        dst = os.path.join(icons_dir, icon)
        if not os.path.exists(dst):
            with open(dst, "wb") as f:
                f.write(jar.read(tp))
    items[item] = {"ko": lang_name(ko, item) or lang_name(en, item) or item,
                   "en": lang_name(en, item) or item,
                   "i": icon,
                   "g": 4 if group_for(item) == 3 and icon and icon.startswith("item__") else group_for(item)}
    shape = None if rendered else shape_for(item)
    if shape:
        items[item]["s"] = shape

# 구리 골렘은 아이템이 아니라 몹이라서 이름과 그림을 따로 넣는다
items["copper_golem"].update(ko=ko.get("entity.minecraft.copper_golem", "구리 골렘"),
                             en=en.get("entity.minecraft.copper_golem", "Copper Golem"),
                             i="statue__copper_golem.png", g=4)

# 한국어 이름이 겹치는 아이템 구분 (벽돌/벽돌 블록, 음반 - 13 등)
by_ko = {}
for i, v in items.items():
    by_ko.setdefault(v["ko"], []).append(i)
for ko_name, ids in by_ko.items():
    if len(ids) < 2:
        continue
    blocks = [i for i in ids if f"block.minecraft.{i}" in ko and f"item.minecraft.{i}" not in ko]
    for i in blocks:
        items[i]["ko"] = f"{ko_name} 블록"
    rest = [i for i in ids if i not in blocks]
    if len(rest) < 2:
        continue
    for i in rest:
        t = i.replace("_armor_trim_smithing_template", "").replace("_smithing_template", "")
        extra = (ko.get(f"item.minecraft.{i}.desc") or ko.get(f"trim_pattern.minecraft.{t}")
                 or ko.get(f"upgrade.minecraft.{t}") or items[i]["en"])
        items[i]["ko"] = f"{ko_name} ({extra})"

data = {"version": VERSION, "items": items, "recipes": recipes,
        "raw": sorted(raw), "storage": storage}
with open(os.path.join(SITE, "data.js"), "w", encoding="utf-8") as f:
    f.write("window.MC_DATA = ")
    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";\n")

print(f"버전 {VERSION}: 아이템 {len(items)}개, 레시피 {len(recipes)}개, 아이콘 {len(os.listdir(icons_dir))}개, "
      f"원재료 기본값 {len(raw)}개, 블록 짝 {len(storage)}개")
missing = [i for i, v in items.items() if not v["i"]]
print("아이콘 없음:", len(missing), missing[:30])
