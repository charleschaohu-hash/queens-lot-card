# -*- coding: utf-8 -*-
"""
分区规则表（Queens 低密度住宅区）—— 已对照现行 NYC Zoning Resolution 核实
核实日期：2026-07-25，来源：zr.planning.nyc.gov 现行文本（含 City of Yes for
Housing Opportunity 2024-12-05 修订，下称 CoY）。

⚠ 重要背景：CoY 把 Article II Chapter 3 整体重排了——旧条款号（如 23-32 最小
lot、23-142 FAR）已不存在。现行条款号：
  - 最小 lot 面积/面宽：ZR 23-11（R1-R5）
  - 住宅 FAR：        ZR 23-21（R1-R5）
  - 允许户型：        ZR 22-121 / 22-122（Use Group II）
  - ADU 定义与限制：   ZR 12-10 "ancillary dwelling unit"
  - ADU 后院体量：     ZR 23-341（rear yard permitted obstructions）
  - 停车：            ZR 25-21（Inner Transit Zone）/ 25-22（Outer）/
                      25-23（beyond Greater Transit Zone）/ 25-241（特定 CD）

字段说明：
  min_lot_width_ft / min_lot_area_sqft : 单户/两户 detached（或 zero lot line）
      的每 lot 最小面宽/面积（ZR 23-11 表第一类）。
  min_lot_width_other / min_lot_area_other : "Other residences, where
      permitted"（semi-detached / attached / 多户）的最小值，R1-R5 统一
      1,700 sqft / 18 ft（ZR 23-11 表第二类）；该分区不允许其他形态时为 None。
  units_per_lot : 每 lot 最大户数；None = 允许 multiple dwelling，户数无固定
      上限（受 FAR/bulk 约束）（ZR 22-121/22-122）。
  forms : 允许的建筑形态（ZR 22-122）。
  far / far_qrs : 标准 lot FAR / qualifying residential site FAR（ZR 23-21）。
  far_note : FAR 附注。
  parking_beyond_gtz / parking_outer_tz : 每户所需停车位（比例），
      beyond Greater Transit Zone / Outer Transit Zone（ZR 25-232 / 25-222）。
      Inner Transit Zone 一律 0（ZR 25-211）。
  parking_waiver : 停车豁免说明。
  verified : True = 已对照上述现行 ZR 文本逐条核实。
"""

# ZR 23-11 表第二类："Other residences, where permitted"，R1-R5 统一值
_OTHER_AREA, _OTHER_WIDTH = 1700, 18

# ZR 23-21 脚注1（适用于 FAR 0.75 一档）：
_FAR075_NOTE = ("lot ≥4,000 sqft 时，单个 dwelling unit 的楼面积不得超过"
                "等效 FAR 0.60（ZR 23-21 脚注1，反豪宅条款）")

# ZR 25-222 脚注3 / 25-232 脚注5 原文："For zoning lots existing on
# December 5, 2024 where the lot width is 25 feet or less, no parking shall
# be required."
# ⚠ 关键限定：豁免只给 2024-12-05 当天已存在的 zoning lot。全 Chapter 5 无
# 任何把豁免延伸到分地后子 lot 的解释条款（ZR 想覆盖分地情形时会明写
# "zoning lots subdivided after {date}"，如 curb cut 条款）→ 按平义解释，
# CoY 之后新切出的 25 ft lot 不享受豁免，新建仍按本区比例配停车。
# DOB 实际审查口径待实操验证（见 skills 问题清单）。
_NARROW_WAIVER = ("仅限 2024-12-05 已存在且面宽 ≤25 ft 的 lot 免停车"
                  "（ZR 25-222 脚注3 / 25-232 脚注5）；之后新切出的窄 lot 不适用")

RULES = {
    # ---- R1/R2 全系（22-122(b)(1)：R1、R2 一律限单户 detached）----
    "R1-1": {
        "min_lot_width_ft": 75,      # ZR 23-11
        "min_lot_area_sqft": 7125,   # ZR 23-11
        "min_lot_width_other": None, "min_lot_area_other": None,
        "units_per_lot": 1,          # ZR 22-122(b)(1)
        "forms": "detached",         # ZR 22-122
        "far": 0.75,                 # ZR 23-21
        "far_qrs": None,             # QRS 主通道排除 R1/R2（ZR 12-10 定义）
        "far_note": _FAR075_NOTE,
        "parking_beyond_gtz": 1.00,  # ZR 25-232
        "parking_outer_tz": 1.00,    # ZR 25-222
        "parking_waiver": None,
        "verified": True,
    },
    "R1-2": {
        "min_lot_width_ft": 50,      # ZR 23-11
        "min_lot_area_sqft": 4750,   # ZR 23-11
        "min_lot_width_other": None, "min_lot_area_other": None,
        "units_per_lot": 1,          # ZR 22-122(b)(1)
        "forms": "detached",         # ZR 22-122
        "far": 0.75,                 # ZR 23-21
        "far_qrs": None,
        "far_note": _FAR075_NOTE,
        "parking_beyond_gtz": 1.00,  # ZR 25-232
        "parking_outer_tz": 1.00,    # ZR 25-222
        "parking_waiver": None,
        "verified": True,
    },
    "R1-2A": {
        "min_lot_width_ft": 50,      # ZR 23-11（与 R1-2 同行）
        "min_lot_area_sqft": 4750,   # ZR 23-11
        "min_lot_width_other": None, "min_lot_area_other": None,
        "units_per_lot": 1,          # ZR 22-122(b)(1)
        "forms": "detached",         # ZR 22-122
        "far": 0.75,                 # ZR 23-21
        "far_qrs": None,
        "far_note": _FAR075_NOTE + "；R1-2A 后院 ADU 在 GTZ 外禁止（ZR 12-10）",
        "parking_beyond_gtz": 1.00,  # ZR 25-232
        "parking_outer_tz": 1.00,    # ZR 25-222
        "parking_waiver": None,
        "verified": True,
    },
    "R2": {
        "min_lot_width_ft": 30,      # ZR 23-11（R2 R2A R2X R3X R3-1 R3-2 R4 R5 同行）
        "min_lot_area_sqft": 2850,   # ZR 23-11
        "min_lot_width_other": None, "min_lot_area_other": None,
        "units_per_lot": 1,          # ZR 22-122(b)(1)
        "forms": "detached",         # ZR 22-122
        "far": 0.75,                 # ZR 23-21
        "far_qrs": None,
        "far_note": _FAR075_NOTE,
        "parking_beyond_gtz": 1.00,  # ZR 25-232
        "parking_outer_tz": 1.00,    # ZR 25-222
        "parking_waiver": None,
        "verified": True,
    },
    "R2X": {
        "min_lot_width_ft": 30,      # ZR 23-11
        "min_lot_area_sqft": 2850,   # ZR 23-11
        "min_lot_width_other": None, "min_lot_area_other": None,
        "units_per_lot": 1,          # ZR 22-122(b)(1)：R2 系限单户 detached
        "forms": "detached",         # ZR 22-122
        "far": 1.00,                 # ZR 23-21（R2X 单列一行：1.00/1.00）
        "far_qrs": None,             # QRS 主通道排除 R1/R2
        "far_note": None,
        "parking_beyond_gtz": 1.00,  # ZR 25-232（R1 R2 行）
        "parking_outer_tz": 1.00,    # ZR 25-222
        "parking_waiver": None,
        "verified": True,
    },
    "R2A": {
        "min_lot_width_ft": 30,      # ZR 23-11（CoY 2024-12 修订：原 40）
        "min_lot_area_sqft": 2850,   # ZR 23-11（CoY 2024-12 修订：原 3,800）
        "min_lot_width_other": None, "min_lot_area_other": None,  # 只许 detached
        "units_per_lot": 1,          # ZR 22-122(b)(1)：R1/R2 限单户 detached
        "forms": "detached",         # ZR 22-122
        "far": 0.75,                 # ZR 23-21（CoY 2024-12 修订：原 0.5）
        "far_qrs": None,             # QRS 主通道排除 R1/R2（ZR 12-10 定义）
        "far_note": _FAR075_NOTE + "；R2A 电梯/水箱凸出物不豁免楼面积（ZR 12-10）",
        "parking_beyond_gtz": 1.00,  # ZR 25-232
        "parking_outer_tz": 1.00,    # ZR 25-222
        "parking_waiver": None,
        "verified": True,
    },
    "R3A": {
        "min_lot_width_ft": 25,      # ZR 23-11
        "min_lot_area_sqft": 2375,   # ZR 23-11
        "min_lot_width_other": None, "min_lot_area_other": None,
        "units_per_lot": 2,          # ZR 22-122(b)(2)：单/两户 detached 或 zero lot line
        "forms": "detached / zero lot line",  # ZR 22-122
        "far": 0.75,                 # ZR 23-21（CoY 2024-12 修订：原 0.5+attic≈0.6）
        "far_qrs": 1.00,             # ZR 23-21（需为 qualifying residential site）
        "far_note": _FAR075_NOTE,
        "parking_beyond_gtz": 1.00,  # ZR 25-232
        "parking_outer_tz": 0.50,    # ZR 25-222
        "parking_waiver": _NARROW_WAIVER,
        "verified": True,
    },
    "R3X": {
        "min_lot_width_ft": 30,      # ZR 23-11（CoY 2024-12 修订：原 35）
        "min_lot_area_sqft": 2850,   # ZR 23-11（CoY 2024-12 修订：原 3,325）
        "min_lot_width_other": None, "min_lot_area_other": None,
        "units_per_lot": 2,          # ZR 22-122(b)(3)：单/两户 detached
        "forms": "detached",         # ZR 22-122
        "far": 0.75,                 # ZR 23-21（CoY 2024-12 修订）
        "far_qrs": 1.00,             # ZR 23-21
        "far_note": _FAR075_NOTE,
        "parking_beyond_gtz": 1.00,  # ZR 25-232
        "parking_outer_tz": 0.50,    # ZR 25-222
        "parking_waiver": _NARROW_WAIVER,
        "verified": True,
    },
    "R3-1": {
        "min_lot_width_ft": 30,      # ZR 23-11（detached）
        "min_lot_area_sqft": 2850,   # ZR 23-11（detached）
        "min_lot_width_other": _OTHER_WIDTH,   # ZR 23-11（semi-detached）
        "min_lot_area_other": _OTHER_AREA,     # ZR 23-11（semi-detached）
        "units_per_lot": 2,          # ZR 22-122(b)(2)：单/两户 detached 或 semi-detached
        "forms": "detached / semi-detached",   # ZR 22-122
        "far": 0.75,                 # ZR 23-21（CoY 2024-12 修订）
        "far_qrs": 1.00,             # ZR 23-21
        "far_note": _FAR075_NOTE,
        "parking_beyond_gtz": 1.00,  # ZR 25-232
        "parking_outer_tz": 0.50,    # ZR 25-222
        "parking_waiver": _NARROW_WAIVER,
        "verified": True,
    },
    "R3-2": {
        "min_lot_width_ft": 30,      # ZR 23-11（detached）
        "min_lot_area_sqft": 2850,   # ZR 23-11（detached）
        "min_lot_width_other": _OTHER_WIDTH,   # ZR 23-11
        "min_lot_area_other": _OTHER_AREA,     # ZR 23-11
        "units_per_lot": None,       # ZR 22-121/22-122：不在限制清单 → 允许 multiple dwelling
        "forms": "all forms, incl. multiple dwelling",  # ZR 22-122 未对 R3-2 设限
        "far": 0.75,                 # ZR 23-21（CoY 2024-12 修订）
        "far_qrs": 1.00,             # ZR 23-21
        "far_note": _FAR075_NOTE,
        "parking_beyond_gtz": 0.50,  # ZR 25-232
        "parking_outer_tz": 0.35,    # ZR 25-222
        "parking_waiver": "waiver：算出 ≤1 个位免（beyond GTZ）/ ≤5 个位免（Outer TZ）",
        "verified": True,
    },
    "R4": {
        "min_lot_width_ft": 30,      # ZR 23-11（detached）
        "min_lot_area_sqft": 2850,   # ZR 23-11（detached）
        "min_lot_width_other": _OTHER_WIDTH,   # ZR 23-11
        "min_lot_area_other": _OTHER_AREA,     # ZR 23-11
        "units_per_lot": None,       # ZR 22-121/22-122：允许 multiple dwelling
        "forms": "all forms, incl. multiple dwelling",
        "far": 1.00,                 # ZR 23-21（CoY 2024-12 修订：原 0.75+attic≈0.9）
        "far_qrs": 1.50,             # ZR 23-21
        "far_note": None,
        "parking_beyond_gtz": 0.50,  # ZR 25-232
        "parking_outer_tz": 0.35,    # ZR 25-222
        "parking_waiver": "waiver：算出 ≤3 个位免（beyond GTZ）/ ≤5 个位免（Outer TZ）",
        "verified": True,
    },
    "R4-1": {
        "min_lot_width_ft": 25,      # ZR 23-11（detached / zero lot line）
        "min_lot_area_sqft": 2375,   # ZR 23-11
        "min_lot_width_other": _OTHER_WIDTH,   # ZR 23-11（semi-detached）
        "min_lot_area_other": _OTHER_AREA,     # ZR 23-11（semi-detached）
        "units_per_lot": 2,          # ZR 22-122(b)(4)：单/两户 detached / semi / zero lot line
        "forms": "detached / semi-detached / zero lot line",  # ZR 22-122
        "far": 1.00,                 # ZR 23-21（CoY 2024-12 修订）
        "far_qrs": 1.50,             # ZR 23-21
        "far_note": None,
        "parking_beyond_gtz": 1.00,  # ZR 25-232
        "parking_outer_tz": 0.50,    # ZR 25-222
        "parking_waiver": _NARROW_WAIVER,
        "verified": True,
    },
    "R4A": {
        "min_lot_width_ft": 25,      # ZR 23-11
        "min_lot_area_sqft": 2375,   # ZR 23-11
        "min_lot_width_other": None, "min_lot_area_other": None,
        "units_per_lot": 2,          # ZR 22-122(b)(3)：单/两户 detached
        "forms": "detached",         # ZR 22-122
        "far": 1.00,                 # ZR 23-21（CoY 2024-12 修订）
        "far_qrs": 1.50,             # ZR 23-21
        "far_note": None,
        "parking_beyond_gtz": 1.00,  # ZR 25-232
        "parking_outer_tz": 0.50,    # ZR 25-222
        "parking_waiver": _NARROW_WAIVER,
        "verified": True,
    },
    "R4B": {
        "min_lot_width_ft": 25,      # ZR 23-11（detached / zero lot line）
        "min_lot_area_sqft": 2375,   # ZR 23-11
        "min_lot_width_other": _OTHER_WIDTH,   # ZR 23-11（semi / attached）
        "min_lot_area_other": _OTHER_AREA,     # ZR 23-11
        "units_per_lot": 2,          # ZR 22-122(b)(5)：单/两户，全形态
        "forms": "detached / semi-detached / attached / zero lot line",  # ZR 22-122
        "far": 1.00,                 # ZR 23-21（CoY 2024-12 修订：原 0.9）
        "far_qrs": 1.50,             # ZR 23-21
        "far_note": None,
        "parking_beyond_gtz": 1.00,  # ZR 25-232
        "parking_outer_tz": 0.50,    # ZR 25-222
        "parking_waiver": _NARROW_WAIVER + "；R4B 另可无条件免 1 个位",
        "verified": True,
    },
    "R5": {
        "min_lot_width_ft": 30,      # ZR 23-11（detached）
        "min_lot_area_sqft": 2850,   # ZR 23-11（detached）
        "min_lot_width_other": _OTHER_WIDTH,   # ZR 23-11
        "min_lot_area_other": _OTHER_AREA,     # ZR 23-11
        "units_per_lot": None,       # ZR 22-121/22-122：允许 multiple dwelling
        "forms": "all forms, incl. multiple dwelling",
        "far": 1.50,                 # ZR 23-21（CoY 2024-12 修订：原 1.25）
        "far_qrs": 2.00,             # ZR 23-21
        "far_note": None,
        "parking_beyond_gtz": 0.50,  # ZR 25-232
        "parking_outer_tz": 0.35,    # ZR 25-222
        "parking_waiver": "waiver：算出 ≤5 个位免（beyond GTZ）/ ≤10 个位免（Outer TZ）",
        "verified": True,
    },
    "R5A": {
        "min_lot_width_ft": 25,      # ZR 23-11
        "min_lot_area_sqft": 2375,   # ZR 23-11
        "min_lot_width_other": None, "min_lot_area_other": None,
        "units_per_lot": 2,          # ZR 22-122(b)(3)：单/两户 detached
        "forms": "detached",         # ZR 22-122
        "far": 1.50,                 # ZR 23-21（CoY 2024-12 修订：原 1.1）
        "far_qrs": 2.00,             # ZR 23-21
        "far_note": None,
        "parking_beyond_gtz": 1.00,  # ZR 25-232
        "parking_outer_tz": 0.50,    # ZR 25-222
        "parking_waiver": _NARROW_WAIVER,
        "verified": True,
    },
    "R5B": {
        "min_lot_width_ft": 25,      # ZR 23-11（detached）
        "min_lot_area_sqft": 2375,   # ZR 23-11
        "min_lot_width_other": _OTHER_WIDTH,   # ZR 23-11
        "min_lot_area_other": _OTHER_AREA,     # ZR 23-11
        "units_per_lot": None,       # ZR 22-121/22-122：允许 multiple dwelling
        "forms": "all forms, incl. multiple dwelling",
        "far": 1.50,                 # ZR 23-21（CoY 2024-12 修订：原 1.35）
        "far_qrs": 2.00,             # ZR 23-21
        "far_note": None,
        "parking_beyond_gtz": 0.50,  # ZR 25-232
        "parking_outer_tz": 0.25,    # ZR 25-222
        "parking_waiver": "waiver：算出 ≤5 个位免（beyond GTZ）/ ≤10 个位免（Outer TZ）",
        "verified": True,
    },
    "R5D": {
        "min_lot_width_ft": 25,      # ZR 23-11（detached）
        "min_lot_area_sqft": 2375,   # ZR 23-11
        "min_lot_width_other": _OTHER_WIDTH,   # ZR 23-11
        "min_lot_area_other": _OTHER_AREA,     # ZR 23-11
        "units_per_lot": None,       # ZR 22-121/22-122：允许 multiple dwelling
        "forms": "all forms, incl. multiple dwelling",
        "far": 2.00,                 # ZR 23-21（CoY 2024-12 修订）
        "far_qrs": 2.00,             # ZR 23-21
        "far_note": None,
        "parking_beyond_gtz": 0.50,  # ZR 25-232
        "parking_outer_tz": 0.25,    # ZR 25-222
        "parking_waiver": "waiver：算出 ≤5 个位免（beyond GTZ）/ ≤10 个位免（Outer TZ）",
        "verified": True,
    },
}

# ---------------- ADU（City of Yes 新增，ZR 12-10 "ancillary dwelling unit"） ----------------
ADU_RULES = {
    "max_floor_area_sqft": 800,          # ZR 12-10：ADU ≤800 sqft 楼面积
    "per_residence": 1,                  # ZR 12-10：每个单/两户住宅限 1 个 ADU
    "eligible_units": (1, 2),            # 仅单户/两户住宅的 zoning lot
    "owner_primary_residence": True,     # ZR 12-10：ADU 首次入住时该 lot 须为业主主要住所
    "counts_toward_far": True,           # ZR 23-21 及 Ch.3 未见 FAR 豁免条款 → 计入
                                         #（cellar 空间本身不算 floor area，是唯一"免费"路径）
    "counts_as_dwelling_unit": True,     # ZR 12-10：定义为 "additional dwelling unit"
    # 后院式（backyard ADU）禁区：
    "backyard_banned_districts_beyond_gtz": ("R1-2A", "R2A", "R3A"),  # ZR 12-10：
                                         # 这三区在 Greater Transit Zone 之外禁后院式
    "backyard_banned_in_historic_district": True,   # ZR 12-10
    # 洪水限制（ZR 12-10）：
    #  - 高风险洪水区（ZR 64-11）：flood-resistant construction elevation 以下不许 ADU
    #  - DEP 10年降雨洪水风险区(2050) / 沿海洪水风险区(2080 1%)：禁地下室/cellar ADU、禁后院 ADU
    "flood_high_risk_below_dfe_banned": True,
    "dep_flood_area_no_basement_cellar": True,
    "dep_flood_area_no_backyard": True,
    # 后院式体量（ZR 23-341）：
    "backyard_bulk": "1 层 ≤15 ft（下方带车位时 2 层 ≤25 ft）；占后院 ≤1/3；"
                     "距主楼 ≥10 ft（ZR 23-371）；侧向通道 ≥5 ft（ZR 12-10）",
    "parking_required": 0,               # ZR 25-222/25-232 Column B：ADU 停车 0
}

# QRS（qualifying residential site，ZR 12-10 定义，主通道）：
# R1-R5 内 lot ≥5,000 sqft + 位于 Greater Transit Zone + 临 wide street 或
# block 短边 + 非 R1/R2 → 任何住宅形态 + 更高 FAR（23-21 第二列）。


def get_rule(zonedist: str):
    """按分区名取规则；不存在返回 None。"""
    if not zonedist:
        return None
    return RULES.get(zonedist.strip().upper())
