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

from app.services.document_parser.table_parser import df2html
from shared.services.ai import ai_query_service
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


def normalize_md(s: str) -> str:
    """Normalize markdown string for comparison"""
    s = re.sub(r"^\s*#+\s*", "", s)
    s = re.sub(r"\s+", "", s)
    return s.lower()


def truncate_text(text: str, start_limit: int, end_limit: int) -> str:
    """Truncate text keeping start and end parts"""
    text = str(text)
    total_limit = start_limit + end_limit
    if len(text) <= total_limit:
        return text
    start_part = text[:start_limit]
    end_part = text[-end_limit:] if end_limit > 0 else ''
    return f"{start_part}...{end_part}"


def detect_toc_candidates(md_lines: list, limit_: int = 100) -> list:
    """
    Detect TOC candidates (support multiple TOC areas)
    
    Args:
        md_lines: markdown lines list
        limit_: max lines to consider for each candidate area
    
    Returns:
        List[(start_idx, candidate_lines_with_indices)]
        - start_idx: start index of the candidate area
        - candidate_lines_with_indices: [(line_idx, line_content), ...] non-empty lines list
        if no TOC keywords found, return [(0, the first 150 non-empty lines)]
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
    for start_idx in start_indices:
        end_idx = min(start_idx + limit_, len(md_lines))
        raw_lines = md_lines[start_idx:end_idx]

        candidate_lines_with_indices = []
        for i, line in enumerate(raw_lines):
            absolute_idx = start_idx + i
            if line.strip():
                candidate_lines_with_indices.append((absolute_idx, line))
        
        non_empty_count = len(candidate_lines_with_indices)
        logger.debug(f"Candidate area #{len(candidates)+1}: line {start_idx}-{end_idx-1}, "
                    f"original lines: {len(raw_lines)}, non-empty lines: {non_empty_count}")
        
        candidates.append((start_idx, candidate_lines_with_indices))
    return candidates


async def llm_judge_toc_range(html_table: str, lines_: list, model_name: str = None) -> tuple:
    """
    Use LLM to judge TOC range
    
    Args:
        html_table: HTML table string
        lines_: [(line_idx, line_content), ...] non-empty lines list
        model_name: model name (optional, uses default if not specified)
    
    Returns:
        (toc_start_idx, toc_end_idx) or None
        - toc_start_idx: start index of the TOC content
        - toc_end_idx: end index of the TOC content
    """
    if not lines_:
        return None
    
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
        {"role": "system", "content": "你是一位文档分析专家"},
        {"role": "user", "content": prompt}
    ]
    
    try:
        answer = await ai_query_service.query_ai(
            messages=messages,
            user="toc_detector",
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
            valid_line_indices = set(idx for idx, _ in lines_)
            if toc_start in valid_line_indices and toc_end in valid_line_indices and toc_end >= toc_start:
                return toc_start, toc_end
            else:
                logger.warning("IDs returned by LLM are out of range, ignored")
                return None
        else:
            return None
        
    except Exception as e:
        logger.error(f"LLM parse failed: {e}")
        return None


async def detect_tocs_llm(md_lines: list, model_name: str = None, limit_: int = 100) -> list:
    """
    Use LLM to detect TOC, support multiple TOC areas
    
    Args:
        md_lines: markdown lines list
        model_name: model name (optional)
        limit_: max lines to consider for each candidate area
    
    Returns:
        List[(start_idx, end_idx, toc_lines)] or empty list
        may return multiple TOC areas
    """
    # Step 1: detect candidate areas (may be multiple)
    candidates = detect_toc_candidates(md_lines, limit_)
    if not candidates:
        logger.info("No TOC candidates detected")
        return []
    
    # Step 2: evaluate each candidate area with LLM
    all_results = []
    
    for idx, (_, lines_) in enumerate(candidates):
        df = pd.DataFrame(lines_, columns=["行号", "内容"])
        df["内容"] = df["内容"].apply(lambda x: truncate_text(x.strip(), 50, 10))
        html_table = df2html(df, index=False)
        
        llm_result = await llm_judge_toc_range(html_table, lines_, model_name)
        
        if llm_result is not None:
            toc_start, toc_end = llm_result
            toc_lines = md_lines[toc_start:toc_end+1]
            logger.info(f"TOC area #{idx+1} detected, from {toc_start} to {toc_end}, with {len(toc_lines)} lines")
            all_results.append((toc_start, toc_end, toc_lines))
        else:
            logger.info(f"TOC area #{idx+1} not detected")
    return all_results


async def hiearchy_llm(df, model_name: str = None, max_depth: int = 6, max_len: int = 8192):
    """
    Use LLM to analyze hierarchy structure
    
    Args:
        df: DataFrame with id, heading columns
        model_name: model name (optional)
        max_depth: max depth of hierarchy
        max_len: max tokens for output
    
    Returns:
        List of dicts with id and level
    """
    level_html = df2html(df)
    ot_limit = int(len(level_html) * 1.2)
    ot_limit = min(ot_limit, max_len)

    paras = {"max_tokens": ot_limit, "max_depth": max_depth, "top_title": None}
    prompt, temperature, top_p, max_tokens = build_prompt(
        task="eval-headings", 
        texts=level_html, 
        query="", 
        paras=paras
    )
    messages = [
        {"role": "system", "content": "you are a document auditing expert"},
        {"role": "user", "content": prompt}
    ]
    
    answer = await ai_query_service.query_ai(
        messages=messages,
        user="toc_hierarchy",
        model=model_name,
        stream=False,
        max_tokens=max_tokens,
        temperature=temperature
    )
    layout_res = eval_response(answer)
    return layout_res


async def parse_toc_hierarchy(toc_df, max_depth: int = 6, model_name: str = None) -> list:
    """
    Parse TOC hierarchy using LLM
    
    Args:
        toc_df: DataFrame with id, heading columns
        max_depth: max depth of hierarchy
        model_name: model name (optional)
    
    Returns:
        List of dicts with line_id, content, level
    """
    try:
        toc_hierarchy = await hiearchy_llm(toc_df, model_name=model_name, max_depth=max_depth)
        # develop mapping
        id_to_level = {item["id"]: item["level"] for item in toc_hierarchy}
        
        toc_with_level = []
        for _, row in toc_df.iterrows():
            line_id = row["id"]
            content = row["heading"]
            level = id_to_level.get(line_id, 1)
            toc_with_level.append({
                "line_id": line_id,
                "content": content,
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
        toc_with_level: [{"line_id": line index, "content": content, "level": level}, ...]
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
        content = item["content"]
        original_level = item["level"]
        
        # normalize level: -1 -> level_for_minus_one
        normalized_level = level_for_minus_one if original_level == -1 else original_level
        while len(stack) > 1 and stack[-1][1] >= normalized_level:
            stack.pop()
        
        parent_dict = stack[-1][0]
        parent_dict[content] = {}
        stack.append((parent_dict[content], normalized_level))
    return root


async def eval_toc_levels(toc_lines: list, model_name: str = None, max_depth: int = 6) -> tuple:
    """
    Analyze TOC hierarchy and generate nested JSON
    
    Args:
        toc_lines: list of TOC lines
        model_name: model name (optional)
        max_depth: max depth of hierarchy
    
    Returns:
        (toc_with_level, toc_tree)
        - toc_with_level: list with level information
        - toc_tree: nested JSON structure
    """
    data = []
    for i, line in enumerate(toc_lines):
        content = line.strip()
        if content:
            data.append({
                "id": i,
                "heading": content,
                "level": "Not Sure"
            })
    toc_df = pd.DataFrame(data)
    
    if toc_df.empty:
        logger.info("TOC is empty, skip hierarchy analysis")
        return [], {}
    
    # Step 3: evaluate TOC hierarchy with LLM
    toc_with_level = await parse_toc_hierarchy(toc_df, max_depth, model_name)
    
    # Step 4: build nested JSON
    toc_tree = build_tree_tocs(toc_with_level)
    return toc_with_level, toc_tree


async def detect_tocs_in_texts(md_lines: list, model_name: str = None, branch: str = "normal", limit_: int = 100):
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
        toc_area = await detect_tocs_llm(md_lines, model_name, limit_)
    elif branch == "plus-ocr":
        # TODO implement OCR branch
        return None, md_lines
    else:
        logger.error(f"Not supported branch: {branch}")
        return None, md_lines
    
    if not toc_area or len(toc_area) == 0:
        logger.warning("TOC detection failed, no TOC area detected")
        return None, md_lines
    
    logger.info("-" * 60)
    logger.info("Step 2: analyze TOC hierarchy")
    logger.info(f"{len(toc_area)} TOC areas detected")
    logger.info("-" * 60)
    
    toc_hierarchies = []
    ranges_to_remove = []
    
    for idx, (toc_start, toc_end, toc_lines) in enumerate(toc_area):
        logger.info(f"Analyzing TOC area #{idx+1} hierarchy")
        
        toc_with_level, toc_tree = await eval_toc_levels(toc_lines, model_name, max_depth=6)
        toc_hierarchies.append({
            "toc_range": (toc_start, toc_end),
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
