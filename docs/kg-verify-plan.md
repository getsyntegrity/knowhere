# KG 导航 + 底层 Discovery 验证操作手册（Runbook）

本手册是 `apps/worker/debug_retrieval.py` 的配套操作指南，面向人工测试：**按顺序做就行**，每一步都写明了要改的参数、要跑的命令、要看的日志和通过标准。

最近一次更新：2026-04-23。G1–G7 + 跨文档边校验已通过；G8/G9 执行方式见 §8、§9。

---

## 0. 文档怎么用

- 想**快速 smoke test**：跑 §3 → §4（G1 基线），10 分钟能确认整条管道没坏。
- 想**完整验证 KG + Discovery**：按 §4–§9 顺序做，每组独立、互不污染。
- 想**理解各参数**：看 §2「参数速查」。
- 出问题时：对照 §10「已知差异与排障」。

术语约定：
- **DOC_A** = Atlas Technical Handbook，`doc_debug_ret_01`
- **DOC_B** = mock_welding_guide，`doc_debug_ret_02`
- **scope** = `user_id=local-dev-user` / `namespace=default`

---

## 1. 先决条件与环境

### 1.1 基础设施
- 本地 docker-compose 基础设施已启动。快速自检：
  ```bash
  docker ps --filter "name=knowhere_" --format "table {{.Names}}\t{{.Status}}"
  ```
  期望看到 `knowhere_postgres` / `knowhere_redis` / `knowhere_localstack` 都是 `Up ...`。
- 服务起停与初始化脚本：[deploy/local-dev/start-dev.sh](../deploy/local-dev/start-dev.sh)
  - **日常测试**：上述 `docker ps` 能看到三个容器 Up，就**不用**重跑脚本。
  - 机器 / Docker Desktop 重启过 → 跑 `./deploy/local-dev/start-dev.sh`（**不加** `--init-user`）把容器拉起来即可。
  - 只有以下情况才用 `--init-user`（三步都是幂等的：建 user 表 → `alembic upgrade heads` → seed `local-dev-user`）：
    - 初次部署
    - 拉了新 migration
    - user 表被清了 / `local-dev-user` 账号丢了
- [apps/worker/.env](../apps/worker/.env) 里 `DATABASE_URL` 指向本地 Postgres。
- 如需测 Agent/LLM（§5 G2、§7 G4 等）：`.env` 中至少一个 LLM key 可用（`DS_KEY` / `ALI_API_KEYS` / `GLM_API_KEY` / `GPT_API_KEY`）。

### 1.2 Python 运行环境
**强烈推荐**使用 [apps/worker/venv](../apps/worker/venv) 下的 Python，避开 `uv run` 在干净缓存下重新编译 C 扩展（曾导致 ingest 卡 10 分钟以上）：

```bash
cd apps/worker
./venv/bin/python -V   # 应显示 Python 3.11.x
```

### 1.3 日志目录约定
建议把每次运行的完整日志落盘到 `/tmp/knowhere_debug_logs/`，按分组命名，便于事后审计：

```bash
mkdir -p /tmp/knowhere_debug_logs
# 命名规范建议：g1.log、g2.log、…、g7a.log、g7b.log、g9_run1.log、g9_run2.log
```

### 1.4 本地 KB 目录
```
~/.knowhere/chengke_kb/
├── EN_Atlas Technical Handbook rev Aug 2013.pdf/chunks.json
└── mock_welding_guide/chunks.json
```
两篇都存在才能跑完整 runbook；缺一篇时脚本会在 Phase 1 报 `文档目录不存在` 并退出。

---

## 2. 参数速查（[apps/worker/debug_retrieval.py](../apps/worker/debug_retrieval.py) 顶部）

| 参数 | 默认值（当前仓库） | 作用 | 典型取值 |
|------|------------------|------|----------|
| `KB_ROOT` | `~/.knowhere/chengke_kb` | 本地 KB 根目录 | 一般不改 |
| `DETERMINISTIC_USER_ID` | `local-dev-user` | 写入/检索的 user_id | 一般不改 |
| `DETERMINISTIC_NAMESPACE` | `default` | 写入/检索的 namespace | 一般不改 |
| `DOCS` | Atlas 先、welding 后 | 待 ingest 文档列表。**顺序即 publish 顺序**；后发布的文档计算 keyword overlap 时用"新文档全量 ∩ 对端 top_keywords"非对称策略 | 调顺序可观察边建立方向 |
| `SINGLE_DOC_MODE` | `False` | `True` 时只 ingest `DOCS[0]` | G1 单文档基线设 `True`，其它都设 `False` |
| `TEST_QUERIES` | **G8 边界集（空/无关/超长）** | 本轮要跑的 query 列表 | 每组测试前都要改，见各组 |
| `TOP_K` | `10` | 传给 `run_retrieval_query` 的 top_k | G6 小 KB 验证用 `200` |
| `DATA_TYPE` | `1` | 单通道 fallback（`DATA_TYPES` 为空时使用） | 1=text优先, 3=image, 4=table |
| `DATA_TYPES` | `[1]` | 对每个 query 依次按列表跑多个 data_type | G5 通道切换用 `[1, 3, 4]` |
| `EXCLUDE_DOCUMENT_IDS` | `[]` | 排除整篇文档 | G7a 用 `["doc_debug_ret_02"]` |
| `EXCLUDE_SECTIONS` | `[]` | 排除具体 section_path | G7b 用 `[{"document_id":..., "section_path":...}, ...]` |

> **注意**：仓库当前 `TEST_QUERIES` 预置为 G8 边界 case（空串 / 无关英文 / 超长句）。跑 G1 基线前务必改回正常 query，否则会被空 query + 超长 query 污染结果。

### 2.1 `data_type` 取值对照（来自 `app_service._resolve_allowed_chunk_types`）
| `data_type` | `allowed_chunk_types` | 含义 |
|-------------|----------------------|------|
| 1 | `None` | 不限类型（默认混合） |
| 3 | `{"image"}` | 仅 image |
| 4 | `{"table"}` | 仅 table |
| 5 | `{"text", "image"}` | text + image |
| 6 | `{"text", "table"}` | text + table |

---

## 3. 两个核心运行命令

> **Shell 小贴士**：
> - `cd apps/worker` 只在**仓库根目录**时执行。如果你已经在 `apps/worker/`（`pwd` 显示路径以 `/apps/worker` 结尾），**不要再 cd**。
> - 日志文件名**不要用**尖括号 `<xxx>` 形式。zsh / bash 会把 `<xxx>` 当成输入重定向，直接报 `no such file or directory`。请把下面 `g1.log` 换成对应分组名（见 §16 总表）。

### 3.1 常规运行（启用 LLM）
```bash
# 仅当还在仓库根目录时需要：
cd apps/worker

./venv/bin/python -u debug_retrieval.py 2>&1 | tee /tmp/knowhere_debug_logs/g1.log
```

`-u` 强制 stdout/stderr 不缓冲，`tee` 同时落盘和上屏。日志文件名按分组替换为 `g1.log` / `g2.log` / … / `g7a.log` / `g9_run1.log` 等。

### 3.2 禁用 LLM 运行（测底层 Discovery，对应 §6 G3）
```bash
# 仅当还在仓库根目录时需要：
cd apps/worker

env DS_KEY= GLM_API_KEY= ALI_API_KEYS= GPT_API_KEY= LLM_MOCK_ENABLED=false \
  ./venv/bin/python -u debug_retrieval.py 2>&1 | tee /tmp/knowhere_debug_logs/g3.log
```

> `LLM_MOCK_ENABLED` 必须写成 `false` 或省略，写成空字符串会被 pydantic-settings 拒绝。

---

## 4. Step 0：ingest + 跨文档边校验（每个分组前都默认跑过一次）

### 4.1 目的
确认两篇文档能正常入库，并且 DOC_B 与 DOC_A 之间能建立 `related` 边（`weight ≈ 0.9552`）。**这是后续所有分组的前置条件**。

### 4.2 参数
脚本默认就是这组：`SINGLE_DOC_MODE=False`，`DOCS` 两篇齐全。`TEST_QUERIES` 可以临时改成 `["stainless steel grades"]` 这类有意义的 query，避免跑空。

### 4.3 命令
§3.1。

### 4.4 日志必现项
- `清理旧数据 docs=['doc_debug_ret_01', 'doc_debug_ret_02']`
- 两次 `Document 状态发布完成` + 两次 `知识图谱发布完成`
- `INGEST 结果统计（所有 debug 文档）` 下两行：
  - `doc_debug_ret_01` → `document_chunks 152 rows`、`document_sections 114 rows`、`graph_nodes 1 rows`
  - `doc_debug_ret_02` → `document_chunks 10 rows`、`document_sections 10 rows`、`graph_nodes 1 rows`、`graph_edges 1 rows`
- `跨文档 edges（user=local-dev-user, ns=default）: 1 条`
- 那 1 条边的摘要：
  ```
  doc:doc_debug_ret_02  <->  doc:doc_debug_ret_01  weight=0.9552
  shared=['austenitic','corrosion','grade','grades','high','resistance','stainless','steel','steels']
  ```

### 4.5 通过标准
- chunk / section / graph_nodes 行数完全匹配上表。
- **跨文档 edges ≥ 1**，且 weight ≥ 0.8。

### 4.6 如果不通过
- **边数为 0**：`mock_welding_guide/chunks.json` 的 keyword 列表被动过。对照 §11 的 DB 现状校验 SQL 看 DOC_B 的 top_keywords，必要时恢复 mock 数据。
- **chunk 数异常**：`chunks.json` 被改过或解析失败，看 `加载了 N 个 chunks` 行。

---

## 5. G1：基线（单/多文档常规 query）

### 5.1 目的
最基本的冒烟：常规 query 能返回结构化结果，`section_path` 有多级，无异常。

### 5.2 参数
```python
SINGLE_DOC_MODE = False
TEST_QUERIES = [
    "stainless steel grades",
    "torque values",
    "material properties",
]
TOP_K = 10
DATA_TYPES = [1]
EXCLUDE_DOCUMENT_IDS = []
EXCLUDE_SECTIONS = []
```

### 5.3 命令
§3.1 → `/tmp/knowhere_debug_logs/g1.log`

### 5.4 日志必现项
- 每个 query 有对应的 `Query N/3: "..." [data_type=1]`。
- 每个 query 最终有 `Router: discovery_only` 或 `Router: discovery+agent`（取决于 LLM 是否选到文档）。
- 每条结果都有 `type`、`score`、`path`、`file`。
- 至少 1 个 query 的 top 结果 `path` 形如 `STAINLESS STEELS - INTRODUCTION TO THE GRADES AND FAMILIES / ...`（多级）。

### 5.5 通过标准
- 3 个 query 都返回 ≥ 5 条结果，**无 Exception/Traceback**。
- 有结果的 `path` 不全是空或 `Root`。

### 5.6 恢复
下一组前保持这组参数，只改 `TEST_QUERIES` 等必要字段。

---

## 6. G2：Agent 两阶段 LLM 导航

### 6.1 目的
启用 LLM 时，`agent_navigate` 能完成 STEP 1（选文档）→ STEP 1b（GREP 补文档）→ STEP 1c（图边扩展）→ STEP 2（为每篇选 chunk）。

### 6.2 参数
```python
SINGLE_DOC_MODE = False
TEST_QUERIES = [
    "stainless steel grades",
    "material properties",
]
TOP_K = 10
DATA_TYPES = [1]
EXCLUDE_DOCUMENT_IDS = []
EXCLUDE_SECTIONS = []
```
确认 `.env` 里 `DS_KEY`（或其它 LLM key）非空。

### 6.3 命令
§3.1 → `/tmp/knowhere_debug_logs/g2.log`

### 6.4 日志必现项
```
🧭 AGENT NAVIGATE START
📋 STEP 0: Knowledge Map Overview (2 files)
📄 STEP 1: LLM File Selection
  LLM raw response: ["doc_debug_ret_02", "doc_debug_ret_01"]   ← 或其它非空数组
  ✅ LLM selected 2 files in <ms>
🔎 STEP 1b: GREP Discovery
  GREP tokenized units (cap 8): [...]
  GREP hit document_ids: [...]
🔗 STEP 1c: Edge Expansion
  edge_expand hop=0: ...
📖 Processing: <doc_name> [<doc_id>]    ← 每篇一次
hydrate: N/N paths resolved
Router: discovery+agent  |  Results: ...
```

### 6.5 通过标准
- 至少 1 个 query 看到 `LLM selected ≥ 1 files` 且 `Router: discovery+agent`。
- `hydrate: N/N` 全部成功解析。
- 返回结果里同时包含两篇文档的 chunk。

### 6.6 备注
- 当 LLM 返回 `[]` 时，`agent_navigate` 会直接 return（见 §10.1），回退到 `discovery_only`。此时 G2 这个 query 不算通过，但可作为 §10 排障依据。

---

## 7. G3：LLM 不可用时底层 Discovery 兜底

### 7.1 目的
即使 LLM 完全不可用，底层 `path_channel` / `content_channel` / `term_channel` 也能召回焊接相关 chunk。

### 7.2 参数
```python
TEST_QUERIES = [
    "MIG TIG electrode shielded arc",
]
TOP_K = 10
DATA_TYPES = [1]
```

### 7.3 命令（§3.2）
```bash
cd apps/worker
env DS_KEY= GLM_API_KEY= ALI_API_KEYS= GPT_API_KEY= LLM_MOCK_ENABLED=false \
  ./venv/bin/python -u debug_retrieval.py 2>&1 | tee /tmp/knowhere_debug_logs/g3.log
```

### 7.4 日志必现项
- **不能**出现 `🧭 AGENT NAVIGATE START`（LLM 已禁）。
- 必须有 `term_channel: N rows`（N > 0）。
- 最终 `Router: discovery_only  |  Results: ≥ 3`。
- 结果里有 `Welding Processes / MIG`、`/ TIG`、`/ SMAW` 这类 path。

### 7.5 通过标准
- 有 ≥ 3 条结果落在 `mock_welding_guide` 的 Welding Processes 各 section。
- `Router` 永远是 `discovery_only`。

---

## 8. G4：图边扩展（Edge Expansion）

### 8.1 目的
当 LLM 只选了一篇文档时，`STEP 1c` 能通过 `graph_edges` 把另一篇邻居文档也纳入检索范围。

### 8.2 参数
```python
TEST_QUERIES = [
    "austenitic grade 304",
]
TOP_K = 10
DATA_TYPES = [1]
```
（`austenitic grade 304` 同时在两篇里都有命中，便于让 LLM 选其中一篇后图边补上另一篇。）

### 8.3 命令
§3.1 → `/tmp/knowhere_debug_logs/g4.log`

### 8.4 日志必现项
```
🔗 STEP 1c: Edge Expansion
  Input documents: [...]
  edge_expand hop=0: doc_nodes_found=<N> (of <N> requested)
  edge_expand hop=0: edges_traversed=1  neighbor_nodes=<N>
```

### 8.5 通过标准
- `edges_traversed ≥ 1`。
- `neighbor_nodes ≥ 1`（意味着至少一篇邻居文档被拉入）。
- 最终结果中同时出现两篇文档。

---

## 9. G5：`data_type` 通道切换

### 9.1 目的
同一 query 在 `data_type=1/3/4` 下分别返回 **混合 / 仅 image / 仅 table**。

### 9.2 参数
```python
TEST_QUERIES = [
    "welding parameters table",
]
TOP_K = 10
DATA_TYPES = [1, 3, 4]   # 关键：对同一 query 跑 3 次
```

### 9.3 命令
§3.1 → `/tmp/knowhere_debug_logs/g5.log`

### 9.4 日志必现项
对应三次 `Query 1/1: "welding parameters table" [data_type=X]`，每次都有：
```
allowed_chunk_types=None       ← data_type=1
allowed_chunk_types={'image'}  ← data_type=3
allowed_chunk_types={'table'}  ← data_type=4
```

### 9.5 通过标准
- `data_type=1`：结果数 ≥ 5，类型混合。
- `data_type=3`：结果数 ≥ 1，**所有**结果 `type=image`。
- `data_type=4`：结果数 ≥ 1，**所有**结果 `type=table`（应包含 `tables / table-1 welding-params.html`）。

---

## 10. G6：小 KB 短路

### 10.1 目的
当 scope 内 chunk 总数 ≤ `top_k` 时，跳过所有 discovery/agent，直接全量返回。

### 10.2 参数
```python
TEST_QUERIES = [
    "welding parameters table",
]
TOP_K = 200         # 当前库 scope 有 162 chunks，设 200 可触发
DATA_TYPES = [1]
```

### 10.3 命令
§3.1 → `/tmp/knowhere_debug_logs/g6.log`

### 10.4 日志必现项
```
📊 Total chunks in scope: 162
⚡ Small KB optimization: 162 chunks <= top_k=200, returning all
small_kb load: loaded=162 rows after signal/exclude filters
Router: small_kb_all  |  Results: <N>
```

### 10.5 通过标准
- `router_used` 字符串为 **`small_kb_all`**（不是 `small_kb`，见 §10.2）。
- `Results` 数与 `_load_all_scoped_chunks` 输出一致（通常因为 `_with_citation` 裁剪，会略少于 162）。

### 10.6 跑完恢复
```python
TOP_K = 10
```

---

## 11. G7：`exclude_document_ids` / `exclude_sections` 排除

### 11.1 G7a：排整篇文档

参数：
```python
TEST_QUERIES = ["welding parameters table"]
EXCLUDE_DOCUMENT_IDS = ["doc_debug_ret_02"]
EXCLUDE_SECTIONS = []
```

日志必现：
- `exclude_docs=['doc_debug_ret_02']  exclude_secs=0`
- 所有结果 `file` 都是 `EN_Atlas Technical Handbook rev Aug 2013.pdf`。
- **不能**出现 `PostgresSyntaxError: syntax error at or near "$3"`（老 bug，见 §10.3）。

通过标准：
- `mock_welding_guide` 完全不在结果里。
- 无 SQL 异常。

### 11.2 G7b：排指定 section

参数：
```python
TEST_QUERIES = ["welding parameters table"]
EXCLUDE_DOCUMENT_IDS = []
EXCLUDE_SECTIONS = [
    {"document_id": "doc_debug_ret_02", "section_path": "Welding Processes / MIG"},
    {"document_id": "doc_debug_ret_02", "section_path": "Welding Processes / TIG"},
]
```

日志必现：
- `exclude_docs=[]  exclude_secs=2`
- 结果里 mock_welding 不再出现 `Welding Processes / MIG` 或 `Welding Processes / TIG`，但可以出现 `tables / table-1 welding-params.html`、`Welding Processes / SMAW` 等。

通过标准：
- 指定 section 不在结果中。
- 其它 section 正常返回。

### 11.3 跑完恢复
```python
EXCLUDE_DOCUMENT_IDS = []
EXCLUDE_SECTIONS = []
```

---

## 12. G8：边界 query（空 / 无关 / 超长）

### 12.1 目的
空 query、完全无关的英语句子、超长 query 都不应把系统打崩。

### 12.2 参数
```python
TEST_QUERIES = [
    "",
    "the quick brown fox jumps over the lazy dog",
    ("stainless steel welding parameters austenitic grade 304 TIG MIG electrode shielding gas argon " * 10).strip(),
]
TOP_K = 10
DATA_TYPES = [1]
```
> 超长 query 建议用 `* 10`（约 1 KB）。`* 30` 曾触发 LLM 长上下文与 plainto_tsquery 解析压力，可选做。

### 12.3 命令
§3.1 → `/tmp/knowhere_debug_logs/g8.log`

### 12.4 日志必现项与通过标准
| 子 case | 期望行为 | 通过判定 |
|---------|---------|----------|
| 空 query | 返回 0 条或兜底路径，**不抛异常** | 日志里这条 query 段无 Traceback；`Results: N`（N 可以是 0） |
| 无关 query | Router 多半是 `discovery_only`，结果 ≤ 3 或为空；LLM 可能返回 `[]` 后 fallback | 无异常；结果数合理 |
| 超长 query | ingest 不受影响；retrieval 耗时 ≥ 5s 可接受 | 最终能完成，`所有检索测试完成` 打印 |

### 12.5 如果 case 2/3 超时或报错
- 查 `LLM raw response:` 行，判断是否是 LLM 超时 → 可临时按 §3.2 禁 LLM 复测。
- 查 `plainto_tsquery` 相关报错 → 可能是 tsvector 侧被某个特殊 token 噎住。
- `* 30` 跑不过就降到 `* 10`。

---

## 13. G9：`retrieval_hit_stats` 累加

### 13.1 目的
每次检索完成后，后台异步任务会 upsert `retrieval_hit_stats`：
- `hit_kind='document'`（`chunk_id=NULL`）：每个命中文档 1 行，重复命中 `hit_count += 1`
- `hit_kind='chunk'`（`chunk_id=<id>`）：每个命中 chunk 1 行，重复命中 `hit_count += 1`

相关实现在 [packages/shared-python/shared/services/retrieval/hit_stats_service.py](../packages/shared-python/shared/services/retrieval/hit_stats_service.py) 与 `app_service.schedule_retrieval_hit_stats_update`。

### 13.2 参数
```python
TEST_QUERIES = ["stainless steel grades"]
TOP_K = 10
DATA_TYPES = [1]
EXCLUDE_DOCUMENT_IDS = []
EXCLUDE_SECTIONS = []
```

### 13.3 执行步骤

1. **第 1 次跑**，落盘到 `g9_run1.log`：
   ```bash
   cd apps/worker
   ./venv/bin/python -u debug_retrieval.py 2>&1 | tee /tmp/knowhere_debug_logs/g9_run1.log
   ```
2. **等 2 秒**让异步 hit stats 写入完成（`schedule_retrieval_hit_stats_update` 是 best-effort task）。
3. **查库基线**（用 `psql` 或任意 SQL 客户端，DSN 来自 `.env`）：
   ```sql
   SELECT hit_kind, document_id, chunk_id, hit_count, last_hit_at
   FROM retrieval_hit_stats
   WHERE user_id = 'local-dev-user'
     AND namespace = 'default'
   ORDER BY hit_kind, document_id, chunk_id;
   ```
   记下每行的 `hit_count`（应全部为 1）。
4. **第 2 次跑**，落盘到 `g9_run2.log`（**用同一个 query，不要改参数**）。
5. 再等 2 秒后重跑同一条 SQL。

> ⚠️ 注意：`debug_retrieval.py` 的 `ingest_to_db` 在开头会**清空** `retrieval_hit_stats` 里 debug 文档的记录。所以**第 2 次跑不能重新 ingest**，否则基线会被清零。
> 可以在第 1 次跑完后，**注释掉脚本里 `ingest_to_db(docs_to_run)` 那一行**再跑第 2 次；或单独写一个只跑 `asyncio.run(run_queries())` 的小脚本。

### 13.4 通过标准
- 第 1 次跑完：
  - 每个被命中 document 有 1 行 `hit_kind='document'`，`hit_count=1`
  - 每个被命中 chunk 有 1 行 `hit_kind='chunk'`，`hit_count=1`
- 第 2 次跑完（未重跑 ingest）：
  - 相同行的 `hit_count=2`
  - `last_hit_at` 晚于第 1 次
  - 行数不应增加（upsert 命中唯一键）

### 13.5 如果 hit_count 没涨
- 确认第 2 次没意外重跑 ingest（日志里是否出现 `清理旧数据 docs=...`）。
- 确认 `schedule_retrieval_hit_stats_update` 的 asyncio task 没被提前 cancel：看日志末尾是否有 `retrieval_hit_stats:<user>:<ns>` 相关 warning。
- 查表时 user_id/namespace 大小写与脚本一致。

---

## 14. 已知实现差异与排障

### 14.1 LLM 返回空时不会触发内部 GREP 补文档
`agent_navigate` 在 STEP 1 的 LLM 返回空数组/全部非法时 **直接 return**（约 `agent_navigate.py:530-534`），不会进入 STEP 1b GREP。这种情况下系统表现为 `Router: discovery_only`，由底层 `term_channel` 兜底——这是 G3 能通过的路径，**不是 bug**。

### 14.2 Small KB 路由名
触发小 KB 短路时 `router_used` 是 `small_kb_all`（字符串包含 `_all` 后缀），不是 `small_kb`。§10 判定按实际字符串。

### 14.3 已修复：exclude_document_ids 的 asyncpg SQL 语法错误
历史 bug：[packages/shared-python/shared/services/retrieval/channels.py](../packages/shared-python/shared/services/retrieval/channels.py) 原来用 `AND d.document_id NOT IN :excluded_doc_ids`，在 asyncpg 下会触发 `syntax error at or near "$3"`。  
修复：改为 `AND d.document_id <> ALL(:excluded_doc_ids)`，参数从 `tuple` 改为 `list`。  
G7a 日志若再次出现该错误，说明有人回退了这个修复。

### 14.4 exclude_document_ids 与知识地图 overview
`agent_navigate` 的 STEP 0 知识地图当前仍会展示已被 `EXCLUDE_DOCUMENT_IDS` 排除的文档，LLM 可能选到它们、再被下游过滤为空导致 fallback。功能无害，只是多一次无效 LLM 调用。

### 14.5 `uv run` 首次启动慢
`uv run python debug_retrieval.py` 在干净缓存下会重编 `gevent`、`psycopg2-binary` 等 C 扩展，可能卡 5–15 分钟且无输出。改用 `./venv/bin/python -u ...`（§1.2）。

### 14.6 空字符串 `LLM_MOCK_ENABLED`
pydantic-settings 不接受 `LLM_MOCK_ENABLED=""`（bool 解析失败）。禁 LLM 时必须写 `LLM_MOCK_ENABLED=false` 或完全不设该变量。

---

## 15. 当前数据库基线（快速自检）

运行任何分组前，最好先确认库里就是以下状态（最近一次 ingest 之后）：

```sql
-- 文档概览
SELECT d.document_id, d.source_file_name, d.status,
       (SELECT count(*) FROM document_chunks dc
          WHERE dc.document_id = d.document_id
            AND dc.job_result_id = d.current_job_result_id) AS chunks,
       (SELECT count(*) FROM document_sections ds
          WHERE ds.document_id = d.document_id
            AND ds.job_result_id = d.current_job_result_id) AS sections,
       (SELECT count(*) FROM graph_nodes gn
          WHERE gn.owner_document_id = d.document_id
            AND gn.job_result_id = d.current_job_result_id) AS graph_nodes
FROM documents d
WHERE d.user_id = 'local-dev-user'
  AND d.namespace = 'default'
  AND d.document_id IN ('doc_debug_ret_01', 'doc_debug_ret_02')
ORDER BY d.document_id;
```
期望：
- `doc_debug_ret_01`：152 chunks / 114 sections / 1 graph_node
- `doc_debug_ret_02`：10 chunks / 10 sections / 1 graph_node

```sql
-- 跨文档边
SELECT edge_id, edge_kind, source_node_id, target_node_id,
       weight, properties->'shared_keywords' AS shared
FROM graph_edges
WHERE user_id = 'local-dev-user' AND namespace = 'default';
```
期望：
- 1 行：`related:doc_debug_ret_01<->doc_debug_ret_02`
- `weight ≈ 0.9552`
- `shared` 含 9 个关键词（austenitic / corrosion / grade / grades / high / resistance / stainless / steel / steels）

```sql
-- chunk 类型分布
SELECT document_id, chunk_type, count(*) AS cnt
FROM document_chunks
WHERE user_id = 'local-dev-user' AND namespace = 'default'
  AND document_id IN ('doc_debug_ret_01', 'doc_debug_ret_02')
GROUP BY 1, 2 ORDER BY 1, 2;
```
期望：
- `doc_debug_ret_01`：text=114 / table=18 / image=20
- `doc_debug_ret_02`：text=9 / table=1

```sql
-- hit_stats（G9 基线/对照）
SELECT hit_kind, document_id, chunk_id, hit_count, last_hit_at
FROM retrieval_hit_stats
WHERE user_id = 'local-dev-user' AND namespace = 'default'
ORDER BY hit_kind, document_id, chunk_id;
```
G9 未跑时此表为空。G9 跑完第 1 次后应有若干行 `hit_count=1`，跑完第 2 次（不重 ingest）应升到 `hit_count=2`。

---

## 16. 分组现状总表

| 分组 | 能力 | 现状 | 参考日志 |
|------|------|------|----------|
| Step 0 Edge | 跨文档边建立 | 已通过 | `g1.log` / `g4.log` 头部 |
| G1 | 多 query 基线 | 已通过 | `g1.log` |
| G2 | Agent 两阶段 LLM | 已通过 | `g2.log` |
| G3 | 无 LLM discovery 兜底 | 已通过 | `g3.log` |
| G4 | 图边扩展 | 已通过 | `g4.log` |
| G5 | data_type 切换 | 已通过 | `g5.log` |
| G6 | 小 KB 短路 | 已通过 | `g6.log` |
| G7a/b | exclude 机制 | 已通过（顺带修复 SQL bug） | `g7a.log` / `g7b.log` |
| G8 | 边界 query | **待人工补跑**（§12） | `g8.log` |
| G9 | hit_stats 累加 | **待人工补跑**（§13） | `g9_run1.log` / `g9_run2.log` |

---

## 17. 一次完整 runbook 结束后要做的事

1. 把 `debug_retrieval.py` 的 `TEST_QUERIES` / `TOP_K` / `DATA_TYPES` / `EXCLUDE_*` 恢复到日常基线（参考 §5.2 G1 基线）。
2. `git status` 检查 [apps/worker/debug_retrieval.py](../apps/worker/debug_retrieval.py) 是否只剩预期的 diff。
3. `/tmp/knowhere_debug_logs/` 下的日志按需归档或清理。
4. 如果某个分组新发现了问题，**把结论追加到 §14 或 §16** 再交接。
