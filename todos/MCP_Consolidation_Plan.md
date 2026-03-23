# Knowhere MCP 整合方案 — 双 Server 分析与路线图

> 日期: 2026-03-23 | 作者: Antigravity Agent

---

## 1. 现状：两个 MCP Server

| 维度 | 旧: `worker/app/services/mcp/knowhere_mcp_server.py` | 新: `knowhere-mcp/server.py` |
|------|------|------|
| **定位** | 🏠 本地知识检索 — 读 `~/.knowhere/` 已解析数据 | ☁️ 云端解析服务 — 调 `api.knowhereto.ai` |
| **工具** | `search_knowledge` (关键词搜索) + `get_knowledge_overview` (KB 概览) | `parse_document` + `get_job_status` + `get_parsed_chunks` |
| **数据源** | 本地 `knowledge_graph.json` + `chunks.json` | Knowhere Cloud API |
| **依赖** | `mcp` (老SDK) + `jieba` + `connect_builder` | `fastmcp` v3 + `requests` |
| **耦合** | 🔴 深耦合 worker (`from app.services.connect_builder.graph_builder`) | 🟢 零耦合，独立包 |
| **SDK版本** | `mcp.server.fastmcp.FastMCP` (旧) | `fastmcp.FastMCP` v3 (新) |

### 核心结论

> **它们不是重复功能，而是互补的两个阶段**：新的 = "造知识"(parse)，旧的 = "用知识"(retrieve)。

---

## 2. 旧 MCP 的问题

| # | 问题 | 影响 |
|---|------|------|
| 1 | 深耦合 `connect_builder.graph_builder.record_chunk_hits` | 无法独立运行/发布 |
| 2 | 使用旧版 `mcp.server.fastmcp` 而非 `fastmcp` v3 | API 不兼容 |
| 3 | 搜索是纯关键词 (jieba 分词 + term count) | 无向量/语义检索 |
| 4 | 只能读 `~/.knowhere/` 本地目录 | 不支持 Cloud KB |
| 5 | `description=` 在 FastMCP v3 已改为 `instructions=` | 启动会报错 |

### 旧 MCP 有价值的部分

- ✅ `search_knowledge` 的设计思路：关键词 + KG edge 关联
- ✅ `get_knowledge_overview` 的 KB 结构展示
- ✅ `_format_files_overview` 的人类可读输出

---

## 3. 路线选项

### 方案 A：合并为一个 MCP Server（推荐 ✅）

```
knowhere-mcp/server.py (统一服务)
├── parse_document()         ← Cloud API: 解析新文档
├── get_job_status()         ← Cloud API: 查询 job
├── get_parsed_chunks()      ← Cloud API: 下载结果
├── search_knowledge()       ← Cloud API retrieve (如有) 或本地搜索
└── get_knowledge_overview() ← Cloud API 或本地 KB 概览
```

**优势**：
- 用户只配置 1 个 MCP Server
- 统一 SDK 版本（fastmcp v3）
- 独立可发布，零耦合

**挑战**：
- 需要决定 `search_knowledge` 走 Cloud API 还是保留本地搜索
- 如果保留本地搜索，需解耦 `connect_builder` 依赖

### 方案 B：保持两个独立 Server

```
knowhere-mcp/server.py        ← Cloud: parse + job 管理
worker/mcp/knowhere_mcp_server.py  ← Local: search + overview (重构去耦合)
```

**优势**：
- 职责清晰分离
- 本地搜索不依赖网络

**劣势**：
- 用户需配置 2 个 MCP Server
- 维护两套代码 + 两套 SDK

### 方案 C：分层架构

```
knowhere-mcp/
├── server.py          ← 统一入口，注册所有 tool
├── cloud_tools.py     ← Cloud API tools (parse, job, chunks)
└── local_tools.py     ← 本地 KB tools (search, overview)
```

**优势**：统一入口 + 代码分离
**劣势**：稍复杂

---

## 4. 决策依赖

继续前需要确认：

| 问题 | 影响 |
|------|------|
| Knowhere API 是否有/将有 `retrieve` endpoint？ | 决定 `search_knowledge` 走 Cloud 还是本地 |
| 知识图谱是否仍存储在 `~/.knowhere/`？ | 决定本地搜索是否仍有意义 |
| `connect_builder.record_chunk_hits` 是否仍需要？ | 决定旧 MCP 的 stats 功能是否保留 |
| 目标用户是否需要离线搜索？ | 决定是否保留本地搜索能力 |

---

## 5. 建议执行步骤

| 步骤 | 内容 | 前置条件 |
|------|------|---------|
| 1 | 确认 API 是否有 retrieve endpoint | 用户确认 |
| 2 | 如果有：将 `search_knowledge` 改为调 Cloud API | 步骤 1 |
| 2' | 如果没有：提取旧 MCP 的搜索逻辑，解耦 `connect_builder` | 步骤 1 |
| 3 | 合并到 `knowhere-mcp/server.py` (方案 A 或 C) | 步骤 2 |
| 4 | 升级 SDK: `mcp.server.fastmcp` → `fastmcp` v3 | 步骤 3 |
| 5 | 标记旧 `worker/mcp/` 为 deprecated | 步骤 4 |

---

## 6. 参考文件

| 文件 | 路径 |
|------|------|
| 旧 MCP Server | `apps/worker/app/services/mcp/knowhere_mcp_server.py` (315 行) |
| 新 MCP Server | `knowhere-mcp/server.py` (~190 行) |
| connect_builder | `apps/worker/app/services/connect_builder/` |
| graph_builder | `apps/worker/app/services/connect_builder/graph_builder.py` |
