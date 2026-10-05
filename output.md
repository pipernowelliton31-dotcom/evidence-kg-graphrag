# Cell 22 多并发测试输出（10题）

来源：`evidence_kg_openrouter_debug.ipynb`，Cell 22（JSON 中第 46 个 cell），execution_count = 47。保存的 20 个输出包含完整运行日志和 10 题答案；

## 导出内容与来源

- [原始 cell source 与全部 MIME 输出](kg_debug_run_q5q10_fix/cell22_export/notebook_outputs.json)（含 Markdown、text/plain、stream）。
- [导出清单、图谱和检索代码 SHA-256](kg_debug_run_q5q10_fix/cell22_export/manifest.json)。
- 原始日志保存了 `plan`（intent）、`mode`（retrieval mode）、覆盖数量和耗时。这里的 mode 是检索模式，不是 Codex 的 Plan Mode。
- Notebook 没有保存运行时 `multi_results` 的完整 query_plan、stats、context，也没有保存模型的隐藏推理过程。下方完整检索详情是在同一图谱和当前代码上离线重算的结果，明确与原始输出区分；每题 JSON 还包含实际送入回答模型的检索上下文、事实、图路径和原始证据。

原始 Cell 23 的 [完整调用指标](kg_debug_run_q5q10_fix/openrouter_metrics.json) 包含此前多个阶段共 65 条请求。最后 10 条 QA 指标与 Cell 22 完成顺序及四舍五入后的耗时全部吻合，已作为辅助指标归入各题；原日志没有问题 ID。

## 原始运行摘要

| 题号 | plan / intent | mode | 耗时（秒） | 原始检索计数 | prompt tokens | completion tokens |
|---|---|---|---:|---|---:|---:|
| Q1 | causal | ranked | 51.5 | `structured=24 scope=0 augmentation=0 table_units=0 table_columns=0 table_rows=0/0 timeline=36/36 paths=6` | 6166 | 3547 |
| Q2 | cross_format_identity | ranked | 17.1 | `structured=24 scope=0 augmentation=0 table_units=0 table_columns=0 table_rows=0/0 timeline=0/0 paths=0` | 7496 | 843 |
| Q3 | factual | ranked | 17.7 | `structured=24 scope=0 augmentation=0 table_units=0 table_columns=0 table_rows=0/0 timeline=0/0 paths=6` | 7080 | 1130 |
| Q4 | structured_lookup | ranked | 22.5 | `structured=24 scope=0 augmentation=0 table_units=2 table_columns=7 table_rows=36/36 timeline=0/0 paths=6` | 7621 | 2222 |
| Q5 | structured_enumeration | exhaustive | 43.7 | `structured=8 scope=8 augmentation=6 table_units=0 table_columns=0 table_rows=0/0 timeline=0/0 paths=6` | 8491 | 2036 |
| Q6 | causal | ranked | 20.0 | `structured=24 scope=0 augmentation=0 table_units=0 table_columns=0 table_rows=0/0 timeline=0/0 paths=6` | 7144 | 1291 |
| Q7 | causal | ranked | 24.6 | `structured=24 scope=0 augmentation=0 table_units=0 table_columns=0 table_rows=0/0 timeline=0/0 paths=6` | 8408 | 1882 |
| Q8 | causal | ranked | 16.1 | `structured=24 scope=0 augmentation=0 table_units=0 table_columns=0 table_rows=0/0 timeline=0/0 paths=6` | 7448 | 684 |
| Q9 | comparison | ranked | 18.1 | `structured=24 scope=0 augmentation=0 table_units=0 table_columns=0 table_rows=0/0 timeline=0/0 paths=6` | 8038 | 792 |
| Q10 | structured_lookup | ranked | 48.6 | `structured=24 scope=0 augmentation=0 table_units=2 table_columns=8 table_rows=27/27 timeline=0/0 paths=6` | 7380 | 2568 |

## Cell 22 全部原始输出

<!-- Original output 1/20: stream -->

```text
[图谱] source=latest backend=native nodes=286 facts=1344 path=C:\Users\Agesen\Downloads\Task4\github-release\evidence-kg-graphrag\kg_debug_run_q5q10_fix\work
Q2 finished in 17.1s | plan=cross_format_identity mode=ranked structured=24 scope=0 augmentation=0 table_units=0 table_columns=0 table_rows=0/0 timeline=0/0 paths=0
Q3 finished in 17.7s | plan=factual mode=ranked structured=24 scope=0 augmentation=0 table_units=0 table_columns=0 table_rows=0/0 timeline=0/0 paths=6
Q4 finished in 22.5s | plan=structured_lookup mode=ranked structured=24 scope=0 augmentation=0 table_units=2 table_columns=7 table_rows=36/36 timeline=0/0 paths=6
Q6 finished in 20.0s | plan=causal mode=ranked structured=24 scope=0 augmentation=0 table_units=0 table_columns=0 table_rows=0/0 timeline=0/0 paths=6
Q7 finished in 24.6s | plan=causal mode=ranked structured=24 scope=0 augmentation=0 table_units=0 table_columns=0 table_rows=0/0 timeline=0/0 paths=6
Q1 finished in 51.5s | plan=causal mode=ranked structured=24 scope=0 augmentation=0 table_units=0 table_columns=0 table_rows=0/0 timeline=36/36 paths=6
Q8 finished in 16.1s | plan=causal mode=ranked structured=24 scope=0 augmentation=0 table_units=0 table_columns=0 table_rows=0/0 timeline=0/0 paths=6
Q5 finished in 43.7s | plan=structured_enumeration mode=exhaustive structured=8 scope=8 augmentation=6 table_units=0 table_columns=0 table_rows=0/0 timeline=0/0 paths=6
Q9 finished in 18.1s | plan=comparison mode=ranked structured=24 scope=0 augmentation=0 table_units=0 table_columns=0 table_rows=0/0 timeline=0/0 paths=6
Q10 finished in 48.6s | plan=structured_lookup mode=ranked structured=24 scope=0 augmentation=0 table_units=2 table_columns=8 table_rows=27/27 timeline=0/0 paths=6

==============================================================================================================
Q1: 2026年第二季度，明创工坊的明星产品"AI代码助手插件"季度收入从12.8万元降至9.1万元，下降29%。请按时间顺序列出Q2期间与该产品收入下降相关的全部变更事件，并说明每个事件与收入下降的因果关系。注意：相关线索分散在Excel（含隐藏的备注列）、Word、PDF、PPT等多种文档中，且该产品在不同文档中使用不同名称。
```

<!-- Original output 2/20: display_data -->

## 1. 结论
按时间顺序，相关事件为：①**2026-04-08** code-assist-pro（AI代码助手插件、P03）从免费增值模式改为订阅制，4月12日完成方案评审并落实到P03付费用户；订单归因显示该定价策略贡献Q2收入下降的**17%**。②**2026年5—6月** GitHub Copilot免费策略上线，先降低P03的付费价值，随后在6月分流用户；该事件进一步削弱付费转化，但材料未给出可与17%、12%相加的独立贡献比例。③**2026-05-06** Cursor v2发布并变更代码补全API接口签名，P03原有分析模块需要重写且无法正常发版，覆盖全部用户。④**2026-05-08** P03暂停v2.2并回退v2.1，但兼容问题仍在持续。⑤**2026-05-15** 启动紧急修复；5月6日至20日适配停更，已购用户投诉由45条/月升至128条/月。⑥**2026-05-20** Cursor v2.3发布并解决P03兼容问题，结束持续约两周的适配中断。订单归因显示工具升级兼容性问题贡献收入下降的**12%**。两项已量化贡献合计**29%**，与收入从12.8万元降至9.1万元、约下降28.9%相符；直接原因仍是**订阅制调整和Cursor升级兼容故障的双重影响**。

## 2. 推理路径
“AI代码助手插件” →（同一产品P03/code-assist-pro；来源：测试集A_工作室运营手册.docx，第2.1节；测试集A_产品规格与定价文档.pdf，第5、8、14—15页；测试集A_运营数据记录.xlsx，“产品变更记录”A15:I21；测试集A_产品运营分析报告.pptx，第2、3、6、7页）→ 2026-04-08定价调整 →（免费增值→订阅制，影响P03付费用户；来源：测试集A_工作室运营手册.docx，第2.1节；测试集A_运营数据记录.xlsx，“产品变更记录”A15:I15、A17:I17；测试集A_产品规格与定价文档.pdf，第5页）→ 订单归因定价策略对Q2收入下降贡献-17%（来源：测试集A_运营数据记录.xlsx，“订单明细”A80:J116）→ 2026年5月Copilot免费策略降低付费价值、2026年6月分流P03用户（来源：测试集A_运营数据记录.xlsx，“AI工具使用统计”A1:H26）→ 2026-05-06 Cursor v2接口变化 →（P03模块需重写、无法正常发版；来源：测试集A_产品规格与定价文档.pdf，第8、15页）→ 2026-05-08回退v2.1（来源：测试集A_产品运营分析报告.pptx，第7页；测试集A_运营数据记录.xlsx，“产品变更记录”A20:H20）→ 2026-05-15紧急修复但投诉增加、适配持续停更（来源：测试集A_产品运营分析报告.pptx，第7页；测试集A_运营数据记录.xlsx，“产品变更记录”A21:I21）→ 2026-05-20 v2.3解决兼容问题（来源：测试集A_产品运营分析报告.pptx，第7页）→ 订单归因兼容性问题贡献收入下降-12%（来源：测试集A_运营数据记录.xlsx，“订单明细”A80:J116）→ 收入记录为12.8万元降至9.1万元、续费率由82%降至63%（来源：测试集A_产品运营分析报告.pptx，第7页；测试集A_运营数据记录.xlsx，“收入与续费率统计”I19）。6月1日收入分析及6月25日季度复盘只是确认上述“双重影响”，没有形成新的独立原因事件（来源：测试集A_运营数据记录.xlsx，“产品变更记录”A26:I26、A31:H31）。

## 3. 不确定项
Copilot免费策略虽然被明确记录为降低付费价值并分流用户，但没有给出独立的收入下降贡献比例，不能确定它是否已部分包含在“定价策略-17%”中；此外，2026-06-15材料使用的是“记录日期”，且“Cursor v2.3于5月20日解决兼容问题”与“P03 v2.3于6月15日适配Cursor v2”可能分别指底层工具和插件版本，材料不足以把6月15日认定为收入下降原因。

<!-- Original output 3/20: stream -->

```text

==============================================================================================================
Q2: "AI代码助手插件"这一产品在PDF、Word、Excel、PPT、图片5种格式文档中分别使用了什么名称？每种格式中包含哪些仅在该格式中可见的独有信息？请逐一列出。
```

<!-- Original output 4/20: display_data -->

## 1. 结论
“AI代码助手插件”（实体：**code-assist-pro**）的跨格式名称及各自独有信息如下：

1. **PDF：`code-assist-pro`**  
   独有信息：**产品定价规格矩阵**。

2. **Word：`代码助手`**  
   独有信息：**兼容性问题与风险预警**，包括深度依赖 Cursor，以及 Cursor v2 升级造成的功能失效、发布受阻、用户体验下降和用户流失风险。

3. **Excel：`代码助手插件P03`**  
   独有信息：**收入和续费率数据**。

4. **PPT：`智能编程插件`**  
   独有信息：**迭代记录号 `IT-2026-008` 和评审编号 `RV-2026-0412`**。

5. **图片：`AI编程工具`**  
   独有信息：**产品架构图中的产品依赖关系和姊妹产品连线**。

## 2. 推理路径
- “AI代码助手插件” →（同一产品实体，标准名称）→ `code-assist-pro` →（5种跨格式别名绑定）→ PDF `code-assist-pro`、Word `代码助手`、Excel `代码助手插件P03`、PPT `智能编程插件`、图片 `AI编程工具`（来源：**测试集A_产品规格与定价文档.pdf**，第15页，表2，第2行各格式称呼列；**测试集A_工作室运营手册.docx**，“6. 产品名称对照表”，表2第2行）。
- `code-assist-pro` →（PDF独有）→ **定价规格矩阵**；→（Word独有）→ **兼容性问题与风险预警**；→（Excel独有）→ **收入和续费率数据**；→（PPT独有）→ **`IT-2026-008`、`RV-2026-0412`**；→（图片独有）→ **产品依赖关系及姊妹产品连线**（来源：**测试集A_产品规格与定价文档.pdf**，第16页，表9后的说明）。
- Word 独有风险的具体表现可由 Cursor v2 接口和补全机制变化、代码分析模块失效、无法正常发布更新及影响续费意愿等记录核实（来源：**测试集A_工作室运营手册.docx**，“3.2 产品兼容性与更新”，第24—39段）。
- Excel 的收入和续费率字段实际出现在“收入与续费率统计”Sheet，包含月收入、付费用户数、新增用户、流失用户、续费率和客单价（来源：**测试集A_运营数据记录.xlsx**，“收入与续费率统计”Sheet，第1—31行）。

## 3. 不确定项
无重要不确定项。

<!-- Original output 5/20: stream -->

```text

==============================================================================================================
Q3: 客户"程序员老王"购买了"AI代码助手插件"的年度订阅。请给出从该客户到产品收入下降的完整关联链路，包括：客户→产品→依赖的AI工具→定价策略变更→续费结果。标注每跳的信息来源。
```

<!-- Original output 6/20: display_data -->

## 1. 结论
现有证据无法完整证明“程序员老王购买 AI代码助手插件年度订阅”并形成一条逐跳可核验的“客户→产品→依赖的AI工具→定价策略变更→续费结果”链路。已能确认：AI代码助手插件（code-assist-pro，PPT称“智能编程插件”）收入在2026年Q2由12.8万元降至9.1万元，下降29%；2026年4月8日全局定价由“免费增值”改为“订阅制”，定价策略对收入下降贡献为-17%；产品开发主要依赖Cursor，辅以GitHub Copilot。材料只说明续费率下降、短期流失严重，未给出程序员老王个人续费结果或年度订阅续费金额。

## 2. 推理路径
- 客户“程序员老王” →(订单客户记录)→ 订单明细中的客户记录（来源：`测试集A_运营数据记录.xlsx`，`订单明细!G4、G19、G34、G49、G64`）；但当前提供的结构化证据未显示其中某一行同时满足“产品=AI代码助手插件”与“年度订阅”，因此不能据此确认题干中的购买事实。
- AI代码助手插件 →(同一产品的跨文档别名)→ code-assist-pro / 智能编程插件（来源：`测试集A_产品规格与定价文档.pdf`，第15页表2，第2行；`测试集A_产品运营分析报告.pptx`，第2张幻灯片）。
- AI代码助手插件 →(依赖/开发工具)→ Cursor为主力IDE，GitHub Copilot用于代码补全（来源：`测试集A_工作室运营手册.docx`，第1节“工作室简介”）。
- AI代码助手插件 →(定价变更影响)→ 2026年4月8日全局定价由免费增值改为订阅制（基础9.9元/月、高级29.9元/月）（来源：`测试集A_产品运营分析报告.pptx`，第2张幻灯片；`测试集A_运营数据记录.xlsx`，`订单明细!J33`）。
- 定价策略 →(收入下降归因)→ 产品Q2收入下降中贡献-17%；同期Cursor v1→v2升级造成兼容性问题、停更2周，兼容性因素贡献-12%（来源：`测试集A_产品运营分析报告.pptx`，第2张幻灯片；`测试集A_工作室运营手册.docx`，第2节“2.1 定价策略与AB实验”）。
- 定价策略/兼容性变化 →(续费表现)→ 续费率下降、短期流失严重（来源：`测试集A_产品运营分析报告.pptx`，第8张幻灯片）；但材料没有明确记录“程序员老王”是否续费。

## 3. 不确定项
“程序员老王”是否购买 AI代码助手插件年度订阅、对应订单编号及日期，以及其个人续费结果（续费/未续费、金额或时间）在当前证据中均未明确；因此无法可靠补出“客户→产品→AI工具→定价变更→该客户续费结果”的完整逐跳链路。

<!-- Original output 7/20: stream -->

```text

==============================================================================================================
Q4: PDF文档中的产品定价规格表（T1）在跨页续表中省略了"定价"和"适用平台"两列。对于续表中出现的产品，请说明如何通过其他文档（Word/Excel/PPT）还原这些缺失的定价和平台信息，并给出至少2个具体产品的还原路径。
```

<!-- Original output 8/20: display_data -->

## 1. 结论
现有结构化证据显示，PDF第5页续表实际上继承了第4页的7列表头，并未真正省略“定价”和“适用平台”：例如“code-assist-pro基础版”为9.9元/月、VSCode，“高级版”为29.9元/月、VSCode。若原PDF版面显示缺列，可先按产品族名称匹配：续表产品名 → PDF第4页同族产品 → 其他格式中的精确版本资料。例如，基础版和高级版均匹配到“code-assist-pro”产品族，由Word确认两档价格，再由该产品族在PDF首页表中的平台字段补出VSCode；Excel和PPT可用于交叉核验产品身份及使用场景，但不能单独替代价格或平台字段。

## 2. 推理路径
路径一：PDF第5页“code-assist-pro基础版” →(版本归入code-assist-pro产品族)→ Word《工作室运营手册》2.1“基础版9.9元/月” →(同族平台回填)→ PDF第4页code-assist-pro“适用平台=VSCode”，最终还原则定为“9.9元/月；VSCode”（来源：测试集A_产品规格与定价文档.pdf，第5页表1第3行、第4页表1第4行；测试集A_工作室运营手册.docx，2.1节）；Word 3.2及Excel“AI工具使用统计”Sheet A2:H6进一步表明该插件面向Cursor编程环境，用于身份和使用场景核验，但不把Cursor误写成表中的“适用平台”字段（来源：测试集A_工作室运营手册.docx，3.2节；测试集A_运营数据记录.xlsx，“AI工具使用统计”Sheet A2:H6）。路径二：PDF第5页“code-assist-pro高级版” →(版本归入同一产品族且备注明确“高级版”)→ Word《工作室运营手册》2.1“高级版29.9元/月” →(同族平台回填)→ PDF第4页code-assist-pro“适用平台=VSCode”，最终还原则定为“29.9元/月；VSCode”（来源：测试集A_产品规格与定价文档.pdf，第5页表1第4行、第4页表1第4行；测试集A_工作室运营手册.docx，2.1节）。PPT第8页仅记录该智能编程插件的迭代事项，不含这两项缺失字段，因此只能辅助确认产品记录范围，不能作为定价或平台来源（来源：测试集A_产品运营分析报告.pptx，第8页）。

## 3. 不确定项
Word和Excel没有直接给出“适用平台=VSCode”的字段值，该平台是依据续表版本与第4页code-assist-pro同族产品匹配回填；若原始PDF第5页确实在视觉上删除了两列，应保留这一回填来源，而不能声称VSCode由Word、Excel或PPT独立证明。

<!-- Original output 9/20: stream -->

```text

==============================================================================================================
Q5: Excel"订单明细"Sheet的备注列中隐藏了6条关键线索（分布在不同的行中）。请找出全部6条隐藏线索，并按时间顺序串联成一条完整的事件链，说明这些事件之间的因果关系。
```

<!-- Original output 10/20: display_data -->

## 1. 结论
6条线索按时间串联为：①新客户注册量首次突破日均50人（Q2前的业务增长信号）→ ②2026-04-08全局定价由免费增值改为订阅制，基础版9.9元/月、高级版29.9元/月 → ③2026-05-06 Cursor从v1升级至v2，导致 code-assist-pro（Excel称“代码助手插件P03”，PPT称“智能编程插件”）出现兼容性问题并停更适配 → ④2026-05-20完成v2.3修复，同时设计素材包V3停售并由V4替代、文案助手并入周报工具 → ⑤兼容问题期间客户投诉激增，工单由月均45条升至128条 → ⑥2026-06-01确认P03收入由12.8万元降至9.1万元、下降29%，归因为定价策略贡献-17%、工具升级兼容性问题贡献-12%。明确的因果主线是：Cursor升级 → 兼容性问题及停更 → 投诉增加和收入受损；定价策略调整则与兼容性问题共同造成P03收入下降29%。现有证据不能证明“新客户增长”直接导致定价调整，也不能证明5月20日的产品组合调整是收入下降原因。

## 2. 推理路径
新客户注册量首次突破日均50人（测试集A_运营数据记录.xlsx，订单明细，A8/J8） →（构成Q2调整前的业务增长背景，但不构成已证实因果）→ 2026-04-08全局定价策略从免费增值转为订阅制，基础版9.9元/月、高级版29.9元/月（测试集A_运营数据记录.xlsx，订单明细，J33；测试集A_产品运营分析报告.pptx，Slide 2） → 2026-05-06 Cursor v1→v2升级（测试集A_产品运营分析报告.pptx，Slide 6） →(引发) code-assist-pro兼容性问题及两周适配停更（测试集A_运营数据记录.xlsx，订单明细，J63；测试集A_产品运营分析报告.pptx，Slide 6） →(造成)客户投诉量激增，工单由月均45条增至128条（测试集A_运营数据记录.xlsx，订单明细，J93；测试集A_产品运营分析报告.pptx，Slide 6） →(表现为)2026-06-01 P03收入12.8万元降至9.1万元、下降29%（测试集A_产品运营分析报告.pptx，Slides 2、6） →(归因至)定价策略-17%、工具升级兼容性-12%（测试集A_运营数据记录.xlsx，订单明细，J108；测试集A_产品运营分析报告.pptx，Slide 2）。“设计素材包V3停售并由V4替代、文案助手并入周报工具”发生于2026-05-20（测试集A_运营数据记录.xlsx，订单明细，J78；测试集A_产品运营分析报告.pptx，Slide 2），与兼容问题最终修复同日，但材料未建立其与收入下降之间的因果关系。

## 3. 不确定项
当前抽取结果未提供第8行对应的确切订单日期，因此只能确认“日均50人”事件位于Q2事件链之前，无法给出其精确日期；Excel原始提取还将这些行标记为“Hidden=False”，这里的“隐藏线索”应理解为嵌在备注列中的关键信息，而非被Excel隐藏的行。

<!-- Original output 11/20: stream -->

```text

==============================================================================================================
Q6: "设计素材包V3"被"设计素材包V4"替代。请说明：(1)替代的原因是什么？(2)V4覆盖了V3的哪些内容？(3)V4上线后的用户评分反馈如何？(4)这个替代决策记录在哪些文档中？
```

<!-- Original output 12/20: display_data -->

## 1. 结论
2026年5月20日，设计素材包V3停售并由设计素材包V4替代。替代原因是V4功能全面升级，能够完整承接V3，并新增3D素材库120个、动效模板60个。V4覆盖V3的全部内容，同时增加了上述新内容。V4上线后的用户评分均分为3.2/5，主要反馈是稳定性问题较多；低于V3的4.0分，部分客户仍偏好V3，紧急修复已列入6月计划。替代决策记录在《测试集A_工作室运营手册.docx》《测试集A_运营数据记录.xlsx》《测试集A_产品规格与定价文档.pdf》《测试集A_产品运营分析报告.pptx》中；此外，《测试集A_产品架构图.png》也体现了这组替代关系。

## 2. 推理路径
设计素材包V3 →(停售并由其替代)→ 设计素材包V4（来源：测试集A_工作室运营手册.docx，“5. 产品迭代与维护/5.1 产品淘汰与替代”，第48—60段）→ V4覆盖V3全部内容，并新增3D素材库120个、动效模板60个、功能全面升级（同上）→ V4上线评分3.2/5、稳定性问题较多，而V3为4.0分、仍有部分客户偏好（同上）。产品规格文档进一步印证：V3于2026年5月20日停售，V4覆盖其全部内容，上线后评分3.2/5且稳定性问题较多（来源：测试集A_产品规格与定价文档.pdf，第6页）。Excel中的产品变更记录和订单备注均记录V3停售、由V4替代（来源：测试集A_运营数据记录.xlsx，“产品变更记录”Sheet，A1:I31；“订单明细”Sheet，J78）。PPT记录替代日期和替代关系（来源：测试集A_产品运营分析报告.pptx，第2页、第8页）；产品架构图也记录V3与V4的替代关系（来源：测试集A_产品架构图.png，整图）。

## 3. 不确定项
“文档”若仅指Word、Excel、PDF、PPT四类文件，则共有4份；将配套架构图也计入记录材料时，则共涉及5份材料。

<!-- Original output 13/20: stream -->

```text

==============================================================================================================
Q7: 2026年4月8日的定价策略变更（免费增值→订阅制）对哪些产品和客户影响最大？请列出受影响最大的3个产品及其影响数据，并说明哪些产品不受影响及原因。
```

<!-- Original output 14/20: display_data -->

## 1. 结论
按报告标注的Q2收入相对降幅，2026年4月8日定价变更后受影响最大的3个产品是：①**智能编程插件（code-assist-pro/P03）**：4—6月收入由12.5万元降至9.1万元，报告标注下降29%，6月续费率63%；其中定价变更与Cursor兼容问题形成双重影响。②**极简笔记**：收入由1.3万元降至1.0万元，下降23%，6月续费率79%。③**API接口测试工具**：收入由2.1万元降至1.7万元，下降19%，6月续费率85%。客户层面，智能编程插件用户受冲击最明显：新用户付费率由7.8%降至2.1%，老用户续费率由82%降至63%，分别下降5.7和19个百分点；报告将整体收入下降中的17个百分点归因于定价变更。**DL课程不受此次订阅制变更影响**，因为课程类维持一次买断、不纳入订阅制，续费率保持100%。

## 2. 推理路径
全局定价策略变更 →(发生于2026-04-08，免费增值改为订阅制，基础9.9元/月、高级29.9元/月)→ 订阅制产品（来源：测试集A_产品运营分析报告.pptx，Slide 2）→(报告判断“定价变更对订阅制产品影响最大”)→ 智能编程插件、极简笔记、API接口测试工具等出现较大收入下降（来源：测试集A_产品运营分析报告.pptx，Slide 4）→(按报告标注降幅29%＞23%＞19%)→ 智能编程插件＞极简笔记＞API接口测试工具（来源：测试集A_产品运营分析报告.pptx，Slide 4）。智能编程插件 →(同一产品别名)→ code-assist-pro/智能编程插件(P03) →(定价适配后，新用户付费率7.8%→2.1%、老用户续费率82%→63%)→ 新用户付费转化和老用户留存均明显受损（来源：测试集A_工作室运营手册.docx，第2.1节，段落9—19；测试集A_产品运营分析报告.pptx，Slide 2、4）。DL课程 →(风险预案规定课程类维持一次买断)→ 不纳入订阅制 →(续费率维持100%)→ 不受此次定价变更影响（来源：测试集A_产品运营分析报告.pptx，Slide 4、5；测试集A_运营数据记录.xlsx，“产品变更记录”Sheet，第18行F18）。

## 3. 不确定项
无重要不确定项。

<!-- Original output 15/20: stream -->

```text

==============================================================================================================
Q8: Cursor v3即将发布，"AI代码助手插件"面临什么风险？请根据Word文档中的风险预警说明，分析可能的影响路径和张明的应对建议。
```

<!-- Original output 16/20: display_data -->

## 1. 结论
Cursor v3预计于2026年Q3（9—10月）发布，可能再次调整API，AI代码助手插件（Word称“代码助手”、code-assist-pro）需要重新适配，预计周期为2—3周，风险评级为高。可能的影响路径是：版本接口变化 → 插件适配与停更 → 用户体验下降、续费意愿降低 → 续费率跌破50% → 产品面临持续收入风险，并可能需要调整产品方向。张明的应对建议是预留v3适配开发时间，并在v3 beta阶段提前完成适配，以压缩停更窗口并降低续费损失。

## 2. 推理路径
AI代码助手插件 →(深度依赖)→ Cursor编程环境（来源：测试集A_工作室运营手册.docx，§3.2，段落24—39）→(版本升级导致接口和补全机制变化)→ Cursor v2曾使代码分析模块失效（来源：测试集A_工作室运营手册.docx，§3.2，段落24—39）→(同类变化可能再次发生)→ Cursor v3可能变更API、插件需要再次适配（来源：测试集A_工作室运营手册.docx，§5.2，段落61—75）→(适配期间若再次停更)→ 续费率可能降至50%以下并形成持续收入风险（来源：测试集A_工作室运营手册.docx，§5.2，段落61—75）。张明负责该风险事项（来源：测试集A_运营数据记录.xlsx，“产品变更记录”Sheet第29行、H29）→(预留开发时间)→ 在Cursor v3 beta阶段提前适配，预计投入2—3周（来源：测试集A_工作室运营手册.docx，§5.2，段落61—75）。

## 3. 不确定项
Cursor v3的发布窗口及API变更幅度仍是预估，实际适配周期取决于最终变更范围；若2026年Q3续费率低于50%，文档仅明确提出应考虑调整产品方向，未给出具体调整方案。

<!-- Original output 17/20: stream -->

```text

==============================================================================================================
Q9: 编号"RV-2026-0412"在PPT中出现在两个不同的场景中。请说明这两个场景分别是什么，该编号被重复使用是否会造成歧义？在构建知识图谱时如何处理这种编号重复的情况？
```

<!-- Original output 18/20: display_data -->

## 1. 结论
编号“RV-2026-0412”被用于两个场景：一是2026年4月12日的“定价策略变更方案评审”，评审结论为有条件通过，关联变更编号为CHG-014；二是2026年5月25日的“设计素材包V4质量反馈处理单”。单独使用该编号会造成歧义，因为它不是唯一标识；但结合记录类型、日期和业务对象后可以区分。构建知识图谱时，应将两个业务实体分别建档，不按该编号合并；把“RV-2026-0412”建模为被多个实体复用的标识，并增加实体类型、日期及来源等限定，例如使用“评审编号:RV-2026-0412@2026-04-12”和“处理单编号:RV-2026-0412@2026-05-25”，同时保留 `reuses_identifier_of` 关系及证据来源。

## 2. 推理路径
“RV-2026-0412” →(评审编号)→“定价策略变更方案评审”，记录日期为2026-04-12、评审人为张明、关联变更为CHG-014（来源：测试集A_产品运营分析报告.pptx，Slide 7，Rounded Rectangle 4）→(评审对象)→“code-assist-pro/智能编程插件”。另一路径为“RV-2026-0412” →(处理单编号)→“设计素材包V4质量反馈处理单”，日期为2026-05-25（来源：测试集A_产品运营分析报告.pptx，Slide 7，Rounded Rectangle 4；Slide 8，TextBox 10）→(重复使用)→“定价策略变更评审”。Slide 8明确说明该编号用于定价策略变更评审，并指出同一编号在5月25日亦用于V4质量反馈处理单（来源：测试集A_产品运营分析报告.pptx，Slide 8，TextBox 10）；Slide 7的备注直接标明“编号重复使用”（来源：测试集A_产品运营分析报告.pptx，Slide 7，Rounded Rectangle 4）。因此，图谱应保留两个事件节点及其重复标识关系，而不是将二者错误合并。

## 3. 不确定项
“V4质量反馈处理单”与“设计素材包V4质量反馈处理单”在不同证据中的名称范围略有差异，材料未提供显式的别名绑定；这不影响“同一编号被两个场景复用”的结论，但若需严格确认处理单对应的完整产品名称，应进一步核验原始业务记录。

<!-- Original output 19/20: stream -->

```text

==============================================================================================================
Q10: PDF文档中的AI工具使用对照表（T2）的续表清空。请根据首页表头和续表数据，还原正确的列对应关系，并说明判断依据。同时，该表中哪些AI工具与"AI代码助手插件"存在直接或间接的关联？
```

<!-- Original output 20/20: display_data -->

## 1. 结论
T2续表应继续沿用首页的8列顺序：**工具名称｜用途分类｜主要使用场景｜调用频次/月｜月度成本｜版本｜依赖产品｜备注**。例如“Cursor月调用量—8万次—v2—v1→v2迁移后统计”分别落在第1、4、6、8列，其余列保留“—”；“162美元/月”落在第5列，“code-assist-pro”落在第7列。与“AI代码助手插件”（即 **code-assist-pro**）有关联的AI工具共有：**Cursor为直接关联，GitHub Copilot为间接关联**。其中“Cursor月调用量”和“Cursor v2适配进度”只是Cursor的统计或进度记录，“Copilot月调用量”和“Copilot免费政策”只是GitHub Copilot的统计或政策记录，不应算作独立工具。

## 2. 推理路径
T2首页表头 →(定义8列及顺序)→ 工具名称、用途分类、主要使用场景、调用频次/月、月度成本、版本、依赖产品、备注（来源：测试集A_产品规格与定价文档.pdf，第7页表1，表头/第2—15行）→(续表schema明确继承第7页表头)→ 第8页续表使用同一8列结构（来源：测试集A_产品规格与定价文档.pdf，第8页表1，TABLE_SCHEMA）→(数据位置交叉验证)→ “8万次”“3万次”“2千次”属于调用频次/月，“162美元/月”和“约18万元/月”属于月度成本，“v2/v1.5/v2024”属于版本，“v1→v2迁移后统计”“占支出35%”等属于备注（来源：同PDF第8页表1，第5—13行）。具体对应为：**Cursor月调用量—8万次—v2—v1→v2迁移后统计｜Copilot月调用量—3万次—v1.5—免费额50000次｜Figma AI月调用量—2千次—v1—设计素材V4开发｜Studio总成本统计—162美元/月—占支出35%｜Studio总收入统计—约18万元/月—Q2前约15万元/月｜Cursor v2适配进度—已完成2周—v2—code-assist-pro—5月20日恢复更新｜Copilot免费政策—50→200次/月—v1.5—影响P03付费价值｜Tool链覆盖率—18种—全产品线—编程3+设计3+文案2+其它10｜自动化节省工时—约80小时/月—Zapier+Make合计**（来源：同PDF第8页表1，第5—13行）。关联链为：**AI代码助手插件 →(别名)→ code-assist-pro**（来源：测试集A_产品规格与定价文档.pdf，第15页表2第2行；实体别名校验）→(依赖产品)→ **Cursor**（来源：同PDF第7页表1第2行、第8页表1第10行），因此是直接关联；**GitHub Copilot →(代码补全工具，且免费政策影响P03付费价值)→ P03/code-assist-pro**（来源：同PDF第7页表1第3行、第8页表1第6及11行；第15页表2第2行确认P03身份），因此属于间接关联。Excel记录还明确把GitHub Copilot的关联产品写为code-assist-pro（来源：测试集A_运营数据记录.xlsx，“AI工具使用统计”第11—12行，F11:F12）。

## 3. 不确定项
无重要不确定项。

## 每题完整 query plan 与统计（离线重算）

以下不是当时内存中 `multi_results` 的转储，也不是重新生成的回答。原始日志的 intent/mode 与重算结果逐题核对如下。

<details>
<summary>Q1：causal / ranked；与原日志一致：True</summary>


2026年第二季度，明创工坊的明星产品"AI代码助手插件"季度收入从12.8万元降至9.1万元，下降29%。请按时间顺序列出Q2期间与该产品收入下降相关的全部变更事件，并说明每个事件与收入下降的因果关系。注意：相关线索分散在Excel（含隐藏的备注列）、Word、PDF、PPT等多种文档中，且该产品在不同文档中使用不同名称。

[完整检索 JSON（含 context、事实、路径、证据）](kg_debug_run_q5q10_fix/cell22_export/Q01_retrieval.json)

```json
{
  "query_plan": {
    "intent": "causal",
    "structured": true,
    "cross_format_identity": false,
    "table_reconstruction": false,
    "retrieval_mode": "ranked",
    "requested_formats": [
      "pdf",
      "word",
      "excel",
      "ppt"
    ],
    "list_all": true,
    "causal": true,
    "comparison": false,
    "rank": false,
    "timeline": true,
    "expected_count": null,
    "sheet_hints": [],
    "column_hints": [
      "备注"
    ],
    "years": [
      "2026"
    ],
    "months": [],
    "quarters": [
      2
    ],
    "keywords": [
      "明星产品",
      "AI代码助手插件",
      "收入下降",
      "代码助手",
      "明创工坊",
      "ai",
      "12.8",
      "9.1",
      "q2",
      "excel",
      "word",
      "pdf",
      "ppt",
      "2026年第二季度",
      "明星产品\"AI代码助手插件\"季度收入",
      "12.8万元降至9.1万元",
      "下降29%",
      "按时间顺序",
      "Q2期间",
      "该产品收入下降相关",
      "变更事件",
      "每个事件",
      "关系",
      "注意",
      "相关线索分散",
      "Excel",
      "含隐藏",
      "备注列",
      "Word",
      "PDF",
      "PPT等多种文档",
      "且该产品",
      "不同文档",
      "使用不同名称"
    ],
    "relation_weights": {
      "reported_cause": 3.2,
      "has_observation": 1.8,
      "affects": 2.5,
      "depends_on": 1.3,
      "upgraded_to": 1.2,
      "replaced_by": 1.1
    }
  },
  "stats": {
    "structured": 24,
    "facts": 14,
    "seeds": 6,
    "profiles": 4,
    "paths": 6,
    "raw_units": 10,
    "timeline_events": 36,
    "retrieval_mode": "ranked",
    "table_units": 0,
    "table_rows": 0,
    "table_columns": 0,
    "structured_rows": 0,
    "structured_scope_matches": 0,
    "structured_selected_for_augmentation": 0,
    "timeline_context_events": 36,
    "timeline_context_events_omitted": 0,
    "table_context_rows": 0,
    "table_context_rows_omitted": 0
  },
  "qa_metrics_from_original_log": {
    "stage": "qa",
    "batch_index": 0,
    "tasks": 1,
    "attempt": 1,
    "status": "ok",
    "elapsed_s": 51.452,
    "prompt_tokens": 6166,
    "completion_tokens": 3547,
    "total_tokens": 9713,
    "cost": 0
  }
}
```

</details>

<details>
<summary>Q2：cross_format_identity / ranked；与原日志一致：True</summary>


"AI代码助手插件"这一产品在PDF、Word、Excel、PPT、图片5种格式文档中分别使用了什么名称？每种格式中包含哪些仅在该格式中可见的独有信息？请逐一列出。

[完整检索 JSON（含 context、事实、路径、证据）](kg_debug_run_q5q10_fix/cell22_export/Q02_retrieval.json)

```json
{
  "query_plan": {
    "intent": "cross_format_identity",
    "structured": false,
    "cross_format_identity": true,
    "table_reconstruction": false,
    "retrieval_mode": "ranked",
    "requested_formats": [
      "pdf",
      "word",
      "excel",
      "ppt",
      "image"
    ],
    "list_all": true,
    "causal": false,
    "comparison": true,
    "rank": false,
    "timeline": false,
    "expected_count": 5,
    "sheet_hints": [],
    "column_hints": [],
    "years": [],
    "months": [],
    "quarters": [],
    "keywords": [
      "AI代码助手插件",
      "代码助手",
      "ai",
      "pdf",
      "word",
      "excel",
      "ppt",
      "\"AI代码助手插件\"这一产品",
      "PDF",
      "Word",
      "Excel",
      "PPT",
      "图片5种格式文档",
      "分别使用",
      "什么名称？每种格式",
      "包含",
      "该格式",
      "可见",
      "独有信息？"
    ],
    "relation_weights": {}
  },
  "stats": {
    "structured": 24,
    "facts": 14,
    "seeds": 6,
    "profiles": 4,
    "paths": 0,
    "raw_units": 10,
    "timeline_events": 0,
    "retrieval_mode": "ranked",
    "table_units": 0,
    "table_rows": 0,
    "table_columns": 0,
    "structured_rows": 0,
    "structured_scope_matches": 0,
    "structured_selected_for_augmentation": 0,
    "timeline_context_events": 0,
    "timeline_context_events_omitted": 0,
    "table_context_rows": 0,
    "table_context_rows_omitted": 0
  },
  "qa_metrics_from_original_log": {
    "stage": "qa",
    "batch_index": 0,
    "tasks": 1,
    "attempt": 1,
    "status": "ok",
    "elapsed_s": 17.073,
    "prompt_tokens": 7496,
    "completion_tokens": 843,
    "total_tokens": 8339,
    "cost": 0
  }
}
```

</details>

<details>
<summary>Q3：factual / ranked；与原日志一致：True</summary>


客户"程序员老王"购买了"AI代码助手插件"的年度订阅。请给出从该客户到产品收入下降的完整关联链路，包括：客户→产品→依赖的AI工具→定价策略变更→续费结果。标注每跳的信息来源。

[完整检索 JSON（含 context、事实、路径、证据）](kg_debug_run_q5q10_fix/cell22_export/Q03_retrieval.json)

```json
{
  "query_plan": {
    "intent": "factual",
    "structured": false,
    "cross_format_identity": false,
    "table_reconstruction": false,
    "retrieval_mode": "ranked",
    "requested_formats": [],
    "list_all": false,
    "causal": false,
    "comparison": false,
    "rank": false,
    "timeline": false,
    "expected_count": null,
    "sheet_hints": [],
    "column_hints": [],
    "years": [],
    "months": [],
    "quarters": [],
    "keywords": [
      "定价策略变更",
      "AI代码助手插件",
      "收入下降",
      "定价策略",
      "程序员老王",
      "代码助手",
      "ai",
      "客户\"程序员老王\"购买",
      "\"AI代码助手插件\"",
      "年度订阅",
      "给出",
      "该客户",
      "产品收入下降",
      "完整关联链路",
      "包括",
      "客户→产品→依赖",
      "AI工具→定价策略变更→续费结果",
      "标注每跳",
      "信息来源"
    ],
    "relation_weights": {
      "depends_on": 2.0,
      "uses": 2.0,
      "has_observation": 2.0,
      "purchased": 2.0,
      "cites_data": 2.0
    }
  },
  "stats": {
    "structured": 24,
    "facts": 14,
    "seeds": 6,
    "profiles": 4,
    "paths": 6,
    "raw_units": 10,
    "timeline_events": 0,
    "retrieval_mode": "ranked",
    "table_units": 0,
    "table_rows": 0,
    "table_columns": 0,
    "structured_rows": 0,
    "structured_scope_matches": 0,
    "structured_selected_for_augmentation": 0,
    "timeline_context_events": 0,
    "timeline_context_events_omitted": 0,
    "table_context_rows": 0,
    "table_context_rows_omitted": 0
  },
  "qa_metrics_from_original_log": {
    "stage": "qa",
    "batch_index": 0,
    "tasks": 1,
    "attempt": 1,
    "status": "ok",
    "elapsed_s": 17.7,
    "prompt_tokens": 7080,
    "completion_tokens": 1130,
    "total_tokens": 8210,
    "cost": 0
  }
}
```

</details>

<details>
<summary>Q4：structured_lookup / ranked；与原日志一致：True</summary>


PDF文档中的产品定价规格表（T1）在跨页续表中省略了"定价"和"适用平台"两列。对于续表中出现的产品，请说明如何通过其他文档（Word/Excel/PPT）还原这些缺失的定价和平台信息，并给出至少2个具体产品的还原路径。

[完整检索 JSON（含 context、事实、路径、证据）](kg_debug_run_q5q10_fix/cell22_export/Q04_retrieval.json)

```json
{
  "query_plan": {
    "intent": "structured_lookup",
    "structured": true,
    "cross_format_identity": false,
    "table_reconstruction": true,
    "retrieval_mode": "ranked",
    "requested_formats": [
      "pdf",
      "word",
      "excel",
      "ppt"
    ],
    "list_all": false,
    "causal": false,
    "comparison": false,
    "rank": false,
    "timeline": false,
    "expected_count": 2,
    "sheet_hints": [],
    "column_hints": [],
    "years": [],
    "months": [],
    "quarters": [],
    "keywords": [
      "pdf",
      "t1",
      "word/excel/ppt",
      "PDF文档",
      "产品定价规格表",
      "T1",
      "跨页续表",
      "省略",
      "\"定价\"",
      "\"适用平台\"两列",
      "于续表",
      "出现",
      "产品",
      "如何通过其他文档",
      "Word/Excel/PPT",
      "还原这些缺失",
      "定价",
      "平台信息",
      "并给出至少2个具体产品",
      "还原路径"
    ],
    "relation_weights": {}
  },
  "stats": {
    "structured": 24,
    "facts": 14,
    "seeds": 6,
    "profiles": 4,
    "paths": 6,
    "raw_units": 10,
    "timeline_events": 0,
    "retrieval_mode": "ranked",
    "table_units": 2,
    "table_rows": 36,
    "table_columns": 7,
    "structured_rows": 0,
    "structured_scope_matches": 0,
    "structured_selected_for_augmentation": 0,
    "timeline_context_events": 0,
    "timeline_context_events_omitted": 0,
    "table_context_rows": 36,
    "table_context_rows_omitted": 0
  },
  "qa_metrics_from_original_log": {
    "stage": "qa",
    "batch_index": 0,
    "tasks": 1,
    "attempt": 1,
    "status": "ok",
    "elapsed_s": 22.537,
    "prompt_tokens": 7621,
    "completion_tokens": 2222,
    "total_tokens": 9843,
    "cost": 0
  }
}
```

</details>

<details>
<summary>Q5：structured_enumeration / exhaustive；与原日志一致：True</summary>


Excel"订单明细"Sheet的备注列中隐藏了6条关键线索（分布在不同的行中）。请找出全部6条隐藏线索，并按时间顺序串联成一条完整的事件链，说明这些事件之间的因果关系。

[完整检索 JSON（含 context、事实、路径、证据）](kg_debug_run_q5q10_fix/cell22_export/Q05_retrieval.json)

```json
{
  "query_plan": {
    "intent": "structured_enumeration",
    "structured": true,
    "cross_format_identity": false,
    "table_reconstruction": false,
    "retrieval_mode": "exhaustive",
    "requested_formats": [
      "excel"
    ],
    "list_all": true,
    "causal": true,
    "comparison": false,
    "rank": false,
    "timeline": true,
    "expected_count": 6,
    "sheet_hints": [
      "订单明细"
    ],
    "column_hints": [
      "备注"
    ],
    "years": [],
    "months": [],
    "quarters": [],
    "keywords": [
      "excel",
      "Excel\"订单明细\"",
      "备注列",
      "隐藏",
      "6条关键线索",
      "分布",
      "不同",
      "6条隐藏线索",
      "并按时间顺序串联成一条完整",
      "事件链",
      "这些事件之间",
      "关系"
    ],
    "relation_weights": {
      "reported_cause": 3.2,
      "purchased": 2.0,
      "affects": 2.5,
      "has_observation": 1.8,
      "depends_on": 1.3,
      "upgraded_to": 1.2,
      "replaced_by": 1.1
    }
  },
  "stats": {
    "structured": 8,
    "facts": 14,
    "seeds": 6,
    "profiles": 4,
    "paths": 6,
    "raw_units": 10,
    "timeline_events": 0,
    "retrieval_mode": "exhaustive",
    "table_units": 0,
    "table_rows": 0,
    "table_columns": 0,
    "structured_rows": 0,
    "structured_scope_matches": 8,
    "structured_selected_for_augmentation": 6,
    "timeline_context_events": 0,
    "timeline_context_events_omitted": 0,
    "table_context_rows": 0,
    "table_context_rows_omitted": 0
  },
  "qa_metrics_from_original_log": {
    "stage": "qa",
    "batch_index": 0,
    "tasks": 1,
    "attempt": 1,
    "status": "ok",
    "elapsed_s": 43.688,
    "prompt_tokens": 8491,
    "completion_tokens": 2036,
    "total_tokens": 10527,
    "cost": 0
  }
}
```

</details>

<details>
<summary>Q6：causal / ranked；与原日志一致：True</summary>


"设计素材包V3"被"设计素材包V4"替代。请说明：(1)替代的原因是什么？(2)V4覆盖了V3的哪些内容？(3)V4上线后的用户评分反馈如何？(4)这个替代决策记录在哪些文档中？

[完整检索 JSON（含 context、事实、路径、证据）](kg_debug_run_q5q10_fix/cell22_export/Q06_retrieval.json)

```json
{
  "query_plan": {
    "intent": "causal",
    "structured": false,
    "cross_format_identity": false,
    "table_reconstruction": false,
    "retrieval_mode": "ranked",
    "requested_formats": [],
    "list_all": true,
    "causal": true,
    "comparison": false,
    "rank": false,
    "timeline": false,
    "expected_count": null,
    "sheet_hints": [],
    "column_hints": [],
    "years": [],
    "months": [],
    "quarters": [],
    "keywords": [
      "V3",
      "设计素材包V4",
      "V4",
      "素材包",
      "设计素材包",
      "素材包V3",
      "素材包V4",
      "设计素材包V3",
      "v3",
      "v4",
      "\"设计素材包V3\"被\"设计素材包V4\"替代",
      "替代",
      "什么？",
      "V4覆盖",
      "容？",
      "V4上线后",
      "用户评分反馈如何？",
      "这个替代决策记录",
      "文档"
    ],
    "relation_weights": {
      "reported_cause": 3.2,
      "has_observation": 1.8,
      "has_feedback": 2.0,
      "replaced_by": 1.1,
      "affects": 2.5,
      "depends_on": 1.3,
      "upgraded_to": 1.2
    }
  },
  "stats": {
    "structured": 24,
    "facts": 14,
    "seeds": 6,
    "profiles": 4,
    "paths": 6,
    "raw_units": 10,
    "timeline_events": 0,
    "retrieval_mode": "ranked",
    "table_units": 0,
    "table_rows": 0,
    "table_columns": 0,
    "structured_rows": 0,
    "structured_scope_matches": 0,
    "structured_selected_for_augmentation": 0,
    "timeline_context_events": 0,
    "timeline_context_events_omitted": 0,
    "table_context_rows": 0,
    "table_context_rows_omitted": 0
  },
  "qa_metrics_from_original_log": {
    "stage": "qa",
    "batch_index": 0,
    "tasks": 1,
    "attempt": 1,
    "status": "ok",
    "elapsed_s": 19.983,
    "prompt_tokens": 7144,
    "completion_tokens": 1291,
    "total_tokens": 8435,
    "cost": 0
  }
}
```

</details>

<details>
<summary>Q7：causal / ranked；与原日志一致：True</summary>


2026年4月8日的定价策略变更（免费增值→订阅制）对哪些产品和客户影响最大？请列出受影响最大的3个产品及其影响数据，并说明哪些产品不受影响及原因。

[完整检索 JSON（含 context、事实、路径、证据）](kg_debug_run_q5q10_fix/cell22_export/Q07_retrieval.json)

```json
{
  "query_plan": {
    "intent": "causal",
    "structured": false,
    "cross_format_identity": false,
    "table_reconstruction": false,
    "retrieval_mode": "ranked",
    "requested_formats": [],
    "list_all": true,
    "causal": true,
    "comparison": false,
    "rank": true,
    "timeline": false,
    "expected_count": 3,
    "sheet_hints": [],
    "column_hints": [],
    "years": [
      "2026"
    ],
    "months": [
      4
    ],
    "quarters": [],
    "keywords": [
      "定价策略变更",
      "定价策略",
      "2026年4月8日",
      "免费增值→订阅制",
      "产品",
      "客户",
      "最大？",
      "最大",
      "3个产品",
      "数据",
      "产品不受"
    ],
    "relation_weights": {
      "reported_cause": 3.2,
      "affects": 2.5,
      "purchased": 2.0,
      "cites_data": 2.0,
      "has_observation": 1.8,
      "depends_on": 1.3,
      "upgraded_to": 1.2,
      "replaced_by": 1.1
    }
  },
  "stats": {
    "structured": 24,
    "facts": 14,
    "seeds": 6,
    "profiles": 4,
    "paths": 6,
    "raw_units": 10,
    "timeline_events": 0,
    "retrieval_mode": "ranked",
    "table_units": 0,
    "table_rows": 0,
    "table_columns": 0,
    "structured_rows": 0,
    "structured_scope_matches": 0,
    "structured_selected_for_augmentation": 0,
    "timeline_context_events": 0,
    "timeline_context_events_omitted": 0,
    "table_context_rows": 0,
    "table_context_rows_omitted": 0
  },
  "qa_metrics_from_original_log": {
    "stage": "qa",
    "batch_index": 0,
    "tasks": 1,
    "attempt": 1,
    "status": "ok",
    "elapsed_s": 24.611,
    "prompt_tokens": 8408,
    "completion_tokens": 1882,
    "total_tokens": 10290,
    "cost": 0
  }
}
```

</details>

<details>
<summary>Q8：causal / ranked；与原日志一致：True</summary>


Cursor v3即将发布，"AI代码助手插件"面临什么风险？请根据Word文档中的风险预警说明，分析可能的影响路径和张明的应对建议。

[完整检索 JSON（含 context、事实、路径、证据）](kg_debug_run_q5q10_fix/cell22_export/Q08_retrieval.json)

```json
{
  "query_plan": {
    "intent": "causal",
    "structured": false,
    "cross_format_identity": false,
    "table_reconstruction": false,
    "retrieval_mode": "ranked",
    "requested_formats": [
      "word"
    ],
    "list_all": false,
    "causal": true,
    "comparison": false,
    "rank": false,
    "timeline": false,
    "expected_count": null,
    "sheet_hints": [],
    "column_hints": [],
    "years": [],
    "months": [],
    "quarters": [],
    "keywords": [
      "Cursor v3",
      "张明",
      "AI代码助手插件",
      "代码助手",
      "cursor",
      "v3",
      "ai",
      "word",
      "Cursor",
      "v3即将发布",
      "\"AI代码助手插件\"面临什么风险？",
      "根据Word文档",
      "风险预警",
      "可能",
      "路径",
      "建议"
    ],
    "relation_weights": {
      "affects": 2.5,
      "reported_cause": 3.2,
      "has_observation": 1.8,
      "depends_on": 1.3,
      "upgraded_to": 1.2,
      "replaced_by": 1.1
    }
  },
  "stats": {
    "structured": 24,
    "facts": 14,
    "seeds": 6,
    "profiles": 4,
    "paths": 6,
    "raw_units": 10,
    "timeline_events": 0,
    "retrieval_mode": "ranked",
    "table_units": 0,
    "table_rows": 0,
    "table_columns": 0,
    "structured_rows": 0,
    "structured_scope_matches": 0,
    "structured_selected_for_augmentation": 0,
    "timeline_context_events": 0,
    "timeline_context_events_omitted": 0,
    "table_context_rows": 0,
    "table_context_rows_omitted": 0
  },
  "qa_metrics_from_original_log": {
    "stage": "qa",
    "batch_index": 0,
    "tasks": 1,
    "attempt": 1,
    "status": "ok",
    "elapsed_s": 16.088,
    "prompt_tokens": 7448,
    "completion_tokens": 684,
    "total_tokens": 8132,
    "cost": 0
  }
}
```

</details>

<details>
<summary>Q9：comparison / ranked；与原日志一致：True</summary>


编号"RV-2026-0412"在PPT中出现在两个不同的场景中。请说明这两个场景分别是什么，该编号被重复使用是否会造成歧义？在构建知识图谱时如何处理这种编号重复的情况？

[完整检索 JSON（含 context、事实、路径、证据）](kg_debug_run_q5q10_fix/cell22_export/Q09_retrieval.json)

```json
{
  "query_plan": {
    "intent": "comparison",
    "structured": false,
    "cross_format_identity": false,
    "table_reconstruction": false,
    "retrieval_mode": "ranked",
    "requested_formats": [
      "ppt"
    ],
    "list_all": false,
    "causal": false,
    "comparison": true,
    "rank": false,
    "timeline": false,
    "expected_count": null,
    "sheet_hints": [],
    "column_hints": [],
    "years": [
      "2026"
    ],
    "months": [],
    "quarters": [],
    "keywords": [
      "rv-2026-0412",
      "ppt",
      "编号\"RV-2026-0412\"",
      "PPT",
      "出现",
      "两个不同",
      "场景",
      "这两个场景分别",
      "该编号被重复使用",
      "否会造成歧义？",
      "构建知识图谱时如何处理这种编号重复",
      "情况？"
    ],
    "relation_weights": {}
  },
  "stats": {
    "structured": 24,
    "facts": 14,
    "seeds": 6,
    "profiles": 4,
    "paths": 6,
    "raw_units": 10,
    "timeline_events": 0,
    "retrieval_mode": "ranked",
    "table_units": 0,
    "table_rows": 0,
    "table_columns": 0,
    "structured_rows": 0,
    "structured_scope_matches": 0,
    "structured_selected_for_augmentation": 0,
    "timeline_context_events": 0,
    "timeline_context_events_omitted": 0,
    "table_context_rows": 0,
    "table_context_rows_omitted": 0
  },
  "qa_metrics_from_original_log": {
    "stage": "qa",
    "batch_index": 0,
    "tasks": 1,
    "attempt": 1,
    "status": "ok",
    "elapsed_s": 18.149,
    "prompt_tokens": 8038,
    "completion_tokens": 792,
    "total_tokens": 8830,
    "cost": 0
  }
}
```

</details>

<details>
<summary>Q10：structured_lookup / ranked；与原日志一致：True</summary>


PDF文档中的AI工具使用对照表（T2）的续表清空。请根据首页表头和续表数据，还原正确的列对应关系，并说明判断依据。同时，该表中哪些AI工具与"AI代码助手插件"存在直接或间接的关联？

[完整检索 JSON（含 context、事实、路径、证据）](kg_debug_run_q5q10_fix/cell22_export/Q10_retrieval.json)

```json
{
  "query_plan": {
    "intent": "structured_lookup",
    "structured": true,
    "cross_format_identity": false,
    "table_reconstruction": true,
    "retrieval_mode": "ranked",
    "requested_formats": [
      "pdf"
    ],
    "list_all": true,
    "causal": false,
    "comparison": false,
    "rank": false,
    "timeline": false,
    "expected_count": null,
    "sheet_hints": [],
    "column_hints": [],
    "years": [],
    "months": [],
    "quarters": [],
    "keywords": [
      "AI代码助手插件",
      "代码助手",
      "pdf",
      "ai",
      "t2",
      "PDF文档",
      "AI工具使用",
      "照表",
      "T2",
      "续表清空",
      "根据首页表头",
      "续表数据",
      "还原正确",
      "应关系",
      "判断依据",
      "同时",
      "该表",
      "AI工具",
      "\"AI代码助手插件\"存",
      "直接或间接",
      "关联？"
    ],
    "relation_weights": {
      "uses": 2.0,
      "cites_data": 2.0
    }
  },
  "stats": {
    "structured": 24,
    "facts": 14,
    "seeds": 6,
    "profiles": 4,
    "paths": 6,
    "raw_units": 10,
    "timeline_events": 0,
    "retrieval_mode": "ranked",
    "table_units": 2,
    "table_rows": 27,
    "table_columns": 8,
    "structured_rows": 20,
    "structured_scope_matches": 0,
    "structured_selected_for_augmentation": 0,
    "timeline_context_events": 0,
    "timeline_context_events_omitted": 0,
    "table_context_rows": 27,
    "table_context_rows_omitted": 0
  },
  "qa_metrics_from_original_log": {
    "stage": "qa",
    "batch_index": 0,
    "tasks": 1,
    "attempt": 1,
    "status": "ok",
    "elapsed_s": 48.638,
    "prompt_tokens": 7380,
    "completion_tokens": 2568,
    "total_tokens": 9948,
    "cost": 0
  }
}
```

</details>
