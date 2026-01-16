"""
目录检测测试脚本（LLM版本）
================================
使用大模型智能判断目录的起始和终止位置，并分析层级结构

核心思路：
1. 找到"目录"关键字行
2. 往下取150行作为候选区域
3. 截取每行的部分内容，生成HTML表格
4. 让LLM判断哪些行是真正的目录内容
5. 分析目录层级，生成嵌套JSON结构
"""

from pyexpat import model
import re
import asyncio
import json
import pandas as pd
from app.services.document_parser.table_parser import df2html


def normalize_md(s):
    s = re.sub(r"^\s*#+\s*", "", s)
    s = re.sub(r"\s+", "", s)
    return s.lower()


def truncate_text(text, start_limit, end_limit):
    text = str(text)
    total_limit = start_limit + end_limit
    if len(text) <= total_limit:
        return text
    start_part = text[:start_limit]
    end_part = text[-end_limit:] if end_limit > 0 else ''
    return f"{start_part}...{end_part}"


def detect_toc_candidates(md_lines):
    """
    Detect toc candidates (support multiple toc areas)
    
    Args:
        md_lines: markdown lines list
    
    Returns:
        List[(start_idx, candidate_lines_with_indices)]
        - start_idx: start index of the candidate area
        - candidate_lines_with_indices: [(line_idx, line_content), ...] non-empty lines list
        if no toc keywords found, return [(0, the first 150 non-empty lines)]
    """
    
    toc_keywords = {"目录", "目次", "tableofcontents", "contents"}
    candidate_limit = 150
    
    # Step 1: find all toc keywords
    start_indices = []
    for i, line in enumerate(md_lines):
        if normalize_md(line) in toc_keywords:
            start_indices.append(i)
    
    # Step 2: if no toc keywords found, use the first line as the candidate area
    if not start_indices:
        print("⚠️ no toc keywords found, using the first line as the candidate area")
        start_indices = [0]
    else:
        print(f"✅ {len(start_indices)} toc keywords found:")
        for idx in start_indices:
            print(f"  - line {idx}: {md_lines[idx].strip()}")
    
    # Step 3: build candidate areas for each start index
    candidates = []
    for start_idx in start_indices:
        end_idx = min(start_idx + candidate_limit, len(md_lines))
        raw_lines = md_lines[start_idx:end_idx]

        candidate_lines_with_indices = []
        for i, line in enumerate(raw_lines):
            absolute_idx = start_idx + i
            if line.strip():
                candidate_lines_with_indices.append((absolute_idx, line))
        
        non_empty_count = len(candidate_lines_with_indices)
        print(f"  candidate area #{len(candidates)+1}: line {start_idx}-{end_idx-1}")
        print(f"  original lines: {len(raw_lines)}, non-empty lines: {non_empty_count}")
        
        candidates.append((start_idx, candidate_lines_with_indices))
    return candidates


async def llm_judge_toc_range(html_table, lines_, model_name="deepseek-chat"):
    """
    使用大模型判断目录的起始和终止位置
    
    Args:
        html_table: HTML表格字符串
        candidate_lines_with_indices: [(line_idx, line_content), ...] 非空行列表
        model_name: 使用的模型名称
    
    Returns:
        (toc_start_idx, toc_end_idx) 或 None
        - toc_start_idx: 目录内容的起始行号（绝对行号）
        - toc_end_idx: 目录内容的终止行号（绝对行号，包含）
    """
    from shared.services.ai import ai_query_service
    from shared.services.ai.response_process_service import eval_response
    from shared.services.ai.prompt_service import build_prompt
    
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
        answer = await ai_query_service.query(
            messages=messages,
            model_name=model_name,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        result = eval_response(answer)
        toc_start = result.get("toc_start")
        toc_end = result.get("toc_end")
        confidence = result.get("confidence", "low")
        print(f"[INFO]: llm judge: toc_start={toc_start}, toc_end={toc_end}, confidence={confidence}")
        
        if toc_start is not None and toc_end is not None:
            valid_line_indices = set(idx for idx, _ in lines_)
            if toc_start in valid_line_indices and toc_end in valid_line_indices and toc_end >= toc_start:
                return toc_start, toc_end
            else:
                print(f"[WARNING]: ids returned by llm are out of range, ignored")
                return None
        else:
            return None
        
    except Exception as e:
        print(f"[ERROR]: llm parse failed: {e}")
        return None


async def detect_tocs_llm(md_lines, model_name="deepseek-chat"):
    """
    使用LLM检测目录（普通分支 - 异步版本，支持多个目录区域）
    
    Args:
        md_lines: markdown行列表
        model_name: 使用的模型名称
    
    Returns:
        List[(start_idx, end_idx, toc_lines)] 或 空列表
        可能返回多个目录区域
    """
    # Step 1: detect candidate areas (may be multiple)
    candidates = detect_toc_candidates(md_lines)
    if not candidates:
        print("[INFO]: no toc candidates detected")
        return []
    
    # Step 2: evaluate each candidate area with llm
    all_results = []
    
    for idx, (_, lines_) in enumerate(candidates):
        df = pd.DataFrame(lines_, columns=["行号", "内容"])
        df["内容"] = df["内容"].apply(lambda x: truncate_text(x.strip(), 50, 10))
        html_table = df2html(df, index=False)
        
        # TODO if the last index of toc area >= the last index of md_lines, extend the search area...
        llm_result = await llm_judge_toc_range(html_table, lines_, model_name)
        
        if llm_result is not None:
            toc_start, toc_end = llm_result
            toc_lines = md_lines[toc_start:toc_end+1]
            print(f"[INFO]: toc area #{idx+1} detected, from {toc_start} to {toc_end}, with {len(toc_lines)} lines")
            all_results.append((toc_start, toc_end, toc_lines))
        else:
            print(f"[INFO]: toc area #{idx+1} not detected")

    return all_results


# def detect_tocs_llm_ocr(md_lines, model_name="deepseek-chat"):
#     """
#     使用LLM检测目录（OCR分支）
    
#     TODO: 实现OCR版本的目录检测
#     - 使用视觉模型识别页面
#     - 检测页面布局
#     - 识别目录区域
#     """
#     print("  ⚠️ OCR分支暂未实现")
#     return None


# ============================================================
# 目录层级分析和JSON生成
# ============================================================


async def parse_toc_hierarchy(toc_df, max_depth=6, model_name="deepseek-chat"):
    """
    使用LLM分析目录的层级结构（使用 eval-headings 任务）
    """
    from app.services.document_parser.layout_parser import hiearchy_llm
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
        print(f"  ❌ LLM层级分析失败: {e}")
        return []


def build_tree_tocs(toc_with_level):
    """
    build nested json from toc with level
    
    Args:
        toc_with_level: [{"line_id": line index, "content": content, "level": level}, ...]
        level: 1 for h1, 2 for h2..., -1 will be treated as the lowest level title
    
    Returns:
        nested json structure
    
    Notes:
    in the toc scenario, all lines are treated as titles:
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


async def analyze_tocs(toc_lines, model_name="deepseek-chat", max_depth=6):
    """
    分析目录层级并生成嵌套JSON（异步版本）
    
    Args:
        toc_lines: 目录行列表
        model_name: 使用的模型名称
        max_depth: 最大层级深度
    
    Returns:
        (toc_with_level, nested_json)
        - toc_with_level: 带层级信息的列表
        - nested_json: 嵌套的JSON结构
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
        print("[INFO]: toc is empty, skip hierarchy analysis")
        return [], {}
    
    # Step 3: evaluate toc hierarchy with llm
    toc_with_level = await parse_toc_hierarchy(toc_df, max_depth, model_name)
    
    # Step 4: build nested json
    nested_json = build_tree_tocs(toc_with_level)
    return toc_with_level, nested_json


async def detect_tocs_in_texts(md_lines, model_name="deepseek-chat", branch="normal"):
    """
    测试目录检测
    
    Args:
        md_lines: markdown行列表
        model_name: 使用的模型名称
        branch: "normal" 或 "ocr"
    """
    
    print("\n" + "-" * 60)
    print(f"Step 1: detect toc lines, with {branch} method")
    print("-" * 60)
    
    if branch == "normal":
        toc_area = await detect_tocs_llm(md_lines, model_name)
    elif branch == "plus-ocr":
        # TODO implement ocr branch
        return None
    else:
        print(f"  ❌ Not supported branch: {branch}")
        return None
    
    if not toc_area or len(toc_area) == 0:
        print("\n  ❌ Toc detection failed, no toc area detected")
        return None
    
    print("\n" + "-" * 60)
    print("Step 2: analyze toc hierarchy")
    print(f"\n  {len(toc_area)} toc areas detected")
    print("-" * 60)
    
    toc_hierarchies = []
    for idx, (toc_start, toc_end, toc_lines) in enumerate(toc_area):
        print(f"\n--- analyze toc area #{idx+1} hierarchy ---")
        
        toc_with_level, nested_json = await analyze_tocs(toc_lines, model_name, max_depth=6)
        
        toc_hierarchies.append({
            "toc_range": (toc_start, toc_end),
            "toc_with_level": toc_with_level,
            "nested_json": nested_json
        })
        
        json_output_path = str(md_path).replace('.md', f'_toc_{idx+1}_graph.json')
        with open(json_output_path, 'w', encoding='utf-8') as f:
            json.dump(nested_json, f, ensure_ascii=False, indent=2)
        print(f"  toc json saved to: {json_output_path}")
    
    return toc_hierarchies


if __name__ == "__main__":
    md_path = "/Users/wuchengke/Desktop/sxjg/tmp/陕西建工/16.陕建控股制度下-1.pdf/full.md"
    model_name = "qwen3-max" #deepseek-chat
    branch = "normal"

    with open(md_path, 'r', encoding='utf-8') as f:
        md_lines = f.readlines()
    asyncio.run(detect_tocs_in_texts(md_lines, model_name, branch))

    
        


