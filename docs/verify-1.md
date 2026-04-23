# G1 有效 Query 检索复盘（2 条）

本文档基于 `debug_retrieval.py` 一次完整跑数后落盘的日志 `docs/g1.log`（2026-04-23 15:00 左右），**仅整理当时配置里「有实际检索意义」的两条 query**：与领域无关的英文句、以及超长重复的焊接相关句。原先 `TEST_QUERIES` 中的空串在本复盘里**不计入**（且生产环境已在 `run_retrieval_query()` 中对空/纯空白 query 做 `empty_query_filtered` 拦截）。

| 项 | 值 |
|----|----|
| 原始日志 | `docs/g1.log` |
| 用户 / 命名空间 | `local-dev-user` / `default` |
| top_k | 10 |
| data_type | 1（文本优先） |
| 文档 | `doc_debug_ret_01` Atlas 手册；`doc_debug_ret_02` mock_welding_guide；跨文档边 weight≈0.9552 |

---

## Query 1：无关英文句（`the quick brown fox jumps over the lazy dog`）

### 1.1 底层发现（PHASE 1）

- 作用域：`Total chunks in scope: 162`。
- 三通道：`path_channel` 与 `content_channel` 均为 0 行；**仅 `term_channel` 返回 20 行**（term 命中 `term_search_text` 等，与 query 字面是否「像不锈钢」无强约束）。
- RRF：10 行来自 **1 个 channel**（`weights={'path': 1.5}`，即仅 term 侧有有效列表时的融合表现）。
- section 合并：`section_merge=10->9`，即合并后 9 条 discovery 候选进入后续与 Agent 的并集。

证据：

```300:325:docs/g1.log
  📊 Total chunks in scope: 162
  📡 PHASE 1: Bottom-Layer Discovery (channels=['content', 'path', 'term'])
  ...
  📡 path_channel: 0 rows in 0ms
  ...
  📡 content_channel: 0 rows in 16ms
  ...
  📡 term_channel: 20 rows in 6ms
  ...
  🔀 RRF Fusion: 10 rows from 1 channels (weights={'path': 1.5})
  ...
  retrieval: section_merge=10->9
```

### 1.2 KG 导航 / Agent（PHASE 2）

- 进入 `agent_navigate`：Knowledge Map 覆盖两篇文档元信息。
- **LLM 选档**：`LLM raw response: []` → 判定无相关文件，**0 条 path**。
- 系统行为：`Agent returned 0 paths, falling back to lexical graph`（本 run 中最终**未再产出 Agent path**，以底层 discovery 结果为准）。

证据：

```327:345:docs/g1.log
  🧭 PHASE 2: Agent Navigation
  ...
  📄 STEP 1: LLM File Selection
  ...
  LLM raw response: []
  ...
  ⚠️  LLM returned no valid files (raw=[]) in 1482ms
  ...
  ⚠️  Agent returned 0 paths in 1489ms, falling back to lexical graph
```

### 1.3 路由与最终「回答结果」（返回 chunk 列表）

- **router**：`discovery_only`（纯底层发现路径；Agent 无贡献）。
- **条数**：9 条（因 `top_k=10` 而 discovery 经合并后为 9）。
- **来源**：全部为 `EN_Atlas Technical Handbook rev Aug 2013.pdf`（`mock_welding_guide` 未进入 Top9）。
- **得分**：`rrf_score` 量级约 `0.0214`～`0.0246`（与 Agent 侧常见占位分 `2.0` 不同）。

证据（摘要行 + 打印出的前几条 path/file）：

```349:404:docs/g1.log
  ✅ RETRIEVAL COMPLETE: 9 results | router=discovery_only | 1535ms
  ...
  Router: discovery_only  |  Results: 9  |  data_type=1
  [ 1] ... path: Root
  [ 2] ... path: THE FAMILY OF MATERIALS
  ...
  [ 9] ... path: STAINLESS STEELS - INTRODUCTION TO THE GRADES AND FAMILIES / The Families of Stainless Steels / Martensitic Stainless Steels
```

**本轮结论（可读性）**：在「与 KB 完全无关」的句子上，系统仍可能靠 **term 通道**扫出一批与不锈钢主题相关的块；**LLM 选档正确退回空**，最终用户看到的是 **Atlas 侧泛相关片段**，属于边界行为样本，不应当作「精准焊接问答」的验收标准。

---

## Query 2：超长重复焊接句（`stainless steel welding parameters ...` 重复 30 次）

> 以下在文档中只写简称「超长焊接 query」；完整串见 `g1.log` 中 `Query 3/3` 行。

### 2.1 底层发现（PHASE 1）

- 作用域：仍为 162 chunks。
- 同样仅 **term 通道有命中**：`term_channel: 20 rows`；**单条 term score 被抬到 150.0**（重复词导致词频/打分放大），与 Query 1 的 `3.0` 形成对比。
- RRF 后 10 行；`section_merge=10->8` → **8 条 discovery 侧路径**再进入与 Agent 合并。

证据：

```418:443:docs/g1.log
  📊 Total chunks in scope: 162
  ...
  📡 term_channel: 20 rows in 20ms
      [0] score=150.0000  path=STAINLESS STEELS - INTRODUCTION TO THE GRADES AND FAMILIES  type=text
  ...
  🔀 RRF Fusion: 10 rows from 1 channels (weights={'path': 1.5})
  ...
  retrieval: section_merge=10->8
```

### 2.2 KG 导航（文件级 → GREP → 边扩展 → 路径级）

**STEP 1 LLM 选档**：只选了 `doc_debug_ret_02`（`mock_welding_guide`）。

**STEP 1b GREP（导航侧「补文档」）**：

- 从超长 query 抽 token（cap 8 展示）：`stainless, steel, welding, parameters, austenitic, grade, 304, tig`（`total=390` 为原始 token 规模）。
- GREP 命中两篇：`doc_debug_ret_01`、`doc_debug_ret_02`；日志写明 **`GREP added 1 new documents`**（相对「仅 LLM 选中的那一篇」补回 Atlas）。

**STEP 1c Edge expansion**：`edges_traversed=1`，但两篇已同时在集合中，**无新增邻居**（`No new neighbors found via edges`）。

**STEP 2 LLM 选 path（每文档最多 3 条，与 max_chunks/file 配置一致）**：

| 文档 | 选择的 section_path（共 3+3=6 条） |
|------|-----------------------------------|
| mock_welding_guide | `Welding Processes / TIG`，`Welding Processes / MIG`，`tables / table-1 welding-params.html` |
| Atlas 手册 | `... / Austenitic Stainless Steels`，`FABRICATION`，`FABRICATION / Welding` |

证据（节选）：

```460:528:docs/g1.log
  LLM raw response: ["doc_debug_ret_02"]
  ...
  GREP hit document_ids: ['doc_debug_ret_01', 'doc_debug_ret_02']
  ✅ GREP added 1 new documents
  ...
  edge_expand ... edges_traversed=1 neighbor_nodes=2
  ℹ️  No new neighbors found via edges
  ...
  Selected 3 paths ... → Welding Processes / TIG ... MIG ... tables / table-1 welding-params.html
  ...
  Selected 3 paths ... → ... Austenitic Stainless Steels ... FABRICATION ... FABRICATION / Welding
  🧭 AGENT NAVIGATE COMPLETE: 6 paths from 2 files in 8343ms
```

### 2.3 与 Discovery 并集、路由与最终返回

- **Agent→Discovery**：`agent_paths=6`，`discovery_paths=8`，**仅 5 条为 Agent 独有**（`new_paths=5`，与「6 条中 1 条与 discovery 重叠」一致）。
- **合并**：`Union: 8 discovery + 5 agent → 10 merged`；因截断/去重，最终对外 **9 条**（与 `RETRIEVAL COMPLETE: 9 results` 一致）。
- **router**：`discovery+agent`（两路都生效）。

证据：

```530:543:docs/g1.log
  🔗 Agent→Discovery union:
      agent_paths=6, discovery_paths=8, new_paths=5
  New paths from agent (not in discovery):
      → Welding Processes / TIG
      → Welding Processes / MIG
      → tables / table-1 welding-params.html
      → FABRICATION
      → FABRICATION / Welding
  ...
  🔄 Union: 8 discovery + 5 agent → 10 merged
  ✅ RETRIEVAL COMPLETE: 9 results | router=discovery+agent | 8387ms
```

**最终 9 条结果（`debug_retrieval` 打出来的 path / file 摘要）**：

| # | score（日志） | 主要来源 | section_path | 文件 |
|---|----------------|----------|----------------|------|
| 1–7 | ≈0.0214～0.0246 | 偏 Discovery（RRF） | 多条 `STAINLESS STEELS...` / `THE FAMILY OF MATERIALS` 等 | Atlas 手册 |
| 8 | 2.0 | Agent 独有 | `Welding Processes / TIG` | mock_welding_guide |
| 9 | 2.0 | Agent 独有 | `Welding Processes / MIG` | mock_welding_guide |

（第 7 名附近为 `Standard Classifications` 等，仍属 Atlas 目录内文本块。）

证据：

```558:594:docs/g1.log
  Router: discovery+agent  |  Results: 9  |  data_type=1
  [ 1] ... path: STAINLESS STEELS - INTRODUCTION TO THE GRADES AND FAMILIES
  ...
  [ 7] ... path: ... / Standard Classifications
  [ 8] ... path: Welding Processes / TIG
       file: mock_welding_guide
  [ 9] ... path: Welding Processes / MIG
       file: mock_welding_guide
```

**本轮结论（可验收点）**：

- **底层发现**：在超长重复下，term 侧打分被「堆词」显著抬高，**Atlas 大手册仍占 RRF 前排**（符合「大库 + 高词频」行为）。
- **KG 导航**：LLM 先偏 `mock_welding_guide`；**GREP 把 Atlas 拉回导航范围**；两文档各选 3 条 path，共 **6 条**导航路径。
- **合并结果**：**Discovery 与 Agent 去重后联合**，最终 Top9 中 **2 条来自 mock 的 TIG/MIG 具体工艺**，其余多为 Atlas 的牌号/总览类块——这正好展示「**导航补具体、底层保广度**」的叠加方式。

---

## 与验证文档的关联

- 更完整的分组步骤（G1–G9）仍见 `docs/kg-Discovery-verification-plan.md`。
- 若需只复现本文两条 query，可将 `debug_retrieval.py` 的 `TEST_QUERIES` 改为仅含上述两条（并注意空 query 已在生产与调试脚本层过滤）。
