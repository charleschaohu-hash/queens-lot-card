# R1-R5 低密度住宅分区规则（人话版）

核实日期 2026-07-25。全部对照 **zr.planning.nyc.gov 现行文本**（已含 City of
Yes for Housing Opportunity，2024-12-05 通过，下称 CoY）。条款号均为现行编号。

> ⚠ 最大的坑：CoY 把 Article II 整章**重排了条款号**。网上大量文章（包括
> 2024 年前的 DCP 页面）引用的 23-32 / 23-142 / 23-141 都是旧号，已不存在。
> 现行：最小 lot＝**23-11**，FAR＝**23-21**，户型＝**22-121/22-122**，
> 停车＝**25-21/25-22/25-23**，ADU＝**12-10 定义**＋**23-341 体量**。

## 一张总表（现行规则）

| 分区 | 最小lot(detached) | 最小lot(其他形态) | 户数/lot | 形态 | FAR(标准/QRS) |
|---|---|---|---|---|---|
| R1-1 | 7,125 sqft / 75 ft | —（只许detached） | 1 | detached | 0.75 / — |
| R1-2 | 4,750 / 50 | — | 1 | detached | 0.75 / — |
| R1-2A | 4,750 / 50 | — | 1 | detached | 0.75 / —（GTZ外禁后院ADU） |
| R2 | 2,850 / 30 | — | 1 | detached | 0.75 / — |
| R2X | 2,850 / 30 | — | 1 | detached | 1.00 / — |
| R2A | 2,850 sqft / 30 ft | —（只许detached） | 1 | detached | 0.75 / — |
| R3A | **2,375 / 25** | — | 2 | detached, zero-lot-line | 0.75 / 1.00 |
| R3X | 2,850 / 30 | — | 2 | detached | 0.75 / 1.00 |
| R3-1 | 2,850 / 30 | 1,700 / 18 (semi) | 2 | detached, semi | 0.75 / 1.00 |
| R3-2 | 2,850 / 30 | 1,700 / 18 | 多户 | 全形态 | 0.75 / 1.00 |
| R4 | 2,850 / 30 | 1,700 / 18 | 多户 | 全形态 | 1.00 / 1.50 |
| R4-1 | 2,375 / 25 | 1,700 / 18 (semi) | 2 | detached, semi, ZLL | 1.00 / 1.50 |
| R4A | 2,375 / 25 | — | 2 | detached | 1.00 / 1.50 |
| R4B | 2,375 / 25 | 1,700 / 18 | 2 | 全形态（限两户） | 1.00 / 1.50 |
| R5 | 2,850 / 30 | 1,700 / 18 | 多户 | 全形态 | 1.50 / 2.00 |
| R5A | 2,375 / 25 | — | 2 | detached | 1.50 / 2.00 |
| R5B | 2,375 / 25 | 1,700 / 18 | 多户 | 全形态 | 1.50 / 2.00 |
| R5D | 2,375 / 25 | 1,700 / 18 | 多户 | 全形态 | 2.00 / 2.00 |

出处：lot＝ZR 23-11；户数与形态＝ZR 22-121 + 22-122；FAR＝ZR 23-21。
"多户" = 该分区不在 22-122 限制清单里，multiple dwelling 合法，户数由
FAR/bulk/dwelling unit factor 实际约束，没有固定的每 lot 上限。

**FAR 0.75 一档的反豪宅脚注**（ZR 23-21 脚注1）：标准 lot ≥4,000 sqft 时，
**单个 dwelling unit** 的楼面积不得超过等效 FAR 0.60。→ 大 lot 上想用满
0.75 必须做两户，单户独吞会被卡在 0.60。

**QRS（qualifying residential site，ZR 12-10）**：R1-R5 内 lot ≥5,000 sqft
＋位于 Greater Transit Zone ＋临 wide street（或 block 短边）＋非 R1/R2 →
解锁"任何住宅形态"＋右列更高 FAR。这是 CoY 的 Transit-Oriented Development
通道。低于 5,000 sqft 的普通小 lot 与它无缘。

## CoY 前后对照（为什么 PLUTO residfar 变了）

- CoY **取消了 attic allowance**（旧 R3 是 0.5 + 20% 阁楼系数 ≈ 0.6），改为
  直接抬高平值 FAR：R3 系 0.5→**0.75**，R4 系 →**1.00**，R5→**1.50**，
  R5D→**2.00**。PLUTO（26v1）的 `residfar=0.75` 对 R3A 就是这个新口径，
  **不含**任何附加系数，可直接 `lotarea × residfar` 用。
- 阁楼现在的处理在 floor area 定义里（ZR 12-10）：坡屋顶下**净高 <8 ft 的
  attic 空间不计楼面积**，≥8 ft 计入。也就是说"阁楼红利"没有消失，只是从
  FAR 系数变成了净高门槛。
- 最小 lot 也放宽了（ZR 23-11，CoY 修订）：R2A 从 3,800/40 降到
  **2,850/30**；R3X 从 3,325/35 降到 **2,850/30**。（旧值来自 CoY 前通行
  资料，仅作背景参考，未重新核对旧版原文。）
- cellar（地下室，过半在地面下）一直不算楼面积；basement（过半在地面上）算。

## ADU 专节（ZR 12-10 "ancillary dwelling unit"，CoY 2024-12 新增）

**基本盘**：每个**单户或两户住宅**的 zoning lot 可加 **1 个 ADU，≤800 sqft**。
形态：主楼内（attic / basement / 加建 extension）、车库改建、后院独立小屋
（backyard ADU）、cellar。

**硬条件**：
1. **业主自住**：ADU 首次取得入住时，该 lot 必须是业主的主要住所（primary
   residence of an owner）。→ 纯投资出租盘做不了，除非业主住其中一户。
2. **计入 FAR**：Ch.3 未见任何 ADU 楼面积豁免条款 → ADU 占用剩余可建面积。
   唯一例外是 cellar ADU（cellar 本身不算 floor area）。
3. **计入户数**：定义写明是 "additional dwelling unit"。
4. **停车 0 位**：所有分区、所有停车分区，ADU 停车要求都是 0
   （ZR 25-222/25-232 表 Column B）。

**后院式（backyard ADU）禁区**（ZR 12-10）：
- **R1-2A、R2A、R3A 且位于 Greater Transit Zone 之外** → 禁（⚠ Whitestone
  的 R3A 大概率在 GTZ 外，即后院式不可，只能做主楼内/车库/cellar 式——
  GTZ 边界要查 DCP 地图逐地块确认）；
- LPC 历史区 → 禁；
- DEP 洪水风险区（10年降雨/2050、沿海1%/2080）→ 禁后院式＋禁 basement/cellar 式；
- 高风险洪水区（ZR 64-11）→ flood elevation 以下不许 ADU。

**后院式体量**（ZR 23-341 / 23-371）：1 层 ≤15 ft（下方带车位则 2 层
≤25 ft）；占后院面积 ≤1/3；距主楼 ≥10 ft；须有 ≥5 ft 宽侧向通道直达。

## 停车（CoY 三分区制，ZR 25-21/22/23）

| 区域 | 单/两户新建每户 | ADU | 备注 |
|---|---|---|---|
| Inner Transit Zone | **0** | 0 | ZR 25-211，全部免 |
| Outer Transit Zone | R3A系 50%，R3-2/R4 35%，R5系 25-35% | 0 | ZR 25-222 |
| Greater Transit Zone 之外 | R2A/R3A系 **100%**，R3-2/R4/R5系 50% | 0 | ZR 25-232 |

**窄 lot 豁免——注意日期限定**（25-222 脚注3 / 25-232 脚注5，原文）：
> "For zoning lots **existing on December 5, 2024** where the lot width is
> 25 feet or less, no parking shall be required."

豁免只给 **2024-12-05 当天已存在**的 zoning lot。全 Chapter 5 没有把豁免
延伸到分地后子 lot 的解释条款；反证：ZR 想覆盖分地情形时都会明写（curb
cut 条款里有 "zoning lots subdivided after June 30, 1989…"、"only for a
resulting subdivided zoning lot that…" 这类表述），脚注 5 偏偏没有。
→ **按平义解释：CoY 之后新切出的 25 ft lot 不享受豁免**，新建住宅仍按本区
比例配位（beyond GTZ 的 R3A 系 = 每户 100%，两户就是 2 个位，25 ft 面宽
上很难摆）。存量老窄 lot（12/5/2024 前已存在）才是免停车的。DOB 实际
审查口径未验证，见下方问题清单。
另注意 ZR 25-241：Queens CD3/CD4（Junction Blvd 以东）和 CD14 即使在
Outer Transit Zone 内也按"GTZ 之外"的表执行（Council 妥协条款）。

## ZR 文本没写清、需要问实操者的问题

1. **GTZ 边界怎么逐地块查**：Greater/Inner/Outer Transit Zone 的法定地图在
   哪个 Appendix？ZoLa 上有没有图层？Whitestone R3A 是否全域在 GTZ 外？
2. **DEP 洪水风险图**：ADU 条款引用的 DEP "10-year rainfall flood risk
   area"（2050）和 "coastal flood risk area"（2080）地图的权威查询入口？
   与 PLUTO `pfirm15_flag` 不是同一张图，不能互替。
3. **ADU 与 FAR 用尽的 lot**：已建满 0.75 的房子还能否加 cellar ADU？
   （cellar 不算楼面积，理论可行，DOB 实操是否放行？）
4. **ADU 是否触发 Multiple Dwelling Law**：1 户＋1 ADU＝2 DU 没问题，但
   2 户＋1 ADU＝3 DU，是否被 MDL 认定为 multiple dwelling（消防/规范升级）？
   ZR 管不到 MDL，这是州法层面的问题。
5. **业主自住的执行细节**：只查"首次入住时"？之后卖掉/搬走 ADU 还合法吗？
   deed restriction 还是仅 DOB 备案？
6. **zero lot line 实操**：R3A 允许 zero lot line，Queens 实际有人这么建吗？
   与相邻业主的协议怎么做？
7. **切地手续**：50×100 → 2×(25×100) 走 DOB subdivision 还是 DCP？周期和
   费用？（17-08/17-06 母地 2025-10 完成分割，可问经手人）
8. **反豪宅 0.60 脚注的执行口径**：两户住宅里一大一小（如 0.6+0.15）是否
   合规？"associated with any single dwelling unit" 怎么算公共面积？
9. **新切 25 ft lot 的停车要求，DOB 实际按什么口径审？** 脚注 5 平义只豁免
   2024-12-05 已存在的 lot，新切子 lot 不在内（见上节）——你的项目
   （17-08/17-06，2025-10 分割）配了几个位？是主动配的还是 DOB 要求配的？
   有没有走什么豁免/解释路径（如按母地存在日期主张、74-52 特批等）？

## 数据源

- [ZR 23-11 最小 lot](https://zr.planning.nyc.gov/article-ii/chapter-3/23-11)
- [ZR 23-21 FAR](https://zr.planning.nyc.gov/article-ii/chapter-3/23-21)
- [ZR 22-121 / 22-122 户型](https://zr.planning.nyc.gov/article-ii/chapter-2/22-121)
- [ZR 12-10 定义（ADU / QRS / floor area）](https://zr.planning.nyc.gov/article-i/chapter-2/12-10)
- [ZR 23-341 后院许可障碍物](https://zr.planning.nyc.gov/article-ii/chapter-3/23-341)
- [ZR 25-211 / 25-222 / 25-232 / 25-241 停车](https://zr.planning.nyc.gov/article-ii/chapter-5/25-222)
