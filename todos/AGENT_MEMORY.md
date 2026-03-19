# Knowledge Graph + Agent Memory Integration

> 将 knowhere 解析后的文档数据自动转化为 Agent 可消费的知识图谱，通过 MCP + Skill 双轨接入 Agent 产品。

---

## 核心架构理解

```
~/.knowhere/knowledge/{kb_id}/
├── default_root/                  ← 已有：各文件的解析结果 (chunks.json, hierarchy.json 等)
│   ├── 报告.pdf/
│   │   ├── chunks.json
│   │   └── hierarchy.json
│   ├── 规范.docx/
│   │   ├── chunks.json
│   │   └── hierarchy.json
│   └── ...
└── knowledge_graph.json           ← NEW：KB 级别，与 default_root 并存，增量更新
```

**关键设计原则**：

1. `knowledge_graph.json` 是 **KB 级别**的，不属于任何单个文件的 ZIP 包
2. 每次解析新文件后，**增量更新** knowledge_graph
3. 图的纵向结构 = 多个文件的 hierarchy 合并在 `Default_Root` 下
4. 图的横向结构 = connect_builder 发现的 chunk 间跨文件边
5. 即使没有任何横向边，以 `Default_Root` 为根的树本身就是一个合法的图

```
                    Default_Root (根节点)
                   /          |           \
              报告.pdf     规范.docx      方案.pdf
              /    \         |            /    \
           第1章  第2章    总则         编制依据  施工内容
           /  \                          |
         1.1  1.2                      chunk_X
          |                              ↕ ← 横向边 (connect_builder)
        chunk_A ──────────────────→ chunk_X
              related (score=0.85)
```

---

## Phase 1: 知识图谱生成

### 数据流

```
每次文件解析完成后:
  1. 读取该文件的 chunks (带 path/keywords/tokens)
  2. 读取 KB 下所有已有 chunks (从各文件的 chunks.json)
  3. 对全量 chunks 运行 connect_builder → 跨文件边
  4. 从全量 chunks 的 path 字段重建完整树 (Default_Root 为根)
  5. 组装 knowledge_graph.json = 树 + 边 + 节点元数据
  6. 写入 KB 根目录 (与 default_root 平级)
```

### 目标产出

```json
{
  "version": "1.0",
  "updated_at": "2026-03-18T...",
  "kb_id": "...",
  "stats": { "total_nodes": 150, "total_edges": 22, "total_files": 5 },

  "tree": {
    "Default_Root": {
      "报告.pdf": {
        "第1章": { "1.1 概述": {}, "1.2 范围": {} }
      },
      "规范.docx": {
        "总则": {}, "术语": {}
      }
    }
  },

  "nodes": [
    {
      "id": "chunk_001",
      "type": "text",
      "path": "Default_Root/报告.pdf/第1章/1.1 概述",
      "summary": "...",
      "keywords": ["施工方案", "基坑"],
      "content_preview": "前200字..."
    }
  ],

  "edges": [
    {
      "source": "chunk_001",
      "target": "chunk_042",
      "relation": "related",
      "score": 0.85,
      "shared_keywords": ["施工方案", "安全交底"]
    }
  ]
}
```

### 文件变更

#### [NEW] [graph_builder.py](file:///Users/wuchengke/Desktop/knowhereapi-main/apps/worker/app/services/connect_builder/graph_builder.py)

```python
def build_knowledge_graph(
    all_chunks: List[Dict],         # KB 下所有文件的 chunks 合并
    connections: Dict[str, List],   # connect_builder 输出
    kb_id: str = "",
    content_preview_len: int = 200,
) -> Dict[str, Any]:
    """
    从全量 chunks + connections 组装 KB 级别的 knowledge_graph.json。

    tree: 从 all_chunks 的 path 字段重建 (复用 _restore_graph_by_paths 逻辑)
    nodes: 从 all_chunks 提取 (id/type/path/summary/keywords + content 截断)
    edges: 直接来自 connections
    """

def update_knowledge_graph(
    existing_graph: Dict[str, Any],  # 已有的 knowledge_graph.json
    new_chunks: List[Dict],          # 新解析文件的 chunks
    existing_chunks: List[Dict],     # 已有的全部 chunks (从 existing_graph.nodes 恢复)
    kb_id: str = "",
) -> Dict[str, Any]:
    """
    增量更新 knowledge_graph.json：

    1. tree: 将 new_chunks 的 path 合并到已有 tree (dict.update 逐层合并)
    2. nodes: append new_chunks 的节点到 existing nodes
    3. edges: 只跑 new_chunks vs existing_chunks 的增量匹配:
       - 为 new_chunks 构建关键词索引
       - 遍历 existing_chunks 的关键词，与 new_chunks 索引做交集
       - 新产生的 edges append 到已有 edges
       → O(new × existing) 而不是 O(all²)
    4. stats: 重新计算
    """
```

**增量匹配核心逻辑**（复用 connect_builder 的 scoring）：

```python
def _incremental_connections(
    new_chunks: List[Dict],
    existing_chunks: List[Dict],
    config: Dict = None,
) -> Dict[str, List[Dict]]:
    """
    只匹配 new ↔ existing，跳过 existing ↔ existing（已有边不变）。
    复用 _build_keyword_index / _compute_keyword_score 等已有函数。

    1. 对 new_chunks 和 existing_chunks 分别建关键词索引
    2. 对每个 new_chunk，在 existing 索引中找候选
    3. 对每个 existing_chunk，在 new 索引中找候选
    4. 评分 + 去重 + 过滤 → 新增 edges
    """
```

#### [MODIFY] [debug_parse.py](file:///Users/wuchengke/Desktop/knowhereapi-main/apps/worker/debug_parse.py)

在解析完成生成 ZIP 后，额外调用 `build_knowledge_graph()`（首次）或 `update_knowledge_graph()`（后续） → 写入 `add_dir/../knowledge_graph.json`（与 default_root 平级）。

> [!NOTE]
> **不修改 [zip_result_service.py](file:///Users/wuchengke/Desktop/knowhereapi-main/packages/shared-python/shared/services/storage/zip_result_service.py)** — knowledge_graph.json 不进 ZIP 包。

---

## Phase 2: Agent 映射 (MCP + Skill)

### 存储约定

```
~/.knowhere/                              ← 全局数据目录（已确认）
├── config.json                            ← MCP Server 配置 (端口、日志等)
└── knowledge/
    └── {kb_id}/
        ├── default_root/                  ← 解析结果目录 (已有)
        │   ├── 文件A.pdf/...
        │   └── 文件B.docx/...
        └── knowledge_graph.json           ← 知识图谱 (与 default_root 平级)
```

### MCP Server

#### [NEW] [knowhere_mcp_server.py](file:///Users/wuchengke/Desktop/knowhereapi-main/apps/worker/app/services/mcp/knowhere_mcp_server.py)

轻量 stdio 模式 MCP Server，读取 `~/.knowhere/knowledge/` 目录：

```python
@mcp.tool()
def search_knowledge(query: str, top_k: int = 5) -> str:
    """搜索知识库，返回最相关的 chunk 及关联关系。"""
    # MVP: jieba 分词 + content/keywords 关键词匹配
    # 后续: 接入 knowhere-kb 检索管线

@mcp.tool()
def get_knowledge_overview() -> str:
    """获取知识库概览（文档列表 + 图谱统计）。"""
    # 返回 knowledge_graph.json 的 tree + stats
```

### Antigravity Skill

#### [NEW] [knowhere_memory/SKILL.md](file:///Users/wuchengke/Desktop/knowhereapi-main/.agent/skills/knowhere_memory/SKILL.md)

引导 Agent 通过 MCP 或直接读 `~/.knowhere/` 获取知识。

---

## Phase 3: Antigravity 端到端测试

1. 用 [debug_parse.py](file:///Users/wuchengke/Desktop/knowhereapi-main/apps/worker/debug_parse.py) 解析 2 个测试文档
2. 确认 `knowledge_graph.json` 生成在 `default_root` 同级
3. 复制到 `~/.knowhere/knowledge/test_kb/`
4. 启动 MCP Server / 配置 Skill
5. Antigravity 测试："我的知识库有哪些文档？"、"帮我查关于 XX 的内容"

---

## Verification Plan

### Automated Tests

扩展 [test_connect_builder.py](file:///Users/wuchengke/Desktop/knowhereapi-main/apps/worker/tests/services/test_connect_builder.py) 或新建 `test_graph_builder.py`：
1. `test_build_knowledge_graph_basic` — chunks + connections → 验证 JSON 结构
2. `test_tree_from_paths` — 多文件 paths → 正确的 Default_Root 树
3. `test_incremental_update` — 已有图 + 新 chunks → 图正确扩展
4. `test_empty_edges_valid_graph` — 无横向边 → 图仍合法（纯树）

### Manual Verification

1. [debug_parse.py](file:///Users/wuchengke/Desktop/knowhereapi-main/apps/worker/debug_parse.py) 解析测试文档 → 检查 knowledge_graph.json
2. Antigravity 中测试 MCP tool 自动触发（用户手动）

---

## 实施顺序

| 步骤 | 内容 | 依赖 |
|------|------|------|
| 1 | `graph_builder.py` — build + update | 无 |
| 2 | 集成到 [debug_parse.py](file:///Users/wuchengke/Desktop/knowhereapi-main/apps/worker/debug_parse.py) | Step 1 |
| 3 | 单元测试 | Step 1 |
| 4 | [debug_parse.py](file:///Users/wuchengke/Desktop/knowhereapi-main/apps/worker/debug_parse.py) 端到端验证 | Step 2 |
| 5 | `knowhere_mcp_server.py` (MVP) | Step 1 |
| 6 | Antigravity Skill 文件 | Step 5 |
| 7 | Antigravity 端到端测试 | Step 5+6, 用户手动 |
