# Agentic Profiler — 文档智能分类与路由

> 状态: **已实现 (MVP)**
> 创建: 2026-02-27
> 优先级: 主线任务

---

## 1. 目标

在文档进入 `checkerboard_inject_parse()` 之前，用**轻量级分析 (~50-300ms)** 生成 `DocProfile`，驱动路由决策和类型标注。当前 MVP 针对 PDF，后续可扩展至 DOCX、PPTX 等。

### 核心收益

- **Fast Path**: 简单 PDF 用 `pymupdf4llm` 本地转换，跳过 MinerU 远程调用 → **速度 10-20x，成本归零**
- **类型感知**: 扫描件/图集/PPT 转 PDF 等走针对性策略 → **解析质量提升**
- **可扩展**: Profile 结构开放，新增类型只需加判断规则

---

## 2. Profile 数据结构

```python
@dataclass
class DocProfile:
    file_type: str                  # "pdf", "docx", "pptx", ...
    route: Literal["fast", "standard"]
    scan_type: Optional[Literal["electronic", "scanned", "mixed"]] = None
    doc_category: Literal["generic", "atlas", "ppt_converted"] = "generic"

    # 原始特征
    page_count: int = 0
    avg_text_density: float = 0     # 每页平均字符数
    avg_image_coverage: float = 0   # 图片面积 / 页面面积 (0-1)
    has_tables: bool = False
    has_embedded_fonts: bool = False
    is_multi_column: bool = False   # 多栏排版
    sample_text: str = ""           # 前 500 字
    reasoning: str = ""             # 决策依据
```

---

## 3. 二维分类体系

两个维度**独立判定、互不冲突**，一个 PDF 可以同时是 `scanned + atlas`。

### 3.1 维度一: scan_type

| 分类 | 条件 |
|------|------|
| **scanned** | ≥70% 采样页为扫描页 |
| **mixed** | 有扫描页但 < 70% |
| **electronic** | 0 扫描页 |

**扫描页判定**: `text_len < 50 且 img_coverage > 60%`

### 3.2 维度二: doc_category

按优先级依次判定：

| 类型 | 条件 | 说明 |
|------|------|------|
| **atlas** | `avg_text < 200/页` 且 `avg_img > 40%` | 图集/图册 |
| **ppt_converted** | `≥80% 横向页` 且 纵横比匹配幻灯片格式 | PPT 转 PDF |
| **generic** | 以上都不满足 | 默认类型 |

**幻灯片格式**: 4:3 (1.333) / 16:9 (1.778) / 16:10 (1.600)，容差 ±5%

---

## 4. 路由决策

```
                    ┌─────────────────┐
                    │   输入 PDF      │
                    └────────┬────────┘
                             ▼
                ┌────────────────────────────┐
           Yes  │ scanned / atlas /          │
          ┌─────│ ppt_converted ?            │
          │     └────────────┬───────────────┘
          │                  │ No
          ▼                  ▼
     ┌──────────┐  ┌─────────────────┐
     │ STANDARD │  │ multi_column ?  │
     └──────────┘  └──┬──────────┬───┘
                  Yes │          │ No
                      ▼          ▼
               ┌──────────┐ ┌───────────────┐
               │ STANDARD │ │ text ≥ 100 ?  │
               └──────────┘ └──┬─────────┬──┘
                           Yes │         │ No
                               ▼         ▼
                         ┌────────┐ ┌──────────┐
                         │  FAST  │ │ STANDARD │
                         └────────┘ └──────────┘
```

**一句话**: 只有 **单栏、非扫描、非图集、非 PPT、有可提取文本 (≥100 字/页)** 的电子版 PDF 走 fast。

---

## 5. 两条路径的引擎

| | Fast Path | Standard Path |
|---|---|---|
| **引擎** | `pymupdf4llm.to_markdown()` | MinerU VLM API |
| **图片** | ✅ 提取到 `images/` + md 引用 | ✅ VLM 理解 |
| **表格** | ✅ markdown 表格 | ✅ 精准还原 |
| **速度** | 0.5-4s (本地) | 10-60s (API) |
| **成本** | 0 | API 调用费 |
| **输出** | `full.md` + `images/` | `full.md` + `images/` |
| **下游** | `parse_md()` | `parse_md()` (完全兼容) |

---

## 6. 集成架构

```
kb_tasks.py
  └── S3 下载到 local_temp_path
        └── checkerboard_inject_parse(local_path, ...)       # parse_service.py
              ├── profile = profile_document(local_path)     # doc_profiler.py (~150ms)
              ├── 📋 log profile.summary()
              └── if PDF:
                    parse_pdfs(path, profile=profile)         # pdf_parser.py
                      ├── fast  → pymupdf4llm → full.md → parse_md()
                      └── standard → MinerU VLM → full.md → parse_md()
```

### 涉及文件

| 文件 | 角色 |
|------|------|
| `doc_profiler.py` | 核心分析模块：特征提取 + 分类判定 |
| `parse_service.py` | 集成入口：调用 profiler，传递 profile 给各 parser |
| `pdf_parser.py` | PDF 路由执行：根据 `profile.route` 选择引擎 |

---

## 7. 采集的 6 个特征

| 特征 | 提取方式 | 用途 |
|------|---------|------|
| `avg_text_density` | `page.get_text()` 字符数 | scan_type / fast 判定 |
| `avg_image_coverage` | `page.get_image_rects()` 面积比 | scan_type / atlas 判定 |
| `has_tables` | drawings 中线条 ≥ 10 条 | 备用 |
| `has_embedded_fonts` | `page.get_fonts()` | 备用 |
| `is_multi_column` | 文本块 Y 重叠 + X 分离 ≥ 3 对 | fast 防护 |
| `orientation` | 页面宽高比 | ppt_converted 判定 |

采样策略: ≤50 页全量分析，>50 页均匀采样 20 页 + 首尾各 3 页。

---

## 8. 验证结果

| 文件 | scan_type | category | route | 原因 |
|------|-----------|----------|-------|------|
| 表格 PDF (3p) | electronic | generic | **standard** | multi-column |
| 英文报告 (36p) | electronic | generic | **standard** | multi-column |
| PPT 转 PDF (16p) | electronic | **ppt_converted** | **standard** | 16:9 横向 |
| 评估表 (6p) | electronic | generic | **standard** | text=0 (纯矢量) |
| 22G101 图集 (64p) | **scanned** | **atlas** | **standard** | 扫描 + 图集 |

Profiler 耗时: 72-303ms per file。

---

## 9. 后续扩展

| 阶段 | doc_category | 触发条件 |
|------|-------------|---------|
| Phase 2 | `paper` (科研论文) | sample_text 含 "Abstract/摘要/References" |
| Phase 2 | `patent` (专利) | sample_text 含 "权利要求/Claims" |
| Phase 3 | `legal` (法律文件) | sample_text 含 "第X条/甲方乙方" |
| Phase 3 | `spec` (规范手册) | 大量编号条款 + 表格 |

Phase 2+ 可扩展 `profile_document()` 支持 DOCX / PPTX profiling。每个类型只需在 `doc_profiler.py` 中添加规则，不影响主流程。
