# PDF 表格内嵌图片恢复方案

> 关联任务: TASKS.md → **表格内嵌图片 Phase 2**
> 状态: TODO
> 创建: 2026-02-27

---

## 背景

MinerU 解析 PDF 时自动合并跨页表格为单个 `<table>` HTML，但**丢弃表格内的图片**（`<td>` 为空）。
DOCX 场景（Phase 1）已通过 `iter_block_items` + `table2html` 解决，本方案针对 PDF 场景。

### 测试验证

| 场景 | 测试文件 | 结果 |
|------|----------|------|
| PDF 表格内图片 | `test_files/cross_page_table_test.pdf` | ❌ MinerU HTML 中 Status 列为空 `<td>` |
| DOCX 表格内图片 | `tmp_files/cross_page_table_test.docx` | ✅ 35 张图片全部正确提取 (MD5 验证) |

---

## 方案 D: PyMuPDF 坐标提取 (推荐)

### 原理

```
MinerU 输出 full.md (HTML 表格, 图片 <td> 为空)
        ↓
PyMuPDF page.get_images() + page.get_image_rects()
→ 获取图片精确坐标 (x0, y0, x1, y1)
        ↓
layout.json → 每页 table block 的 bbox
        ↓
图片 rect ∩ table bbox → 确定图片属于哪个表格
        ↓
按 y 坐标排序 → 映射到 HTML 行号 → 注入回空 <td>
```

### 实现位置

`pdf_parser.py` 的 `parse_pdfs()` 函数中，MinerU 完成后、`parse_md()` 之前：

```python
async def parse_pdfs(...):
    await upload_and_parse(...)            # MinerU 解析
    recover_table_images(pdf_path, output_dir)  # NEW: 补回表格图片
    parsed_df = await parse_md(...)        # MD 解析
```

新建模块: `pdf_table_image_recovery.py`

#### 核心步骤

1. 读取 `layout.json` → 获取每页 table block bbox
2. PyMuPDF 提取图片 → 坐标 + 像素数据
3. 过滤: 图片 rect 在 table bbox 内 → 标记为表格图片
4. 按 y 坐标排序 → 推断行号 (基于表格 bbox 高度等分)
5. 解析 `full.md` 中的 `<table>` HTML → 找空 `<td>`
6. 注入 `<em>[image-N]</em>` 到对应空 `<td>`
7. 保存图片到 `images/` 目录
8. 重写 `full.md`

### ⚠️ 限制

| 限制 | 说明 |
|------|------|
| **扫描件 PDF 无效** | 扫描件中"图片"是整页光栅图，PyMuPDF 无法提取独立表格内图片对象 |
| **仅限本地文件** | 需要原始 PDF 路径；远程 URL 需额外下载步骤 |
| **不等高行映射偏差** | y 坐标等分估算行号，对行高差异大的表格可能偏差 |
| **同一行多图** | 需按 x 坐标排序分配不同列 |

---

## 方案 C: MinerU 交叉对比 (备选)

MinerU 虽然在 table block 内忽略图片，但在非 table 区域能正确识别图片。
方案: 让 MinerU 同时以 table 模式和 image 模式解析同一区域，交叉对比结果。

**缺点**: 需要定制 MinerU 的识别策略，对远端 API 模式不可行。暂搁置。

---

## 验证方法

```bash
cd apps/worker && python3 debug_parse.py
# 测试文件: tmp_files/cross_page_table_test.pdf
```

验证项:
- [ ] `full.md` 中 `<table>` 的空 `<td>` 是否被注入 `[image-N]`
- [ ] `images/` 目录下是否有提取的图片
- [ ] 图片数量 = 35
- [ ] 图片 MD5 与原始图标一致
