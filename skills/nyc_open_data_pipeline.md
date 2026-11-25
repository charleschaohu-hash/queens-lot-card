# NYC Open Data 管线经验教训

数据管线里踩过/需要预防的坑，逐条更新。

## GeoSearch (geosearch.planninglabs.nyc)
- **BBL 必须从 `features[0].properties.addendum.pad.bbl` 取**。
  顶层的 `pad_bbl` 字段是 null，取它会拿到空值。
- BIN 同理在 `properties.addendum.pad.bin`。
- 同一 BBL 可能返回多个候选（不同 BIN）→ 用于"一地多楼"检测。
- 出现多个**不同 BBL** 的同置信度候选时，必须让用户选，不要默默取第一个。

## Socrata (data.cityofnewyork.us)
- **查询必加 `$limit`**，默认返回条数有限且不稳定，漏数据不报错。
- MapPLUTO 数据集 id：`64uk-42ks`，按 `$where=bbl='{BBL}'` 查询。
- 数值字段全部以字符串返回（如 `"2375"`），用前先转 float。
- PLUTO 版本号在记录的 `version` 字段，卡片脚注要引用。

## BIS / ACRIS
- **BIS、ACRIS 查询必须带 borough 参数**，否则跨区串数据。
- ACRIS 金额字段是 `document_amt`（不是 amount / doc_amount），字符串型。
- ACRIS 结果要**剔除 legacy 的 `FT_` / `BK_` 开头的 document_id**，
  它们是历史迁移数据，字段不全且金额不可信。查 Master 会查不到，
  但**数量本身是信号**（>0 = 产权历史久远，缩微胶卷时代）。

### ACRIS 三表实测记录（2026-07-25）
- **Legals `8h5j-fqxa`**：`$where=borough='4' AND block='4650' AND lot='25'`
  —— borough/block/lot 均为**无前导零的字符串**（"4"/"4650"/"25"，
  不是 "04650"）。⚠ 同一 document_id 会返回**多行重复**，必须去重
  （用 `$group=document_id` 或拿回来后 set 去重）。字段：document_id,
  record_type("L"), borough, block, lot, easement, partial_lot,
  property_type, street_number, street_name, good_through_date。
- **Master `bnx9-e6tj`**：字段 doc_type, document_date, document_amt,
  recorded_datetime, crfn, percent_trans。document_date 偶见缺失，
  回退用 recorded_datetime。
- **Parties `636b-3b5g`**：字段 party_type, name, address。
  **party_type 语义随 doc_type 变**："1"=转出方（DEED卖家/MTGE借款人/
  SAT原借款人），"2"=接收方（DEED买家/MTGE贷款人）。同一方可多行
  （ESTATE OF X 和 EXECUTOR 各一行）。
- **批量查询**：`$where=document_id in('id1','id2',...)`，实测每批 50 个
  id 稳定（GET URL 长度所限；再大建议 POST 或分批）。
- **SAT 配对坑**：SAT 可能解押的是 legacy（FT_）时代的抵押——
  出现"有 SAT 却无对应现代 MTGE"属正常（如 2013 SAT 对应 1987 FT_ 抵押），
  不要当异常。反向才是信号：MTGE 后无任何 SAT = 未解押。
- ZONE / DECL / CERT 类 $0 文书是分区声明/证明类，不是交易，
  不要混进成交价计算；DEED 里 <$10,000 的是名义转让（亲属过户等），
  单独归类不当成交价。
- **新分割子 lot 在 ACRIS 是空白**（实测：4/4650/26 切于 2025-10，
  legals 返回 `[]`）——历史文书全挂在母 lot 号下，直到分割后第一份
  新文书登记。管线做法：查无文书且 PLUTO `appbbl` 非空 → 自动回退
  查母地 BBL，卡片标注"以下为母地记录"。

## DOB 三源实测记录（2026-07-25）

### DOB NOW Job Application Filings `w9ak-ipjd`
- 参数：`borough='Queens'`（**首字母大写单词**，非数字非全大写）、
  `block='4650'` / `lot='25'`（**无前导零**）。也有现成 `bbl` 字段可用。
- 关键字段：job_filing_number, job_type, filing_status, filing_date,
  current_status_date, initial_cost, total_construction_floor_area,
  job_description, owner_s_business_name / owner_first+last_name,
  applicant_first+last_name, proposed_dwelling_units, proposed_no_of_stories。
- **job_filing_number 结构**：`Q01262008-I1`。`-` 前缀是项目主号；
  `-I1`=初始备案，`-P1/-P2...`=批后修改(PAA)，`-S1...`=子备案（围挡/
  SOE/接驳等）。聚合规则：按主号归组，主备案取 -I1，项目组当前状态取
  组内 current_status_date 最新那份 filing 的 filing_status。
- 实测见到的状态值：`Permit Entire`（许可全发）/ `Approved` /
  `Plan Examiner Review`（图审中）/ `LOC Issued`（完工信=完结）。
  三档映射常量见 src/dob.py（默认未知状态归"活跃"，宁严勿漏）。

### BIS `ipu4-2q9a` ——⚠ 名不副实
- 这个数据集实际是 **DOB Permit Issuance**（BIS 时代许可签发记录），
  不是 job filings（那是 ic3t-wcy2）。没有 job_status 字段，只有
  permit_status / filing_status。
- 参数：`borough='QUEENS'`（**全大写**）、`block='04650'` / `lot='00025'`
  （**5 位补零**）——和 DOB NOW 完全相反，三个数据源三种格式。

### DOB Job Application Filings `ic3t-wcy2`——BIS 工单表（2026-07-28 实测）
- 参数：`borough='QUEENS'`（**全大写**）、`block='04650'` / `lot='00025'`
  （**5 位补零**）——与 `ipu4-2q9a` 同格式，与 DOB NOW 相反。
- 关键字段：job__（工单号）、doc__（分册号，一 job 多 doc 行，**按 job__
  去重计数**）、job_type（**代码**：NB/DM/A1/A2/A3/SI/SC/PA/SG，
  SI=Subdivision Improved）、job_status + job_status_descrp（后者可读，如
  `PERMIT ISSUED - ENTIRE JOB/WORK` / `SIGNED OFF` / `COMPLETED` /
  `PLAN EXAM - DISAPPROVED`）、pre__filing_date / latest_action_date
  （**MM/DD/YYYY**）、initial_cost（**带 $ 和逗号的字符串** "$0.00"）、
  job_description、bin__。
- **⚠ BIS 与 DOB NOW 是不互数的双系统，核对必须分账**。铁证（17-08）：
  同一个开发项目，NB + 两个 DM 走 DOB NOW，而**分地文书（SI）和 BPP
  人行道（A3，job_description 明写 "IN CONJUNCTION WITH DOB
  JOB#Q01262008"）走 BIS**。BIS 页面的 jobs 数 ≠ DOB NOW filings 数，
  两边各对各的：卡片 DOB Summary 拆成 "Filings — DOB NOW" 与
  "Jobs — BIS" 两行。
- **与 `ipu4-2q9a`（许可签发）会撞 job 号**：同一 job 发过许可就两表都有。
  管线以工单表为准、许可表只补 ic3t 里没有的 job（防双计）。
- **老工单不销案就一直"活"**：BIS 时代 job 无人 sign off 的，status 停在
  PERMIT ISSUED / PLAN EXAM - APPROVED——按宁严勿漏归"活跃"。实测
  11 Center Dr 由此浮出 2013 年 NB 12,159 sqft 未销案 + SOE/围挡/BPP
  一串配套，正好解释其 14 条未结 ECB 与 $79,375 欠费（烂尾信号，
  对空地标的是重要画像）。

### 违规两表
- **DOB Violations `3h2n-5cm9`**：`boro='4'`（数字字符串）、
  block/lot **5 位补零**。未结判定：violation_category 含 `ACTIVE`
  （已结的是 `V*-DOB VIOLATION - DISMISSED`）。无金额字段。
- **ECB Violations `6bgk-3dad`**：`boro='4'`、block 5 位补零、
  ⚠ **lot 是 4 位补零**（'0025'，与 DOB 违规表不同！）。
  未结判定：ecb_violation_status='ACTIVE'；欠费字段 balance_due
  （另有 penality_imposed——注意官方拼写就是错的）。

### DOB Complaints Received `eabe-havv`（2026-07-28 实测）
- ⚠ **这张表没有 boro/block/lot 字段，只能按 `bin in('...')` 查**。
  DOB 四源里唯一一个 BIN-only 的表——管线必须先解析出 BIN 集合才能查投诉，
  这是它和违规两表的根本差异。
- 字段：complaint_number, status, date_entered, house_number, house_street,
  zip_code, bin, community_board, complaint_category, unit,
  disposition_date, disposition_code, inspection_date, dobrundate。
- **status 全库只有两个值**（实测 `$group=status`）：`ACTIVE`（21,076 条）/
  `CLOSED`（3,092,051 条）。未结判定就是 `status='ACTIVE'`，没有第三态。
- ⚠ **ACTIVE 的投诉照样可以有 disposition_date + disposition_code**——
  别拿"有处置日期"当已结的判据。实测 17-08（BIN 4105310）投诉 4A37298：
  status=ACTIVE，disposition_date=06/09/2026，disposition_code=**C1**，
  查代码表得 C1 = *"INSPECTOR UNABLE TO GAIN ACCESS - 1ST ATTEMPT"*
  ——进不了门，处置动作发生过但案子没了结，所以仍是 ACTIVE。合乎逻辑。
- **disposition_code 查 `6v9u-ndjg`**（Building Complaint Disposition Codes，
  两个字段 code / disposition）。**complaint_category 没有公开代码表**
  （实测 catalog 搜不到），只能拿到裸代码如 `4S`——别硬编造含义。
- 日期是 `MM/DD/YYYY` 字符串（和 ACRIS 的 ISO、DOB NOW 的 ISO 又不一样）。
- `dobrundate` 是全表快照时间戳（`20260727000000`），可当数据时效判据。

### BIN 解析规则（投诉查询与 BIS 链接的前置步骤）
- **GeoSearch 对空地 / 新分割 lot 只返回区级占位 BIN**，形如 `4000000`
  （区号 + 6 个 0）。实测 12 个地块里有 4 个中招：4044410060、4046500026、
  4049700011、4057590001。拿它去查投诉会串到全区，必须过滤。
  判据：7 位数字且不以 `000000` 结尾（`dob.is_real_bin`）。
- **真 BIN 从 DOB 四表里捞**：DOB NOW `bin`、BIS 许可 `bin__`、
  DOB 违规 `bin`、ECB 违规 `bin`。实测 4049700011 → GeoSearch 给 4000000，
  DOB 表给 **4112220**（与深挖报告一致）。
- **主 BIN 取序**：GeoSearch 首选结果的 BIN 优先，其次按 DOB 表出现顺序。
  一地多楼时次要 BIN（常见是车库，如 17-08 的 4481884）列为
  "additional structures"，不做主链接。

### ⚠ BIS 网页（a810-bisweb.nyc.gov）本机不可达
- 2026-07-28 实测：curl / playwright headless chromium / 真实 Chrome
  三种客户端一律返回 **403 Access Denied（Akamai）**，
  **连站点首页 `bisweb/bispi00.jsp` 都 403**——说明是整站级客户端封锁，
  不是某个 servlet 或参数格式的问题。
- 因此 `PropertyProfileOverviewServlet?bin=` 这个链接格式**无法在本机验证**，
  卡片按该格式输出，人工点开复核。若将来发现 BIN-only 被拒，回退式已备好：
  `?boro={1-5}&houseno={门牌}&street={街名, URL 编码}`
  （Queens 连字符门牌 `17-08` 原样传，不拆）——见 `dob.bis_url()`。

## Official verification URLs（2026-07-28 实测）

卡片各板块的官方核验链接模式。测法：curl 看 HTTP 码不够（SPA 假路径也
200），可用的都做了 playwright 渲染/内容抽查。

### ✅ 实测可用
- **ZoLa 地块页**：`zola.planning.nyc.gov/l/lot/{boro}/{block}/{lot}`
  （block/lot 无前导零，如 `/l/lot/4/4650/25`）。渲染验证：页面出现
  "17-08 149TH STREET, 11357"。挂身份/规矩/土地/潜力四板块。
- **ZR 条款页**：`zr.planning.nyc.gov/article-{i|ii}/chapter-{n}/{条款号}`。
  规律：12-xx → article-i/chapter-2；2X-YY → article-ii/chapter-X 的个位
  （22→ch2，23→ch3，25→ch5）。实测 23-11/23-21/22-121/22-122/12-10/
  25-232 全部 200。构造函数 `lot_card.zr_url()`。
- **ACRIS 文书直达**：`a836-acris.nyc.gov/DS/DocumentSearch/
  DocumentDetail?doc_id={document_id}`——**可以按 document_id 直达文书
  详情页**（实测 2025060900980001 返回带 DEED/当事人名的完整页面）。
  卡片 DEED/MTGE 行逐条挂链。检索入口 `/DS/DocumentSearch/Index` 也通。
- **DOF Property Information Portal**：`propertyinformationportal.nyc.gov/
  parcels/parcel/{十位BBL}`。渲染验证：出业主名 + 成交记录（连 DEED
  文书号都展示）。挂权属板块。⚠ 假 BBL 也返回 200 外壳，HTTP 码不能证真。
- **数据集目录页**：`data.cityofnewyork.us/d/{dataset_id}`（302 → 友好
  URL）。脚注静态挂 PLUTO/ACRIS×3/DOB NOW/Complaints/ECB 七个。

### ⚠ 本机 403，待人工浏览器验证（与 BIS 同封锁族）
- **DOB NOW Public Portal**：`a810-dobnow.nyc.gov/publish/Index.html`
  ——curl 与 playwright 均 403（Akamai）。卡片按官方入口格式输出 +
  "search BIN {bin}" 提示；**是否支持 BIN/job 号 deep link 无法测**，
  真浏览器里确认后若有 deep link 格式再升级。
- **DOB BIS**（前轮已记）：整站 403，`?bin=` 式待人工点测。

### 卡面展示约定
- 每板块尾一条灰字："Verify: {Name} ↗ · …"。
- 构造出的每地块 URL（ZoLa/PIP/ACRIS 入口/BIS/DOB NOW）在**首次出现**
  处附可见短 URL（PNG 不可点击，读者需要看得见的地址）；ZR 链接不附
  ——条款号本身即可检索的引用。

## 缓存约定（本项目）
- 原始 API 返回按 BBL 分文件夹存 `cache/{BBL}/`：
  `geosearch.json`、`pluto.json`、`acris_{legals,master,parties}.json`、
  `dob_{jobs,bis,violations,complaints}.json`、`ecb_violations.json`。
- `cache/address_index.json` 存地址 slug → BBL 映射，供重复查询命中缓存。
- `--fresh` 参数强制绕过缓存重抓。
