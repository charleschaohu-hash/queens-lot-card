# queens-deal-tool

Queens 低密度住宅地块投资分析工具集。第一个工具：**地块档案卡生成器** ——
输入一个地址，产出一张适合微信直发的地块档案卡（md / html / png / pdf）。

## 用法

```bash
python3 src/lot_card.py "17-08 149th St, Queens, NY"
python3 src/lot_card.py "17-08 149th St, Queens, NY" --fresh   # 强制重抓 API
```

产出：
- `cards/{BBL}_{地址slug}.{md,html,png,pdf}`
- PDF 自动复制一份到 `~/Desktop/地块档案卡/`

## 卡片内容（头部 + 8 个板块）

1. **头部** — 地址、社区+zip、分区徽章、BBL、开发中/有违规徽章
2. **身份** — BBL 拆解、学区、地上建筑栋数（PLUTO numbldgs）、
   分割/存留/并地警示（appbbl 三形态判别）
3. **规矩** — 四个否决检查位：商业 overlay / 特殊区 / 地标历史区 / FEMA 洪水区；splitzone 跨分区警示
4. **土地与现状** — 面积、面宽×进深、地块类型、建筑类别、户数、层数
5. **潜力** — 允许建造 / 已用 / ★未用面积三数字卡 + 分地（detached/semi 分形态判）/
   户型/单元乘法/ADU 四行判定；C/M 分区整体降级免责
6. **成交历史（ACRIS）** — 上次易手、卖家→买家类型、未解押抵押（SAT 债主
   匹配制）、LIS PENDENS、交易脉搏、★议价空间分档（信号时效规则）
7. **施工动态（DOB）** — 活跃备案项目组三态判定、违规与 ECB 欠费；有重型备案时
   给"开发中"红条并把 4/5 板块降级为历史参考
8. **DOB Summary** — 对标 BIS Property Profile 概览的双列表（投诉/两类违规/
   备案数/ECB 欠费）+ BIS 直达链接
9. **权属** — 业主（ACRIS 最新 DEED 买方为主、PLUTO 名册为辅）+ 动机信号、税务估值

## 目录结构

```
src/       lot_card.py 主程序；rules.py 分区规则表（已核实，标条款号）
           acris.py 成交历史模块；dob.py 施工动态模块
skills/    经验知识库（API 踩坑记录、分区规则核实笔记）
cache/     原始 API 返回，按 BBL 分文件夹
cards/     成品卡片
reports/   盲测报告、深挖专项报告
```

## 数据源

- [NYC GeoSearch v2](https://geosearch.planninglabs.nyc)（地址 → BBL/BIN）
- [MapPLUTO (Socrata 64uk-42ks)](https://data.cityofnewyork.us/resource/64uk-42ks.json)（地块属性）
- ACRIS 三表：Legals `8h5j-fqxa` → Master `bnx9-e6tj` + Parties `636b-3b5g`
- DOB：DOB NOW 备案 `w9ak-ipjd`、BIS 许可签发 `ipu4-2q9a`、
  DOB 违规 `3h2n-5cm9`、ECB 违规 `6bgk-3dad`
- ⚠ 四组数据源的 borough/block/lot 参数格式各不相同，逐条实测记录见
  `skills/nyc_open_data_pipeline.md`

## 当前进度

- ✅ 地块档案卡生成器 v1：GeoSearch + MapPLUTO 管线、缓存、四格式输出
- ✅ 规则核实专项（2026-07-25）：`rules.py` 已对照现行 ZR（含 City of Yes
  2024-12 修订）逐条核实并标条款号；ADU/停车规则入库；判定①②引用条款号，
  ④ADU 输出真实条件判定；详见 `skills/zoning_rules_r_districts.md`
- ✅ **ACRIS 成交历史模块**（`src/acris.py`）：三表接力、legacy 文书分流、
  以最近真实成交日截断的抵押配对、LIS PENDENS 检测、当事人分类器；
  合成信号"议价空间"高/中/低分档已上卡
- ✅ **DOB 施工动态模块**（`src/dob.py`）：备案项目组聚合与活跃/完结/死亡
  三态判定、重型工种（NB/Full Demolition）触发"开发中"红条并把土地与
  潜力板块降级为历史参考、DOB+ECB 未结违规与欠费上卡
- ✅ **盲测闭环**（2026-07-25）：12 地址盲测 → 6 缺陷 3 观察项 → 同日修复
  并全量重跑验证，逐条见 `reports/blind_test_round1.md`
- ✅ **深挖专项**（2026-07-27）：BBL 4049700011（Flushing 16 层 condo，
  零售+酒店+社区设施混合用途）验证了工具在 condo / 商业区非标目标上的
  临场分析能力——贷款结构、单元 lot 分布、ACRIS 数据时效边界，
  见 `reports/deep_dive_4049700011.md`
- ✅ **英文化改造**（2026-07-28）：卡片四格式 + 终端输出全部英文，
  bldgclass/lottype 对照表保留但输出英文描述；中文只留在源码注释、
  `skills/` 与 `reports/`，卡面零中文（全角 ｜ 与全角空格一并换成
  拉丁字符，避免在西文字体下发虚）
- ✅ **DOB Summary 板块**（2026-07-28）：对标 BIS Property Profile 概览的
  双列表（Complaints / Violations-DOB / Violations-OATH-ECB / Jobs-Filings
  / ★Unpaid ECB balance），附按 BIN 构造的 BIS 页面直达链接；
  接入 DOB Complaints Received `eabe-havv`（BIN-only 表，需先解析 BIN 集合）
- ✅ **Jobs/Filings 口径校准**（2026-07-28）：改为 BIS 口径优先，
  格式 `11 (4 projects)` —— 主数 = 逐份 filing 计数（DOB NOW 各项目组
  filing 数之和 + BIS job 数），括注 = 项目组数。两个口径并列，
  和 BIS 页面对照时不会再对不上
- ✅ **BIS 工单接入 + 双系统分账**（2026-07-28）：接入 DOB Job
  Application Filings `ic3t-wcy2`（真正的 BIS 工单表），DOB Summary 备案
  行拆为 "Filings — DOB NOW"（逐份 filing + 括注项目组）与 "Jobs — BIS"
  （去重 job 数）两行——BIS 与 DOB NOW 是不互数的双系统，核对分账；
  BIS 活跃工单进施工动态列表（标 [BIS] + 简述）。实测收获：17-08 的
  分地文书（SI）与 BPP 在 BIS 侧现身；11 Center Dr 浮出 2013 年未销案
  NB 及配套链，解释其 ECB 欠费来历（烂尾信号）。ARA/LAA 等 BIS 内部
  指标无开放数据，卡面脚注声明
- ✅ **bldgarea 出处标注**：有活跃 DM/NB 备案时升级为警告
  "既不是原建筑也不是新建筑"，否则出小字脚注标 PLUTO 版本
- **当前状态：查案模式全线贯通** —— 地块身份、规矩、潜力、成交、施工、
  DOB 汇总、权属七条线索链路打通，标准住宅地块与非标混合用途目标均已
  实盘验证；13 个地址写法（12 个 BBL）全量重跑零报错
- ⚠ 遗留：Greater Transit Zone 边界与 DEP 洪水风险图无逐地块数据源，
  ADU 判定仍是条件式输出（见 skills 文档的问题清单）
- ⚠ 遗留：BIS 网页整站封锁自动化客户端（Akamai 403，首页亦然），
  `?bin=` 链接格式无法在本机验证，需人工点开复核；
  回退式 `?boro=&houseno=&street=` 已在 `dob.bis_url()` 备好
- ✅ **卡片自核验**（2026-07-28）：每个板块尾部挂官方数据源直达链接
  （"Verify: … ↗" 灰字行）——ZoLa 地块页（身份/规矩/土地/潜力）、ZR
  条款页（判定行引用的每个条款号）、ACRIS 文书详情页（DEED/MTGE 逐条
  直达 + 检索入口）、DOB NOW 门户（附 BIN 检索提示）、DOF Property
  Portal（权属）、七个数据集目录页（脚注）。PNG/PDF 不可点击处附可见
  短 URL。链接模式逐一实测，记录在 skills"Official verification URLs"；
  DOB NOW/BIS 本机 403 待人工点测。**卡片现在是自核验的——每一板块的
  底层数据都可一键回到官方源头对质**
- ✅ **代码审查修复轮**（2026-07-28，Fable 5 审查）：正确性 7 项（BBL 选择
  持久化 + 非交互护栏 / SAT 债主匹配制 / numbldgs 建筑数 / appbbl 三形态
  判别 / 分地判定分形态 / C-M 区降级免责 / LP 只认真实成交）+ 数据口径
  2 项（Socrata 自动翻页防截断 / 脚注分源数据时效）+ 议价信号时效规则
  （卖方侧遗产/法拍信号随成交作废，业主侧前瞻触发）；13 地址全量重跑
  验收，明细见 `reports/code_review_fable5.md` 修复记录

## 下一步计划

1. **GIS 跨区工具** — 跨 borough 通用化、地图截图嵌入卡片
2. **GTZ/DEP 图层接入** — 解决 ADU 判定的两个"取决于"条件

## Backlog（暂缓，待真实需求触发）

- **结构重构**（审查报告 C1-C5、D 类、F1）：拆 render.py、合并两份
  `_cached_get`、终端渲染函数化、bldgclass 字典补 D/G/H 段、批量模式复用
  浏览器实例。演示后进入扫街阶段、批量场景暴露瓶颈时再动——
  跑得好的东西不重构。
