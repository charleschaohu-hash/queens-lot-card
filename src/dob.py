# -*- coding: utf-8 -*-
"""
DOB 施工动态模块：BBL → 施工备案项目组 + 违规状况 + BIS 式汇总。
数据源（2026-07-25 实测参数格式，complaints 于 2026-07-28 补测）：
  - DOB NOW Job Application Filings  w9ak-ipjd
      borough='Queens'（首字母大写单词）, block='4650'/lot='25'（无前导零）
  - BIS 时代补查                      ipu4-2q9a（⚠ 实为 DOB Permit Issuance）
      borough='QUEENS'（全大写）, block='04650'/lot='00025'（5位补零）
  - DOB Violations                   3h2n-5cm9
      boro='4'（数字）, block='04650'/lot='00025'（5位补零）
  - ECB Violations                   6bgk-3dad
      boro='4'（数字）, block='04650'，⚠ lot='0025'（4位补零，与 DOB 不同！）
  - DOB Complaints Received          eabe-havv
      ⚠ 无 boro/block/lot 字段，只能按 bin in(...) 查——必须先解析 BIN 集合
  - DOB Job Application Filings      ic3t-wcy2（BIS 工单，2026-07-28 补测）
      borough='QUEENS'（全大写）, block='04650'/lot='00025'（5位补零）
      ⚠ BIS 与 DOB NOW 是不互数的双系统——同一项目的文书可横跨两边
      （实测 17-08：分地 SI + BPP 在 BIS，NB/DM 在 DOB NOW），核对必须分账
"""
import datetime
import json
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "cache"

DOBNOW_URL = "https://data.cityofnewyork.us/resource/w9ak-ipjd.json"
BIS_URL = "https://data.cityofnewyork.us/resource/ipu4-2q9a.json"
BISJOBS_URL = "https://data.cityofnewyork.us/resource/ic3t-wcy2.json"
DOBVIOL_URL = "https://data.cityofnewyork.us/resource/3h2n-5cm9.json"
ECBVIOL_URL = "https://data.cityofnewyork.us/resource/6bgk-3dad.json"
COMPLAINTS_URL = "https://data.cityofnewyork.us/resource/eabe-havv.json"

# BIS Property Profile Overview——卡片上的人工复核直达链接
BIS_PROFILE_BIN = ("https://a810-bisweb.nyc.gov/bisweb/"
                   "PropertyProfileOverviewServlet?bin={bin}")
# 无可用 BIN 时的回退式（街名需 URL 编码；Queens 带连字符门牌原样传）
BIS_PROFILE_ADDR = ("https://a810-bisweb.nyc.gov/bisweb/"
                    "PropertyProfileOverviewServlet?boro={boro}&houseno={houseno}"
                    "&street={street}")

BOROUGH_NAME = {"1": "Manhattan", "2": "Bronx", "3": "Brooklyn",
                "4": "Queens", "5": "Staten Island"}

# ---- 状态三档映射（按 2026-07-25 实测 + DOB NOW 状态清单；小写比较） ----
# 实测见到：Permit Entire / Approved / Plan Examiner Review / LOC Issued
STATUS_DONE = {"signed off", "loc issued", "completed", "co issued",
               "certificate of occupancy issued"}
STATUS_DEAD = {"withdrawn", "terminated", "denied", "abandoned",
               "cancelled", "job cancelled"}
# 其余一切（filed / plan examiner review / objections / approved /
# permit issued / permit entire / partial permit / on hold ...）→ 活跃

# 重型工种（触发"开发中"警示 + bldgarea 出处警告）
HEAVY_TYPES = {"new building", "full demolition"}


def classify_status(status: str) -> str:
    s = (status or "").strip().lower()
    if s in STATUS_DONE:
        return "done"
    if s in STATUS_DEAD:
        return "dead"
    return "active"


def is_real_bin(b) -> bool:
    """区级占位 BIN（1000000/4000000…）不是真建筑，查投诉会串到全区。"""
    s = str(b or "").strip()
    return len(s) == 7 and s.isdigit() and not s.endswith("000000")


MAX_PAGES = 20  # B1: $offset 翻页上限；触顶记 trunc 标签，绝不静默截断


def _cached_get(cache_file: Path, fresh: bool, url: str, params: dict, log=print,
                tag="", trunc: list = None):
    """B1: 自动翻页抓全；翻满 MAX_PAGES 仍满页 → tag 记入 trunc 列表。
    缓存命中且行数恰为整页倍数 → 可能是翻页上线前的旧单页缓存，同样记 trunc。"""
    limit = int(params.get("$limit", 1000))
    if not fresh and cache_file.exists():
        data = json.loads(cache_file.read_text())
        if trunc is not None and len(data) >= limit and len(data) % limit == 0:
            trunc.append(tag)
        log(f"  [cache] {tag}: {len(data)} rows")
        return data
    data, offset = [], 0
    while True:
        p = dict(params)
        p["$offset"] = offset
        resp = requests.get(url, params=p, timeout=30)
        resp.raise_for_status()
        batch = resp.json()
        data.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
        if offset >= limit * MAX_PAGES:
            if trunc is not None:
                trunc.append(tag)
            break
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    log(f"  [api] {tag}: {len(data)} rows")
    return data


def _group_dobnow(rows: list) -> list:
    """DOB NOW 备案 → 项目组。
    job_filing_number 形如 Q01262008-I1（主）/-P1（批后修改）/-S1（子备案）。
    '-' 前缀为项目主号；同一 filing 多行取 current_status_date 最新。"""
    # 1) filing 去重取最新
    by_filing = {}
    for r in rows:
        fn = r.get("job_filing_number") or ""
        prev = by_filing.get(fn)
        if not prev or (r.get("current_status_date") or "") > (prev.get("current_status_date") or ""):
            by_filing[fn] = r
    # 2) 按主号聚合
    groups = {}
    for fn, r in by_filing.items():
        jobno = fn.split("-")[0]
        groups.setdefault(jobno, []).append(r)
    out = []
    for jobno, filings in groups.items():
        filings.sort(key=lambda r: r.get("job_filing_number") or "")
        main = next((f for f in filings
                     if (f.get("job_filing_number") or "").endswith("-I1")), filings[0])
        # 项目组当前状态：组内 current_status_date 最新的那份 filing 的状态
        latest = max(filings, key=lambda r: r.get("current_status_date") or "")
        owner = (main.get("owner_s_business_name")
                 or f"{main.get('owner_first_name', '')} {main.get('owner_last_name', '')}".strip()
                 or None)
        applicant = f"{main.get('applicant_first_name', '')} {main.get('applicant_last_name', '')}".strip() or None
        out.append({
            "source": "DOB NOW", "job_no": jobno,
            "job_type": main.get("job_type") or "?",
            "status": latest.get("filing_status") or "?",
            "status_class": classify_status(latest.get("filing_status")),
            "filing_date": (main.get("filing_date") or "")[:10] or None,
            "description": (main.get("job_description") or "").strip()[:80] or None,
            "cost": float(main.get("initial_cost") or 0) or None,
            "floor_area": float(main.get("total_construction_floor_area") or 0) or None,
            "owner": owner, "applicant": applicant,
            "n_filings": len(filings),
        })
    out.sort(key=lambda g: g["filing_date"] or "", reverse=True)
    return out


def _group_bis(rows: list) -> list:
    """BIS(ipu4-2q9a 许可签发) → 按 job__ 聚合为历史项目组。
    该表无完结状态，保守规则：permit_status 含 IN PROCESS 视为活跃，
    REVOKED 视为死亡，其余按完结（历史许可）处理。"""
    groups = {}
    for r in rows:
        groups.setdefault(r.get("job__") or "?", []).append(r)
    out = []
    for jobno, perms in groups.items():
        latest = max(perms, key=lambda r: r.get("issuance_date") or "")
        ps = (latest.get("permit_status") or "").upper()
        cls = "active" if "IN PROCESS" in ps else ("dead" if "REVOKED" in ps else "done")
        owner = (latest.get("owner_s_business_name")
                 or f"{latest.get('owner_s_first_name', '')} {latest.get('owner_s_last_name', '')}".strip()
                 or None)
        out.append({
            "source": "BIS", "job_no": jobno,
            "job_type": latest.get("job_type") or "?",
            "status": latest.get("permit_status") or "?",
            "status_class": cls,
            "filing_date": (latest.get("filing_date") or "")[:10] or None,
            "description": (latest.get("work_type") or None),
            "cost": None, "floor_area": None,
            "owner": owner, "applicant": None,
            "n_filings": len(perms),
        })
    return out


# BIS 工单 job_type 代码 → 可读名（NB/DM 命中 HEAVY_TYPES 触发"开发中"）
_BIS_JOBTYPE = {"NB": "New Building", "DM": "Full Demolition",
                "A1": "Alteration Type 1", "A2": "Alteration Type 2",
                "A3": "Alteration Type 3", "SI": "Subdivision (Improved)",
                "SC": "Subdivision (Condo)", "PA": "Place of Assembly",
                "SG": "Sign"}


def _mdY_to_iso(s):
    """BIS 日期 MM/DD/YYYY → YYYY-MM-DD（与 DOB NOW 的 ISO 对齐）"""
    s = (s or "")[:10]
    if len(s) == 10 and s[2] == "/" and s[5] == "/":
        return f"{s[6:]}-{s[:2]}-{s[3:5]}"
    return s or None


def _group_bisjobs(rows: list) -> list:
    """BIS 工单（ic3t-wcy2）→ 按 job__ 聚合（一个 job 多个 doc__ 行）。
    状态用 job_status_descrp 过 classify_status（SIGNED OFF/COMPLETED →
    done；PERMIT ISSUED 等 → active，宁严勿漏）。"""
    groups = {}
    for r in rows:
        groups.setdefault(r.get("job__") or "?", []).append(r)
    out = []
    for jobno, docs in groups.items():
        main = min(docs, key=lambda r: r.get("doc__") or "99")
        latest = max(docs, key=lambda r: _mdY_to_iso(r.get("latest_action_date")) or "")
        status = latest.get("job_status_descrp") or latest.get("job_status") or "?"
        cost = (main.get("initial_cost") or "").replace("$", "").replace(",", "")
        owner = f"{main.get('owner_s_first_name', '')} {main.get('owner_s_last_name', '')}".strip() or None
        out.append({
            "source": "BIS", "job_no": jobno,
            "job_type": _BIS_JOBTYPE.get(main.get("job_type"),
                                         f"BIS {main.get('job_type') or '?'}"),
            "status": status,
            "status_class": classify_status(status),
            "filing_date": _mdY_to_iso(main.get("pre__filing_date")),
            "description": (main.get("job_description") or "").strip()[:80] or None,
            "cost": float(cost) if cost.replace(".", "").isdigit() and float(cost) else None,
            "floor_area": float(main.get("total_construction_floor_area") or 0) or None,
            "owner": owner, "applicant": None,
            "n_filings": len(docs),
        })
    out.sort(key=lambda g: g["filing_date"] or "", reverse=True)
    return out


def _collect_bins(geo_bins, *rowsets) -> list:
    """BIN 解析：GeoSearch 优先（其首选项即主 BIN），DOB 各表补漏。
    ⚠ GeoSearch 对空地/新分割 lot 只给区级占位 BIN（4000000），
    真 BIN 得从 DOB 表里捞（实测 4049700011 → 4112220）。
    返回去重后的有序列表，主 BIN 在前。"""
    out = []
    for b in (geo_bins or []):
        if is_real_bin(b) and str(b) not in out:
            out.append(str(b))
    for rows, keys in rowsets:
        for r in rows:
            for k in keys:
                b = r.get(k)
                if is_real_bin(b) and str(b) not in out:
                    out.append(str(b))
    return out


def get_activity(bbl: str, fresh: bool = False, log=print, geo_bins=None) -> dict:
    """主入口：备案项目组 + 三态 + 违规 + 投诉汇总。出错返回 {'error': ...}"""
    try:
        return _get_activity(bbl, fresh, log, geo_bins or [])
    except requests.RequestException as e:
        log(f"  ⚠ DOB query failed: {e}")
        return {"error": str(e)}


def _get_activity(bbl: str, fresh: bool, log, geo_bins: list) -> dict:
    boro_num = str(int(bbl[0]))
    block_nopad, lot_nopad = str(int(bbl[1:6])), str(int(bbl[6:]))
    block_pad5, lot_pad5 = bbl[1:6], bbl[6:].zfill(5)
    lot_pad4 = str(int(bbl[6:])).zfill(4)
    boro_word = BOROUGH_NAME[boro_num]
    cdir = CACHE_DIR / bbl
    trunc = []  # B1: 触顶数据集标签

    # 1) DOB NOW
    jobs = _cached_get(
        cdir / "dob_jobs.json", fresh, DOBNOW_URL,
        {"$where": f"borough='{boro_word}' AND block='{block_nopad}' AND lot='{lot_nopad}'",
         "$limit": 500}, log, "DOB NOW jobs", trunc)
    dobnow_groups = _group_dobnow(jobs)
    groups = list(dobnow_groups)

    # 2a) BIS 工单（ic3t-wcy2，真正的 job filings）——Jobs — BIS 行的口径源
    bisjobs = _cached_get(
        cdir / "dob_bis_jobs.json", fresh, BISJOBS_URL,
        {"$where": f"borough='{boro_word.upper()}' AND block='{block_pad5}' AND lot='{lot_pad5}'",
         "$limit": 500}, log, "BIS jobs", trunc)
    bisjob_groups = _group_bisjobs(bisjobs) if bisjobs else []
    groups += bisjob_groups
    bisjob_nos = {g["job_no"] for g in bisjob_groups}

    # 2b) BIS 许可签发补查（⚠ 实为 DOB Permit Issuance）——只补 ic3t 里
    # 没有的 job（同一 job 两表都有时以工单表为准，防双计）
    bis = _cached_get(
        cdir / "dob_bis.json", fresh, BIS_URL,
        {"$where": f"borough='{boro_word.upper()}' AND block='{block_pad5}' AND lot='{lot_pad5}'",
         "$limit": 500}, log, "BIS permits", trunc)
    bis_groups = [g for g in (_group_bis(bis) if bis else [])
                  if g["job_no"] not in bisjob_nos]
    groups += bis_groups

    # DOB Summary 双行口径（BIS 与 DOB NOW 不互数，分账）：
    #   Filings — DOB NOW = 逐份 filing 数（括注项目组数）
    #   Jobs — BIS       = ic3t-wcy2 去重 job 数（对应 BIS 页面的 jobs 计数）
    dobnow_filing_count = sum(g["n_filings"] for g in dobnow_groups)
    bis_job_count = len(bisjob_nos | {g["job_no"] for g in bis_groups})

    # 3) 违规
    dviol = _cached_get(
        cdir / "dob_violations.json", fresh, DOBVIOL_URL,
        {"$where": f"boro='{boro_num}' AND block='{block_pad5}' AND lot='{lot_pad5}'",
         "$limit": 500}, log, "DOB violations", trunc)
    open_dob = [v for v in dviol
                if "ACTIVE" in (v.get("violation_category") or "").upper()]

    eviol = _cached_get(
        cdir / "ecb_violations.json", fresh, ECBVIOL_URL,
        {"$where": f"boro='{boro_num}' AND block='{block_pad5}' AND lot='{lot_pad4}'",
         "$limit": 500}, log, "ECB violations", trunc)
    open_ecb = [v for v in eviol
                if (v.get("ecb_violation_status") or "").upper() == "ACTIVE"]
    ecb_balance = sum(float(v.get("balance_due") or 0) for v in open_ecb)

    # 4) BIN 解析 → 投诉（⚠ 投诉表只认 BIN，没有 boro/block/lot）
    bins = _collect_bins(geo_bins,
                         (jobs, ("bin",)), (bis, ("bin__",)),
                         (dviol, ("bin",)), (eviol, ("bin",)))
    if bins:
        idlist = ",".join(f"'{b}'" for b in bins)
        comps = _cached_get(
            cdir / "dob_complaints.json", fresh, COMPLAINTS_URL,
            {"$where": f"bin in({idlist})", "$limit": 2000}, log, "DOB complaints", trunc)
    else:
        log("  ⚠ no real BIN resolved — complaints unavailable (BIN-only dataset)")
        comps = []
    open_comps = [x for x in comps
                  if (x.get("status") or "").upper() == "ACTIVE"]

    # B2: 数据时效——投诉表自带全库快照时间戳 dobrundate（YYYYMMDD...）；
    # 无投诉数据时回退用 dob_jobs 缓存文件的抓取时间
    dobrun = max((str(r.get("dobrundate") or "") for r in comps), default="")[:8]
    if len(dobrun) == 8 and dobrun.isdigit():
        data_date = f"{dobrun[:4]}-{dobrun[4:6]}-{dobrun[6:]}"
    else:
        jf = cdir / "dob_jobs.json"
        data_date = (datetime.date.fromtimestamp(jf.stat().st_mtime).isoformat()
                     if jf.exists() else None)

    # 三态判定
    active = [g for g in groups if g["status_class"] == "active"]
    active_heavy = [g for g in active if g["job_type"].lower() in HEAVY_TYPES]
    active_alt = [g for g in active if g["job_type"].lower() not in HEAVY_TYPES]
    mode = "a" if active_heavy else ("b" if active_alt else "c")

    return {
        "groups": groups, "mode": mode,
        "active_heavy": active_heavy, "active_alt": active_alt,
        "open_dob_violations": len(open_dob),
        "open_ecb_violations": len(open_ecb),
        "total_dob_violations": len(dviol),
        "total_ecb_violations": len(eviol),
        "ecb_balance_due": ecb_balance,
        "total_complaints": len(comps),
        "open_complaints": len(open_comps),
        "complaints_available": bool(bins),
        "total_filings": len(groups),                  # 全部项目组数（两系统）
        "dobnow_filing_count": dobnow_filing_count,    # DOB NOW 逐份 filing
        "dobnow_project_count": len(dobnow_groups),    # DOB NOW 项目组
        "bis_job_count": bis_job_count,                # BIS 去重 job 数
        "bins": bins,
        "primary_bin": bins[0] if bins else None,
        "extra_bins": bins[1:],
        "truncated": trunc,                  # B1: 触顶数据集，计数可能不完整
        "data_date": data_date,              # B2: DOB 数据时效
    }


def bis_url(sig: dict, address: str = None, boro_num: str = None) -> str:
    """卡片上的 BIS 直达链接：优先 BIN 式，无 BIN 时回退 boro/houseno/street。"""
    from urllib.parse import quote
    if sig and sig.get("primary_bin"):
        return BIS_PROFILE_BIN.format(bin=sig["primary_bin"])
    if address and boro_num:
        parts = address.strip().split(" ", 1)
        if len(parts) == 2:
            # Queens 连字符门牌（17-08）BIS 原样接受，不做拆分
            return BIS_PROFILE_ADDR.format(boro=boro_num, houseno=quote(parts[0]),
                                           street=quote(parts[1]))
    return None
