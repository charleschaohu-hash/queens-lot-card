# -*- coding: utf-8 -*-
"""
ACRIS 成交历史模块：BBL → 结构化交易史。
三步接力：Legals(8h5j-fqxa) → Master(bnx9-e6tj) + Parties(636b-3b5g)。
参数格式（2026-07-25 实测）：borough/block/lot 均为无前导零的字符串，
如 borough='4' AND block='4650' AND lot='25'。
"""
import datetime
import json
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "cache"

LEGALS_URL = "https://data.cityofnewyork.us/resource/8h5j-fqxa.json"
MASTER_URL = "https://data.cityofnewyork.us/resource/bnx9-e6tj.json"
PARTIES_URL = "https://data.cityofnewyork.us/resource/636b-3b5g.json"

BATCH = 50  # document_id in(...) 单次批量上限（保守值，防 URL 过长）

# ---- 卖家议价空间分档阈值（供以后调） ----
BARGAIN_HIGH_HOLD_YEARS = 20   # 持有 ≥ N 年且无负债 → 高
BARGAIN_LOW_HOLD_YEARS = 5     # 持有 < N 年 → 低（浮盈薄）
BARGAIN_DEBT_RATIO = 0.60      # 未解押抵押 ≥ 成交价 × N → 低（欠款重）


# ---------- 抓取 ----------

MAX_PAGES = 20  # B1: $offset 翻页上限（limit×20 行）；触顶极罕见，标记不静默


def _paged_fetch(url: str, params: dict):
    """B1: Socrata 自动翻页。返回 (rows, truncated)——翻满 MAX_PAGES 仍满页
    视为触顶，绝不静默截断。"""
    limit = int(params.get("$limit", 1000))
    out, offset = [], 0
    while True:
        p = dict(params)
        p["$offset"] = offset
        resp = requests.get(url, params=p, timeout=30)
        resp.raise_for_status()
        batch = resp.json()
        out.extend(batch)
        if len(batch) < limit:
            return out, False
        offset += limit
        if offset >= limit * MAX_PAGES:
            return out, True


def dataset_good_through(fresh: bool = False):
    """B2: ACRIS 全库 good_through_date（数据集级 max，深挖报告同口径）。
    ⚠ 不能用单 lot 各行的 max——沉睡地块最后一份文书旧 ≠ 数据旧。
    结果按天缓存（cache/acris_good_through.json）；查询失败返回 None。"""
    cache = CACHE_DIR / "acris_good_through.json"
    today = datetime.date.today().isoformat()
    if not fresh and cache.exists():
        try:
            d = json.loads(cache.read_text())
            if d.get("fetched") == today:
                return d.get("value")
        except json.JSONDecodeError:
            pass
    try:
        resp = requests.get(LEGALS_URL, params={
            "$select": "max(good_through_date)", "$limit": 1}, timeout=30)
        resp.raise_for_status()
        rows = resp.json()
        val = (rows[0].get("max_good_through_date") or "")[:10] or None if rows else None
    except (requests.RequestException, ValueError):
        return None
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"fetched": today, "value": val}))
    return val


def _cached_get(cache_file: Path, fresh: bool, url: str, params: dict):
    """返回 (rows, cache命中, truncated)。缓存命中时若行数恰为整页倍数，
    可能是翻页功能上线前的旧单页缓存 → 保守标 truncated，提示 --fresh。"""
    limit = int(params.get("$limit", 1000))
    if not fresh and cache_file.exists():
        data = json.loads(cache_file.read_text())
        suspect = len(data) >= limit and len(data) % limit == 0
        return data, True, suspect
    data, truncated = _paged_fetch(url, params)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return data, False, truncated


def _batch_fetch(url: str, ids: list, select: str = None):
    """document_id in(...) 分批查询，合并结果"""
    out = []
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        idlist = ",".join(f"'{d}'" for d in chunk)
        params = {"$where": f"document_id in({idlist})", "$limit": 5000}
        if select:
            params["$select"] = select
        rows, _ = _paged_fetch(url, params)
        out.extend(rows)
    return out


def fetch_acris(bbl: str, fresh: bool = False, log=print):
    """三步接力抓取；原始返回落盘 cache/{BBL}/acris_*.json"""
    borough = str(int(bbl[0]))
    block = str(int(bbl[1:6]))   # 无前导零（实测）
    lot = str(int(bbl[6:]))
    cdir = CACHE_DIR / bbl

    # 1) Legals：⚠ borough 必带（block/lot 五区重号）
    legals, hit, trunc = _cached_get(
        cdir / "acris_legals.json", fresh, LEGALS_URL,
        {"$where": f"borough='{borough}' AND block='{block}' AND lot='{lot}'",
         "$limit": 500})
    log(f"  [{'cache' if hit else 'api'}] ACRIS legals: {len(legals)} rows"
        + ("  ⚠ possibly truncated" if trunc else ""))

    # 2) 去重 + 分堆：现代 id vs legacy FT_/BK_（legacy 查 Master 会失败，只计数）
    doc_ids = sorted({r["document_id"] for r in legals if r.get("document_id")})
    legacy_ids = [d for d in doc_ids if d.startswith(("FT_", "BK_"))]
    modern_ids = [d for d in doc_ids if not d.startswith(("FT_", "BK_"))]

    # 3) Master + Parties 批量
    master_file = cdir / "acris_master.json"
    parties_file = cdir / "acris_parties.json"
    if not fresh and master_file.exists() and parties_file.exists():
        master = json.loads(master_file.read_text())
        parties = json.loads(parties_file.read_text())
        log(f"  [cache] ACRIS master/parties: {len(master)} / {len(parties)}")
    else:
        master = _batch_fetch(MASTER_URL, modern_ids) if modern_ids else []
        parties = _batch_fetch(PARTIES_URL, modern_ids) if modern_ids else []
        cdir.mkdir(parents=True, exist_ok=True)
        master_file.write_text(json.dumps(master, ensure_ascii=False, indent=2))
        parties_file.write_text(json.dumps(parties, ensure_ascii=False, indent=2))
        log(f"  [api] ACRIS master/parties: {len(master)} / {len(parties)}")

    return {"legals": legals, "master": master, "parties": parties,
            "legacy_ids": legacy_ids, "modern_ids": modern_ids,
            "truncated": trunc}


# ---------- 信号计算 ----------

def _pdate(s):
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


import re

# 实体后缀词表（token 级匹配防误伤：\bCO\b 不会命中 COHEN）
_ENTITY_RE = re.compile(
    r"\b(LLC|L\.L\.C\.?|CORP\.?|CORPORATION|INC\.?|INCORPORATED|TRUST|"
    r"LTD\.?|L\.T\.D\.?|CO\.?|LP|L\.P\.?|LLP|REALTY|HOLDINGS?|PROPERTIES|"
    r"COMPANY|PARTNERS(HIP)?|ASSOCIATES|GROUP|FUND|CAPITAL|BANK)\b")
_ESTATE_RE = re.compile(
    r"ESTATE OF|AS EXECUT(OR|RIX)|AS ADMINISTRAT(OR|RIX)|\bDECEASED\b")
# "姓, 名" 模式（兜底判个人）
_PERSON_RE = re.compile(r"^[A-Z' .-]+,\s*[A-Z' .-]+$")


# ---- A2: SAT-MTGE 债主匹配 ----
# 泛化词（机构名里不携带身份信息的 token）：比较时剔除，只比"招牌词"。
# MERS 系（含 NOMINEE）刻意归入泛化——裸 "MERS" 名义人身份对不上具体债主，
# 匹配不到招牌词 → 落存疑。方向：宁可多报存疑，不可漏报真实负债。
_GENERIC_LENDER_TOKENS = {
    "BANK", "NA", "N", "A", "THE", "OF", "FOR", "AS", "NATIONAL", "ASSOCIATION",
    "ASSN", "BANKING", "TRUST", "COMPANY", "CO", "CORP", "CORPORATION", "INC",
    "LLC", "LP", "FSB", "FA", "SB", "MORTGAGE", "MORT", "MTGE", "HOME", "LOANS",
    "LOAN", "FINANCIAL", "FINANCE", "CREDIT", "UNION", "SAVINGS", "FEDERAL",
    "SERVICES", "SERVICING", "GROUP", "FUND", "FUNDING", "CAPITAL", "HOLDINGS",
    "MERS", "NOMINEE", "ELECTRONIC", "REGISTRATION", "SYSTEMS", "SYSTEM",
    "DIV", "DIVISION", "USA", "US", "AMERICA", "NEW", "YORK", "NY",
}


def _brand_toks(name: str) -> set:
    """机构名 → 招牌词集合（剔泛化词）。空集 = 无从识别（如裸 MERS）。"""
    toks = set(re.sub(r"[^A-Z0-9 ]", " ", (name or "").upper()).split())
    return toks - _GENERIC_LENDER_TOKENS


def _lender_match(mtge_lender_names: list, sat_party_names: list) -> bool:
    """MTGE 贷方（party_type '2'）与 SAT 当事人名单是否同一债主。
    判据：双方招牌词有交集。任一侧无招牌词 → 不匹配（保守）。"""
    for a in mtge_lender_names:
        ta = _brand_toks(a)
        if not ta:
            continue
        for b in sat_party_names:
            if ta & _brand_toks(b):
                return True
    return False


# 当事人类型常量（卡片输出为英文；lot_card 权属板块复用同一套）
T_ESTATE = "Estate/Executor"
T_REFEREE = "Referee (foreclosure)"
T_ENTITY = "Entity"
T_INDIVIDUAL = "Individual"
T_UNKNOWN = "Unclassified"


def classify_party(name: str) -> str:
    """当事人名称 → 类型。也被 lot_card 权属板块复用。"""
    n = (name or "").upper().strip()
    if not n:
        return "—"
    if _ESTATE_RE.search(n):
        return T_ESTATE
    if "REFEREE" in n:
        return T_REFEREE
    if _ENTITY_RE.search(n):
        return T_ENTITY
    if _PERSON_RE.match(n):
        return T_INDIVIDUAL
    # 单 token 或无逗号的自然人写法也常见（如 "MERS"、"JOHN SMITH"）：
    # 不强行归类，照录
    return f"{T_UNKNOWN} ({name})"


def _pick_type(types: list) -> str:
    """一组当事人 → 一个主标签，按信号强度取"""
    for t in (T_ESTATE, T_REFEREE, T_ENTITY, T_INDIVIDUAL):
        if t in types:
            return t
    for t in types:  # 全是未识别 → 取第一个照录
        if t.startswith(T_UNKNOWN):
            return t
    return "—"


def analyze(raw: dict) -> dict:
    """从原始三表算出卡片信号 dict"""
    master, parties = raw["master"], raw["parties"]
    today = datetime.date.today()
    sig = {"no_records": not master and not raw["legacy_ids"]}

    # 按文书归并（doc 附 date/amt/type）
    docs = []
    for m in master:
        docs.append({
            "id": m.get("document_id"),
            "type": (m.get("doc_type") or "").upper(),
            "date": _pdate(m.get("document_date")) or _pdate(m.get("recorded_datetime")),
            "amt": float(m.get("document_amt") or 0),
        })
    docs = [d for d in docs if d["date"]]
    party_by_doc = {}
    for p in parties:
        party_by_doc.setdefault(p.get("document_id"), []).append(p)

    # a. 最近真实成交（DEED ≥ $10,000）；小额 DEED 归"非市场转让"
    deeds = [d for d in docs if d["type"] == "DEED"]
    real_sales = sorted([d for d in deeds if d["amt"] >= 10000], key=lambda d: d["date"])
    sig["nominal_deeds"] = len(deeds) - len(real_sales)
    cutoff = None
    if real_sales:
        last = real_sales[-1]
        cutoff = last["date"]
        held = (today - last["date"]).days / 365.25
        # 按 name+party_type 去重（原始 parties 表有重复行）
        sellers = list(dict.fromkeys(
            p["name"] for p in party_by_doc.get(last["id"], [])
            if p.get("party_type") == "1" and p.get("name")))
        buyers = list(dict.fromkeys(
            p["name"] for p in party_by_doc.get(last["id"], [])
            if p.get("party_type") == "2" and p.get("name")))
        sig["last_sale"] = {
            "date": last["date"].isoformat(), "price": last["amt"],
            "years_held": round(held, 1),
            "sellers": sellers, "buyers": buyers,
            "seller_type": _pick_type([classify_party(n) for n in sellers]),
            "buyer_type": _pick_type([classify_party(n) for n in buyers]),
            "doc_id": last["id"],  # 卡片直达 ACRIS DocumentDetail 用
        }
    else:
        sig["last_sale"] = None

    # c. 未解押抵押：以最近真实成交日为截断线——之前的 MTGE 推定已随
    #    成交清偿（title 要求），降为"历史抵押"备注，不计入当前负债。
    #    nominal deed（<$10,000）不作为截断线。
    #    A2 配对制（债主匹配）：一份 SAT 只有当其当事人名单与某笔截断线后
    #    MTGE 的贷方（party_type '2'）招牌词吻合时才允许清账。防的是迟登记
    #    SAT（解的是截断线前旧押，如实测 19-10 的 2019 SAT 解 2004 ABN AMRO）
    #    被贪心配给新押。配不上的：其后完全无 SAT → 确定未解押（open）；
    #    有 SAT 但债主对不上 → 存疑（uncertain）。宁可多报存疑，不可漏报。
    all_mtges = sorted([d for d in docs if d["type"] == "MTGE"], key=lambda d: d["date"])
    if cutoff:
        mtges = [m for m in all_mtges if m["date"] >= cutoff]
        hist_mtges = [m for m in all_mtges if m["date"] < cutoff]
        sig["historical_mortgages"] = [
            {"date": m["date"].isoformat(), "amt": m["amt"]} for m in hist_mtges]
    else:
        mtges = all_mtges
        hist_mtges = []
        sig["historical_mortgages"] = []
    sats = sorted([d for d in docs if d["type"].startswith("SAT")], key=lambda d: d["date"])

    def _lenders(doc):     # MTGE 贷方名单
        return [p["name"] for p in party_by_doc.get(doc["id"], [])
                if p.get("party_type") == "2" and p.get("name")]

    def _sat_parties(doc):  # SAT 当事人全名单（party_type 语义随 doc_type 漂移，全收）
        return [p["name"] for p in party_by_doc.get(doc["id"], []) if p.get("name")]

    hist_lender_sets = [_lenders(m) for m in hist_mtges]
    avail_sats, unresolved, ambiguous = list(sats), [], False
    for i, mt in enumerate(mtges):  # 由旧到新逐一配对
        lenders = _lenders(mt)
        cands = [s for s in avail_sats if s["date"] >= mt["date"]]
        matched = [s for s in cands
                   if lenders and _lender_match(lenders, _sat_parties(s))]
        if matched:
            chosen = matched[0]
            # 同债主的其他候选押（含截断线前的历史押）也能配上这份 SAT
            # → 到底解谁的无法唯一确定，保守标"存疑"
            if any(m2["date"] <= chosen["date"] and
                   _lender_match(_lenders(m2), _sat_parties(chosen))
                   for m2 in mtges[i + 1:]) or \
               any(_lender_match(hl, _sat_parties(chosen))
                   for hl in hist_lender_sets):
                ambiguous = True
            avail_sats.remove(chosen)
        elif cands:
            # 其后有 SAT 但债主对不上（或贷方缺名）→ 存疑
            unresolved.append((mt, False))
            ambiguous = True
        else:
            # 其后连一份 SAT 都没有 → 确定未解押
            unresolved.append((mt, True))
    open_mtges = [mt for mt, hard in unresolved]
    all_hard = unresolved and all(hard for _, hard in unresolved)
    if not mtges:
        sig["open_mortgage"] = {"status": "clear", "detail": []}
    elif open_mtges:
        sig["open_mortgage"] = {
            "status": "open" if (all_hard and not ambiguous) else "uncertain",
            "detail": [{"date": m["date"].isoformat(), "amt": m["amt"],
                        "doc_id": m["id"]} for m in open_mtges]}
    elif ambiguous:
        sig["open_mortgage"] = {
            "status": "uncertain",
            "detail": [{"date": m["date"].isoformat(), "amt": m["amt"],
                        "doc_id": m["id"]} for m in mtges]}
    else:
        sig["open_mortgage"] = {"status": "clear", "detail": []}

    # d. 风险信号：LIS PENDENS 且其后无真实成交（A7：名义转让 <$10,000
    #    不了结讼争，不作为 LP 解除依据）
    lps = [d for d in docs
           if "LIS PENDENS" in d["type"] or d["type"] == "LP" or d["type"].startswith("LP ")]
    sig["lis_pendens"] = None
    if lps:
        last_lp = max(lps, key=lambda d: d["date"])
        sales_after = [d for d in real_sales if d["date"] > last_lp["date"]]
        if not sales_after:
            sig["lis_pendens"] = last_lp["date"].isoformat()

    # e. 交易脉搏：近 10 年文书总数（含 $0）
    cutoff = today - datetime.timedelta(days=3652)
    sig["pulse_10y"] = len([d for d in docs if d["date"] >= cutoff])
    sig["sleepy"] = sig["pulse_10y"] <= 1

    # f. legacy 深历史
    sig["legacy_count"] = len(raw["legacy_ids"])
    sig["has_deep_history"] = sig["legacy_count"] > 0

    # B2: 数据时效——全库 good_through（数据集级）；失败回退本 lot 各行 max
    # 并明确标注口径差（per-lot max 只说明该 lot 最后一份文书的保证期）
    gt = dataset_good_through()
    if not gt:
        gts = [(r.get("good_through_date") or "")[:10] for r in raw["legals"]]
        gt = max((g for g in gts if g), default=None)
        if gt:
            gt += " (per-lot, dataset-level query failed)"
    sig["good_through"] = gt
    sig["truncated"] = bool(raw.get("truncated"))

    # g. 合成信号：卖家议价空间
    sig["bargain"] = _bargain(sig)
    return sig


def _fmt_money(v):
    return f"${v:,.0f}"


def _bargain(sig) -> dict:
    """卖家议价空间：估算底线 + 分档。
    底线 = max(最近真实成交价, 未解押抵押总额)。
    A8 信号时效规则：遗产/法拍作为上次成交的【卖方】出现 = 信号已随那次
    转手兑现（estate 已经卖完离场），不再驱动现业主的动机 → 不触发 High，
    只在结论后追加"信号已耗尽"备注。前瞻性的高动机只认两类：
      · 现业主本身是遗产/执行人（由 apply_owner_context 注入）
      · LP 在档且其后无真实成交（活讼争）
    分档：LP（High）> 长持无债（High）> 债重（Low）> 短持（Low）> Medium。"""
    ls = sig.get("last_sale")
    om = sig.get("open_mortgage") or {"status": "clear", "detail": []}
    debt = sum(m["amt"] for m in om["detail"]) if om["status"] in ("open", "uncertain") else 0
    price = ls["price"] if ls else None
    years = ls["years_held"] if ls else None

    # 卖方侧已耗尽的信号 → 备注（历史语境保留，档位不受其影响）
    spent = ""
    if ls and ls["seller_type"] in (T_ESTATE, T_REFEREE):
        kind = "estate" if ls["seller_type"] == T_ESTATE else "foreclosure"
        spent = (f" (acquired via {kind} sale {ls['date']} — "
                 f"seller-side signal spent at that transfer)")

    floors = [v for v in (price, debt or None) if v]
    if not floors:
        return {"level": "Not estimable",
                "reason": "insufficient data (no sale price and no mortgage record)"
                          + spent,
                "floor": None}
    floor = max(floors)

    # 活讼争：LIS PENDENS 且其后无真实成交 → High
    if sig.get("lis_pendens"):
        return {"level": "High",
                "reason": f"LIS PENDENS on file ({sig['lis_pendens']}) — "
                          f"motivation outweighs price" + spent,
                "floor": floor}
    # 长持无债 → High
    if years is not None and years >= BARGAIN_HIGH_HOLD_YEARS and debt == 0:
        return {"level": "High",
                "reason": f"no open mortgage and held {years} years — basis long since "
                          f"recovered, any sale is a gain" + spent,
                "floor": floor}
    # 债重 → Low
    if price and debt >= price * BARGAIN_DEBT_RATIO:
        return {"level": "Low",
                "reason": f"held {years} years but {_fmt_money(debt)} still unsatisfied — "
                          f"floor roughly ≥ {_fmt_money(floor)}" + spent,
                "floor": floor}
    # 短持 → Low
    if years is not None and years < BARGAIN_LOW_HOLD_YEARS:
        return {"level": "Low",
                "reason": f"held only {years} years, thin paper gain — floor ≈ purchase "
                          f"price {_fmt_money(price)} + costs" + spent,
                "floor": floor}
    return {"level": "Medium",
            "reason": f"no strong motivation signal — floor roughly ≥ {_fmt_money(floor)}"
                      + spent,
            "floor": floor}


def apply_owner_context(sig, owner_name: str):
    """A8 前瞻信号：现业主（PLUTO 名册或 ACRIS 最新买方）本身是遗产/执行人
    → 执行人主导出售在前方，升 High。由 lot_card 在确定权属后调用。"""
    if not isinstance(sig, dict) or sig.get("error") or not sig.get("bargain"):
        return
    if not owner_name or owner_name == "—":
        return
    if classify_party(owner_name) == T_ESTATE and sig["bargain"]["level"] != "High":
        sig["bargain"] = {
            "level": "High",
            "reason": f"current title held by estate/executor ({owner_name}) — "
                      f"executor-driven sale ahead, motivation outweighs price",
            "floor": sig["bargain"].get("floor"),
        }


def get_history(bbl: str, fresh: bool = False, log=print) -> dict:
    """对外主入口：抓取 + 计算，返回信号 dict；出错返回 {'error': ...}"""
    try:
        raw = fetch_acris(bbl, fresh, log)
        return analyze(raw)
    except requests.RequestException as e:
        log(f"  ⚠ ACRIS query failed: {e}")
        return {"error": str(e)}
