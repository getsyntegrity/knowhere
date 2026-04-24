# verify-4 top_summary 入库修复验证

本文档记录 2026-04-24 本地按生产流程重跑后的验证结果，目标是确认 `document_top_summary` 已从解析阶段正确传递到 `document_chunks.chunk_metadata`，并进一步用于 `graph_nodes.properties.top_summary`，让 KG 导航真正使用我们约定的 non-LLM `top_summary` 逻辑。

## 本轮验证目标

- 修复 `kb_tasks` 中 `document_top_summary` 未成功注入 chunk metadata 的问题
- 确认 non-LLM 场景下的 `top_summary` 生成逻辑已真实进入生产链路
- 确认 `agent_navigate` 读取到的是新的 `GraphNode.top_summary`，而不是旧的标题拼接 fallback

## 根因结论

这次定位到的根因不是“字段注入后被数据库或发布链路弄丢”，而是更前面一层：

1. 生产解析阶段当时并不会在 `add_dir` 下预先产出 `hierarchy.json`
2. `kb_tasks` 在生成 `document_top_summary` 时调用 `load_navigation_top_summary(add_dir, source_file_name)`
3. 因为 `hierarchy.json` 不存在，`load_navigation_top_summary()` 返回空字符串
4. `document_top_summary` 因而根本没有注入到 chunk `metadata`
5. 后续 `graph_service` 只能继续走旧 fallback，用 section title 简单拼接 `top_summary`

## 修复内容

本次修复包含 3 个点：

1. 在 `apps/worker/app/services/connect_builder/summary_builder.py` 新增 `build_hierarchy_from_paths()` 和 `ensure_hierarchy_json()`，当解析器没有落 `hierarchy.json` 时，根据 chunk `path` 先物化一份层级树。
2. 在 `apps/worker/app/core/tasks/kb_tasks.py` 中，调用 `load_navigation_top_summary()` 前先执行 `ensure_hierarchy_json(...)`，再把生成出的 `document_top_summary` 注入每个 chunk 的 `metadata`。
3. 在 `packages/shared-python/shared/services/storage/zip_result_service.py` 中保留已有扩展 `metadata` 字段，避免生成 `chunks.json` 时把 `document_top_summary` 这类字段覆盖掉。

## 本轮生产流重跑

本轮继续使用你指定的 2 个 PDF，按完整生产链路执行：

- 清理 debug scope 数据
- 上传原始文件到本地 S3
- 创建 job / metadata
- 调 `kb_tasks._parse()`
- 生成结果包并上传
- `publish_document_state`
- `publish_document_graph`
- 执行 retrieval query，观察 KG 导航读取到的 `top_summary`

本轮实跑脚本：

```bash
uv run python debug_retrieval.py
```

## 关键验证结果

### 1. 结果包阶段已稳定生成 hierarchy

重跑日志中两份文档都出现了 `Added hierarchy.json` 和 `Added hierarchy_slim.json`，说明生产链路里现在已经有可供 `load_navigation_top_summary()` 读取的结构树。

### 2. chunk metadata 已真实写入 `document_top_summary`

重跑后直接查库，结果如下：

- `1_自主可控 寒武纪迎来放量周期.pdf`
  - `31 / 31` 个 chunks 都带有 `document_top_summary`
- `2_20250115-民生证券-民生证券利率专题：以史为鉴，牛尾还是牛市延续？.pdf`
  - `77 / 77` 个 chunks 都带有 `document_top_summary`

这说明这次不是“只在单个 chunk 上偶然成功”，而是整篇文档的所有 chunk 都拿到了统一的 document-level navigation summary。

### 3. GraphNode 已使用新的 top_summary

重跑后查 `graph_nodes`，两个 document node 上的 `properties.top_summary` 已与 chunk metadata 中的 `document_top_summary` 一致：

- `1_自主可控 寒武纪迎来放量周期.pdf`

```text
This document includes the following contents:
- 公司研究
  - 自主可控加强，寒武纪或迎来营收快速放量周期
- 相关研报
  - 要点
- 分析师声明
- 法律主体声明
- 特别声明
- 光大证券研究所
- 光大证券股份有限公司关联机构
  - 香港
  - 北京
  - 深圳
  - 英国
```

- `2_20250115-民生证券-民生证券利率专题：以史为鉴，牛尾还是牛市延续？.pdf`

```text
This document includes the following contents: - 1 复盘：牛市在交易什么？
```

这说明 KG 顶层导航现在拿到的已经不是旧的 section-title 拼接，而是新的 non-LLM `top_summary` 生成结果。

### 4. agent_navigate 已读到新的 top_summary

重跑日志里的 `Knowledge Map Overview` 已打印出新的 `top_summary`，例如第一篇文档展示为：

```text
This document includes the following contents:
- 公司研究
  - 自主可控加强，寒武纪或迎来营收快速放量周期
- 相关研报
  - 要点
...
```

这说明从：

`summary_builder` -> `kb_tasks` -> `document_chunks.chunk_metadata` -> `graph_service` -> `graph_nodes.properties.top_summary` -> `agent_navigate`

整条链已经打通。

## 补充测试

本轮还补了两个聚焦测试：

- `apps/worker/tests/tasks/test_kb_tasks.py`
  - 新增测试，验证解析阶段会补建 `hierarchy.json` 并注入 `document_top_summary`
- `packages/shared-python/shared/tests/test_atlas_image_packaging.py`
  - 验证 `ZipResultService` 不会覆盖已有扩展 metadata，`document_top_summary` 会保留在 `chunks.json`

执行结果：

- `uv run pytest tests/tasks/test_kb_tasks.py -k "document_top_summary or passes_chunks_directly"`：通过
- `pytest packages/shared-python/shared/tests/test_atlas_image_packaging.py -k "vector_images"`：通过

## 最终结论

这次修复后，`document_top_summary` 已经真实进入生产流程，并成功用于 KG 导航：

- 生产解析阶段现在能保证有 `hierarchy.json` 可读
- non-LLM `top_summary` 已成功注入每个 chunk 的 `metadata`
- document graph 发布时已优先读取该注入值
- `agent_navigate` 已开始消费新的 `GraphNode.top_summary`

也就是说，之前你指出的那个问题已经修复完成，KG 现在确实是在按我们前面约定的 `top_summary` 逻辑工作。
