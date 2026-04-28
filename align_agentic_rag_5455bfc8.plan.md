---
name: Align Agentic RAG
overview: 对照 `/Users/wuchengke/Desktop/rag_plan.md`，当前不进入 `nav_section_select` 的直接原因是生产发布链路没有把 `document_nav_sections` 注入到 chunk metadata，导致 GraphNode 的 `nav_sections` 为空；同时测试入口和生产入口还有几处不一致。
todos:
  - id: fix-kb-nav-injection
    content: 根治 doc_nav 发布链路：统一抽取入口、去重实现、禁止静默失败
    status: pending
  - id: update-contract-tests
    content: 更新 contract test，覆盖 doc_nav 和 GraphNode.nav_sections
    status: pending
  - id: fix-agentic-state
    content: 修复 mixed select/drill 的状态迁移
    status: pending
  - id: align-debug-production
    content: 让 debug 脚本可走真实生产 retrieval 入口
    status: pending
isProject: false
---

# 修正 Agentic RAG 生产与测试一致性

## 已定位的不一致
- 生产发布根因不是“少一个 import”本身，而是 **doc_nav section 抽取逻辑散落在多处、异常被静默吞掉、发布链路没有不变量校验**。[`/Users/wuchengke/Desktop/knowhere/knowhereapi-main/apps/worker/app/core/tasks/kb_tasks.py`](/Users/wuchengke/Desktop/knowhere/knowhereapi-main/apps/worker/app/core/tasks/kb_tasks.py) 的 `_extract_nav_sections_for_publish()` 与 [`/Users/wuchengke/Desktop/knowhere/knowhereapi-main/apps/worker/app/services/connect_builder/graph_builder.py`](/Users/wuchengke/Desktop/knowhere/knowhereapi-main/apps/worker/app/services/connect_builder/graph_builder.py) 的 `_extract_nav_sections_from_kb()` 重复实现同一规则，但行为不完全受测试约束；其中 `kb_tasks.py` 当前异常会退化为 `[]`，最终让 [`/Users/wuchengke/Desktop/knowhere/knowhereapi-main/packages/shared-python/shared/services/retrieval/graph_service.py`](/Users/wuchengke/Desktop/knowhere/knowhereapi-main/packages/shared-python/shared/services/retrieval/graph_service.py) 写出空 `GraphNode.properties.nav_sections`。
- 生产写入链路和计划描述存在偏差：`graph_builder.py` 已把 `nav_sections` 写进 `knowledge_graph.json` 的 `files[*]`，但真实 DB GraphNode 发布并不读取该 JSON，而是从 `DocumentChunk.chunk_metadata.document_nav_sections` 提取。这条 metadata 注入链路必须和 `knowledge_graph.json` 使用同一个 doc_nav 抽取 helper，避免两套规则继续漂移。
- Agentic 混合 select+drill 逻辑不完整：[`types.py`](/Users/wuchengke/Desktop/knowhere/knowhereapi-main/packages/shared-python/shared/services/retrieval/agentic/types.py) 的 `AgentState.apply(NAV_SECTION_SELECT)` 只处理 `selected_paths` 和 `need_deeper_drill`，没有处理 [`tools.py`](/Users/wuchengke/Desktop/knowhere/knowhereapi-main/packages/shared-python/shared/services/retrieval/agentic/tools.py) 返回的 `pending_drill_entries`，会丢掉同一层里“部分 select、部分 drill”的后续钻取。
- Policy 与计划略不一致：[`policy.py`](/Users/wuchengke/Desktop/knowhere/knowhereapi-main/packages/shared-python/shared/services/retrieval/agentic/policy.py) 没有计划里的 `need_more_paths` 分支；如果仍需要兼容旧状态，应补上。
- Trace “best-effort” 实现不安全：[`trace.py`](/Users/wuchengke/Desktop/knowhere/knowhereapi-main/packages/shared-python/shared/services/retrieval/agentic/trace.py) 的 `create_run()` flush 失败后不 rollback，缺少 `retrieval_runs` 表时会污染同一个 session，导致后续 retrieval 全失败。
- 测试入口与生产入口不完全一致：[`debug_retrieval.py`](/Users/wuchengke/Desktop/knowhere/knowhereapi-main/apps/worker/debug_retrieval.py) 的 `agentic_plan` 直接调用 `RetrievalAgent`，而生产 [`app_service.py`](/Users/wuchengke/Desktop/knowhere/knowhereapi-main/packages/shared-python/shared/services/retrieval/app_service.py) 只有 `RETRIEVAL_AGENTIC_ENABLED=true` 且非 small-KB shortcut 时才走它。
- 合约测试仍有旧产物假设：[`test_parse_task_contract.py`](/Users/wuchengke/Desktop/knowhere/knowhereapi-main/apps/worker/tests/contract/test_parse_task_contract.py) 仍读取/断言 `hierarchy.json`，且没有断言 `doc_nav.json`、`document_nav_sections`、`GraphNode.properties.nav_sections`，和 `rag_plan.md` 的“doc_nav 是唯一导航结构”不一致。

## 建议修复顺序
1. 建立单一 doc_nav 发布 helper：在 `summary_builder.py` 或新的相邻模块中提供 `extract_nav_sections_for_publish(file_dir) -> list[dict]`，统一处理 `root/__root__/images/tables` 过滤、字段裁剪、summary 截断、`chunk_count`/`children_count` 规范化。`kb_tasks.py` 和 `graph_builder.py` 都调用这个 helper，不再各自读 JSON、各自维护过滤规则。
2. 让发布链路失败可见：`kb_tasks.py` 不再用裸 `except Exception: return []` 静默吞掉 doc_nav 解析错误。对于“文件不存在”可返回空并打 debug；对于 JSON 解析错误或结构异常要 warning 并带上 `job_id/add_dir/source_file_name` 上下文。这样不会因为单个文档阻断整条 parse，但也不会把数据损坏伪装成正常空 nav。
3. 在发布阶段校验关键不变量：当文档 `chunks_count > CHUNK_COUNT_THRESHOLD` 且 `doc_nav.json` 存在时，`document_nav_sections` 为空应打明确 warning；`GraphNode.properties.nav_sections` 仍由 `graph_service.py` 写入，但输入必须来自统一 helper 注入的 chunk metadata。
4. 补发布链路测试：在 contract test 里断言 chunk metadata 含 `document_nav_sections`，GraphNode properties 含非空 `nav_sections`，ZIP 含 `doc_nav.json`；移除旧 `hierarchy.json` 断言，避免测试继续认可旧导航产物。
5. 修 agentic 状态机：让 `AgentState.apply()` 在 `selected_paths` 状态下同时消费 `pending_drill_entries`，保证混合 select/drill 不丢栈。
6. 补 policy 兼容分支：按 plan 加回 `need_more_paths -> DOCUMENT_PATH_SELECT`，除非确认该状态已废弃。
7. 修 trace 安全性：`TraceRecorder.create_run()` / `complete()` 捕获 DB 异常后对 session rollback，或默认关闭 trace 直到迁移可用。
8. 调整调试入口：让 `debug_retrieval.py` 增加“生产入口模式”，通过 `run_retrieval_query()` + `RETRIEVAL_AGENTIC_ENABLED=true` 验证真实路由；保留直接 `RetrievalAgent` 模式作为单元化 agentic 本体测试。

## 验证目标
- 重新入库后，`document_chunks.chunk_metadata.document_nav_sections` 非空。
- `graph_nodes.properties.nav_sections` 非空，`chunks_count > 30` 文档触发 `document_path_select -> need_nav_drill -> nav_section_select`。
- 小文档 `chunks_count <= 30` 仍走 `document_path_select` 平铺选择。
- 生产入口和 debug 入口在同一数据上报告一致的 action/route。