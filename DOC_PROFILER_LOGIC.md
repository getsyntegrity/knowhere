# Doc Profiler 判断逻辑说明

> 文件：`apps/worker/app/services/document_parser/doc_profiler.py`
> 说明：此文档梳理 `profile_document()` 的完整决策链路，并标注当前存在的问题。

---

## ⚠️ 生产现状：大量代码是死逻辑

经过 `parse_service.py` 和 `pdf_parser.py` 源码审查，**当前生产代码只消费以下字段**：

| 消费位置 | 字段 | 作用 |
|----------|------|------|
| `parse_service.py` L159 | `atlas_candidate` | 触发 VLM 视觉确认 |
| `parse_service.py` L164/186 | `doc_category` | atlas 路由（改扩展名 + 走 `atlas_parser`） |
| `parse_service.py` L173 | `page_count` | 页数上限拦截（> 600 报错） |
| `pdf_parser.py` L212 | `route` | **被读取但无实际效果**（L221-246 已注释） |

**以下全部是死代码（不被任何生产路径消费）：**
- `route` / `decision_band` 的 `fast` / `safe_fast` / `gray_zone` 分类
- `estimated_fast_benefit` / `estimated_risk_score` 评分
- 整个 `_classify_route()` 硬门 + safe_fast 判断链
- `scan_type`、`is_multi_column`、`is_degraded_electronic` 等特征
- `has_tables`、`table_signal_strength` 等表格信号
- 所有图像复杂度指标（`significant_image_count`、`large_image_page_ratio` 等）

> 唯一有效的判断路径是：**atlas_candidate 四条件** → VLM 确认 → `doc_category="atlas"` → 走 `atlas_parser`。其余全部走 MinerU standard。

---

## 一、整体流程概览

```
profile_document(file_path)
        │
        ├─ 非 PDF → 直接返回 route=standard (不做任何分析)
        │
        └─ PDF → _profile_pdf()
                    │
                    └─ 子进程: _profile_pdf_worker()
                                │
                                ├─ 1. 采样页
                                ├─ 2. 逐页特征提取
                                ├─ 3. 聚合特征 → DocProfile 字段
                                ├─ 4. 判断 scan_type
                                ├─ 5. 判断 doc_category (atlas_candidate / ppt_converted)
                                └─ 6. 判断 route / decision_band (_classify_route)
```

---

## 二、第一步：页面采样策略

| 条件 | 策略 |
|------|------|
| ≤ 50 页 | 取全部页面 |
| > 50 页 | 按步长均匀抽取约 20 页，强制包含首 3 页 + 末 3 页，去重排序 |

**采样数 `n_sampled`** 是后续所有比率计算的分母，代表实际分析的页数（不是总页数）。

---

## 三、第二步：逐页特征提取

每一页提取以下原始信号：

### 3.1 文本信号
- `text_len`：当前页文本字符数（`page.get_text()`）
- `avg_text_density`：所有采样页 `text_len` 的均值

### 3.2 图像信号
逐图像遍历 `page.get_images(full=True)`：

| 变量 | 含义 |
|------|------|
| `img_total_area` | 当前页所有图像 rect 面积之和 |
| `img_coverage` | `img_total_area / page_area`，上限 1.0 |
| `page_max_rect_ratio` | 当前页单张图像的最大面积占比 |
| `page_significant_image_count` | 当前页"重要图像"数量 |
| `page_medium_image_coverage` | 中等图像的总面积占比（累加） |
| `skinny_count` | 细长图像数量（宽高比 > 50 且高 < 30px，退化扫描特征） |

**"重要图像" (`is_significant`) 判定（三选一）：**
```
area_ratio >= 0.12                                          # 占页面 12% 以上
OR (area_ratio >= 0.05 AND (max_dim >= 400 OR pixels >= 250,000))  # 中等面积但尺寸大
OR (area_ratio >= 0.02 AND pixels >= 500,000)              # 小面积但极大像素
```

**页面级图像标志：**
- `page_has_significant_images = page_significant_image_count > 0 OR page_medium_image_coverage >= 0.18`
- `page_has_large_image = page_max_rect_ratio >= 0.25 OR img_coverage >= 0.35`

**文档级图像聚合：**
| 字段 | 含义 |
|------|------|
| `has_significant_images` | 是否有任何采样页含重要图像 |
| `significant_image_count` | 重要图像总数（含"每页至少计 1"的补偿） |
| `max_image_coverage_on_page` | 所有采样页中单张图像最大面积占比 |
| `pages_with_significant_images` | 含重要图像的页数 |
| `large_image_page_ratio` | `large_image_pages / n_sampled` |
| `avg_image_coverage` | 各页 `img_coverage` 的均值 |

### 3.3 绘图 / 表格信号
遍历 `page.get_drawings()`：

| 变量 | 含义 |
|------|------|
| `line_like_items` | 有笔触的线条 + 矩形等效线段数（stroked） |
| `horizontal_line_items` | 近水平线数量 |
| `vertical_line_items` | 近垂直线数量 |
| `rect_items` | 有笔触的矩形数 |
| `fill_only_rect_items` | 仅填充无笔触的矩形数（背景色块） |

**表格信号判断 (`drawing_table_signal`)：**
```
line_like_items >= 12
AND (
    (H_lines >= 2 AND V_lines >= 2)   # 有交叉线网格
    OR rect_items >= 2                 # 有边框矩形
    OR (line_like_items >= 18 AND H >= 3 AND V >= 3)  # 强密度网格
)
```

> ⚠️ **注意**：`page.find_tables()` 也被调用（`_count_detected_tables`），但其结果 **仅写入 `page_details`（debug 信息）**，不用于路由判断。实际路由只用 `drawing_table_signal`。

**文档级表格聚合：**
| 字段 | 含义 |
|------|------|
| `has_tables` | 是否存在 drawing 表格信号 |
| `table_signal_pages` | 有表格信号的页数 |
| `table_signal_strength` | 各页 `page_table_strength` 的均值（范围 0~1） |

### 3.4 多栏检测
条件：text_blocks >= 4，遍历所有文本块对：
- Y 方向有重叠
- X 方向间距 > 页宽 * 0.15
- 满足上述的对数 >= 3 → 判定为多栏页

文档级：`is_multi_column = multi_col_pages > n_sampled * 0.3`（超过 30% 的采样页是多栏）

### 3.5 退化扫描检测
每页 `skinny_count`（细长图）>= 50 → 视为退化页

文档级：`is_degraded_electronic = degraded_pages > n_sampled * 0.5`

### 3.6 扫描页检测
```
is_scan_page = text_len < 50 AND img_coverage > 0.60
```

### 3.7 复杂页检测
```
is_complex_page =
    table_hit                                                   # 有表格信号
    OR page_has_large_image                                     # 有大图
    OR is_multi_col_page                                        # 多栏
    OR (page_has_significant_images AND text_len < 500)         # 图文混排且文本少
    OR (drawing_count >= 25 AND text_len < 500)                 # 绘图密集且文本少
```

文档级：
- `complex_pages`：复杂页总数
- `complex_page_ratio = complex_pages / n_sampled`

---

## 四、第三步：scan_type 判断

| 结果 | 条件 |
|------|------|
| `scanned` | 扫描页比例 >= 70% |
| `mixed` | 扫描页比例 > 0% 且 < 70% |
| `electronic` | 没有任何扫描页 |

---

## 五、第四步：doc_category 判断

### 5.1 Atlas Candidate（图集候选）
四个条件**全满足**：
```
avg_text_density < 200          # 文本极稀疏
avg_image_coverage > 0.30       # 图像覆盖率高
landscape_ratio >= 0.50         # 至少 50% 采样页是横版
page_count >= 2                 # 非单页
```
→ `atlas_candidate = True`，`doc_category` 保持 `"generic"`（等待 VLM 确认后才升为 `"atlas"`）

### 5.2 PPT 转换文档
条件（在 atlas_candidate 未命中时生效）：
```
landscape_ratio >= 0.80         # 80% 以上横版页
doc_category == "generic"       # 未被标记为 atlas
```
再检查首页宽高比是否接近标准幻灯片比例：
- `4:3 ≈ 1.333`
- `16:9 ≈ 1.778`
- `16:10 ≈ 1.600`
- 容差：± 0.05

满足 → `doc_category = "ppt_converted"`

---

## 六、第五步：路由分类 `_classify_route()`

路由结果为三选一：`safe_standard`、`safe_fast`、`gray_zone`

### 6.1 硬门（Hard Gate）→ safe_standard
任意一项命中则直接路由至 `standard`：

| 条件 | 含义 |
|------|------|
| `scan_type != "electronic"` | 有扫描页 |
| `doc_category != "generic"` | 图集或 PPT |
| `is_multi_column` | 多栏布局 |
| `is_degraded_electronic` | 退化扫描文档 |
| `has_tables` | 有表格绘图信号 |
| `max_image_coverage_on_page >= 0.25 OR pages_with_significant_images >= 3 OR large_image_page_ratio >= 0.15` | 重图像文档 |
| `complex_page_ratio >= 0.20` | 复杂页超过 20% |
| `page_count > 150` | 超长文档 |

### 6.2 安全快速通道（Safe Fast）→ safe_fast
硬门全部未命中后，再检查以下 8 项**全部通过**：

| 编号 | 条件 | 阈值 |
|------|------|------|
| 1 | `page_count <=` | 80 |
| 2 | `avg_text_density >=` | 120 |
| 3 | `has_significant_images == False` | — |
| 4 | `max_image_coverage_on_page <=` | 8% |
| 5 | `avg_image_coverage <=` | 3% |
| 6 | `complex_page_ratio <=` | 5% |
| 7 | `text_density_std <=` | 600 |
| 8 | `estimated_risk_score <=` | 0.35 |

全部通过 → `route=fast, band=safe_fast`

### 6.3 灰区（Gray Zone）→ gray_zone
Safe Fast 有任意一项失败 → `route=standard, band=gray_zone`（保守回退）

---

## 七、评分函数

### 7.1 `estimated_fast_benefit`（快速通道收益估算）
```
benefit = 0.35 * page_factor + 0.40 * density_factor + 0.25 * stability_factor
```

| 子分 | 计算 |
|------|------|
| `page_factor` | 2页→0.35, 3-10页→0.7, 11-80页→1.0, 81-150页→0.8, >150页→0.45 |
| `density_factor` | clamp(avg_text_density / 1200, 0, 1) |
| `stability_factor` | clamp(1 - complex_page_ratio*1.5 - large_image_page_ratio*1.2 - table_signal_strength*0.8, 0, 1) |

### 7.2 `estimated_risk_score`（风险估算）
```
risk = 基础风险项累加 + 连续风险项累加
```

**基础风险项（固定值）：**
| 条件 | 加分 |
|------|------|
| scan_type != "electronic" | +0.35 |
| doc_category != "generic" | +0.20 |
| is_multi_column | +0.20 |
| is_degraded_electronic | +0.20 |
| has_tables | +0.30 |
| page_count > 150 | +0.10 |

**连续风险项（比例项）：**
| 条件 | 上限 |
|------|------|
| large_image_page_ratio * 1.2 | max 0.20 |
| complex_page_ratio * 0.8 | max 0.20 |
| table_signal_strength * 0.2 | max 0.15 |
| pages_with_significant_images * 0.04 | max 0.12 |

最终 clamp 到 [0, 1]。

---

## 八、发现的问题与建议

### ✅ 已修复：`has_tables` 和 `has_detected_tables` 完全重复

已删除 `has_detected_tables` 字段，统一使用 `has_tables`。

---

### ✅ 已修复：Atlas 判断中局部变量覆盖顶层常量

已删除未使用的 `ATLAS_IMAGE_COVERAGE_MIN = 0.40`，将函数体内的 `ATLAS_CANDIDATE_IMAGE_COVERAGE_MIN = 0.30` 提升为顶层常量。

---

### ✅ 已修复：`page_significant_coverage` 计算但从未使用

已删除死代码。

---

### ❌ 问题 4：风险评分中 `has_tables` 与硬门重复计数

**位置**：`_estimate_risk_score()` 和 `_classify_route()`

`has_tables` 在两处都被用到：
- 硬门：`has_tables` → 直接拦截到 `safe_standard`（路由关键判断）
- 风险分：`has_tables` → `risk += 0.30`

一旦 `has_tables=True`，文档已经被硬门拦下，风险分里的 `+0.30` 对路由没有任何影响，只是数值虚高。这不是 bug，但是冗余的，且对未来"灰区文档"的风险评估产生干扰。

**建议**：风险分应评估"通过硬门的文档"的相对风险，不应累加已经被硬门覆盖的信号。考虑拆分为 `_estimate_risk_for_gray_zone()`。

---

### ⚠️ 问题 5：PPT 检测仅看第一页宽高比

**位置**：L710
```python
ref_page = doc_page_sizes[0] if doc_page_sizes else None
```
`doc_page_sizes` 包含所有采样页的尺寸，但判断只取 `[0]`（即 **全文档第一页**的尺寸）。如果首页是封面（尺寸异常），会导致误判。

**建议**：取 `doc_page_sizes` 中最常见的宽高比，或取中位数。

---

### ⚠️ 问题 6：`significant_image_count` 的计数逻辑有补偿歧义

**位置**：L586
```python
significant_image_count += page_significant_image_count or 1
```
当 `page_has_significant_images=True` 但 `page_significant_image_count=0`（即仅因 `page_medium_image_coverage >= 0.18` 触发）时，补偿计为 1。
这个 `or 1` 的语义模糊：`significant_image_count` 的值无法精确反映实际图像数量，仅代表"至少有 1 张"的页面数追踪。

**建议**：`significant_image_count` 的语义应限定为"由 is_significant 判断命中的图像数"，medium_image_coverage 触发的情况单独用 `pages_with_medium_images` 计数；或直接在注释中说明这是"近似值"。

---

### ℹ️ 信息：`min_text_density_page` 命名与含义不匹配

**位置**：L665
```python
profile.min_text_density_page = min(text_lengths) if text_lengths else 0.0
```

命名暗示"密度"但实际存储的是原始字符数（`text_len`），而不是归一化的密度值（没有除以页面面积）。`avg_text_density` 也是同样的问题——都是字符数均值，不是真正的密度。字段命名不一致，但在整个代码库中已统一使用，改动成本较高，建议在注释中注明单位是"字符数"而不是"字符/面积"。

---

## 九、变量依赖关系图

```
page.get_text()
    └─ text_len → avg_text_density, text_density_std, min_text_density_page
                → is_scan_page (text_len < 50)
                → is_complex_page (text_len < 500)

page.get_images()
    └─ img_coverage → avg_image_coverage
    └─ page_max_rect_ratio → max_image_coverage_on_page
    └─ is_significant → has_significant_images, pages_with_significant_images,
                        significant_image_count [hard gate, safe_fast check]
    └─ page_has_large_image → large_image_page_ratio [hard gate, safe_fast check, risk]
    └─ skinny_count → is_degraded_electronic [hard gate, risk]

page.get_drawings()
    └─ line_like_items, H/V lines, rect_items
        └─ drawing_table_signal → has_tables [hard gate, risk]
        └─ page_table_strength → table_signal_strength [risk]

page.get_text("blocks")
    └─ text_blocks → is_multi_col_page → is_multi_column [hard gate, risk]

is_scan_page → scan_type [hard gate, risk]
is_complex_page → complex_page_ratio [hard gate, risk, safe_fast check]

landscape_pages / n_sampled
    └─ → is_atlas_candidate [→ atlas_candidate flag]  ← 🟢 生产唯一活跃路径
    └─ → PPT detection [→ doc_category=ppt_converted] [hard gate]

_classify_route(profile)  ← ⚫ 生产未使用
    └─ hard gates → safe_standard
    └─ safe_fast checks (8项) → safe_fast / gray_zone
```

---

## 十、下一步优化建议

当前关于 fast path（`route`）与风险评分的体系完全是脱离生产消费的死代码，且风险评分采用纯硬规则线性叠加，显得过于粗糙和冗余。下一步优化建议如下：

1. **清理沉淀，移除死代码：**
   如果近期不打算重启 fast path，或者当真正需要引入其他轻量级 parser 路径时会有不同的方案，建议直接移除 `DOC_PROFILER` 中关于 `route`、`decision_band` 以及风险评分（`estimated_fast_benefit` / `estimated_risk_score` / `_classify_route`）的代码块，仅保留用于探测图集及退化的核心统计特征。
2. **重构评分体系：**
   若决定保留或重启 fast path，不应再用基于写死的数值阈值累加方式。应根据过往积累的大量生产数据集建立机器学习分类模型（哪怕是轻量级的树模型），综合评估“能否用此路径且保证低风险”，而非拍脑袋给定诸如 `+0.30`、`+0.20` 并在不同逻辑节点（硬门和风险分）重复计费。
3. **隔离诊断与干预：**
   将用于人类调试分析的特征（如 `page.find_tables()`）严密阻断于路由决策之外（仅写入 `profile.reasoning` / `page_details`）。
4. **抽离常数管理：**
   将大量阈值常量提取至配置文件，以便于运维和验证环境动态调参，避免由于硬编码导致的重构黑盒。

---

*最后更新：2026-04-09*
