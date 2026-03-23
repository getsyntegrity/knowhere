# Knowhere 知识图谱集成设计文档

> **版本**: v1.1 | **日期**: 2026-03-21 | **作者**: Ontos AI

---

## 1. 核心思路

将 Knowhere 从「文档解析」升级为「解析 + 记忆构建」一站式服务。**图谱构建集成到解析流程中，解析即建图谱，一次调用完成。**

```
用户发文件 (TG/飞书/企微/手动)
    ↓
客户端调用 Knowhere 解析 API（传入 kb_id）
    ↓
服务端: 解析文档 → 生成 chunks → 自动构建/增量更新图谱
    ↓
返回 chunks + knowledge_graph（一个响应）
    ↓
客户端存储到 ~/.knowhere/{kb_id}/
    ↓
Agent 通过 knowhere_memory Skill 读取记忆
```

---

## 2. 服务端改动

### 2.1 解析 API 扩展

在现有解析 API 的请求中新增 `kb_id` 参数，响应中新增 `knowledge_graph`：

**请求新增字段**:

```json
{
  "kb_id": "user_ontosai",            // 知识库标识（用户维度）
  "source": "telegram",               // 来源渠道
  "source_channel": "group:-100353"   // 来源渠道标识
}
```

**响应新增字段**:

```json
{
  "knowledge_graph": {
    "version": "2.0",
    "stats": { "total_files": 5, "total_chunks": 327, "total_cross_file_edges": 3 },
    "files": { ... },
    "edges": [ ... ]
  },
  "chunk_stats": { ... }
}
```

> 如果请求中未传 `kb_id`，则不构建图谱，行为与现有 API 一致（向后兼容）。

### 2.2 服务端处理流程

```python
# 在现有 parse pipeline 末尾追加
def post_parse_build_graph(kb_id, doc_id, new_chunks):
    existing_chunks = load_kb_chunks(kb_id)       # 服务端存储的历史 chunks
    existing_graph = load_knowledge_graph(kb_id)

    save_chunks(kb_id, doc_id, new_chunks)         # 累积存储

    if existing_graph is None:
        connections = build_connections(new_chunks)
        graph = build_knowledge_graph(new_chunks, connections, kb_id)
    else:
        graph = update_knowledge_graph(
            existing_graph, new_chunks, existing_chunks, kb_id
        )

    save_knowledge_graph(kb_id, graph)
    return graph
```

### 2.3 服务端存储

服务端为每个 `kb_id` 维护 chunks 历史记录，用于增量构建：

```
{DATA_DIR}/kb/{kb_id}/{doc_id}/chunks.json
```

---

## 3. 本地存储结构 (`~/.knowhere/`)

### 3.1 目录结构

```
~/.knowhere/                              # 系统级，所有 Agent 可访问
└── {kb_id}/                              # 用户维度，如 "user_ontosai"
    ├── knowledge_graph.json              # 统一知识图谱（跨渠道关联）
    ├── chunk_stats.json                  # 各 chunk 使用统计
    └── {doc_id}/                         # 每个文档一个子目录
        ├── chunks.json                   # 全部 chunks
        ├── metadata.json                 # 文档元信息（含来源标记）
        ├── hierarchy.json                # 文档结构树
        ├── images/                       # 提取的图片
        └── tables/                       # 提取的表格
```

### 3.2 kb_id 设计原则

**kb_id = 用户/租户**，不是渠道。来源信息记录在 metadata 中：

| 场景 | kb_id 示例 |
|------|-----------|
| 个人用户 | `user_chengke` |
| 组织 | `org_ontosai` |

---

## 4. Metadata 字段

> 以下字段仅在存储层新增，**不修改解析过程产出的任何字段**。

### 4.1 文档 metadata（`{doc_id}/metadata.json`）

```json
{
  "doc_id": "Tesla-Q4-2025",
  "title": "Tesla Q4 2025 Update",
  "source": "telegram",
  "source_channel": "group:-1003531224749",
  "source_label": "TSLA-Q4-2025-Update.pdf",
  "original_file_name": "TSLA-Q4-2025-Update.pdf",
  "ingested_at": "2026-03-17T09:52:01.912Z",
  "job_id": "job_41dda0f5089e",
  "checksum": "sha1:3e821de8d2d...",
  "chunk_count": 71,
  "statistics": {
    "total_chunks": 71,
    "text_chunks": 35,
    "image_chunks": 19,
    "table_chunks": 17
  }
}
```

新增字段：

| 字段 | 说明 |
|------|------|
| `source` | 来源渠道：`"telegram"` / `"feishu"` / `"wecom"` / `"manual"` |
| `source_channel` | 渠道标识，如 `"group:-100353"` |
| `checksum` | 文件指纹，用于去重 |

### 4.2 knowledge_graph.json

沿用现有 v2.0 格式，不修改。

### 4.3 chunk_stats.json

Agent 每次读取 chunk 时 bump `hit_count`，用于计算文件重要度。

---

## 5. 客户端改动（knowhere-claw 插件）

### 5.1 OpenClaw 配置 (`openclaw.json`)

```json
"knowhere-claw": {
  "enabled": true,
  "config": {
    "scopeMode": "global",
    "knowledgeGraph": {
      "enabled": true,
      "kbIdSource": "global",
      "kbId": "user_ontosai"
    }
  }
}
```

### 5.2 插件流程变更

```
现在:  parse API → 返回 chunks → 本地 JS 建图谱（简化版）
改后:  parse API(kb_id) → 返回 chunks + knowledge_graph → 直接存到 ~/.knowhere/
```

插件只需：接收响应 → 保存 `knowledge_graph.json` 到 `~/.knowhere/{kb_id}/`。**不再需要本地图谱构建代码。**

---

## 6. 实施计划

### Phase 1 — 立即可用（零代码改动）

修改 Mac Mini `openclaw.json` 配置（参见 5.1），重启 OpenClaw。

效果：`scopeMode: "global"` 共享文档池 + 现有 JS 版图谱构建生效。

### Phase 2 — 服务端图谱集成

1. 解析 API 增加 `kb_id` 参数，响应增加 `knowledge_graph` 字段
2. 服务端在 parse 完成后自动调用 `build_and_deploy()`
3. knowhere-claw 插件改为直接保存 API 返回的图谱

效果：Python 全功能版图谱（增量更新、精确 TF-IDF），客户端零依赖。

---

## 7. Mac Mini 部署（Phase 1）

```bash
ssh ontosai@<mac-mini-ip>
nano ~/.openclaw/openclaw.json    # 修改 knowhere-claw config（见 5.1）
openclaw restart
```

验证：
1. TG 发文件 → 等待解析完成
2. `ls ~/.knowhere/user_ontosai/` → 应有文档子目录 + `knowledge_graph.json`
3. TG 问 "我之前发过什么文件？" → Agent 通过记忆回答
