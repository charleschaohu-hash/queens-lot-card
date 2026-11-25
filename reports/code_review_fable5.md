# 代码审查报告（Fable 5 · 2026-07-28）

只读审查，未改动任何代码。范围：`src/` 全部四个文件（lot_card.py 1155 行 /
acris.py 330 行 / dob.py 278 行 / rules.py 351 行），对照 README、`skills/`
两份文档、`reports/` 两份报告与 `cache/`、`cards/` 实际产物核实。

严重度定义（贴合本项目性质——卡片直接用于投资判断）：
- **高** = 可能让卡片给出错误数字/错误标的，或给出会导致错误决策的判定
- **中** = 特定条件下产出误导性内容，或数据口径隐患
- **低** = 可维护性 / 死代码 / 文档不一致

带 ✅实证 标记的发现已用现有 cache/cards 数据复现确认，不是推测。

---

## A. 正确性风险

### A1｜高｜交互选择的 BBL 不持久化，重跑会静默翻回候选 #1
**[lot_card.py:152-156](../src/lot_card.py#L152-L156) + [197-206](../src/lot_card.py#L197-L206) + [225-226](../src/lot_card.py#L225-L226)**
歧义候选（同置信度多 BBL）每次运行都重新走一遍选择逻辑：cache 里存的是
GeoSearch **完整响应**（含全部候选），`address_index.json` 只存 slug→BBL 映射
但**读取时不用它短路候选选择**。后果链：用户交互式选了候选 #2 → idx 记下
bbl₂ → 下次非交互重跑（如批量再生成脚本）→ 加载 bbl₂ 目录下的缓存响应 →
候选逻辑重新触发 → 非交互默认取 #1 → **整张卡换成了另一个地块**，且 idx
被改写回 bbl₁，无任何警告。17-08 每次跑都弹出 3 个候选（本轮批量再生成
全靠"默认 #1 恰好正确"才没出事）。
**修法**：cache 命中且 slug 在 idx 里时，直接信 idx 记录的 BBL，跳过候选
选择；只有 `--fresh` 或 idx 缺失才重新选。约 10 行。
**工作量**：20 分钟（含用 17-08 验证）。

### A2｜高｜SAT 跨截断线错配，可能把未解押抵押标成 clear
**[acris.py:207-228](../src/acris.py#L207-L228)**
D2 修复把成交日之前的 MTGE 降为"历史抵押"，但 **SAT 列表没有做对应切分**
（216 行取的是全量 SAT）。场景：MTGE 2010（历史）→ 成交 2015（截断）→
MTGE 2016（现任）→ SAT 2017 **实际解的是 2010 那笔**（迟登记——正是 D2
发现的"SAT 漏登记"同款现象，skills 文档也记过"2013 SAT 对应 1987 FT_
抵押"的实例）。贪心配对会把 SAT 2017 分给 MTGE 2016 → 当前负债显示
clear → **议价空间从"低（债重）"误判为"高（长持无债）"**。方向刚好是
危险的那边：高估卖家让步空间。
**修法**：不必做完美配对——当存在历史抵押、且某份 SAT 的日期同时晚于
某历史 MTGE 与某现任 MTGE 时，该配对降为 `uncertain`（已有的存疑通道），
不再输出 clear。约 15 行。
**工作量**：45 分钟（需构造一个三层测试用例）。

### A3｜中｜"Structures on site" 把区级占位 BIN 当真建筑数 ✅实证
**[lot_card.py:213-219](../src/lot_card.py#L213-L219)**
`bin_count` 数的是 GeoSearch 返回的 BIN 个数，不过滤 `4000000` 占位符，
且 `max(len, 1)` 强制下限 1。实证：11 Center Dr（V0 **空地**）geo_bins =
`['4000000']` → 卡片印 "Structures on site: 1"。空地卡上写"地上建筑 1 栋"
是肉眼可见的错数字。dob 模块明明已有 `is_real_bin()` 过滤器和从 DOB 表
捞真 BIN 的逻辑（4046500026 就是这么找到 4625708 的），身份板块没用上。
**修法**：bin_count 改用 `dob` 信号里解析后的 `bins` 数（或至少过滤占位
BIN，0 就显示 0）；注意 dob 查询在 build_context 之后，需要把这行显示
挪到 dob 结果可用之后或传入。
**工作量**：30 分钟。

### A4｜中｜appbbl == 自身 BBL 时显示"由母地【自己】分割而来" ✅实证
**[lot_card.py:274-288](../src/lot_card.py#L274-L288)**
apportionment 后保留原 lot 号的地块，PLUTO `appbbl` 等于自身 BBL。
实证：17-08 卡印 "Subdivided from parent lot **4046500025**"——这就是它
自己；4049700011 同款。读者会当成数据错误，且"母地"语义失真（它是被
重划边界的存量 lot，不是切出来的新 lot）。ACRIS 母地回退在
[lot_card.py:1069](../src/lot_card.py#L1069) 已经做了 `mother != bbl` 防护，
说明这个坑当时想到过，唯独警示文案没防。
**修法**：`appbbl == bbl` 时改文案为 "Lot lines re-drawn (apportionment)
on {date}"，不再提 parent。5 行。
**工作量**：15 分钟。

### A5｜中｜分地判定①忽略 semi/attached 形态的更小最小 lot（假阴性）
**[lot_card.py:368-391](../src/lot_card.py#L368-L391)，[rules.py:170-171](../src/rules.py#L170-L171) 等**
判定①只用 detached 的 `min_lot_width_ft / min_lot_area_sqft`（2×30 ft /
2×2,850 sqft 一档），**`min_lot_width_other / min_lot_area_other`
（1,700 sqft / 18 ft）录了库但从未被读**。R3-1、R3-2、R4、R4-1、R4B、
R5、R5B、R5D 八个区里，一块 40 ft 面宽的 lot 切两块 20 ft semi-detached
是合规路径，判定①却给 ✗。这是"漏掉可行标的"方向的错误——对找地工具
来说和误报同样致命。
**修法**：判定①依次测 detached 和 other 两档，任一通过即 ✓ 并注明按
哪种形态成立（"two 18-ft semi-detached lots per ZR 23-11"）。
**工作量**：1 小时（含挑一个 R3-1/R4 宽地实测）。

### A6｜中｜商业分区套住宅 FAR 得出荒谬的"Overbuilt teardown"结论 ✅实证
**[lot_card.py:340-355](../src/lot_card.py#L340-L355)**
潜力板块只用 `residfar`。实证：4049700011（**C4-2**，residfar 2.43、
commfar 3.40）的卡印着 "★ Overbuilt lot — teardown not applicable:
existing 254,196 sqft > allowed 104,490 sqft"——对一栋 2024 年封顶的
16 层混合用途 condo 说"拆了重建会亏面积"，判定框架整个不适用。深挖
专项已证明你们会跑非标目标，这类卡流出去有损可信度。
**修法**：`zonedist1` 非 R 打头（或 commfar > residfar）时，三数字卡与
overbuilt 判定降级为 "Residential-FAR view only — commercial district
(commfar {x}), development potential out of this tool's scope"，不输出
teardown 结论。
**工作量**：45 分钟。

### A7｜中｜名义转让（<$10k DEED）会解除 LIS PENDENS 警报
**[acris.py:243-251](../src/acris.py#L243-L251)**
LP "其后无成交" 用的是 `deeds`（全量，含 <$10,000 名义转让）。LP 之后
一笔 $0 亲属过户/转 LLC 并不了结讼争，却会让"风险信号"从 ⚠ 变
"no LIS PENDENS ✓"。同文件 177-178 行明明已把 real_sales 分了出来。
**修法**：`deeds_after` 改用 `real_sales`。1 行。
**工作量**：10 分钟。

### A8｜中｜遗产信号无时效（已知边界，重申）
**[acris.py:289-294](../src/acris.py#L289-L294)**
盲测报告"已知边界"第 2 条记录过、当时决定不修：13.6 年前的遗产成交
（11 Center Dr，现业主已是公司持有 13 年）仍触发"Bargaining leverage:
High — estate sale"。本轮重申是因为它是**方向性误导**（高估动机），且
修法便宜：遗产/法拍档位加 `years_held <= N`（建议 N=3）门槛，超龄降为
Medium 并注明 "stale estate signal ({years}y ago)"。
**工作量**：20 分钟。是否修由你定夺——若维持"记录不修"，请在卡面加注。

### A9｜低｜终端摘要在超建时仍打印负数 unused
**[lot_card.py:1088-1089](../src/lot_card.py#L1088-L1089)**
md/html 都把负数转成"超建 X"语义，唯独终端打印 `★unused -138 sqft`。
盲测 D4 修复漏了终端这一处。
**工作量**：10 分钟。

### A10｜低｜ADU 判定在 unitsres 缺失时按"可能适用"处理
**[lot_card.py:424-425](../src/lot_card.py#L424-L425)**
`unitsres` 为 None（PLUTO 缺字段）落入 else 分支输出 "May apply"。
缺数据应输出 "? unit count missing"，不应默认乐观。
**工作量**：10 分钟。

---

## B. 数据处理隐患

### B1｜中｜所有 Socrata 查询无 $limit 触顶检测——静默截断
**[dob.py:194/202/215/222/235](../src/dob.py#L194)，[acris.py:68/48](../src/acris.py#L68)**
legals/jobs/BIS/两违规表 `$limit=500`，complaints `$limit=2000`，master
批量 5000。返回行数 == limit 时没有任何警告，DOB Summary 的 Total 列
会**少报且看起来言之凿凿**。72 份文书的深挖 lot 离 500 尚远，但大楼
（4049700011 邻栋 condo 有 156 个单元 lot 的量级）撞线完全可能。
**修法**：`_cached_get` 加一行 `len(data) >= limit` → 打警告并在信号 dict
里带 `truncated` 标记，卡面对应行加 "≥" 前缀。
**工作量**：30 分钟（与 C1 合并做更划算）。

### B2｜中｜缓存无时效概念，旧数据以今天的生成日期示人
**[dob.py:69-73](../src/dob.py#L69-L73)，[acris.py:31-33](../src/acris.py#L31-L33)**
除 `--fresh` 外缓存永不过期。卡片脚注 `generated {今天}` + PLUTO 版本号，
但 ACRIS/DOB/投诉数据实际是**首次抓取那天**的。投诉表自带
`dobrundate`（快照时间戳）、ACRIS 有 `good_through_date`（深挖报告还
专门算过 2026-06-30 这个边界），都没上卡。半年后重发一张卡，违规数是
半年前的，脚注却是当天。
**修法**：`_cached_get` 落盘时同存 fetch 时间（或直接用文件 mtime），
脚注改为 `PLUTO 26v1 · ACRIS thru {good_through} · DOB fetched {date}`；
可选：cache 超 N 天自动转 fresh。
**工作量**：1 小时。

### B3｜中｜无 GeoSearch 真 BIN 时，主 BIN 取自 DOB 表的任意先后
**[dob.py:155-170](../src/dob.py#L155-L170)**
`_collect_bins` 的顺序 = geo 优先，其后按 jobs→bis→violations→ecb 的
**行序**。11 Center Dr：geo 只给占位符，primary_bin 落为 4870647（jobs
表先出现），4101287（BIS 表）成了 "additional"——哪个是主楼没有依据，
BIS 链接可能指向次要结构。
**修法**：难有完美解；至少在 extra_bins 注释里改说 "BIN order arbitrary
beyond GeoSearch"，或用出现频次/最新 filing 归属做启发式。
**工作量**：30 分钟（文案级）～2 小时（启发式）。

### B4｜低｜缓存 JSON 损坏（写中断）会以裸 traceback 崩溃
**[dob.py:71](../src/dob.py#L71)，[acris.py:33](../src/acris.py#L33)**
`json.loads` 的 `JSONDecodeError` 不在 `requests.RequestException` 捕获
范围内。`load_address_index` 防了这个，模块缓存没防。
**修法**：损坏时视为 cache miss 重抓。
**工作量**：15 分钟。

### B5｜低｜Master 表未按 document_id 去重
**[acris.py:156-171](../src/acris.py#L156-L171)**
Legals 的多行重复是实测确认并去重了的；Master 按 id in(...) 查询后直接
逐行建 docs，若 Master 也存在重复行（未实测排除），金额会被双计进
pulse 与配对。防御性 1 行去重成本极低。
**工作量**：10 分钟。

### B6｜低｜同 BBL 多地址写法互相覆盖 geosearch 缓存
**[lot_card.py:222-224](../src/lot_card.py#L222-L224)**
"149-44 20th Ave" 与 "14944 20th Avenue" 共用 `cache/4046700043/
geosearch.json`，后跑的覆盖先跑的——缓存内容取决于最后用哪种写法查。
两种写法归一同 BBL 时无害，但与 A1 叠加时会放大候选漂移面。修 A1 时
一并考虑（按 slug 存或存 chosen 摘要）。
**工作量**：并入 A1。

---

## C. 结构与可维护性

### C1｜中｜`_cached_get` 两份近似实现
**[acris.py:31-39](../src/acris.py#L31-L39) vs [dob.py:69-80](../src/dob.py#L69-L80)**
签名和日志格式略异的同一函数。建议抽 `src/fetch.py`（或并入一个
`socrata.py`），同时把 B1 的触顶检测、B4 的损坏容错、B2 的时间戳一次
装进去——四个问题一个改动点。
**工作量**：1 小时（含回归跑 13 地址）。

### C2｜中｜lot_card.py 1155 行，渲染层约占 550 行
职责混装：抓取（130-250）、业务判定（255-474）、三个渲染器（479-993）、
CLI 编排（1029-1155）。**不建议大拆**——但 `render_md / render_html /
CSS / render_png_pdf` 是纯函数，切成 `src/render.py` 零风险，主文件回到
~600 行业务本体。GIS/地图嵌入是下一步计划，渲染层马上还会长，现在切
比之后切便宜。
**工作量**：45 分钟（纯搬运 + import 调整）。

### C3｜低｜终端摘要 40 行内联在 main()
**[lot_card.py:1076-1117](../src/lot_card.py#L1076-L1117)**
与 md/html 共享行构造器却在 main 里手排。抽 `render_terminal(c)` 后
main 只剩编排。
**工作量**：20 分钟。

### C4｜低｜`import re` 埋在 acris.py 第 106 行
**[acris.py:106](../src/acris.py#L106)** 模块中部 import，移到顶部。
**工作量**：2 分钟。

### C5｜低｜BIS 项目组的 `n_filings` 语义与 DOB NOW 不同
**[dob.py:150](../src/dob.py#L150) vs [lot_card.py:572-573](../src/lot_card.py#L572-L573)**
DOB NOW 组的 n_filings = filing 数（参与 Jobs/Filings 主数），BIS 组的
n_filings = **许可行数**（不参与主数，但 `_fmt_group` 会把它显示成
"N filings"）。同名字段两种含义，下次改口径必踩。建议 BIS 组改名
`n_permits` 并在 `_fmt_group` 里显示 "N permits"。
**工作量**：20 分钟。

---

## D. 死代码与过期逻辑

### D1｜低｜`geosearch` 返回的 chosen feature 无人使用
**[lot_card.py:1039](../src/lot_card.py#L1039)** `geo` 接了就丢。返回值
四元组可以砍成三元组，或留着给将来 GIS 用——二选一，别悬着。
**工作量**：5 分钟。

### D2｜低｜`_batch_fetch` 的 `select` 参数从未被传
**[acris.py:42-54](../src/acris.py#L42-L54)** 无调用方使用。删参或留注释。
**工作量**：5 分钟。

### D3｜低｜项目组 dict 里 description/owner/applicant 算了不渲染
**[dob.py:110-121](../src/dob.py#L110-L121)** `_fmt_group` 不消费这三个
字段。不算错（调试有用），但若确定不上卡，注释说明意图。
**工作量**：5 分钟。

### D4｜低｜bldgclass 字典缺口在盲测 D3 就点过名，只补了 V 段
**[lot_card.py:39-58](../src/lot_card.py#L39-L58)** 盲测报告原话
"V0-V9（空地）、**D（电梯公寓）、G（车库）等缺失**"——D/G/H 段至今
未补，深挖卡实际印出 "H9 – class not in dictionary"。跑非标目标已是
现实用法，建议至少补 D/G/H/S/K 常见段。
**工作量**：30 分钟（对照 DOF 官方类别表抄录）。

---

## E. skills / 文档与代码一致性

### E1｜中｜README "七个板块" 实列 8 项，且漏了 DOB Summary ✅实证
**[README.md:17-25](../README.md#L17)** 标题写"七个板块"，下面列表编号
1-8；而且当天晚些加入的 **DOB Summary 板块不在列表里**（实际卡片有
9 个区块：头部 + 8 节）。进度节倒是记了 DOB Summary——同文件自相矛盾。
**修法**：列表补 DOB Summary（位于施工动态后），标题改"八个板块"或
"头部 + 8 个板块"。
**工作量**：5 分钟。

### E2｜中｜zoning skills 总表缺 R1-1/R1-2/R1-2A/R2/R2X 五行
**[skills/zoning_rules_r_districts.md:13-27](../skills/zoning_rules_r_districts.md#L13)**
盲测 O1 修复往 rules.py 补录了这五个区（含条款号、verified=True），
skills 文档的"一张总表"没同步——表从 R2A 开始。文档标题自称
"R1-R5"，实际覆盖 R2A-R5D。下次有人对照文档核 rules.py 会误以为
R1/R2 系是代码私自加的。
**工作量**：15 分钟。

### E3｜低｜pipeline skills 与代码逐条核对结果：其余全部一致
逐条核过：Legals 无前导零参数 ✓、批量 50 ✓（`BATCH=50`）、legacy
FT_/BK_ 剔除 ✓、ECB lot 4 位补零 ✓（`lot_pad4`）、DOB NOW 状态三档 ✓、
投诉表 BIN-only 与 status 二值 ✓、占位 BIN 判据 ✓（`is_real_bin`）、
BIS 403 记录与 `bis_url()` 回退式 ✓。无需修改。
唯一补充建议：投诉一节可加一句"查询 `$limit=2000`，触顶风险见 B1"。

---

## F. 性能

### F1｜低｜每张卡独立启动一次 Chromium
**[lot_card.py:1012-1024](../src/lot_card.py#L1012-L1024)** 批量再生成
13 地址 = 13 次浏览器冷启动（约 1-2s/次）。单张交互使用无感，批量再
生成占总时长的主要部分。若批量重跑会成为常态（每轮验收都在跑），值得
加一个 `--batch` 入口复用同一 browser 实例；否则不动。
**工作量**：45 分钟（可选）。

### F2｜——｜其余无明显浪费
缓存命中逻辑健全（本轮批量再生成除投诉外零 API 重复请求）；
`_batch_fetch` 顺序请求在当前规模（≤2 批）无所谓。无发现。

---

## 建议修复顺序

**第一批：错误数字与错误标的（预计 2.5 小时）**
1. A1 候选 BBL 持久化 —— 唯一可能"整卡换地块"的问题
2. A3 占位 BIN 计入建筑数 —— 实证错数字，修法现成
3. A4 自身母地文案 —— 实证误导文案，5 行
4. A7 名义转让解除 LP —— 1 行
5. A2 SAT 跨截断线错配 —— 影响负债与议价档位

**第二批：判定质量（预计 2.5-3 小时）**
6. A5 分地判定补 other 形态 —— 消除假阴性（漏标的）
7. A6 商业分区 overbuilt 降级 —— 非标目标卡面可信度
8. B1 $limit 触顶检测 + C1 合并 `_cached_get`（一次改动带 B4）
9. A8 遗产信号时效 —— 若你维持"记录不修"则跳过，但请卡面注明

**第三批：口径与文档（预计 1 小时）**
10. B2 数据时效上卡（good_through_date / dobrundate / fetch 日期）
11. E1 README 板块数 + E2 skills 总表补五行
12. D4 bldgclass 补 D/G/H 段
13. A9 / A10 两个小分支

**第四批：结构（可选，预计 1.5 小时）**
14. C2 渲染层拆 render.py（建议在 GIS 动工前做）
15. C3 / C4 / C5 / D1 / D2 / D3 清理
16. F1 批量模式（若批量重跑常态化）

---

*审查方法说明：所有 A/B 级发现均已在现有 cache 数据上推演过触发路径，
其中标 ✅实证 的四项直接在现有卡片/缓存中复现；未标注的（A1/A2/A5/A7
等）需要特定数据形态触发，判断依据是代码路径 + skills 文档记录的真实
数据行为（如迟登记 SAT 的既往实例）。本轮未运行任何修改。*

---

# 修复记录（2026-07-28 同日闭环）

批准范围：第一批 A1-A7 全部（A1/A2/A4/A5 按批示口径）、第二批 B1/B2、
A8（按"信号挂在最近成交"规则）、E1/E2 文档同步。第四批结构类全部暂缓，
已记入 README Backlog。13 地址全量重跑，另补 1 个合成用例单元测试。

## 逐项修复

| 项 | 实现 | 位置 |
|---|---|---|
| A1 | 既往 BBL 选择从 address_index 短路（`[index] prior BBL choice honored`）；非交互 + 多候选 + 无既往选择 → **exit 2 不出卡**，提示先交互跑一次。实测：18-15 149th St（新歧义地址）正确拒绝且不污染 index/cache | lot_card.py `geosearch()` |
| A2 | SAT 配对升级债主匹配制：SAT 当事人与 MTGE 贷方（party_type '2'）**招牌词**（剔泛化词，MERS 系归泛化）有交集才许清账；同债主多押或与历史押撞债主 → 存疑；其后无 SAT → 确定 open；有 SAT 但对不上 → 存疑 | acris.py `analyze()` + `_lender_match` |
| A3 | 建筑数改用 PLUTO `numbldgs`（空地=0），标注 `(PLUTO)`；GeoSearch BIN 只作投诉查询种子 | lot_card.py |
| A4 | appbbl==自身 → 扫同母地兄弟 lot（`fetch_siblings`，缓存 pluto_siblings.json）：有同日兄弟 → "Retained lot from subdivision"；查无 → "Lot merger"；查询失败 → 中性文案不猜 | lot_card.py |
| A5 | 分地判定抽出 `split_feasibility()`：detached / semi-other 两档分别判分别呈现；detached-only 区不出现第二段。`tests/test_split.py` 5 组用例全过 | lot_card.py + tests/ |
| A6 | 非 R 分区：潜力板块降级免责（含 commFAR 值 + builtFAR 毛面积口径声明），overbuilt/teardown 结论撤销，第三数字卡改"R-lens residual (reference only)" | lot_card.py |
| A7 | LP 解除只认真实成交（≥$10,000），名义转让不了结讼争 | acris.py |
| A8 | 卖方侧遗产/法拍信号随成交作废 → 只留"signal spent"备注；前瞻 High 只认两类：现业主本身是遗产/执行人（`apply_owner_context` 注入）、LP 在档无后续真实成交 | acris.py |
| B1 | 两模块 Socrata 查询自动 $offset 翻页（上限 20 页）；触顶/旧单页缓存可疑 → 卡面警示"counts may be incomplete"，绝不静默 | acris.py / dob.py |
| B2 | 脚注分源时效：`MapPLUTO 26v1 · ACRIS good through 2026-06-30 · DOB run 2026-07-27 · generated ...`。ACRIS 用**数据集级** max（深挖报告同口径；首版误用 per-lot max 会把沉睡地块标成十年旧数据，已改，失败回退 per-lot 并注明口径） | acris.py `dataset_good_through()` + lot_card.py |
| E1 | README 板块清单补 DOB Summary、改"头部 + 8 个板块"；Backlog 节记录暂缓的结构项 | README.md |
| E2 | skills 总表补 R1-1/R1-2/R1-2A/R2/R2X 五行（与 rules.py 对齐） | skills/zoning_rules_r_districts.md |

## 验收结果（批示 ①-⑤）

1. ✅ 11 Center Dr：`Structures on site: 0 (PLUTO)`；议价 High(estate) →
   **Medium** + "seller-side signal spent" 备注
2. ✅ 17-08 → "Retained lot from subdivision on 2025-10-29 — sibling lot(s)
   4046500026 split off"；4049700011 → "Lot merger on 2023-07-05"；
   17-06（appbbl≠自身）保持 "Subdivided from parent lot" 不受影响
3. ✅ 13 地址无 semi-可分实盘用例（19-10 R3-1 仅 19 ft，两档皆 ✗ 但两段
   分别上卡）→ 按批示用 `tests/test_split.py` 合成用例：R3-1/R4 40×100
   detached ✗ · semi ✓，R3A 不出第二段，17-16 detached ✓ 回归不破，全过
4. ✅ 17-12：`$1,000,000 unsatisfied (MTGE 2018-11-07)` / Low —— 一字不变
   （2018 押后无任何 SAT → 确定 open，不经过匹配歧义通道）
5. ✅ 全部 13 张卡脚注为分源时效格式

## 议价/负债全量 diff（13 地址，基线 = 修复前）

**档位变化 3 处，均为规则设计内：**
- 11 Center Dr：High(estate) → **Medium**（A8，验收要求）
- 17-08 / 17-06：High(estate) → **Low（债重：$665k / $950k = 70%）** + spent
  备注 —— A8 的连带效果：卖方侧遗产信号对"已被开发商买走"的地块不再
  给 High。这是语义修正而非误伤：现业主是重杠杆在建开发商，对其议价
  不是遗产逻辑。原"已印证"叙事保留在 Seller → buyer 行（hot 高亮不变）
- 150-95 Powells Cove：High(长持无债) → **Medium**（A2 活捉：旧逻辑把
  2006 年**卖家** WATERSIDE LLC 的 NYCB 建设贷 SAT 配给了买家同日的
  Wells Fargo $873k 购房贷，产出假 clear；实际一份 2022 Wells SAT 对两笔
  Wells 押，真歧义 → $13,896 落存疑，档位随之从"无债长持"回落）

**负债明细变化 2 处（档位不变，均更保守）：**
- 141-18：存疑 2 笔 → 3 笔（+2003 GREENPOINT $14.5k——无 GREENPOINT SAT，
  旧逻辑曾把它贪心配给 WACHOVIA 的 SAT）
- 19-10：存疑 2 笔($735k) → 5 笔($825.9k)（+LASALLE/CITI 小额押——BofA
  2014 SAT 疑为 LaSalle 后继行但招牌词对不上，按纪律落存疑；同时
  2004 ABN AMRO $328k 被 2019 迟登记 SAT **正确清账**、2017 BETHPAGE
  被同债主 SAT 正确清账——债主匹配制双向都在工作）

其余 7 地址（17-16、17-12、149-44、154-07、24-31、4049700011、和 17-08 的
负债金额本身）零变化。

## 未修事项（按批示）

- 第四批结构类（C1-C5、D1-D4、F1）→ README Backlog，扫街阶段带真实
  需求再动
- A9/A10（终端负数 unused、ADU 缺数据分支）未在批准范围内，保留在
  上方审查发现清单里待下轮
