# -*- coding: utf-8 -*-
"""A5 分地判定单元测试（split_feasibility）。

为什么用单元测试：13 个在册地址里没有"semi 可分而 detached 不可分"的
实盘用例（19-10 是 R3-1 但地块太小，两档都不过；17-16 是 R3A 只有
detached 档）。用合成地块覆盖关键分支。

运行：python3 tests/test_split.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from lot_card import split_feasibility          # noqa: E402
from rules import get_rule                      # noqa: E402

FAILURES = []


def check(desc, cond):
    print(("  ✓ " if cond else "  ✗ ") + desc)
    if not cond:
        FAILURES.append(desc)


# ---- 1. R3-1 40×100（4,000 sqft）：A5 的核心场景 ----
# detached 需 2×30 ft / 2×2,850 sqft = 60 ft / 5,700 sqft → ✗
# semi    需 2×18 ft / 2×1,700 sqft = 36 ft / 3,400 sqft → ✓
ok, note = split_feasibility(get_rule("R3-1"), 40, 4000)
print(f"R3-1 40×100: {note}")
check("整体判 ✓（semi 档通过）", ok is True)
check("detached 段显示 ✗", "detached ✗" in note)
check("semi 段显示 ✓", "semi-detached/other ✓" in note)
check("semi 门槛 36 ft / 3,400 sqft 上卡", "36 ft / 3,400 sqft" in note)

# ---- 2. R4 同尺寸（other 档同值）----
ok, note = split_feasibility(get_rule("R4"), 40, 4000)
print(f"\nR4 40×100: {note}")
check("R4 整体判 ✓（semi/multi 档）", ok is True)
check("两段各自呈现", "detached ✗" in note and "semi-detached/other ✓" in note)

# ---- 3. R3A（detached-only 区）不出现第二段 ----
ok, note = split_feasibility(get_rule("R3A"), 40, 4000)
print(f"\nR3A 40×100: {note}")
check("R3A 只有 detached 段", "semi-detached/other" not in note)
check("R3A 40 ft 判 ✗（需 50 ft）", ok is False)

# ---- 4. R3A 50×100（17-16 同款）：detached ✓ 回归不破 ----
ok, note = split_feasibility(get_rule("R3A"), 50, 5000)
print(f"\nR3A 50×100: {note}")
check("R3A 50×100 判 ✓（盲测 #6 结论保持）", ok is True)

# ---- 5. 面宽够但面积不够：两条件必须同时满足 ----
ok, note = split_feasibility(get_rule("R3-1"), 40, 3000)
print(f"\nR3-1 40×75 (3,000 sqft): {note}")
check("面积不足时 semi 档也判 ✗", ok is False)

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s)")
    sys.exit(1)
print("ALL PASS")
