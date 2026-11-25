# -*- coding: utf-8 -*-
"""
地块档案卡生成器（卡片输出全英文；中文只留在本文件注释与 skills/ 文档）
用法: python src/lot_card.py "17-08 149th St, Queens, NY" [--fresh]
"""
import argparse
import datetime
import json
import re
import shutil
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import acris
import dob
from rules import get_rule, ADU_RULES

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "cache"
CARDS_DIR = PROJECT_ROOT / "cards"
DESKTOP_DIR = Path.home() / "Desktop" / "地块档案卡"

GEOSEARCH_URL = "https://geosearch.planninglabs.nyc/v2/search"
PLUTO_URL = "https://data.cityofnewyork.us/resource/64uk-42ks.json"

# ---- 官方核验链接（模式实测记录见 skills/nyc_open_data_pipeline.md）----
# 已验证可用（2026-07-28，playwright 渲染/内容抽查）：ZoLa、ZR、ACRIS
# DocumentDetail、DOF PIP。DOB NOW 门户本机 403（与 BIS 同封锁族），
# 链接按官方入口格式输出，待人工点测。
ZOLA_LOT_URL = "https://zola.planning.nyc.gov/l/lot/{boro}/{block}/{lot}"
ACRIS_DOC_URL = ("https://a836-acris.nyc.gov/DS/DocumentSearch/"
                 "DocumentDetail?doc_id={doc_id}")
ACRIS_SEARCH_URL = "https://a836-acris.nyc.gov/DS/DocumentSearch/Index"
DOBNOW_PORTAL_URL = "https://a810-dobnow.nyc.gov/publish/Index.html"
DOF_PIP_URL = "https://propertyinformationportal.nyc.gov/parcels/parcel/{bbl}"
DATASET_URL = "https://data.cityofnewyork.us/d/{id}"
DATASET_LINKS = [  # 脚注静态目录链接（任务书指定七个）
    ("PLUTO", "64uk-42ks"), ("ACRIS Legals", "8h5j-fqxa"),
    ("ACRIS Master", "bnx9-e6tj"), ("ACRIS Parties", "636b-3b5g"),
    ("DOB NOW", "w9ak-ipjd"), ("Complaints", "eabe-havv"), ("ECB", "6bgk-3dad"),
]


def zr_url(section: str):
    """ZR 条款号 → zr.planning.nyc.gov 章节页（规则核实轮用过的同一批 URL；
    12-xx 在 Article I Chapter 2，2X-YY 在 Article II Chapter Y）。"""
    if section.startswith("12-"):
        return f"https://zr.planning.nyc.gov/article-i/chapter-2/{section}"
    return f"https://zr.planning.nyc.gov/article-ii/chapter-{section[1]}/{section}"

BOROUGH_EN = {"1": "Manhattan", "2": "Bronx", "3": "Brooklyn",
              "4": "Queens", "5": "Staten Island"}

# PLUTO lottype 代码 → 描述（语义沿用建表时的口径，仅换语言）
LOTTYPE_EN = {
    "0": "Mixed", "1": "Corner", "2": "Through", "3": "Multiple frontage",
    "4": "Landlocked", "5": "Interior",
}

# DOF 建筑类别代码 → 描述（V 段空地是本工具的重点标的类型）
BLDGCLASS_EN = {
    "A0": "one-family detached (Cape Cod)", "A1": "two-story detached single-family",
    "A2": "one-story detached single-family", "A3": "large detached single-family",
    "A4": "city row-house style single-family", "A5": "attached single-family",
    "A6": "summer cottage, single-family", "A7": "mansion-type single-family",
    "A8": "bungalow colony", "A9": "miscellaneous single-family",
    "B1": "two-family, brick", "B2": "two-family, frame",
    "B3": "two-family, converted", "B9": "miscellaneous two-family",
    "C0": "three-family walk-up", "C1": "multi-family walk-up (rental, no elevator)",
    "C2": "five- to six-family walk-up", "C3": "four-family walk-up",
    "C4": "old-law tenement", "C5": "converted apartment",
    "C6": "walk-up co-op", "C7": "walk-up with ground-floor stores",
    "C8": "co-op, converted", "C9": "garden apartments",
    # V 段：空地
    "V0": "vacant land (residential zoning)", "V1": "vacant land (commercial frontage)",
    "V2": "vacant land (not buildable)", "V3": "vacant land (other)",
    "V4": "vacant land (police/fire)", "V5": "vacant land (school)",
    "V6": "vacant land (library/hospital)", "V7": "vacant land (port/public)",
    "V8": "vacant land (utility)", "V9": "vacant land (other public)",
}

# 业主/当事人类型 → 卡面标签与配色
OWNER_TAGS = {
    acris.T_ESTATE: ("★ Estate sale (high-motivation seller)", "estate"),
    acris.T_REFEREE: ("Foreclosure-related", "estate"),
    acris.T_ENTITY: ("Likely developer-held", "yellow"),
    acris.T_INDIVIDUAL: ("Individually held", "green"),
}


# ---------- 工具函数 ----------

def fmt_num(val, decimals=0):
    """千分位格式化；缺失返回 —"""
    if val is None or val == "":
        return "—"
    try:
        f = float(val)
    except (TypeError, ValueError):
        return str(val)
    if decimals == 0:
        return f"{f:,.0f}"
    return f"{f:,.{decimals}f}"


def to_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def raw(pluto, key):
    """取 PLUTO 字段原始值，缺失返回 None"""
    v = pluto.get(key)
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    return v


def flag(pluto, key):
    """布尔型旗标字段：Socrata 对 MapPLUTO 部分字段（irrlotcode/splitzone）
    返回 JSON 布尔，另一些（pfirm15_flag）返回 '1'/'Y' 字符串——双形态兼容。
    返回 True / False / None（缺失）"""
    v = pluto.get(key)
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    if isinstance(v, bool):
        return v
    return str(v).strip().upper() in ("Y", "TRUE", "1")


def slugify(address: str) -> str:
    s = address.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def owner_tag_for(name: str):
    """业主名 → (标签, 样式)。分类逻辑与 ACRIS 共用一套词表。"""
    t = acris.classify_party(name)
    if t in OWNER_TAGS:
        return OWNER_TAGS[t]
    if t.startswith(acris.T_UNKNOWN):
        return "Unclassified", "yellow"
    return "—", "green"


def split_feasibility(rule, lotfront, lotarea):
    """A5: 分地判定①——detached 与 semi/attached（"other"）两档分别评估，
    分形态呈现（产品形态、售价、买家完全不同，✓ 必须标明是哪种 ✓）。
    仅当分区允许 other 形态（min_lot_*_other 非空）才出现第二段。
    返回 (any_ok, note)。ZR 23-11。"""
    segs, any_ok = [], False
    forms = [("detached", rule["min_lot_width_ft"], rule["min_lot_area_sqft"])]
    if rule.get("min_lot_width_other") and rule.get("min_lot_area_other"):
        forms.append(("semi-detached/other",
                      rule["min_lot_width_other"], rule["min_lot_area_other"]))
    for name, w, a in forms:
        need_w, need_a = 2 * w, 2 * a
        ok = lotfront >= need_w and lotarea >= need_a
        any_ok = any_ok or ok
        segs.append(f"{name} {'✓' if ok else '✗'} "
                    f"(needs 2×{fmt_num(w)} ft / 2×{fmt_num(a)} sqft "
                    f"= {fmt_num(need_w)} ft / {fmt_num(need_a)} sqft)")
    note = (f"have {fmt_num(lotfront)} ft / {fmt_num(lotarea)} sqft — "
            + " · ".join(segs) + " (ZR 23-11)")
    return any_ok, note


# ---------- 数据获取 ----------

def load_address_index():
    idx_file = CACHE_DIR / "address_index.json"
    if idx_file.exists():
        try:
            return json.loads(idx_file.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_address_index(idx):
    (CACHE_DIR / "address_index.json").write_text(
        json.dumps(idx, ensure_ascii=False, indent=2))


def geosearch(address: str, fresh: bool):
    """GeoSearch 拿 BBL。返回 (bbl, bin_count, geo_bins, geo_feature)
    geo_bins：本 BBL 名下的 BIN 列表，首选结果的 BIN 排第一（供 DOB 投诉查询
    与 BIS 链接用）。含区级占位 BIN（4000000）——由 dob.is_real_bin 过滤。"""
    slug = slugify(address)
    idx = load_address_index()

    data = None
    if not fresh and slug in idx:
        cached = CACHE_DIR / idx[slug] / "geosearch.json"
        if cached.exists():
            data = json.loads(cached.read_text())
            print(f"  [cache] geosearch ← {cached.relative_to(PROJECT_ROOT)}")

    if data is None:
        print(f"  [api] GeoSearch: {address}")
        resp = requests.get(GEOSEARCH_URL, params={"text": address}, timeout=30)
        resp.raise_for_status()
        data = resp.json()

    features = data.get("features") or []
    if not features:
        print("  ✗ GeoSearch returned no result — check the address spelling")
        sys.exit(1)

    def feat_bbl(f):
        # ⚠ BBL 必须从 addendum.pad.bbl 取（顶层 pad_bbl 是 null）
        return (((f.get("properties") or {}).get("addendum") or {})
                .get("pad") or {}).get("bbl")

    def feat_bin(f):
        return (((f.get("properties") or {}).get("addendum") or {})
                .get("pad") or {}).get("bin")

    # 只把与首选结果同等置信度的候选视为"歧义候选"
    top_conf = (features[0].get("properties") or {}).get("confidence") or 0
    peers = [f for f in features
             if abs(((f.get("properties") or {}).get("confidence") or 0) - top_conf) < 1e-6]
    distinct_bbls = []
    for f in peers:
        b = feat_bbl(f)
        if b and b not in distinct_bbls:
            distinct_bbls.append(b)

    chosen = features[0]
    if len(distinct_bbls) > 1:
        # A1: 既往选择（address_index）优先短路——重跑绝不换标的。
        # 要重选：删掉 cache/address_index.json 里对应条目再交互跑一次。
        known = idx.get(slug)
        if known and any(feat_bbl(f) == known for f in features):
            chosen = next(f for f in features if feat_bbl(f) == known)
            print(f"  [index] prior BBL choice {known} honored "
                  f"(delete the address_index entry to re-pick)")
        else:
            print("  ⚠ multiple distinct BBL candidates:")
            cands = []
            for b in distinct_bbls[:3]:
                f = next(x for x in peers if feat_bbl(x) == b)
                label = (f.get("properties") or {}).get("label", "?")
                cands.append((b, f))
                print(f"    [{len(cands)}] BBL {b}  {label}")
            if sys.stdin.isatty():
                try:
                    pick = int(input("  choose [1-{}]: ".format(len(cands))))
                except (ValueError, EOFError):
                    pick = 1
                pick = min(max(pick, 1), len(cands))
                chosen = cands[pick - 1][1]
            else:
                # A1: 非交互 + 无既往选择 → 宁可停下来，不可换标的
                print("  ✗ ambiguous address with no prior choice on file — "
                      "run once interactively to confirm the candidate")
                sys.exit(2)

    bbl = feat_bbl(chosen)
    if not bbl:
        print("  ✗ chosen candidate has no BBL (addendum.pad.bbl empty)")
        sys.exit(1)

    # 一地多楼检测：统计同 BBL 候选的不同 BIN 数；首选结果的 BIN 排第一
    geo_bins, seen = [], set()
    for f in [chosen] + [x for x in features if x is not chosen]:
        if feat_bbl(f) == bbl and feat_bin(f) and feat_bin(f) not in seen:
            seen.add(feat_bin(f))
            geo_bins.append(str(feat_bin(f)))
    bin_count = max(len(geo_bins), 1)

    # 原始返回存 cache/{BBL}/geosearch.json
    bbl_dir = CACHE_DIR / bbl
    bbl_dir.mkdir(parents=True, exist_ok=True)
    (bbl_dir / "geosearch.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    idx[slug] = bbl
    save_address_index(idx)

    return bbl, bin_count, geo_bins, chosen


def fetch_pluto(bbl: str, fresh: bool):
    """查 MapPLUTO，优先读 cache"""
    cached = CACHE_DIR / bbl / "pluto.json"
    if not fresh and cached.exists():
        print(f"  [cache] pluto ← {cached.relative_to(PROJECT_ROOT)}")
        data = json.loads(cached.read_text())
    else:
        print(f"  [api] MapPLUTO: bbl={bbl}")
        resp = requests.get(PLUTO_URL, params={
            "$where": f"bbl='{bbl}'",
            "$limit": 10,  # Socrata 必加 $limit
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    if not data:
        print(f"  ✗ MapPLUTO has no record for BBL {bbl}")
        sys.exit(1)
    return data[0]


def fetch_siblings(bbl: str, fresh: bool):
    """A4: 查同一 appbbl 指向本 BBL 的全部 lot（含自身）。用于区分
    apportionment 的两种形态：分割存留 lot（有兄弟）vs 并地（只有自己）。
    查询失败返回 None（调用方降级为中性文案，不猜）。"""
    cached = CACHE_DIR / bbl / "pluto_siblings.json"
    if not fresh and cached.exists():
        return json.loads(cached.read_text())
    try:
        resp = requests.get(PLUTO_URL, params={
            "$select": "bbl,appdate",
            "$where": f"appbbl='{int(bbl)}'",
            "$limit": 50,
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"  [api] PLUTO siblings of {bbl}: {len(data)} lot(s)")
    return data


# ---------- 业务判定 ----------

def build_context(address, bbl, bin_count, pluto, fresh=False):
    """把所有展示用数据算好，装进一个 dict"""
    c = {}
    c["address"] = raw(pluto, "address") or address
    c["borough_code"] = bbl[0]
    c["borough_en"] = BOROUGH_EN.get(bbl[0], "—")
    c["block"] = str(int(bbl[1:6])) if bbl[1:6].isdigit() else bbl[1:6]
    c["lot"] = str(int(bbl[6:])) if bbl[6:].isdigit() else bbl[6:]
    c["bbl"] = bbl
    c["zipcode"] = raw(pluto, "zipcode") or "—"
    cd = raw(pluto, "cd")
    c["cd"] = f"Queens CD {str(cd)[-2:].lstrip('0')}" if cd else "—"
    c["zone"] = raw(pluto, "zonedist1") or "—"
    c["zone2"] = raw(pluto, "zonedist2")
    c["schooldist"] = raw(pluto, "schooldist")
    c["school_label"] = (f"School District {int(float(c['schooldist']))}"
                         if c["schooldist"] else "—")
    # A3: 建筑数用 PLUTO numbldgs（空地=0）；GeoSearch BIN 计数含区级占位符
    # （4000000）不可靠，只留作 DOB 投诉查询的种子
    nb = to_float(raw(pluto, "numbldgs"))
    c["numbldgs"] = int(nb) if nb is not None else None
    c["bin_count"] = bin_count

    # 母地分割警示：appbbl 非空且 appdate 在近 5 年。
    # A4: appbbl == 自身 BBL（apportionment 保留原 lot 号）时不再自称
    # "母地是自己"——扫同 block 兄弟 lot 区分两种形态：
    #   有兄弟 lot 指向同一母地且同日 → 分割存留 lot（Retained lot）
    #   查无兄弟 → 并地（Lot merger，本 BBL 吸收了相邻 lot）
    c["subdiv_warn"] = None
    appbbl, appdate = raw(pluto, "appbbl"), raw(pluto, "appdate")
    if appbbl and appdate:
        d = None
        for pat in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                d = datetime.datetime.strptime(appdate[:26], pat)
                break
            except ValueError:
                continue
        if d and (datetime.datetime.now() - d).days <= 5 * 365:
            appbbl_s = str(int(float(appbbl)))
            if appbbl_s != bbl:
                c["subdiv_warn"] = (f"⚠ Subdivided from parent lot {appbbl_s} "
                                    f"on {d.date()}")
            else:
                sibs = fetch_siblings(bbl, fresh)
                if sibs is None:
                    c["subdiv_warn"] = (f"⚠ Lot apportionment recorded on {d.date()} "
                                        f"(sibling scan unavailable — verify manually)")
                else:
                    others = sorted({str(int(float(r["bbl"]))) for r in sibs
                                     if r.get("bbl")
                                     and str(int(float(r["bbl"]))) != bbl
                                     and (r.get("appdate") or "")[:10] == str(d.date())})
                    if others:
                        c["subdiv_warn"] = (
                            f"⚠ Retained lot from subdivision on {d.date()} — "
                            f"sibling lot(s) {', '.join(others)} split off, "
                            f"this lot kept its number")
                    else:
                        c["subdiv_warn"] = (
                            f"⚠ Lot merger on {d.date()} — adjacent lot(s) "
                            f"absorbed into this BBL")

    # 规矩：四个否决检查位  (label, 值, 状态 green/yellow/red, 说明)
    checks = []
    ov = raw(pluto, "overlay1")
    checks.append(("Commercial overlay", ov or "None",
                   "yellow" if ov else "green",
                   f"in commercial overlay {ov}" if ov else "Pass"))
    sp = raw(pluto, "spdist1")
    checks.append(("Special district", sp or "None",
                   "yellow" if sp else "green",
                   f"in special purpose district {sp}" if sp else "Pass"))
    lm, hd = raw(pluto, "landmark"), raw(pluto, "histdist")
    lm_hit = lm or hd
    checks.append(("Landmark / historic district", lm_hit or "None",
                   "red" if lm_hit else "green",
                   f"hit: {lm_hit}" if lm_hit else "Pass"))
    flood_hit = bool(flag(pluto, "pfirm15_flag"))
    checks.append(("FEMA flood zone", "1% annual chance" if flood_hit else "None",
                   "red" if flood_hit else "green",
                   "in FEMA 1% annual-chance flood zone (PFIRM 2015)"
                   if flood_hit else "Pass"))
    c["checks"] = checks

    # splitzone 警示（布尔/字符串双形态，见 flag()）
    c["splitzone_warn"] = None
    if flag(pluto, "splitzone"):
        c["splitzone_warn"] = (f"⚠ Split-zoned lot ({c['zone']} + {c['zone2'] or '?'}) — "
                               "potential figures are unreliable, verify on ZoLa")

    # 土地与现状
    c["lotarea"] = to_float(raw(pluto, "lotarea"))
    c["lotfront"] = to_float(raw(pluto, "lotfront"))
    c["lotdepth"] = to_float(raw(pluto, "lotdepth"))
    lt = raw(pluto, "lottype")
    lt_key = str(int(float(lt))) if lt else None
    c["lottype_label"] = (f"{LOTTYPE_EN.get(lt_key, 'Unknown')} ({lt_key})"
                          if lt_key else "—")
    irr = flag(pluto, "irrlotcode")
    c["irr_label"] = "—" if irr is None else ("Irregular lot" if irr else "Regular lot")
    yb = to_float(raw(pluto, "yearbuilt"))
    c["yearbuilt"] = str(int(yb)) if yb else "—"
    bc = raw(pluto, "bldgclass")
    c["bldgclass_label"] = (f"{bc} – {BLDGCLASS_EN[bc]}" if bc in BLDGCLASS_EN else
                            (f"{bc} – class not in dictionary" if bc else "—"))
    c["unitsres"] = to_float(raw(pluto, "unitsres"))
    c["bldgarea"] = to_float(raw(pluto, "bldgarea"))
    c["numfloors"] = to_float(raw(pluto, "numfloors"))

    # 潜力
    c["residfar"] = to_float(raw(pluto, "residfar"))
    c["builtfar"] = to_float(raw(pluto, "builtfar"))
    c["commfar"] = to_float(raw(pluto, "commfar"))
    # A6: 非 R 分区（C/M/PARK…）——本工具只建模住宅 FAR，潜力板块整体降级
    # 免责；builtFAR 是毛面积口径，不作超建依据
    c["nonres"] = not c["zone"].upper().startswith("R")
    c["nonres_warn"] = None
    if c["nonres"]:
        cf = fmt_num(c["commfar"], 2) if c["commfar"] is not None else "—"
        c["nonres_warn"] = (
            f"⚠ Non-residential district ({c['zone']}) — this tool models "
            f"residential FAR only (commFAR {cf} not modeled). Figures below are "
            f"a residential-lens reference, not development guidance; builtFAR is "
            f"gross-area based and not evidence of overbuild.")
    if c["lotarea"] is not None and c["residfar"] is not None:
        c["allowed_sf"] = c["lotarea"] * c["residfar"]
    else:
        c["allowed_sf"] = None
    used = c["bldgarea"] or 0
    if c["allowed_sf"] is not None:
        c["unused_sf"] = c["allowed_sf"] - used
        c["util_pct"] = (used / c["allowed_sf"] * 100) if c["allowed_sf"] else None
    else:
        c["unused_sf"] = None
        c["util_pct"] = None
    # 超建（合法不合规老房）：未用面积为负 → teardown 排除信号。
    # A6: 非 R 分区不给 teardown 结论（住宅 FAR 视角在此不成立）
    c["overbuilt"] = (c["unused_sf"] is not None and c["unused_sf"] < 0
                      and not c["nonres"])
    c["overbuilt_msg"] = (f"★ Overbuilt lot — teardown not applicable: existing "
                          f"{fmt_num(used)} sqft > allowed {fmt_num(c['allowed_sf'])} sqft, "
                          f"rebuilding would lose floor area") if c["overbuilt"] else None

    # 开发潜力四行（规则已对照现行 ZR 核实，见 src/rules.py 与
    # skills/zoning_rules_r_districts.md）
    rule = get_rule(c["zone"])
    lines = []

    # FAR 交叉验证：rules.py（ZR 23-21）与 PLUTO residfar 不一致 → 报矛盾
    c["far_conflict"] = None
    if rule and c["residfar"] is not None and abs(rule["far"] - c["residfar"]) > 1e-6:
        c["far_conflict"] = (f"⚠ Rule conflict: ZR 23-21 standard FAR {rule['far']} ≠ "
                             f"PLUTO residFAR {c['residfar']} — verify manually")

    # ① 分地（ZR 23-11）——A5: detached / semi-other 两档分别判（见 split_feasibility）
    if rule and rule["min_lot_width_ft"] and rule["min_lot_area_sqft"] and \
            c["lotfront"] is not None and c["lotarea"] is not None:
        splittable, note = split_feasibility(rule, c["lotfront"], c["lotarea"])
        lines.append(("① Subdivision", "✓" if splittable else "✗",
                      "Split feasibility: " + note))
    else:
        splittable = False
        lines.append(("① Subdivision", "?",
                      f"no subdivision rule on file for {c['zone']}"))

    # ② 户型（ZR 22-121 / 22-122）
    units_per_lot = rule["units_per_lot"] if rule else None
    if rule and units_per_lot:
        lines.append(("② Dwelling type", "✓",
                      f"{c['zone']} allows {units_per_lot} dwelling unit(s) per lot "
                      f"({rule['forms']}) (ZR 22-121/22-122)"))
    elif rule and units_per_lot is None and rule.get("verified"):
        lines.append(("② Dwelling type", "✓",
                      f"{c['zone']} allows multiple dwellings — no fixed unit cap, "
                      f"bounded by FAR/bulk (ZR 22-121/22-122)"))
    else:
        lines.append(("② Dwelling type", "?",
                      f"no dwelling-type rule on file for {c['zone']}"))

    # ③ 单元乘法
    lots_possible = 2 if splittable else 1
    cur = int(c["unitsres"]) if c["unitsres"] is not None else "—"
    if units_per_lot:
        potential_units = lots_possible * units_per_lot
        lines.append(("③ Unit multiplication", "→",
                      f"now {cur} unit(s) → potential = {lots_possible} lot × "
                      f"{units_per_lot} unit(s)/lot = {potential_units} unit(s)"))
    elif rule and rule.get("verified"):
        lines.append(("③ Unit multiplication", "→",
                      f"now {cur} unit(s) → multi-family district has no fixed unit cap; "
                      f"size off the {fmt_num(c['unused_sf'])} sqft of unused floor area"))
    else:
        lines.append(("③ Unit multiplication", "?",
                      "no per-lot unit rule — cannot compute"))

    # ④ ADU（ZR 12-10 "ancillary dwelling unit"，CoY 2024-12 新增）
    units_now = int(c["unitsres"]) if c["unitsres"] is not None else None
    if units_now is not None and units_now not in ADU_RULES["eligible_units"]:
        lines.append(("④ ADU potential", "✗",
                      f"{units_now} existing unit(s) — ADUs apply only to one- and "
                      f"two-family residences (ZR 12-10)"))
    else:
        conds = ["owner-occupancy (the lot must be the owner's primary residence "
                 "when the ADU is first occupied)"]
        blocked = []
        # 后院式在 R1-2A/R2A/R3A 且 GTZ 之外禁止；GTZ 位置数据里没有 → 列为条件
        if c["zone"] in ADU_RULES["backyard_banned_districts_beyond_gtz"]:
            conds.append(f"backyard type only if the lot sits inside the Greater Transit "
                         f"Zone ({c['zone']} bans backyard ADUs beyond the GTZ)")
        # 历史区：PLUTO histdist 可直接判
        if raw(pluto, "histdist"):
            blocked.append("backyard type banned inside historic districts")
        # 洪水：pfirm15 命中 → 高风险洪水区限制；DEP 降雨/沿海图数据里没有
        if flag(pluto, "pfirm15_flag"):
            blocked.append("FEMA flood zone: no ADU below the flood-resistant "
                           "construction elevation")
        conds.append("not inside a DEP flood-risk area (which would ban cellar and "
                     "backyard types — check the map)")
        note = (f"each 1–2 family residence may add one ADU ≤{ADU_RULES['max_floor_area_sqft']} "
                f"sqft; counts toward FAR, counts as a dwelling unit, 0 parking required "
                f"(ZR 12-10 / 25-232). Conditional on: {'; '.join(conds)}")
        if blocked:
            note += f". Known restrictions: {'; '.join(blocked)}"
        lines.append(("④ ADU potential", "◐", "May apply: " + note))
    c["potential_lines"] = lines

    # 权属（分类词表与 ACRIS 当事人共用，见 acris.classify_party）
    c["ownername"] = raw(pluto, "ownername") or "—"
    c["owner_tag"], c["owner_style"] = owner_tag_for(c["ownername"])
    c["assessland"] = to_float(raw(pluto, "assessland"))
    c["assesstot"] = to_float(raw(pluto, "assesstot"))

    c["pluto_version"] = raw(pluto, "version") or "—"
    c["gen_date"] = datetime.date.today().isoformat()

    # 官方核验链接：ZoLa 地块页 / DOF PIP / 潜力板块引用到的 ZR 条款
    c["zola_url"] = ZOLA_LOT_URL.format(boro=int(bbl[0]), block=int(bbl[1:6]),
                                        lot=int(bbl[6:]))
    c["pip_url"] = DOF_PIP_URL.format(bbl=bbl)
    cited = []
    for _, _, note in lines:
        for span in re.findall(r"ZR ([0-9\-/ ]+)", note):
            for sec in re.split(r"[/ ]+", span):
                if re.fullmatch(r"\d{2}-\d{2,4}", sec) and sec not in cited:
                    cited.append(sec)
    c["zr_cited"] = cited
    return c


def provenance(c):
    """bldgarea 出处说明。有活跃 DM/NB 备案时升级为警告——此时 PLUTO 快照
    既不是原建筑也不是新建筑，两头不靠。返回 (文本, 是否警告级)。"""
    d = c.get("dob") or {}
    ver = c["pluto_version"]
    if d.get("mode") == "a":
        return (f"⚠ Building data per PLUTO {ver} snapshot. Active demolition/"
                f"construction filings exist — figures may reflect neither the "
                f"original nor the new structure.", True)
    return (f"Building data per PLUTO {ver} snapshot.", False)


def verify_links(c, section):
    """各板块的官方核验链接 → [(名称, url, 是否展示短 URL)]。
    短 URL 只在首次出现该目的地时展示（PNG 不可点击，读者需要看得见的
    地址；同卡重复出现只给 名称 ↗）。ZR 链接不展示 URL——条款号本身
    就是可检索的引用。"""
    zola = c["zola_url"]
    d = c.get("dob") or {}
    if section == "identity":
        return [("ZoLa", zola, True)]
    if section in ("zoning", "land"):
        return [("ZoLa", zola, False)]
    if section == "potential":
        out = [("ZoLa", zola, False)]
        out += [(f"ZR {s}", zr_url(s), False) for s in c.get("zr_cited", [])]
        return out
    if section == "sales":
        return [("ACRIS search", ACRIS_SEARCH_URL, True)]
    if section == "construction":
        b = d.get("primary_bin")
        name = f"DOB NOW Portal (search BIN {b})" if b else "DOB NOW Portal (search by address)"
        return [(name, DOBNOW_PORTAL_URL, True)]
    if section == "dob_summary":
        return [("DOB BIS", c["bis_url"], True)] if c.get("bis_url") else []
    if section == "ownership":
        return [("DOF Property Portal", c["pip_url"], True),
                ("ACRIS search", ACRIS_SEARCH_URL, False)]
    return []


def _short(url):
    return url.replace("https://", "").replace("http://", "")


def verify_md(c, section):
    links = verify_links(c, section)
    if not links:
        return None
    parts = []
    for name, url, show in links:
        parts.append(f"[{name} ↗]({url})" + (f" `{_short(url)}`" if show else ""))
    return "<sub>Verify: " + " · ".join(parts) + "</sub>"


def verify_html(c, section, esc):
    links = verify_links(c, section)
    if not links:
        return ""
    parts = []
    for name, url, show in links:
        a = f'<a href="{esc(url)}">{esc(name)} ↗</a>'
        if show:
            a += f' <span class="vurl">{esc(_short(url))}</span>'
        parts.append(a)
    return '<div class="verify">Verify: ' + " · ".join(parts) + "</div>"


def source_line(c):
    """B2: 脚注分源数据时效——ACRIS good_through / DOB run 日期 / PLUTO 版本，
    生成日期单列（生成日 ≠ 数据日）。深挖报告的时效纪律对齐到卡片。"""
    a = c.get("acris") or {}
    d = c.get("dob") or {}
    gt = a.get("good_through") or "—"
    dd = d.get("data_date") or "—"
    return (f"Sources: NYC GeoSearch + MapPLUTO {c['pluto_version']} · "
            f"ACRIS good through {gt} · DOB run {dd} · generated {c['gen_date']}")


# ---------- 成交历史（ACRIS）行构造 ----------

def acris_rows(sig):
    """信号 dict → [(标签, 文本, 样式, 文书链接)]，样式: normal/good/warn/hot/small
    文书链接 = [(名称, url)]（DEED/MTGE 直达 ACRIS DocumentDetail），无则 []。
    供 md/html/终端三处共用（终端忽略链接）"""
    if not sig:
        return []
    if sig.get("error"):
        return [("Sales history", f"ACRIS query failed: {sig['error']}", "warn", [])]
    if sig.get("no_records"):
        return [("Sales history", "no ACRIS record (rare — verify manually)", "warn", [])]

    def doc_links(items):
        return [(n, ACRIS_DOC_URL.format(doc_id=i)) for n, i in items if i]

    rows = []
    if sig.get("from_mother"):
        rows.append(("", f"⚠ Newly subdivided lot with no ACRIS instruments of its own; "
                         f"the following are records of parent lot {sig['from_mother']}",
                     "small", []))
    ls = sig.get("last_sale")
    if ls:
        held = ls["years_held"]
        txt = f"{ls['date']} · ${fmt_num(ls['price'])} · held {held} years to date"
        style = "normal"
        if held >= 20:
            txt += "  ★ long-term hold"
            style = "hot"
        rows.append(("Last transfer", txt, style,
                     doc_links([("DEED", ls.get("doc_id"))])))
        seller_names = ", ".join(ls["sellers"]) or "—"
        buyer_names = ", ".join(ls["buyers"]) or "—"
        txt = (f"{ls['seller_type']} ({seller_names}) → "
               f"{ls['buyer_type']} ({buyer_names})")
        hot = ls["seller_type"] in (acris.T_ESTATE, acris.T_REFEREE) or \
            ls["buyer_type"] == acris.T_REFEREE
        rows.append(("Seller → buyer", txt, "hot" if hot else "normal", []))
    else:
        note = "no modern market sale on record"
        if sig.get("has_deep_history"):
            note += " (title changes may all predate digitization)"
        rows.append(("Last transfer", note,
                     "hot" if sig.get("sleepy") else "normal", []))

    om = sig["open_mortgage"]
    if om["status"] == "clear":
        rows.append(("Current debt", "no unsatisfied mortgage ✓", "good", []))
    elif om["status"] == "open":
        det = "; ".join(f"${fmt_num(m['amt'])} unsatisfied (MTGE {m['date']})"
                        for m in om["detail"])
        rows.append(("Current debt", f"⚠ {det}", "warn",
                     doc_links([(f"MTGE {m['date']}", m.get("doc_id"))
                                for m in om["detail"]])))
    else:
        det = "; ".join(f"MTGE {m['date']} ${fmt_num(m['amt'])}" for m in om["detail"])
        rows.append(("Current debt",
                     f"⚠ mortgage(s) with no confirmed satisfaction (pairing is "
                     f"ambiguous, verify manually): {det}", "warn",
                     doc_links([(f"MTGE {m['date']}", m.get("doc_id"))
                                for m in om["detail"]])))
    hm = sig.get("historical_mortgages") or []
    if hm:
        det = "; ".join(f"MTGE {m['date']} ${fmt_num(m['amt'])}" for m in hm)
        rows.append(("", f"{len(hm)} historical mortgage(s), presumed paid off at closing "
                         f"(no SAT recorded): {det}", "small", []))

    if sig.get("lis_pendens"):
        rows.append(("Risk signal", f"⚠ LIS PENDENS {sig['lis_pendens']}, no sale since — "
                                    f"matter unresolved", "warn", []))
    else:
        rows.append(("Risk signal", "no LIS PENDENS ✓", "good", []))

    txt = f"{sig['pulse_10y']} instrument(s) in the past 10 years"
    if sig.get("sleepy"):
        txt += "  ★ dormant asset"
    rows.append(("Transaction pulse", txt, "hot" if sig.get("sleepy") else "normal", []))

    if sig.get("nominal_deeds"):
        rows.append(("", f"plus {sig['nominal_deeds']} nominal transfer deed(s) "
                         f"(<$10,000, not counted as sale price)", "small", []))
    if sig.get("has_deep_history"):
        rows.append(("", f"plus {sig['legacy_count']} microfilm-era instrument(s) — "
                         f"deep title history", "small", []))
    if sig.get("truncated"):
        rows.append(("", "⚠ instrument list may be incomplete (query cap hit — "
                         "rerun with --fresh)", "small", []))

    bg = sig.get("bargain")
    if bg:
        txt = f"{bg['level']} — {bg['reason']}"
        if sig.get("from_mother"):
            txt += " (based on parent-lot records)"
        rows.append(("Bargaining leverage", txt, "hot" if bg["level"] == "High" else "normal", []))
    return rows


# ---------- 施工动态（DOB）行构造 ----------

def _fmt_group(g):
    parts = [g["job_type"]]
    if g.get("filing_date"):
        parts.append(f"filed {g['filing_date']}")
    parts.append(g["status"])
    if g.get("cost"):
        parts.append(f"cost ${fmt_num(g['cost'])}")
    if g.get("floor_area"):
        parts.append(f"{fmt_num(g['floor_area'])} sqft")
    if g.get("n_filings", 1) > 1:
        parts.append(f"{g['n_filings']} filings")
    # BIS 侧条目附简述并标系统来源——SI/BPP 这类工单光看类型名看不出内容，
    # 且提醒读者这是 DOB NOW 之外的另一套账
    if g.get("source") == "BIS":
        if g.get("description"):
            parts.append(f'"{g["description"][:60]}"')
        parts.append("[BIS]")
    return " · ".join(parts)


def dob_rows(sig):
    """DOB 信号 → [(标签, 文本, 样式)]；样式复用 acris_rows 的体系，
    另加 banner（红条）/banner_y（黄条）/item（缩进条目）"""
    if not sig:
        return []
    if sig.get("error"):
        return [("Construction activity", f"DOB query failed: {sig['error']}", "warn")]

    rows = []
    if sig["mode"] == "a":
        rows.append(("", "⚠ Active development on this lot", "banner"))
        for g in sig["active_heavy"] + sig["active_alt"]:
            rows.append(("", _fmt_group(g), "item"))
        rows.append(("", "→ Conditions on the ground may differ from the PLUTO "
                         "record above", "small"))
    elif sig["mode"] == "b":
        rows.append(("", "Active alteration filings (non-major)", "banner_y"))
        for g in sig["active_alt"]:
            rows.append(("", _fmt_group(g), "item"))
    else:
        rows.append(("Construction activity", "no active filings ✓", "good"))

    n_dob, n_ecb = sig["open_dob_violations"], sig["open_ecb_violations"]
    if n_dob or n_ecb:
        txt = f"⚠ {n_dob} DOB + {n_ecb} ECB open"
        if sig.get("ecb_balance_due"):
            txt += f" (ECB balance due ${fmt_num(sig['ecb_balance_due'])})"
        rows.append(("Violations", txt, "warn"))
    else:
        rows.append(("Violations", "no open violations ✓", "good"))
    return rows


# ---------- DOB Summary（对标 BIS Property Profile 概览） ----------

def dob_summary(sig):
    """→ (表格行 [(指标, 总数, 未结)], 链接说明行 [文本])。
    ARA/LAA 与 BIS "Actions" 是 BIS 内部数据，无公开数据源 → 不列，不编。"""
    if not sig or sig.get("error"):
        return [], []
    comp_t = fmt_num(sig["total_complaints"]) if sig["complaints_available"] else "n/a"
    comp_o = fmt_num(sig["open_complaints"]) if sig["complaints_available"] else "n/a"
    # 备案双行分账：BIS 与 DOB NOW 是不互数的双系统，对照 BIS 页面时
    # 各对各的数（DOB NOW 主数 = 逐份 filing，括注项目组；BIS = 去重 job）
    n_fil, n_proj = sig["dobnow_filing_count"], sig["dobnow_project_count"]
    dobnow_cell = fmt_num(n_fil)
    if n_fil:
        dobnow_cell += f" ({n_proj} project{'' if n_proj == 1 else 's'})"
    table = [
        ("Complaints", comp_t, comp_o),
        ("Violations – DOB", fmt_num(sig["total_dob_violations"]),
         fmt_num(sig["open_dob_violations"])),
        ("Violations – OATH/ECB", fmt_num(sig["total_ecb_violations"]),
         fmt_num(sig["open_ecb_violations"])),
        ("Filings — DOB NOW", dobnow_cell, "—"),
        ("Jobs — BIS", fmt_num(sig["bis_job_count"]), "—"),
        ("Unpaid ECB balance", f"${fmt_num(sig['ecb_balance_due'])}", "—"),
    ]
    notes = ["BIS-only metrics (Actions, ARA/LAA) are not published as open "
             "data — see BIS link below."]
    if not sig["complaints_available"]:
        notes.append("Complaints unavailable: the DOB complaints dataset is keyed on "
                     "BIN only, and no building BIN resolves for this lot.")
    if sig.get("extra_bins"):
        notes.append("Additional structures: BIN " + ", ".join(sig["extra_bins"]))
    if sig.get("truncated"):
        notes.append("⚠ Counts may be incomplete — query cap hit on: "
                     + ", ".join(sig["truncated"]) + " (rerun with --fresh)")
    return table, notes


# ---------- Markdown 渲染 ----------

def render_md(c):
    d = c.get("dob") or {}
    dev_active = d.get("mode") == "a"
    has_viol = bool(d.get("open_dob_violations") or d.get("open_ecb_violations"))
    prov_txt, prov_warn = provenance(c)
    prov_md = f"> {prov_txt}" if prov_warn else f"<sub>{prov_txt}</sub>"
    L = []
    L.append(f"# {c['address']}, Queens, NY {c['zipcode']}")
    badges = ""
    if dev_active:
        badges += " · 🔴 **UNDER DEVELOPMENT**"
    if has_viol:
        badges += " · 🟡 **VIOLATIONS**"
    L.append(f"**{c['cd']}** · Zoning **{c['zone']}** · BBL `{c['bbl']}`{badges}")
    L.append("\n---\n")
    L.append("## Identity")
    L.append(f"- BBL breakdown: {c['borough_en']} ({c['borough_code']}) / "
             f"Block {c['block']} / Lot {c['lot']}")
    L.append(f"- School: {c['school_label']}")
    nb = c["numbldgs"] if c["numbldgs"] is not None else "—"
    L.append(f"- Structures on site: {nb} (PLUTO)")
    if c["subdiv_warn"]:
        L.append(f"- {c['subdiv_warn']}")
    if verify_md(c, "identity"):
        L.append(verify_md(c, "identity"))
    L.append("\n## Zoning Checks")
    for label, val, style, note in c["checks"]:
        mark = {"green": "🟢", "yellow": "🟡", "red": "🔴"}[style]
        L.append(f"- {mark} {label}: {val} ({note})")
    if c["splitzone_warn"]:
        L.append(f"- {c['splitzone_warn']}")
    if verify_md(c, "zoning"):
        L.append(verify_md(c, "zoning"))
    L.append("\n## Land & Structure")
    L.append(prov_md)
    L.append(f"- Lot area: {fmt_num(c['lotarea'])} sqft"
             f" ({fmt_num(c['lotfront'])} ft × {fmt_num(c['lotdepth'])} ft)")
    L.append(f"- Lot type: {c['lottype_label']} · {c['irr_label']}")
    L.append(f"- Built {c['yearbuilt']} · {c['bldgclass_label']}")
    L.append(f"- Existing: {fmt_num(c['unitsres'])} unit(s) · "
             f"{fmt_num(c['bldgarea'])} sqft · {fmt_num(c['numfloors'], 1)} floors")
    if verify_md(c, "land"):
        L.append(verify_md(c, "land"))
    L.append("\n## Development Potential")
    L.append(prov_md)
    if c.get("nonres_warn"):
        L.append(f"> {c['nonres_warn']}")
    if c["splitzone_warn"]:
        L.append(f"> {c['splitzone_warn']}")
    if c.get("far_conflict"):
        L.append(f"> {c['far_conflict']}")
    far = fmt_num(c['residfar'], 2) if c['residfar'] is not None else "—"
    bfar = fmt_num(c['builtfar'], 2) if c['builtfar'] is not None else "—"
    L.append(f"- Allowed: **{fmt_num(c['allowed_sf'])} sqft** "
             f"({fmt_num(c['lotarea'])} × residFAR {far})")
    L.append(f"- Built: {fmt_num(c['bldgarea'])} sqft (builtFAR {bfar})")
    util = f"{c['util_pct']:.0f}%" if c["util_pct"] is not None else "—"
    if c.get("nonres"):
        L.append(f"- R-lens residual: {fmt_num(c['unused_sf'])} sqft "
                 f"(reference only — see disclaimer above)")
    elif c["overbuilt"]:
        L.append(f"- ⚠ **{c['overbuilt_msg']}**")
    else:
        L.append(f"- ★ Unused: **{fmt_num(c['unused_sf'])} sqft** ({util} utilized)")
    L.append("")
    for label, mark, note in c["potential_lines"]:
        L.append(f"- {label} {mark}: {note}")
    if verify_md(c, "potential"):
        L.append(verify_md(c, "potential"))
    L.append("\n## Sales History")
    for label, txt, style, links in acris_rows(c.get("acris")):
        lk = "".join(f" [{n} ↗]({u})" for n, u in links)
        if style == "small":
            L.append(f"  - <sub>{txt}</sub>")
        else:
            L.append(f"- {label}: {txt}{lk}")
    if verify_md(c, "sales"):
        L.append(verify_md(c, "sales"))
    L.append("\n## Construction Activity")
    for label, txt, style in dob_rows(d):
        if style == "small":
            L.append(f"  - <sub>{txt}</sub>")
        elif style in ("banner", "banner_y"):
            L.append(f"> **{txt}**")
        elif style == "item":
            L.append(f"- {txt}")
        else:
            L.append(f"- {label}: {txt}")
    if verify_md(c, "construction"):
        L.append(verify_md(c, "construction"))
    table, notes = dob_summary(d)
    if table:
        L.append("\n## DOB Summary")
        L.append("| Metric | Total | Open |")
        L.append("|---|---:|---:|")
        for metric, total, openv in table:
            L.append(f"| {metric} | {total} | {openv} |")
        L.append("")
        for n in notes:
            L.append(f"  - <sub>{n}</sub>")
        if verify_md(c, "dob_summary"):
            L.append(verify_md(c, "dob_summary"))
    L.append("\n## Ownership")
    if c.get("owner_dual"):
        od = c["owner_dual"]
        L.append(f"- Owner (per ACRIS): {od['acris_names']} · **{od['tag']}**")
        L.append(f"  - <sub>{od['note']}</sub>")
    else:
        L.append(f"- Owner: {c['ownername']} · **{c['owner_tag']}**")
    L.append(f"- Assessed value: land ${fmt_num(c['assessland'])} · "
             f"total ${fmt_num(c['assesstot'])}")
    if verify_md(c, "ownership"):
        L.append(verify_md(c, "ownership"))
    L.append("\n---")
    L.append(f"*{source_line(c)}*")
    ds = " · ".join(f"[{n} ↗]({DATASET_URL.format(id=i)})" for n, i in DATASET_LINKS)
    L.append(f"<sub>Datasets: {ds}</sub>")
    return "\n".join(L) + "\n"


# ---------- HTML 渲染 ----------

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#f2f3f5; font-family:-apple-system,"Helvetica Neue",Arial,sans-serif;
       color:#1f2329; padding:16px; }
.card { max-width:560px; margin:0 auto; background:#fff; border:1px solid #dfe2e8;
        border-radius:12px; padding:24px; }
.section { border-top:1px solid #eceef1; margin-top:18px; padding-top:14px; }
.sec-title { font-size:13px; color:#8a919c; letter-spacing:2px; margin-bottom:10px;
             text-transform:uppercase; }
.header .addr { font-size:20px; font-weight:700; }
.header .sub { font-size:13px; color:#5c6570; margin-top:4px; }
.badge { display:inline-block; background:#1f2329; color:#fff; font-size:12px;
         padding:2px 8px; border-radius:4px; margin-right:6px; vertical-align:1px; }
.badge.red { background:#a12622; }
.badge.yellow { background:#b8860b; }
.dob-banner { background:#fdebea; border:1px solid #f0b9b6; color:#a12622;
              font-size:13px; font-weight:700; border-radius:6px; padding:6px 10px; margin-bottom:8px; }
.dob-banner.y { background:#fff7e6; border-color:#ffe1a8; color:#8a5a00; }
.dob-item { font-size:13px; padding:3px 0 3px 12px; border-left:3px solid #f0b9b6; margin:4px 0; }
.bbl { font-family:"SF Mono",Menlo,Consolas,monospace; font-size:13px; color:#5c6570; }
.row { display:flex; justify-content:space-between; font-size:14px; padding:3px 0; }
.row .k { color:#8a919c; flex-shrink:0; margin-right:12px; }
.row .v { text-align:right; }
.warnline { background:#fff7e6; border:1px solid #ffe1a8; color:#8a5a00;
            font-size:13px; border-radius:6px; padding:6px 10px; margin-top:8px;
            margin-bottom:8px; }
.provenance { font-size:11.5px; color:#aab0b8; margin-bottom:8px; }
.checks { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.chk { border-radius:6px; padding:8px 10px; font-size:13px; }
.chk .t { font-size:12px; opacity:.75; }
.chk .r { font-weight:600; margin-top:2px; }
.chk.green { background:#eaf7ec; color:#1e6b2e; }
.chk.yellow { background:#fff7e6; color:#8a5a00; }
.chk.red { background:#fdebea; color:#a12622; }
.nums { display:flex; gap:8px; margin-bottom:12px; }
.num { flex:1; border:1px solid #eceef1; border-radius:8px; padding:10px 8px; text-align:center; }
.num .big { font-size:19px; font-weight:700; }
.num .lab { font-size:11px; color:#8a919c; margin-top:3px; line-height:1.5; }
.num.hl { background:#e8f1ff; border-color:#bcd6ff; }
.num.hl .big { color:#1250b8; }
.num.over { background:#fff3e0; border-color:#ffcc80; }
.num.over .big { color:#b45309; }
.plist { font-size:13.5px; line-height:1.8; }
.plist .mk { display:inline-block; width:1.4em; font-weight:700; }
.mk.ok { color:#1e6b2e; } .mk.no { color:#a12622; } .mk.q { color:#8a919c; }
.owner-tag { display:inline-block; font-size:12px; border-radius:4px; padding:2px 8px; margin-left:6px; }
.owner-tag.green { background:#eaf7ec; color:#1e6b2e; }
.owner-tag.yellow { background:#fff7e6; color:#8a5a00; }
.owner-tag.estate { background:#a12622; color:#fff; font-weight:700; }
.v.a-good { color:#1e6b2e; }
.v.a-warn { color:#a12622; font-weight:600; }
.v.a-hot { color:#8a5a00; font-weight:600; background:#fff7e6; border-radius:4px; padding:1px 6px; }
.acris-small { font-size:11.5px; color:#aab0b8; padding:2px 0; }
.sumtab { width:100%; border-collapse:collapse; font-size:13.5px; }
.sumtab th { font-size:11px; color:#8a919c; font-weight:600; text-transform:uppercase;
             letter-spacing:.5px; text-align:right; padding:0 0 6px; }
.sumtab th:first-child { text-align:left; }
.sumtab td { padding:5px 0; border-top:1px solid #f2f3f5; text-align:right;
             font-variant-numeric:tabular-nums; }
.sumtab td:first-child { text-align:left; color:#5c6570; }
.sumtab td.open-hit { color:#a12622; font-weight:700; }
.bislink { font-size:12px; margin-top:10px; word-break:break-all; }
.bislink a { color:#1250b8; text-decoration:none; }
.verify { font-size:11px; color:#aab0b8; margin-top:10px; }
.verify a { color:#7a94c9; text-decoration:none; }
.verify .vurl { color:#aab0b8; word-break:break-all; }
.doclink { font-size:11px; color:#7a94c9; text-decoration:none; white-space:nowrap; }
.footer { font-size:11px; color:#aab0b8; margin-top:16px; padding-top:10px;
          border-top:1px solid #eceef1; }
"""


def render_html(c):
    def esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    checks_html = ""
    for label, val, style, note in c["checks"]:
        checks_html += (f'<div class="chk {style}"><div class="t">{esc(label)}</div>'
                        f'<div class="r">{esc(note if style=="green" else val)}</div></div>')

    subdiv = f'<div class="warnline">{esc(c["subdiv_warn"])}</div>' if c["subdiv_warn"] else ""
    splitw = f'<div class="warnline">{esc(c["splitzone_warn"])}</div>' if c["splitzone_warn"] else ""
    farw = f'<div class="warnline">{esc(c["far_conflict"])}</div>' if c.get("far_conflict") else ""

    prov_txt, prov_warn = provenance(c)
    prov_html = (f'<div class="warnline">{esc(prov_txt)}</div>' if prov_warn
                 else f'<div class="provenance">{esc(prov_txt)}</div>')

    far = fmt_num(c["residfar"], 2) if c["residfar"] is not None else "—"
    bfar = fmt_num(c["builtfar"], 2) if c["builtfar"] is not None else "—"
    util = f"{c['util_pct']:.0f}%" if c["util_pct"] is not None else "—"
    nonres_html = (f'<div class="warnline">{esc(c["nonres_warn"])}</div>'
                   if c.get("nonres_warn") else "")
    if c.get("nonres"):
        num3 = (f'<div class="num"><div class="big">{fmt_num(c["unused_sf"])}</div>'
                f'<div class="lab">R-lens residual sqft<br>reference only</div></div>')
        overbuilt_html = ""
    elif c.get("overbuilt"):
        num3 = (f'<div class="num over"><div class="big">{fmt_num(abs(c["unused_sf"]))}</div>'
                f'<div class="lab">★ sqft over the limit<br>{util} utilized</div></div>')
        overbuilt_html = f'<div class="warnline">⚠ {esc(c["overbuilt_msg"])}</div>'
    else:
        num3 = (f'<div class="num hl"><div class="big">{fmt_num(c["unused_sf"])}</div>'
                f'<div class="lab">★ unused sqft<br>{util} utilized</div></div>')
        overbuilt_html = ""

    d = c.get("dob") or {}
    dev_active = d.get("mode") == "a"
    has_viol = bool(d.get("open_dob_violations") or d.get("open_ecb_violations"))
    head_badges = ""
    if dev_active:
        head_badges += '<span class="badge red">UNDER DEVELOPMENT</span>'
    if has_viol:
        head_badges += '<span class="badge yellow">VIOLATIONS</span>'

    dob_html = ""
    for label, txt, style in dob_rows(d):
        if style == "banner":
            dob_html += f'<div class="dob-banner">{esc(txt)}</div>'
        elif style == "banner_y":
            dob_html += f'<div class="dob-banner y">{esc(txt)}</div>'
        elif style == "item":
            dob_html += f'<div class="dob-item">{esc(txt)}</div>'
        elif style == "small":
            dob_html += f'<div class="acris-small">{esc(txt)}</div>'
        else:
            cls = {"good": "a-good", "warn": "a-warn"}.get(style, "")
            dob_html += (f'<div class="row"><span class="k">{esc(label)}</span>'
                         f'<span class="v {cls}">{esc(txt)}</span></div>')

    # DOB Summary（BIS Property Profile 概览式双列表）
    table, notes = dob_summary(d)
    summary_html = ""
    if table:
        rows = ""
        for metric, total, openv in table:
            hit = openv not in ("—", "0", "n/a")
            rows += (f'<tr><td>{esc(metric)}</td><td>{esc(total)}</td>'
                     f'<td class="{"open-hit" if hit else ""}">{esc(openv)}</td></tr>')
        notes_html = "".join(f'<div class="acris-small">{esc(n)}</div>' for n in notes)
        link_html = verify_html(c, "dob_summary", esc)
        summary_html = f"""
  <div class="section">
    <div class="sec-title">DOB Summary</div>
    <table class="sumtab">
      <tr><th>Metric</th><th>Total</th><th>Open</th></tr>
      {rows}
    </table>
    {notes_html}{link_html}
  </div>
"""

    acris_html = ""
    for label, txt, style, links in acris_rows(c.get("acris")):
        if style == "small":
            acris_html += f'<div class="acris-small">{esc(txt)}</div>'
            continue
        cls = {"good": "a-good", "warn": "a-warn", "hot": "a-hot"}.get(style, "")
        lk = "".join(f' <a class="doclink" href="{esc(u)}">{esc(n)} ↗</a>'
                     for n, u in links)
        acris_html += (f'<div class="row"><span class="k">{esc(label)}</span>'
                       f'<span class="v {cls}">{esc(txt)}{lk}</span></div>')

    if c.get("owner_dual"):
        od = c["owner_dual"]
        owner_html = (f'<div class="row"><span class="k">Owner (per ACRIS)</span>'
                      f'<span class="v">{esc(od["acris_names"])}'
                      f'<span class="owner-tag {od["style"]}">{esc(od["tag"])}</span></span></div>'
                      f'<div class="acris-small">{esc(od["note"])}</div>')
    else:
        owner_html = (f'<div class="row"><span class="k">Owner</span>'
                      f'<span class="v">{esc(c["ownername"])}'
                      f'<span class="owner-tag {c["owner_style"]}">{esc(c["owner_tag"])}</span></span></div>')

    v = {k: verify_html(c, k, esc) for k in
         ("identity", "zoning", "land", "potential", "sales",
          "construction", "dob_summary", "ownership")}

    plist = ""
    for label, mark, note in c["potential_lines"]:
        cls = "ok" if mark == "✓" else ("no" if mark == "✗" else "q")
        plist += (f'<div><span class="mk {cls}">{mark}</span>'
                  f'<b>{esc(label)}</b>&nbsp;&nbsp;{esc(note)}</div>')

    rows_land = f"""
      <div class="row"><span class="k">Lot area</span><span class="v">{fmt_num(c['lotarea'])} sqft ({fmt_num(c['lotfront'])} × {fmt_num(c['lotdepth'])} ft)</span></div>
      <div class="row"><span class="k">Lot type</span><span class="v">{esc(c['lottype_label'])} · {esc(c['irr_label'])}</span></div>
      <div class="row"><span class="k">Existing building</span><span class="v">built {esc(c['yearbuilt'])} · {esc(c['bldgclass_label'])}</span></div>
      <div class="row"><span class="k">Existing scale</span><span class="v">{fmt_num(c['unitsres'])} unit(s) · {fmt_num(c['bldgarea'])} sqft · {fmt_num(c['numfloors'],1)} floors</span></div>
    """

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(c['address'])} — Lot Profile</title><style>{CSS}</style></head>
<body><div class="card" id="card">

  <div class="header">
    <div class="addr">{esc(c['address'])}</div>
    <div class="sub">{esc(c['cd'])} · Queens, NY {esc(c['zipcode'])}</div>
    <div class="sub" style="margin-top:8px">
      <span class="badge">{esc(c['zone'])}</span>{head_badges}
      <span class="bbl">BBL {esc(c['bbl'])}</span>
    </div>
  </div>

  <div class="section">
    <div class="sec-title">Identity</div>
    <div class="row"><span class="k">BBL breakdown</span><span class="v">{esc(c['borough_en'])} ({esc(c['borough_code'])}) / Block {esc(c['block'])} / Lot {esc(c['lot'])}</span></div>
    <div class="row"><span class="k">School</span><span class="v">{esc(c['school_label'])}</span></div>
    <div class="row"><span class="k">Structures on site</span><span class="v">{c['numbldgs'] if c['numbldgs'] is not None else '—'} (PLUTO)</span></div>
    {subdiv}
    {v['identity']}
  </div>

  <div class="section">
    <div class="sec-title">Zoning Checks</div>
    <div class="checks">{checks_html}</div>
    {splitw}
    {v['zoning']}
  </div>

  <div class="section">
    <div class="sec-title">Land &amp; Structure</div>
    {prov_html}
    {rows_land}
    {v['land']}
  </div>

  <div class="section">
    <div class="sec-title">Development Potential</div>
    {prov_html}{nonres_html}{splitw}{farw}
    <div class="nums">
      <div class="num"><div class="big">{fmt_num(c['allowed_sf'])}</div>
        <div class="lab">allowed sqft<br>{fmt_num(c['lotarea'])} × FAR {far}</div></div>
      <div class="num"><div class="big">{fmt_num(c['bldgarea'])}</div>
        <div class="lab">built sqft<br>builtFAR {bfar}</div></div>
      {num3}
    </div>
    {overbuilt_html}
    <div class="plist">{plist}</div>
    {v['potential']}
  </div>

  <div class="section">
    <div class="sec-title">Sales History</div>
    {acris_html}
    {v['sales']}
  </div>

  <div class="section">
    <div class="sec-title">Construction Activity</div>
    {dob_html}
    {v['construction']}
  </div>
{summary_html}
  <div class="section">
    <div class="sec-title">Ownership</div>
    {owner_html}
    <div class="row"><span class="k">Assessed value</span>
      <span class="v">land ${fmt_num(c['assessland'])} · total ${fmt_num(c['assesstot'])}</span></div>
    {v['ownership']}
  </div>

  <div class="footer">{esc(source_line(c))}<br>
    Datasets: {" · ".join(f'<a href="{DATASET_URL.format(id=i)}">{n} ↗</a>' for n, i in DATASET_LINKS)}</div>

</div></body></html>
"""
    return html


# ---------- PNG / PDF ----------

def render_png_pdf(html_path: Path, png_path: Path, pdf_path: Path):
    """优先 playwright；装不上则 weasyprint 出 pdf、跳过 png 并明确告知"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ⚠ playwright not installed — falling back to weasyprint for PDF, skipping PNG")
        try:
            from weasyprint import HTML
            HTML(filename=str(html_path)).write_pdf(str(pdf_path))
            return False, True
        except ImportError:
            print("  ✗ weasyprint not installed either — skipping both PNG and PDF")
            return False, False

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 640, "height": 900},
                                device_scale_factor=2)
        page.goto(html_path.as_uri())
        page.wait_for_load_state("networkidle")
        card = page.locator("#card")
        card.screenshot(path=str(png_path))
        page.pdf(path=str(pdf_path), width="640px",
                 print_background=True,
                 margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        browser.close()
    return True, True


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser(description="Queens lot profile card generator")
    ap.add_argument("address", help='address, e.g. "17-08 149th St, Queens, NY"')
    ap.add_argument("--fresh", action="store_true", help="bypass cache and refetch")
    args = ap.parse_args()

    for d in (CACHE_DIR, CARDS_DIR, DESKTOP_DIR):
        d.mkdir(parents=True, exist_ok=True)

    print(f"▶ {args.address}")
    bbl, bin_count, geo_bins, geo = geosearch(args.address, args.fresh)
    print(f"  BBL = {bbl}")
    pluto = fetch_pluto(bbl, args.fresh)

    c = build_context(args.address, bbl, bin_count, pluto, fresh=args.fresh)
    c["acris"] = acris.get_history(bbl, args.fresh)
    c["dob"] = dob.get_activity(bbl, args.fresh, geo_bins=geo_bins)
    c["bis_url"] = dob.bis_url(c["dob"], address=c["address"], boro_num=c["borough_code"])

    # O2: 权属双源——ACRIS 最新 DEED 买方为主、PLUTO 名册为辅，不一致时并列
    ls = c["acris"].get("last_sale") if isinstance(c["acris"], dict) else None
    c["owner_dual"] = None
    if ls and ls.get("buyers") and not c["acris"].get("from_mother"):
        def _toks(s):
            return set(re.sub(r"[^A-Z0-9 ]", " ", s.upper()).split())
        pluto_t = _toks(c["ownername"]) if c["ownername"] != "—" else set()
        match = any(pluto_t and (_toks(b) <= pluto_t or pluto_t <= _toks(b))
                    for b in ls["buyers"])
        if not match:
            tag, style = owner_tag_for(ls["buyers"][0])
            c["owner_dual"] = {
                "acris_names": ", ".join(ls["buyers"]),
                "tag": tag, "style": style,
                "note": (f"ACRIS {ls['date']} DEED grantee (presumed current owner) · "
                         f"PLUTO {c['pluto_version']} roll: {c['ownername']} (lagging)"),
            }
    # 新分割子 lot 在 ACRIS 无独立文书，历史挂在母地名下 → 自动回退查母地
    appbbl = raw(pluto, "appbbl")
    if c["acris"].get("no_records") and appbbl:
        mother = str(int(float(appbbl)))
        if mother != bbl and len(mother) == 10:
            print(f"  no instruments for this lot — falling back to parent lot {mother}")
            mother_sig = acris.get_history(mother, args.fresh)
            if not mother_sig.get("no_records") and not mother_sig.get("error"):
                mother_sig["from_mother"] = mother
                c["acris"] = mother_sig

    # A8 前瞻信号：现业主本身是遗产/执行人 → 议价升 High
    owner_now = (c["owner_dual"]["acris_names"] if c.get("owner_dual")
                 else c["ownername"])
    acris.apply_owner_context(c["acris"], owner_now)

    # 终端摘要
    print(f"  zoning {c['zone']} · {c['school_label']} · "
          f"lot {fmt_num(c['lotarea'])} sqft ({fmt_num(c['lotfront'])}×{fmt_num(c['lotdepth'])} ft)")
    if c["subdiv_warn"]:
        print(f"  {c['subdiv_warn']}")
    if c["splitzone_warn"]:
        print(f"  {c['splitzone_warn']}")
    if c.get("far_conflict"):
        print(f"  {c['far_conflict']}")
    if c.get("nonres_warn"):
        print(f"  {c['nonres_warn']}")
    nb = c["numbldgs"] if c["numbldgs"] is not None else "—"
    print(f"  structures on site: {nb} (PLUTO)")
    for label, val, style, note in c["checks"]:
        mark = {"green": "🟢", "yellow": "🟡", "red": "🔴"}[style]
        print(f"  {mark} {label}: {note}")
    print(f"  potential: allowed {fmt_num(c['allowed_sf'])} / built {fmt_num(c['bldgarea'])} / "
          f"★unused {fmt_num(c['unused_sf'])} sqft")
    if c.get("overbuilt"):
        print(f"  ⚠ {c['overbuilt_msg']}")
    for label, mark, note in c["potential_lines"]:
        print(f"  {label} {mark} {note}")
    print(f"  {provenance(c)[0]}")
    print("  Sales history:")
    for label, txt, style, links in acris_rows(c.get("acris")):
        prefix = f"{label}: " if label else "· "
        print(f"    {prefix}{txt}")
    print("  Construction activity:")
    for label, txt, style in dob_rows(c.get("dob")):
        prefix = f"{label}: " if label else ("· " if style != "item" else "  - ")
        print(f"    {prefix}{txt}")
    table, notes = dob_summary(c.get("dob"))
    if table:
        print("  DOB summary (total / open):")
        for metric, total, openv in table:
            print(f"    {metric:<24} {total:>8} {openv:>8}")
        for n in notes:
            print(f"    · {n}")
        if c.get("bis_url"):
            print(f"    Verify on DOB BIS: {c['bis_url']}")
    if c.get("owner_dual"):
        od = c["owner_dual"]
        print(f"  Ownership: {od['acris_names']} → {od['tag']}")
        print(f"    · {od['note']}")
    else:
        print(f"  Ownership: {c['ownername']} → {c['owner_tag']}")
    print(f"  {source_line(c)}")

    # 输出文件（O3：一地一套卡——清理同 BBL 的旧 slug 文件）
    slug = slugify(args.address)
    base = CARDS_DIR / f"{bbl}_{slug}"
    for old in list(CARDS_DIR.glob(f"{bbl}_*")):
        if old.stem != base.name:
            old.unlink()
            print(f"  removed stale card: {old.name}")
    for old in list(DESKTOP_DIR.glob(f"{bbl}_*.pdf")):
        if old.stem != base.name:
            old.unlink()
    md_path = base.with_suffix(".md")
    html_path = base.with_suffix(".html")
    png_path = base.with_suffix(".png")
    pdf_path = base.with_suffix(".pdf")

    md_path.write_text(render_md(c), encoding="utf-8")
    html_path.write_text(render_html(c), encoding="utf-8")
    png_ok, pdf_ok = render_png_pdf(html_path, png_path, pdf_path)

    outputs = [md_path, html_path]
    if png_ok:
        outputs.append(png_path)
    if pdf_ok:
        outputs.append(pdf_path)
        desk = DESKTOP_DIR / pdf_path.name
        shutil.copy2(pdf_path, desk)

    print("  output:")
    for f in outputs:
        print(f"    {f.relative_to(PROJECT_ROOT)}")
    if pdf_ok:
        print(f"    ~/Desktop/地块档案卡/{pdf_path.name}")
    print()


if __name__ == "__main__":
    main()
