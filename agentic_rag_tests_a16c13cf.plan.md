---
name: Agentic RAG Tests
overview: 针对你当前修改后的代码，测试重点应从旧的多轮 drill 模型切换到新的“一次展示 L1+L2，直接选择 section 并展开 leaf paths”的模型，同时验证生产发布链路不再静默产出空 nav_sections。
todos:
  - id: test-publish-contract
    content: 补并运行发布链路 contract 测试，覆盖 doc_nav、document_nav_sections、GraphNode.nav_sections
    status: pending
  - id: test-agentic-tools
    content: 补并运行 agentic tools 测试，覆盖 2-level nav 与 leaf path 展开
    status: pending
  - id: test-state-trace
    content: 补并运行状态机与 trace rollback 测试
    status: pending
  - id: test-e2e-debug
    content: 重新入库后用 debug_retrieval 验证生产入口和 agentic 本体路径一致
    status: pending
isProject: false
---

# Agentic RAG 测试方案

## 代码检查结论
- 当前 `kb_tasks.py` 已补 `json` 和 warning，但仍是局部修复：`_extract_nav_sections_for_publish()` 仍在 `kb_tasks.py` 内独立实现，和 `graph_builder.py` 的抽取逻辑没有统一。测试应先覆盖这个路径，避免后续再静默返回空。
- 当前 agentic 逻辑已改成 2-level 单次导航：`_load_nav_sections_2level()` 载入 L1 + L2，`nav_section_select()` 解析 `{path, confidence}`，不再使用 `drill/select` action，也不再返回 `need_deeper_drill`。测试预期要按这个新模型写。
- `trace.py` 已在异常后 rollback，需要测 flush 失败不会污染后续检索 session。
- `policy.py` 现在只要 `nav_drill_stack` 非空就执行 `NAV_SECTION_SELECT`，不再受 `max_path_expansions` 限制；这符合“一次导航”模型，但应显式测试避免循环。

## 阶段 1：发布链路单元/合约测试
- 覆盖 `doc_nav.json -> document_nav_sections`：构造含 `Root`、正常 section、`images`、`tables` 的 `doc_nav.json`，断言最终只发布业务 section。若当前设计仍允许 `images/tables`，需先确认这是否是新决策；按 `rag_plan.md` 应过滤。
- 覆盖异常可观测：损坏的 `doc_nav.json` 应产生 warning 且返回空；缺失文件可以安静返回空。重点是区分“正常无文件”和“文件损坏”。
- 覆盖 parse contract：`parse_task` 完成后断言 `document_chunks.chunk_metadata.document_top_summary` 和 `document_nav_sections` 均存在，`graph_nodes.properties.top_summary` 和 `nav_sections` 非空。
- 更新旧产物断言：contract test 不应继续要求 `hierarchy.json`，应改为验证 ZIP 内 `doc_nav.json`，并校验其 `sections/stats` 基本结构。

## 阶段 2：Agentic 工具测试
- `_load_nav_sections_2level()`：给 GraphNode 顶层 nav_sections 和 DocumentSection 子层数据，断言返回顺序为 L1 后接对应 L2，且每项带 `level=1/2`。
- `document_path_select()`：大文档且 GraphNode 有 nav_sections 时返回 `need_nav_drill`；小文档或无 nav_sections 时走 `_build_chunks_slim` 平铺选择。
- `nav_section_select()`：fake LLM 返回 L2 path 时，应展开该 section 下 leaf paths；fake LLM 返回 L1 path 时，应展开该 L1 下所有 descendant leaf paths；重复选择 parent+child 时 leaf paths 要去重。
- fallback：GraphNode 无 nav_sections 时，`nav_section_select()` 应回落到 chunks_slim，并返回可 hydrate 的 path。
- invalid path：LLM 返回不存在 path 时应拒绝，不应产生 selected_paths。

## 阶段 3：状态机与 trace 测试
- `AgentState.apply()`：`DOCUMENT_PATH_SELECT -> need_nav_drill` 后 stack 增加且 `pending_doc_index` 前进；`NAV_SECTION_SELECT -> selected_paths/no_confident_match/error` 后 stack 被 pop，保证不会循环。
- `RuleBasedPolicy`：当 stack 非空时优先 `NAV_SECTION_SELECT`；stack 清空后继续处理下一个 selected doc；`max_docs=0` 仍允许处理全部文档。
- `TraceRecorder`：mock `flush()` 抛异常，断言 `rollback()` 被调用，之后 agentic 工具仍可使用同一 session 查询。

## 阶段 4：本地端到端验证
- 启动本地 Postgres/Redis/LocalStack，清理 debug scope 后重新入库，不使用旧库里的历史数据。
- 入库后先查 DB：`document_chunks.chunk_metadata.document_nav_sections` 非空；`graph_nodes.properties.nav_sections` 非空；`chunks_count` 与 `document_chunks` 行数一致。
- 跑 `debug_retrieval.py` 的 agentic plan small/large/all：大于 30 chunks 的文档应出现 `document_path_select -> need_nav_drill -> nav_section_select -> selected_paths`；最终 router 为 `agentic` 且 results 非空。
- 跑生产入口模式：通过 `run_retrieval_query()` 并设置 `RETRIEVAL_AGENTIC_ENABLED=true`，确认生产入口和直接 `RetrievalAgent` 的 action/route 一致。

## 推荐执行顺序
1. 先跑发布链路 contract test，确认 nav_sections 能进 DB。
2. 再跑 agentic 工具测试，确认 2-level section 选择能正确展开 leaf paths。
3. 再跑状态机/trace 测试，确认不会循环且 trace 失败不污染 session。
4. 最后重新入库并跑本地端到端，确认实际文档能触发 `nav_section_select`。