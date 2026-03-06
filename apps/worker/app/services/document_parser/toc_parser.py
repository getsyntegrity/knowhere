"""
TOC (Table of Contents) Parser Module
Migrated from sxjg/app/kbs/toc_parser.py

Provides functionality for:
- Detecting TOC (Table of Contents) candidates in markdown documents
- Detecting TOC in DOCX documents (SDT containers, styles, field codes)
- Using LLM to determine precise TOC boundaries
- Analyzing TOC hierarchy structure
- Building nested tree structures from TOC
"""

import re
import pandas as pd
from loguru import logger
from lxml import etree

from app.services.common.kb_utils import normalize_md, truncate_text
from app.services.document_parser.table_parser import df2md
from app.services.document_parser.html_parser import df2html
from app.services.document_parser.layout_parser import hiearchy_llm, judge_by_conditions, remove_by_conditions
from shared.services.ai.ai_query_service_sync import sync_ai_query_service as ai_query_service
from shared.services.ai.prompt_service import build_prompt
from shared.services.ai.response_process_service import eval_response


# ==================== DOCX TOC Detection Functions ====================

def get_toc_level(elem, ns):
    """
    检测段落样式是否为 TOC 样式
    
    Args:
        elem: XML 段落元素
        ns: XML 命名空间
    
    Returns:
        bool: True 如果是 TOC 样式
    """
    style = elem.find('.//w:pPr/w:pStyle', namespaces=ns)
    if style is not None:
        val = style.get('{%s}val' % ns['w'])
        if val:
            val_lower = val.lower().strip()
            if "toc" in val_lower or "目录" in val:
                return True
    return False


def detect_sdt_toc(elem, ns):
    """
    检测 SDT (Structured Document Tag) 目录容器
    Word 自动生成的目录通常被包装在 sdt 元素中
    
    Args:
        elem: SDT 元素
        ns: XML 命名空间
    
    Returns:
        dict: {
            'is_toc_sdt': bool - 是否是目录 SDT,
            'gallery_type': str - docPartGallery 类型
        }
    """
    tag = etree.QName(elem.tag).localname if isinstance(elem.tag, str) else None
    
    if tag != 'sdt':
        return {'is_toc_sdt': False, 'gallery_type': None}
    
    is_toc_sdt = False
    gallery_type = None
    
    sdt_pr = elem.find('.//w:sdtPr', namespaces=ns)
    if sdt_pr is not None:
        doc_part_obj = sdt_pr.find('.//w:docPartObj', namespaces=ns)
        if doc_part_obj is not None:
            doc_part_gallery = doc_part_obj.find('.//w:docPartGallery', namespaces=ns)
            if doc_part_gallery is not None:
                gallery_type = doc_part_gallery.get('{%s}val' % ns['w'])
                if gallery_type and 'table of contents' in gallery_type.lower():
                    is_toc_sdt = True
    
    return {
        'is_toc_sdt': is_toc_sdt,
        'gallery_type': gallery_type
    }


def detect_doc_tocs(elem, ns):
    """
    检测目录区域，支持两种检测方式：
    1. 段落样式检测 (TOC 样式)
    2. 域代码检测 (instrText)
    
    注意：SDT 容器检测使用 detect_sdt_toc 函数
    
    Args:
        elem: XML 段落元素
        ns: XML 命名空间
    
    Returns:
        dict: {
            'is_style': bool - 是否是 TOC 样式,
            'is_field_start': bool - 是否是 TOC 域开始,
            'is_field_end': bool - 是否是域结束
        }
    """
    is_style = get_toc_level(elem, ns)
    is_field_start = False

    instrs = elem.findall('.//w:instrText', namespaces=ns)
    for instr in instrs:
        if instr.text:
            instr_text_lower = instr.text.lower()
            if 'toc' in instr_text_lower or 'table of contents' in instr_text_lower or '目录' in instr.text:
                is_field_start = True
                break

    is_field_end = False
    if not is_style:
        fldchars = elem.findall('.//w:fldChar', namespaces=ns)
        for fld in fldchars:
            if fld.get('{%s}fldCharType' % ns['w']) == 'end':
                is_field_end = True
                break
    
    return {
        'is_style': is_style,
        'is_field_start': is_field_start,
        'is_field_end': is_field_end
    }


# ==================== Markdown TOC Detection Functions ====================


def is_content_line(line: str) -> bool:
    """
    Check if a line is valid content for TOC candidates.
    Filter out table tags and LaTeX formulas.
    
    Args:
        line: the line to check
    
    Returns:
        True if the line is valid content, False if it should be filtered out
    """
    stripped = line.strip().lower()
    
    # Filter out html lines
    # TODO if table extract it as lines but keep the id span as 1
    if stripped.startswith("<table>"):
        return False
    
    if stripped.startswith("!["):
        return False

    # Filter out lines containing LaTeX patterns
    latex_patterns = [
        r"\\mathrm\b",
        r"\\frac\b",
        r"\\sum\b",
        r"\\int\b",
        r"\\sqrt\b",
        r"\\alpha\b",
        r"\\beta\b",
        r"\\gamma\b",
        r"\\delta\b",
        r"\\theta\b",
        r"\\lambda\b",
        r"\\sigma\b",
        r"\\omega\b",
        r"\\partial\b",
        r"\\infty\b",
        r"\\left\b",
        r"\\right\b",
        r"\\begin\{",
        r"\\end\{",
        r"\\text\b",
        r"\\mathbf\b",
        r"\\mathit\b",
        r"\\times\b",
        r"\\cdot\b",
        r"\\leq\b",
        r"\\geq\b",
        r"\\neq\b",
        r"\\approx\b",
    ]
    
    for pattern in latex_patterns:
        if re.search(pattern, line, re.IGNORECASE):
            return False
    return True


def detect_toc_candidates(md_lines: list, limit_: int = 100) -> tuple:
    """
    Detect TOC candidates (support multiple TOC areas)
    
    策略：从 start_idx 开始向后扫描，收集恰好 limit_ 个有效行
    同时记录完整的原始范围 [start_idx, end_idx]，便于后续过滤整个目录区域
    
    Args:
        md_lines: markdown lines list
        limit_: 目标有效行数（不是最大扫描行数）
    
    Returns:
        Tuple of (candidates, invalid_ids_by_area, area_ranges)
        - candidates: List[(start_idx, candidate_lines_with_indices)]
          - start_idx: start index of the candidate area
          - candidate_lines_with_indices: [(line_idx, line_content), ...] exactly limit_ valid lines
        - invalid_ids_by_area: List[list] - each list contains invalid line indices for that area
        - area_ranges: List[(start_idx, end_idx)] - 原始 md_lines 的完整范围，用于后续过滤
    """
    
    toc_keywords = {"目录", "目次", "tableofcontents", "contents"}
    
    # Step 1: find all TOC keywords
    start_indices = []
    for i, line in enumerate(md_lines):
        if normalize_md(line) in toc_keywords:
            start_indices.append(i)
    
    # Step 2: if no TOC keywords found, use the first line as the candidate area
    if not start_indices:
        logger.info("No TOC keywords found, using the first line as the candidate area")
        start_indices = [0]
    else:
        logger.info(f"{len(start_indices)} TOC keywords found")
        for idx in start_indices:
            logger.debug(f"  - line {idx}: {md_lines[idx].strip()}")
    
    # Step 3: build candidate areas for each start index
    candidates = []
    invalid_ids_by_area = []
    area_ranges = []
    
    for start_idx in start_indices:
        candidate_lines_with_indices = []
        invalid_ids = []
        current_idx = start_idx
        
        while len(candidate_lines_with_indices) < limit_ and current_idx < len(md_lines):
            line = md_lines[current_idx]
            
            if line.strip():
                if is_content_line(line):
                    candidate_lines_with_indices.append((current_idx, line))
                else:
                    invalid_ids.append(current_idx)
            current_idx += 1
        
        end_idx = current_idx - 1 if current_idx > start_idx else start_idx
        
        valid_count = len(candidate_lines_with_indices)
        invalid_count = len(invalid_ids)
        logger.debug(f"Candidate area #{len(candidates)+1}: line {start_idx}-{end_idx}, "
                    f"valid lines: {valid_count}, invalid lines: {invalid_count}, "
                    f"scanned: {end_idx - start_idx + 1} lines")
        
        candidates.append((start_idx, candidate_lines_with_indices))
        invalid_ids_by_area.append(invalid_ids)
        area_ranges.append((start_idx, end_idx))
    
    return candidates, invalid_ids_by_area, area_ranges


def llm_judge_toc_range(html_table: str, lines_: list, model_name: str = None, use_reindex: bool = False, total_lines: int = 0) -> tuple:
    """
    Use LLM to determine the start and end indices of the TOC content
    
    Args:
        html_table: HTML table of candidate lines
        lines_: [(line_idx, line_content), ...] non-empty lines list
        model_name: model name (optional, uses default if not specified)
        use_reindex: if True, LLM receives 0-based consecutive ids
        total_lines: total number of lines (used when use_reindex=True)
    
    Returns:
        (toc_start_idx, toc_end_idx) or None
        - If use_reindex=True, returns 0-based indices that need to be mapped back
    """
    if not lines_:
        return None
    
    if use_reindex:
        # Use 0-based consecutive indexing
        start_idx = 0
        end_idx = total_lines - 1
    else:
        start_idx = lines_[0][0]
        end_idx = lines_[-1][0]
    
    total_candidates = len(lines_)
    
    paras = {
        "start_idx": start_idx,
        "end_idx": end_idx,
        "total_candidates": total_candidates
    }
    prompt, temperature, top_p, max_tokens = build_prompt(
        task="detect-toc-range",
        texts=html_table,
        query="",
        paras=paras
    )
    
    messages = [
        {"role": "system", "content": "You are a document analysis expert"},
        {"role": "user", "content": prompt}
    ]
    
    try:
        answer = ai_query_service.query_ai(
            messages=messages,
            user_id="toc_detector",
            model=model_name,
            stream=False,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        result = eval_response(answer)
        toc_start = result.get("toc_start")
        toc_end = result.get("toc_end")
        confidence = result.get("confidence", "low")
        logger.info(f"LLM judge: toc_start={toc_start}, toc_end={toc_end}, confidence={confidence}")
        
        if toc_start is not None and toc_end is not None:
            # Validate: indices should be within valid range
            if 0 <= toc_start <= end_idx and 0 <= toc_end <= end_idx and toc_end >= toc_start:
                return toc_start, toc_end
            else:
                logger.warning(f"IDs returned by LLM are out of range [0, {end_idx}], got [{toc_start}, {toc_end}]")
                return None
        else:
            return None
        
    except Exception as e:
        logger.error(f"LLM parse failed: {e}")
        return None


def detect_tocs_llm(md_lines: list, model_name: str = None, limit_: int = 100) -> list:
    """
    Use LLM to detect TOC, support multiple TOC areas
    
    Args:
        md_lines: markdown lines list
        model_name: model name (optional)
        limit_: max lines to consider for each candidate area
    
    Returns:
        List[(start_idx, end_idx, toc_lines)] or empty list
        - toc_lines only contains valid content lines (table/LaTeX/images filtered out)
        may return multiple TOC areas
    """
    # Step 1: detect candidate areas (may be multiple)
    candidates, invalid_ids_by_area, area_ranges = detect_toc_candidates(md_lines, limit_)
    if not candidates:
        logger.info("No TOC candidates detected")
        return []
    
    # Step 2: evaluate each candidate area with LLM
    toc_ranges = []
    
    for idx, ((_, lines_), invalid_ids, (area_start, area_end)) in enumerate(
        zip(candidates, invalid_ids_by_area, area_ranges)
    ):
        # Build mapping: re-index to 0-based consecutive ids for LLM
        # This avoids LLM hallucination on non-existent line numbers
        reindex_to_original = {i: abs_idx for i, (abs_idx, _) in enumerate(lines_)}
        # original_to_reindex = {abs_idx: i for i, (abs_idx, _) in enumerate(lines_)}
        
        # Create DataFrame with re-indexed ids (0, 1, 2, ...)
        df = pd.DataFrame([
            {"id": i, "content": truncate_text(line.strip(), 30, 10)}
            for i, (_, line) in enumerate(lines_)
        ])
        
        md_table = df2md(df, index=False)
        print(md_table)
        llm_result = llm_judge_toc_range(md_table, lines_, model_name, use_reindex=True, total_lines=len(lines_))
        
        if llm_result is not None:
            reindex_start, reindex_end = llm_result
            # Map back to original absolute indices
            toc_start = reindex_to_original.get(reindex_start)
            toc_end = reindex_to_original.get(reindex_end)
            
            if toc_start is not None and toc_end is not None:
                # 使用 area_end 作为过滤范围的结束点（包含所有扫描过的行）
                # toc_start/toc_end 是 LLM 识别的精确 TOC 边界
                # 但 invalid_ids 的范围是 [area_start, area_end]
                toc_lines = [
                    line for i, line in enumerate(md_lines[toc_start : toc_end+1], start=toc_start)
                    if i not in invalid_ids and line.strip()
                ]
                # 返回 area_end 作为实际过滤范围
                toc_ranges.append((toc_start, toc_end, toc_lines, area_end))
            else:
                logger.warning(f"TOC area #{idx+1}: failed to map reindex back to original")
        else:
            logger.info(f"TOC area #{idx+1} not detected")
    return toc_ranges


def parse_toc_hierarchy(toc_df, max_depth: int = 6, model_name: str = None) -> list:
    """
    Parse TOC hierarchy using LLM
    
    Args:
        toc_df: DataFrame with id, heading columns
        max_depth: max depth of hierarchy
        model_name: model name (optional)
    
    Returns:
        List of dicts with id, heading, level
    """
    try:
        toc_hierarchy = hiearchy_llm(toc_df, model_name=model_name, max_depth=max_depth, task="eval-toc-headings")
        id_to_level = {item["id"]: item["level"] for item in toc_hierarchy}

        toc_with_level = []
        for _, row in toc_df.iterrows():
            line_id = row["id"]
            heading = row["heading"]
            level = id_to_level.get(line_id, 1)
            toc_with_level.append({
                "id": line_id,
                "heading": heading,
                "level": level
            })
        return toc_with_level

    except Exception as e:
        logger.error(f"LLM hierarchy analysis failed: {e}")
        return []


def build_tree_tocs(toc_with_level: list) -> dict:
    """
    Build nested JSON from TOC with level
    
    Args:
        toc_with_level: [{"id": line index, "heading": content, "level": level, "reason": ...}, ...]
        level: 1 for h1, 2 for h2..., -1 will be treated as the lowest level title
    
    Returns:
        nested JSON structure
    
    Notes:
    in the TOC scenario, all lines are treated as titles:
    - normal levels (1,2,3...) are treated as is
    - -1 is treated as a level deeper than all normal levels
    """
    if not toc_with_level:
        return {}
    
    # Step 1: collect all levels (exclude -1)
    positive_levels = [item["level"] for item in toc_with_level if item["level"] > 0]
    
    # Step 2: determine the level that -1 should be mapped to
    if positive_levels:
        # if there are normal levels, -1 is mapped to max + 1
        max_positive_level = max(positive_levels)
        level_for_minus_one = max_positive_level + 1
    else:
        level_for_minus_one = 1
    
    # Step 3: build nested structure
    root = {}
    stack = [(root, 0)]
    
    for item in toc_with_level:
        heading = item["heading"]
        original_level = item["level"]
        
        # normalize level: -1 -> level_for_minus_one
        normalized_level = level_for_minus_one if original_level == -1 else original_level
        while len(stack) > 1 and stack[-1][1] >= normalized_level:
            stack.pop()
        
        parent_dict = stack[-1][0]
        parent_dict[heading] = {}
        stack.append((parent_dict[heading], normalized_level))
    return root


def gen_reason_code_toc(text: str) -> str:
    """
    Generate reason code for a text line using judge_by_conditions and remove_by_conditions.
    This aligns with the preds CSV format.
    
    Args:
        text: the text line to analyze
    
    Returns:
        reason code string in format "POS [...] NEG [...]"
    """
    # Clean the text (remove leading # marks)
    text_clean = text.lstrip('#').strip()
    
    pos_code, detail_info = judge_by_conditions(text_clean, return_detail=True)
    neg_code = remove_by_conditions(text_clean)
    
    reason_suffix = detail_info.get('reason_suffix', '')
    reason_str = f"POS {pos_code}{reason_suffix} NEG {neg_code}"
    
    return reason_str


def eval_toc_levels(toc_lines: list, model_name: str = None, max_depth: int = 6) -> tuple:
    """
    Analyze TOC hierarchy and generate nested JSON
    
    Args:
        toc_lines: list of pre-filtered valid TOC lines (invalid content already removed)
        model_name: model name (optional)
        max_depth: max depth of hierarchy
    
    Returns:
        (toc_with_level, toc_tree)
        - toc_with_level: list with level information
          Format: [{"id": int, "heading": str, "level": int, "reason": str}, ...]
        - toc_tree: nested JSON structure
    """
    # Build data for LLM judgment (all lines are valid, pre-filtered)
    valid_data = []
    
    for i, line in enumerate(toc_lines):
        heading = line.strip()
        if not heading:
            continue
        
        valid_data.append({
            "id": i,
            "heading": heading,
            "level": "Not Sure"
        })
    
    toc_df = pd.DataFrame(valid_data)
    
    if toc_df.empty:
        logger.info("No valid TOC content, skip hierarchy analysis")
        return "", {}
    
    # Evaluate TOC hierarchy with LLM
    llm_result = parse_toc_hierarchy(toc_df, max_depth, model_name)
    
    # Build id -> level mapping from LLM result
    id_to_level = {item["id"]: item["level"] for item in llm_result}
    
    # Build final result with reason as post-processing
    result_data = []
    valid_items_for_tree = []
    
    for data in valid_data:
        line_id = data["id"]
        heading = data["heading"]
        level = id_to_level.get(line_id, -1)
        
        # Add reason as post-processing
        reason = gen_reason_code_toc(heading)
        
        if level > 0:
            result_data.append({"id": line_id, "heading": heading, "level": level, "reason": reason})
            valid_items_for_tree.append({"id": line_id, "heading": heading, "level": level, "reason": reason})
    
    if result_data:
        result_df = pd.DataFrame(result_data)
        toc_with_level = df2md(result_df, index=False)
    else:
        toc_with_level = ""
    
    # Build nested JSON
    toc_tree = build_tree_tocs(valid_items_for_tree)
    return toc_with_level, toc_tree


def detect_tocs_in_texts(md_lines: list, model_name: str = None, branch: str = "normal", limit_: int = 150):
    """
    Detect and analyze TOC in texts
    
    Args:
        md_lines: markdown lines list
        model_name: model name (optional)
        branch: "normal" or "plus-ocr"
        limit_: max lines to consider for each candidate area
    
    Returns:
        Tuple of (toc_hierarchies, filtered_md_lines)
        - toc_hierarchies: List[dict] containing:
            {
                "toc_range": (start_idx, end_idx),
                "toc_with_level": [...],
                "toc_tree": {...}
            }
        - filtered_md_lines: md_lines with TOC sections removed
    """
    
    logger.info("-" * 60)
    logger.info(f"Step 1: detect TOC lines, with {branch} method")
    logger.info("-" * 60)
    
    if branch == "normal":
        toc_area = detect_tocs_llm(md_lines, model_name, limit_)
    elif branch == "plus-ocr":
        # TODO implement OCR branch, if implement, direct yield toc-tree
        return None, md_lines
    else:
        logger.error(f"Not supported branch: {branch}")
        return None, md_lines
    
    if not toc_area or len(toc_area) == 0:
        logger.warning("TOC detection failed, no TOC area detected")
        return None, md_lines
    
    logger.info("Step 2: analyze TOC hierarchy")
    logger.info(f"{len(toc_area)} TOC areas detected")
    
    toc_hierarchies = []
    ranges_to_remove = []
    
    for idx, (toc_start, toc_end, toc_lines, area_end) in enumerate(toc_area):
        logger.info(f"Analyzing TOC area #{idx+1}: TOC range [{toc_start}, {toc_end}], scan range ends at {area_end}")
        
        toc_with_level, toc_tree = eval_toc_levels(toc_lines, model_name, max_depth=6)
        toc_hierarchies.append({
            "toc_range": (toc_start, toc_end),
            "scan_range": (toc_start, area_end),
            "toc_with_level": toc_with_level,
            "toc_tree": toc_tree
        })
        ranges_to_remove.append((toc_start, toc_end))
    
    # Step 3: Remove TOC lines from md_lines (process in reverse order to correct indices)
    # Sort ranges by start index descending just to be safe
    ranges_to_remove.sort(key=lambda x: x[0], reverse=True)
    
    for start, end in ranges_to_remove:
        # Slicing removal: [:start] + [end+1:]
        md_lines = md_lines[:start] + md_lines[end+1:]
    
    logger.info(f"Removed TOC lines, remaining {len(md_lines)} lines")
    return toc_hierarchies, md_lines


# ==================== TOC Utility Functions ====================

def load_toc_hierarchies(json_path: str) -> list:
    import json
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)
