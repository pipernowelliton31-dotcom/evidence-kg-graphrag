# 本地验证记录

本地验证开始于 **2026-10-03**，发布整理完成于 **2026-10-04**。这里记录功能、完整性和运行情况，不是官方准确率评分。

## 环境与验证范围

- Windows / Python 3.11；Skill engine 4.0.0，schema 1.3。
- MarkItDown 0.1.8；原生依赖版本与 Skill 清单一致。
- 本地真实模型：`stealth/space-bunny-alpha`；三个阶段 reasoning 均为 `medium`。
- 五份 Test A corpus、一份 questions；问题集从未作为事实来源。
- 原生路线复用已完成的知识库，重新验证完整性并调用 API 回答前三题。
- MarkItDown 路线重新执行解析、prepare、语义抽取、对齐、建图、完整性校验及前三题回答。
- Teleagent 原生调用：**未测试**。

## 测试与检查

| 检查 | 结果 |
| --- | --- |
| 原有 Skill 回归 | 4/4 通过 |
| 新解析路线回归 | 6/6 通过，包括实际 Office 转换、原生结构保留、缓存失效与隔离、转换失败、缺失依赖 |
| 原有交互入口回归 | 4/4 通过，包括冷启动、图谱复用、检查点恢复与模型失败 |
| 新建虚拟环境安装 | 默认运行 + Notebook 安装成功；可选 MarkItDown 安装成功 |
| 新环境 Notebook | 两路配置、依赖、材料角色、parse 和 prepare 均通过 |
| 新环境预生成知识库 | Q1–Q3 检索均成功，context 不超过 18,000 字符 |
| 代码保留 | 原生解析、核心 pipeline、GraphRAG、导出脚本及默认 requirements 与来源逐字节一致 |
| Notebook 发布清理 | 所有代码输出清空，execution_count 为空 |
| 正式依赖安装链 | 7 项直接依赖、13 项必要传递依赖，无 Notebook / 测试 / 开发工具链 |

未装 MarkItDown 的默认环境中，5 个依赖转换的测试按设计跳过，缺失可选依赖的 CLI 测试仍通过；安装可选依赖后全部 14 项测试通过。

一次可选依赖安装遇到 PyPI TLS 连接 EOF；随后 Notebook 的标准 pip 安装成功。未关闭证书校验，也未修改依赖版本。

## 两路构建结果

| 指标 | 原生示例知识库 | 本次 MarkItDown 重建 |
| --- | ---: | ---: |
| DocumentUnits | 57 | 57 |
| 节点 | 273 | 224 |
| 边 | 414 | 349 |
| 事实 | 1,285 | 1,143 |
| 来源证据 | 506 | 511 |
| 保留 unresolved | 1 | 10 |
| pending extraction | 0 | 0 |
| parse failures | 0 | 0 |
| alignment stopped | true | true |
| 完整性校验 | 通过 | 通过 |

`unresolved` 以 warning 保留，不等于结构校验失败。两次模型运行具有随机性，阅读视图也有差异；数量差异不能直接证明哪条路线质量更高。当前未针对这批回答进行人工逐事实评分，不声称问题线索全部召回或答案完全正确。

## API 问答记录

| 路线 | 问题 | 请求耗时（秒） | total tokens | 回答字符数 |
| --- | --- | ---: | ---: | ---: |
| native | Q1 | 18.424 | 8517 | 1273 |
| native | Q2 | 12.193 | 8396 | 932 |
| native | Q3 | 12.558 | 8023 | 910 |
| markitdown | Q1 | 32.564 | 9436 | 1867 |
| markitdown | Q2 | 13.658 | 8522 | 1011 |
| markitdown | Q3 | 22.777 | 8316 | 1065 |

回答正文保存于 [native](../examples/results/native) 与 [markitdown](../examples/results/markitdown)，包括原始问题、结论、推理路径与不确定项。详细检索 context 在本地 `runs/<route>/qa/Q*.json`，不随全部运行日志上传。

## MarkItDown 完整重建的调用统计

| 阶段 | 成功请求 | total tokens | 阶段墙钟时间（秒） |
| --- | ---: | ---: | ---: |
| extraction | 14 | 121,475 | 135.732 |
| alignment | 17 | 222,930 | 70.882 |

QA 两路共 6 个请求，51,210 total tokens。服务本次返回的 `cost` 为 0；这仅表示本次响应值，不代表模型未来免费。重试前的失败尝试可能不在成功请求汇总中。

请求并发执行，因此各请求耗时相加不能作为阶段墙钟耗时。结构统计与调用细节的精选机器可读结果见 [validation_summary.json](validation_summary.json)。

## 复验命令

从仓库根目录执行，先安装相应依赖：

```powershell
$python = ".\.venv\Scripts\python.exe"
& $python -m unittest discover -s .\skill\evidence-kg-builder\tests -v
& $python -m unittest discover -s .\tests -v
& $python .\skill\evidence-kg-builder\scripts\kg_pipeline.py validate --graph .\examples\prebuilt\work\04_knowledge_graph.json --require-complete
```

本次本地完整 MarkItDown 检查点在 `runs/markitdown/work`；Notebook 新环境检查点在 `kg_debug_run/work` 和 `kg_debug_run/work_markitdown`。这些目录被忽略，可在本机进一步检查；远端首次运行按 README 重建。
