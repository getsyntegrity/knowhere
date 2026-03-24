---
name: knowhere_memory
description: Search knowledge from Knowhere parsed documents using 4-tier retrieval.
user-invocable: false
---

# Knowhere Knowledge Memory

## 检索策略（按优先级）

### Tier 2: LLM 自主导航（推荐）

1. **get_knowledge_map()** → 查看所有文档的关键词、重要性、跨文件关联
2. **get_document_structure(kb_id, doc_name)** → 查看目标文档的章节目录
3. **read_document_chunks(kb_id, doc_name, section_path)** → 读取目标章节内容
4. **discover_relevant_files(query)** → 补充发现：grep 全部内容找出可能遗漏的文件

> 将步骤 1 的判断 ∪ 步骤 4 的发现作为最终检索范围

### Tier 3: 关键词搜索（降级）

- **search_knowledge(query)** → 自动关键词匹配 + 评分，返回 top_k 结果

### Tier 4: 直接读文件（最后兜底）

- 用 read 工具直接读 `~/.knowhere/{kb_id}/{doc_name}/chunks_slim.json`

## 回答规范

- 引用文件名 + chunk path
- 跨文档 edges 也要查
- 用用户的语言回答
