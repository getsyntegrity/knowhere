# Retrieval Parity 验证结果（BM25 + 统一分词）

本文档基于 2026-04-23 18:12 左右的真实跑数日志 `docs/verify-2.log`，目标是验证这次 Retrieval Parity 改造后的 3 个关键点：

1. `PATH` / `CONTENT` 两个 channel 在**无向量**前提下已经能正常工作，且打分来自应用层 BM25。
2. 中英混合 query 能走统一 tokenizer，中文 token 不丢失。
3. `TERM` / KG GREP discovery 已复用统一 token 逻辑，英文 stopword 不再参与 token 命中。

## 运行基线

| 项 | 值 |
|----|----|
| 原始日志 | `docs/verify-2.log` |
| 用户 / 命名空间 | `local-dev-user` / `default` |
| top_k | `10` |
| data_type | `1` |
| 文档 | `doc_debug_ret_01` Atlas 手册；`doc_debug_ret_02` mock_welding_guide |
| 跨文档边 | `1` 条，`weight=0.9552` |

本轮实际跑的 3 条 query：

1. `Welding Processes TIG parameters`
2. `Atlas handbook 不锈钢 welding parameters`
3. `the stainless steel welding parameters`

ingest 基线正常，且跨文档边仍存在：

```24:40:docs/verify-2.log
2026-04-23 18:12:24.480 | INFO     | debug_retrieval:ingest_to_db:215 -   📊 INGEST 结果统计（所有 debug 文档）
...
2026-04-23 18:12:24.481 | INFO     | debug_retrieval:ingest_to_db:225 -       document_chunks        │    152 rows
...
2026-04-23 18:12:24.483 | INFO     | debug_retrieval:ingest_to_db:225 -       document_chunks        │     10 rows
...
2026-04-23 18:12:24.483 | INFO     | debug_retrieval:ingest_to_db:237 -   跨文档 edges（user=local-dev-user, ns=default）: 1 条
2026-04-23 18:12:24.483 | INFO     | debug_retrieval:ingest_to_db:239 -     doc:doc_debug_ret_02  <->  doc:doc_debug_ret_01  weight=0.9552  shared=['austenitic', 'corrosion', 'grade', 'grades', 'high', 'resistance', 'stainless', 'steel', 'steels']
```

## 自动测试

本次代码改造后，我先跑了两组聚焦测试：

- `packages/shared-python/shared/tests/test_retrieval_channels.py`：`6 passed`
- `packages/shared-python/shared/tests/test_retrieval_app_service.py`：`23 passed`

它们覆盖了：

- `PATH/CONTENT` 的应用层 BM25 排序
- mixed-language tokenizer
- `TERM` stopwords 去噪
- KG GREP discovery 复用统一 token 逻辑
- retrieval app service 的主流程回归

## Query 1：`Welding Processes TIG parameters`

### 1.1 结论

这是一个**路径导向** query。结果表明：

- `path_channel`、`content_channel`、`term_channel` 三个 channel 全部命中
- `path_channel` 和 `content_channel` 的分数已经是 **BM25 风格的小数分**，不再是之前 fallback 的简单整数重叠计数
- RRF 后 Top1 直接变成 `Welding Processes / TIG`
- Agent 先选中 `mock_welding_guide`，再通过 GREP 把 Atlas 拉回导航范围

### 1.2 底层发现证据

```48:96:docs/verify-2.log
2026-04-23 18:12:24.529 | INFO     | debug_retrieval:run_queries:281 -   Query 1/3: "Welding Processes TIG parameters"  [data_type=1]
...
  📡 path_channel: 19 rows in 55ms
2026-04-23 18:12:24.607 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:843 -     [0] score=6.8409  path=Welding Processes / TIG  type=text
...
  📡 content_channel: 20 rows in 10ms
2026-04-23 18:12:24.617 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:858 -     [0] score=5.2703  path=Welding Processes / TIG  content=Gas Tungsten Arc Welding (GTAW, also known as TIG) produces high quality welds o
...
  📡 term_channel: 20 rows in 7ms
...
  🔀 RRF Fusion: 10 rows from 3 channels (weights={'path': 1.0, 'content': 2.0, 'term': 1.5})
2026-04-23 18:12:24.624 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:901 -     [0] rrf_score=0.0734  path=Welding Processes / TIG
2026-04-23 18:12:24.624 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:901 -     [1] rrf_score=0.0714  path=Welding Processes / MIG
```

### 1.3 KG 导航证据

```113:181:docs/verify-2.log
2026-04-23 18:12:25.755 | INFO     | shared.services.retrieval.agent_navigate:agent_navigate:519 -   LLM raw response: ["doc_debug_ret_02"]
...
2026-04-23 18:12:25.756 | INFO     | shared.services.retrieval.agent_navigate:_grep_discover_document_ids:343 -   GREP tokenized units (cap 8): ['welding', 'processes', 'tig', 'parameters']  (total=4)
2026-04-23 18:12:25.775 | INFO     | shared.services.retrieval.agent_navigate:agent_navigate:547 -   GREP hit document_ids: ['doc_debug_ret_01', 'doc_debug_ret_02']
2026-04-23 18:12:25.775 | INFO     | shared.services.retrieval.agent_navigate:agent_navigate:555 -   ✅ GREP added 1 new documents
...
2026-04-23 18:12:26.539 | INFO     | shared.services.retrieval.agent_navigate:agent_navigate:636 -   LLM raw response: ["Welding Processes / TIG", "tables / table-1 welding-params.html"]
...
2026-04-23 18:12:27.360 | INFO     | shared.services.retrieval.agent_navigate:agent_navigate:636 -   LLM raw response: ["FABRICATION / Welding"]
...
2026-04-23 18:12:27.361 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:941 -     agent_paths=3, discovery_paths=10, new_paths=1
2026-04-23 18:12:27.361 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:945 -       → tables / table-1 welding-params.html
```

### 1.4 最终结果

最终 `router=discovery+agent`，Top10 中前几名已经明显是焊接工艺相关路径：

```190:240:docs/verify-2.log
2026-04-23 18:12:27.637 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:1035 -   ✅ RETRIEVAL COMPLETE: 10 results | router=discovery+agent | 3108ms
...
2026-04-23 18:12:27.637 | INFO     | debug_retrieval:run_queries:308 -   [ 1] type=text   score=0.0734
       path: Welding Processes / TIG
       file: mock_welding_guide
...
2026-04-23 18:12:27.637 | INFO     | debug_retrieval:run_queries:308 -   [ 2] type=text   score=0.0714
       path: Welding Processes / MIG
       file: mock_welding_guide
...
2026-04-23 18:12:27.637 | INFO     | debug_retrieval:run_queries:308 -   [ 3] type=text   score=0.0702
       path: FABRICATION / Welding / Austenitic Stainless Steels
       file: EN_Atlas Technical Handbook rev Aug 2013.pdf
```

## Query 2：`Atlas handbook 不锈钢 welding parameters`

### 2.1 结论

这是一个**中英混合** query。结果表明：

- `GREP tokenized units` 中保留了 `不锈钢`
- `PATH/CONTENT/TERM` 三通道全部命中
- `path_channel` 更偏路径和章节名，`content_channel` 更偏正文和工艺说明
- Agent 直接选中两篇文档，最终把 mock_welding_guide 里的多个具体焊接路径补进并集

### 2.2 底层发现证据

```260:294:docs/verify-2.log
  📡 path_channel: 20 rows in 16ms
2026-04-23 18:12:27.657 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:843 -     [0] score=5.4745  path=FABRICATION / Welding  type=text
2026-04-23 18:12:27.657 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:843 -     [1] score=5.2784  path=FABRICATION / Welding / Welding Dissimilar Metals  type=text
...
  📡 content_channel: 20 rows in 13ms
2026-04-23 18:12:27.670 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:858 -     [0] score=5.4139  path=Final Cleaning  content=Final cleaning and passivation of stainless steel welds is essential. Remove wel
2026-04-23 18:12:27.670 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:858 -     [2] score=3.3605  path=Introduction  content=This mock welding guide describes common arc welding processes used on stainless
...
  📡 term_channel: 20 rows in 9ms
...
  🔀 RRF Fusion: 10 rows from 3 channels (weights={'path': 1.0, 'content': 2.0, 'term': 1.5})
2026-04-23 18:12:27.679 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:901 -     [0] rrf_score=0.0689  path=FABRICATION / Welding
```

### 2.3 统一分词与导航证据

```311:320:docs/verify-2.log
2026-04-23 18:12:28.968 | INFO     | shared.services.retrieval.agent_navigate:agent_navigate:519 -   LLM raw response: ["doc_debug_ret_01", "doc_debug_ret_02"]
...
2026-04-23 18:12:28.969 | INFO     | shared.services.retrieval.agent_navigate:_grep_discover_document_ids:343 -   GREP tokenized units (cap 8): ['atlas', 'handbook', '不锈钢', 'welding', 'parameters']  (total=5)
2026-04-23 18:12:28.981 | INFO     | shared.services.retrieval.agent_navigate:agent_navigate:547 -   GREP hit document_ids: ['doc_debug_ret_01', 'doc_debug_ret_02']
```

### 2.4 Agent 选 path 与最终并集

```365:405:docs/verify-2.log
2026-04-23 18:12:32.877 | INFO     | shared.services.retrieval.agent_navigate:agent_navigate:636 -   LLM raw response: ["tables / table-1 welding-params.html", "Welding Processes / SMAW", "Welding Processes / TIG", "Welding Processes / MIG", "Introduction", "Filler Metals", "Sensitization Control", "Pre-weld Preparation", "Post-weld Treatment", "Final Cleaning"]
...
2026-04-23 18:12:32.879 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:941 -     agent_paths=11, discovery_paths=10, new_paths=9
2026-04-23 18:12:32.879 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:945 -       → tables / table-1 welding-params.html
2026-04-23 18:12:32.880 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:945 -       → Welding Processes / TIG
2026-04-23 18:12:32.880 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:945 -       → Final Cleaning
```

### 2.5 最终结果

最终仍是 `router=discovery+agent`。Top10 仍以 Atlas 的焊接总览为主，但 mock_welding_guide 的 `Final Cleaning` 和焊接表格已经进入最终结果：

```413:466:docs/verify-2.log
2026-04-23 18:12:32.907 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:1035 -   ✅ RETRIEVAL COMPLETE: 10 results | router=discovery+agent | 5269ms
...
2026-04-23 18:12:33.023 | INFO     | debug_retrieval:run_queries:308 -   [ 1] type=text   score=0.0689
       path: FABRICATION / Welding
       file: EN_Atlas Technical Handbook rev Aug 2013.pdf
...
2026-04-23 18:12:33.023 | INFO     | debug_retrieval:run_queries:308 -   [ 9] type=table  score=0.0462
       path: Root
       file: EN_Atlas Technical Handbook rev Aug 2013.pdf
...
2026-04-23 18:12:33.023 | INFO     | debug_retrieval:run_queries:308 -   [10] type=text   score=0.0458
       path: Final Cleaning
       file: mock_welding_guide
```

## Query 3：`the stainless steel welding parameters`

### 3.1 结论

这是一个**带英文 stopword** 的 query。结果表明：

- 统一 token 逻辑没有把 `the` 带进 GREP token 列表
- 三通道仍全部命中
- 最终结果聚焦到焊接、污染控制、选材等不锈钢焊接相关章节，没有因为 `the` 这种虚词造成额外噪音

### 3.2 stopword 过滤证据

```533:541:docs/verify-2.log
2026-04-23 18:12:34.363 | INFO     | shared.services.retrieval.agent_navigate:agent_navigate:519 -   LLM raw response: ["doc_debug_ret_02", "doc_debug_ret_01"]
...
2026-04-23 18:12:34.364 | INFO     | shared.services.retrieval.agent_navigate:_grep_discover_document_ids:343 -   GREP tokenized units (cap 8): ['stainless', 'steel', 'welding', 'parameters']  (total=4)
2026-04-23 18:12:34.373 | INFO     | shared.services.retrieval.agent_navigate:agent_navigate:547 -   GREP hit document_ids: ['doc_debug_ret_01', 'doc_debug_ret_02']
```

这里能直接看到 `the` 已经不在 token 列表里。

### 3.3 底层发现证据

```486:515:docs/verify-2.log
  📡 path_channel: 20 rows in 16ms
2026-04-23 18:12:33.042 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:843 -     [0] score=4.8950  path=DESIGN CONSIDERATIONS IN FABRICATION OF STAINLESS STEELS / Specific Design Points - To Retain Corrosion Resistance / 13. Welding Mild Steel to Stainless Steel  type=text
...
  📡 content_channel: 20 rows in 12ms
2026-04-23 18:12:33.055 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:858 -     [0] score=6.6060  path=SURFACE FINISHING / Electropolishing  content=Electropolishing is an electrochemical process which brightens the steel surface
2026-04-23 18:12:33.055 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:858 -     [1] score=5.5819  path=DESIGN CONSIDERATIONS IN FABRICATION OF STAINLESS STEELS / Specific Design Points - To Retain Corrosion Resistance / 13. Welding Mild Steel to Stainless Steel  content=Mixed-metal welding can be satisfactory, generally using an over-alloyed welding
...
  📡 term_channel: 20 rows in 8ms
...
  🔀 RRF Fusion: 10 rows from 3 channels (weights={'path': 1.0, 'content': 2.0, 'term': 1.5})
```

### 3.4 最终结果

最终 Top10 主要落在 Atlas 的焊接、污染控制、设计与腐蚀相关章节，说明 stopword 被剔除后，query 仍然能稳定聚焦到有效主题词：

```625:678:docs/verify-2.log
2026-04-23 18:12:39.468 | INFO     | shared.services.retrieval.app_service:run_retrieval_query:1035 -   ✅ RETRIEVAL COMPLETE: 10 results | router=discovery+agent | 6444ms
...
2026-04-23 18:12:39.468 | INFO     | debug_retrieval:run_queries:308 -   [ 1] type=text   score=0.0660
       path: FABRICATION / Welding / Welding Dissimilar Metals
...
2026-04-23 18:12:39.468 | INFO     | debug_retrieval:run_queries:308 -   [ 2] type=text   score=0.0636
       path: SURFACE CONTAMINATION IN FABRICATION / Contamination by Carbon Steel
...
2026-04-23 18:12:39.469 | INFO     | debug_retrieval:run_queries:308 -   [10] type=text   score=0.0446
       path: DESIGN CONSIDERATIONS IN FABRICATION OF STAINLESS STEELS / Design to Avoid Corrosion
```

## 总结

这次验证可以确认 3 件事：

1. `PATH` 与 `CONTENT` channel 已经不再是空壳或单纯 FTS 表现。真实日志里两者都持续返回非 0 命中，且是 **BM25 小数分**，例如 `6.8409`、`5.4745`、`6.6060` 这类分值。
2. 混合 query 的统一 tokenizer 已经生效。`Atlas handbook 不锈钢 welding parameters` 这条 query 在 GREP token 中保留了 `不锈钢`，并同时保留英文 token。
3. 英文 stopword 去噪已经生效。`the stainless steel welding parameters` 的 GREP token 里只剩 `stainless / steel / welding / parameters`，`the` 被过滤掉了。

仍需保留的说明：

- 当前验证的是“**无向量时应用层 tokenizer + BM25 + term + RRF + agent**”这条链路。
- 向量权重融合还没做，这一轮不验证 `vector_score`。
- 本轮最终排序里 Atlas 仍然经常压过 mock_welding_guide，这说明现在的系统仍然保留“大文档广覆盖 + Agent 补具体路径”的整体行为，不是只偏向 mock 文档。
