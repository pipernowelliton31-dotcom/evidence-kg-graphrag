# Alignment 编号归属修复（2026-10-05）

已修复生产代码，并恢复 `kg_debug_run_q5q10_fix/work` 的实体映射、事实库和图谱。原始材料与八列表解析单元保持不变。

## 根因与证据

`kg_core._supported_inline_business_codes()` 原先扫描整个 evidence 文本中的“编号/编码/代码”等提示，然后把找到的所有编号赋给当前 mention。`accept_extractions()` 在模型省略 quote 时使用整个 `unit.content_md`，因此同页出现的产品、人物、版本都会继承本不属于自己的记录编号。

PDF 第16页提到 P03 的评审编号 `RV-2026-0412`，换行使规则只读到 `RV-2026`。周报自动生成器、AI简历优化工具、code-assist-pro、设计素材包V4、数据可视化插件五个不同产品都被补成 `inline_product_code=RV-2026`。PPT 中还出现了同类 `CHG-*`、`RV-*` 污染。

随后确定性预对齐按 `same_scoped_id` 合并不同产品；精确名称合并进一步将其他文档中的同名 mention 接入。最终 `entity_fd0fe0ba7cd2e4409e98` 包含106条 mention。该 ID 原本属于数据可视化插件簇；合并后 code-assist-pro 出现次数最多，于是成为显示名称。`build_graph()` 将所有成员名称和别名汇总，才产生了“设计素材包V4、周报工具是 P03 别名”的假象。这不是原始别名表声明，也不是八列表整体错位。

## 代码修复

- 自动生成的 inline code 必须同时出现在实体自身的名称或别名中，并得到 evidence 中完整 token 的支持。
- 使用 token 边界，避免 `AC-47` 与 `AC-470` 等部分匹配。
- 显式抽取的独立 identifier scope 保留；旧的自动 inline scope 中不符合归属规则的编号移除。
- 增加 `reset-alignment` 命令：先归档旧检查点，清理自动编号，清空旧对齐轮次和任务，生成新 fingerprint，并使旧事实库和图谱失效。保留解析单元及抽取的关系、断言。

## 本次数据恢复

清理55个自动编号，重新生成 alignment 任务。宿主助手核对名称、别名及源上下文，通过标准 `accept_alignment` 接口接受两轮决策；未调用外部模型 API。决策 JSON 保存在运行目录中，具体测试实体没有进入生产规则。

修复后独立的产品簇包括：

| 产品 | 修复后的实体 ID |
| --- | --- |
| code-assist-pro / AI代码助手插件 | entity_f85e36ae06194622425a |
| 设计素材包V4 | entity_2b1c07e4e52095848f4e |
| 周报自动生成器 / 周报工具 | entity_ee36a484283ea6068ae4 |
| 数据可视化插件 / 可视化插件 | entity_fd0fe0ba7cd2e4409e98 |

P03 的实体档案中不再包含设计素材包、周报工具、简历工具、可视化插件的别名。现有图谱保留 Cursor 的依赖/使用边和 GitHub Copilot 的开发使用、付费价值影响边；没有由错误实体合并产生的 P03–Figma AI / ChatGPT / DALL-E 3 边。

PDF 第6页表1还明确列出 `code-assist-pro` 的开发工具 `Cursor+Copilot`、维护工具 `Cursor`、运营工具 `Claude`。所以不能仅因 T2 的依赖产品列没有写 P03 就排除 Copilot 或 Claude。Claude 的运营关系在原抽取图谱中未形成边，本次没有人为补写抽取结果；该证据仍保存在原始解析单元中。

## 验证与使用

本次修复的 fingerprint 为 `run_57cc14c220fdec4b53e5`。修复图谱包含286个节点、432条边、1344条事实；完整性校验无错误或警告。原题 Q10 的检索恢复两页 T2，共8列、27行，context 中没有遗漏表格行。原始解析单元、抽取关系、断言均与备份一致。

详细校验数据：`kg_debug_run_q5q10_fix/alignment_repair_audit.json`。备份：`kg_debug_run_q5q10_fix/work/archive/alignment_reset_c56acbb99322983a2294`。

验证命令 `py -3.11 -m unittest discover -s skill/evidence-kg-builder/tests` 共32项，其中27项通过，5项可选 MarkItDown 测试因未安装该可选依赖而跳过；`py -3.11 -m unittest discover -s tests` 的21项全部通过。初次运行暴露了当前 Python 3.11 环境缺少 PDF/Notebook 依赖，补齐正式运行依赖、pandas 和 ipywidgets 后重新运行通过。

Notebook 查询入口已经验证会自动选中修复后的最新 native 图谱。已有 kernel 中的 `rag` / `retrieval` 仍可能持有旧对象，请重新运行 Cell 20，再运行 Cell 21；聊天入口可重新运行 Cell 24。没有重新调用最终回答模型，Notebook 中已显示的旧答案不会自动改写。

其他同 schema / engine version 的受污染检查点可使用：

```powershell
py -3.11 skill/evidence-kg-builder/scripts/kg_pipeline.py reset-alignment --work <work目录>
py -3.11 skill/evidence-kg-builder/scripts/kg_pipeline.py tasks --stage align --work <work目录> --limit 1000 --output <对齐任务.json>
# 由宿主模型或助手核对新任务，使用 accept --stage align 接收每轮响应。
py -3.11 skill/evidence-kg-builder/scripts/kg_pipeline.py build --work <work目录>
py -3.11 skill/evidence-kg-builder/scripts/kg_pipeline.py validate --work <work目录> --require-complete
```

`reset-alignment` 只恢复对齐阶段。若原始解析或语义抽取本身需要更改，应重新 parse/extract。
