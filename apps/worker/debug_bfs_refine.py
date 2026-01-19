"""
BFS Refine Test Script
======================
模拟 pred_titles 的处理流程，使用 TOC 层级信息将 DataFrame 分段处理。

流程：
1. 加载 test_naive_2.csv (est_hierarchies_naive 的输出)
2. 加载 toc_hierarchies.json
3. 使用 TOC 匹配逻辑识别文档结构
4. 根据 build_hierarchy_index 的结果将 DataFrame 分段
5. 每个段作为 est_hierarchies_llm 的输入
"""

import os
import re
import json
import pandas as pd
from test_toc_match import (
    load_toc_hierarchies,
    filter_tocs,
    merge_consecutive_tocs,
    apply_tocs,
    build_hierarchy_index
)
from app.services.common.kb_utils import count_cn_en
from app.services.document_parser.layout_parser import hiearchy_llm, build_level_mapping, execute_level_mapping


def heading_split_tocs(df: pd.DataFrame, hierarchy_index: dict) -> list:
    """
    根据 hierarchy_index 将 DataFrame 分割成多个段（只处理叶子节点）
    
    Args:
        df: 完整的 DataFrame
        hierarchy_index: build_hierarchy_index 返回的层级索引
    
    Returns:
        segments: 列表，每个元素是一个字典:
        {
            "heading": str,          # 段落标题（叶子节点）
            "level": int,            # 层级
            "start_id": int,         # 起始ID
            "end_id": int,           # 结束ID
            "df": pd.DataFrame,      # 该段的数据
            "path": list,            # 从根到当前节点的完整路径 ["模块1", "子模块1"]
            "path_str": str          # 路径字符串 "模块1 --> 子模块1"
        }
    """
    segments = []
    
    def extract_leaf_nodes(node, path=[]):
        """
        递归提取叶子节点
        
        Args:
            node: 当前节点（模块或子模块）
            path: 当前路径（从根到父节点的标题列表）
        """
        current_heading = node["heading"]
        current_path = path + [current_heading]
        
        children = node.get("children", [])
        
        if not children:
            # 叶子节点：没有子节点
            node_start = node["start_id"]
            node_end = node["end_id"]
            node_level = node["map_level"]
            
            # 提取对应的 DataFrame 段
            node_df = df[df['id'].between(node_start, node_end)].copy()
            
            segments.append({
                "heading": current_heading,
                "level": node_level,
                "start_id": node_start,
                "end_id": node_end,
                "df": node_df,
                "path": current_path.copy(),
                "path_str": " --> ".join(current_path)
            })
        else:
            # 非叶子节点：递归处理所有子节点
            for child in children:
                extract_leaf_nodes(child, current_path)
    
    # 处理所有顶级模块
    modules = hierarchy_index.get("modules", [])
    for module in modules:
        extract_leaf_nodes(module)
    
    return segments


def segment_transfer(df: pd.DataFrame, threshold: int = 3000, max_start: int = 50, max_end: int = 10) -> tuple:
    """
    对 segment 的 DataFrame 进行处理（改造自 layout_parser.py 的 heading_tb_transfer）
    
    功能：
    1. 对 heading 列进行截断（保留前 max_start 和后 max_end 字符）
    2. 计算累积token长度，找到超过阈值的分界点 cut_id
    
    Args:
        df: segment 的 DataFrame，包含 id, heading, level 等列
        threshold: token 阈值，超过此值则需要截断
        max_start: 截断时保留的开头字符数
        max_end: 截断时保留的结尾字符数
    
    Returns:
        tuple: (truncated_df, cut_id, total_tokens)
            - truncated_df: heading 被截断后的 DataFrame
            - cut_id: 分界行的 id（-1 表示无需截断，全部可用）
            - total_tokens: 总 token 数
    """
    def truncate_text(text, start_limit, end_limit):
        """截断文本，保留开头和结尾"""
        text = str(text)
        total_limit = start_limit + end_limit
        if len(text) <= total_limit:
            return text
        start_part = text[:start_limit]
        end_part = text[-end_limit:] if end_limit > 0 else ''
        return f"{start_part}...{end_part}"
    
    # 保存原始 heading
    raw_headings = df['heading'].tolist()
    
    # 创建副本进行处理
    truncated_df = df.copy()
    truncated_df["heading"] = truncated_df["heading"].apply(lambda x: truncate_text(x, max_start, max_end))
    truncated_df["raw_heading"] = raw_headings  # 保留原始 heading
    
    # 计算累积 token 长度，找到分界点
    current_len = 0
    cut_id = -1  # -1 表示无需截断
    total_tokens = 0
    
    for idx, row in truncated_df.iterrows():
        # 计算当前行的 token 长度（排除 reason 列，如果存在）
        row_filtered = row.drop(labels=["reason", "raw_heading"], errors="ignore")
        row_len = sum(count_cn_en(str(v)) for v in row_filtered.values)
        total_tokens += row_len
        
        if current_len + row_len > threshold and cut_id == -1:
            # 第一次超过阈值，记录分界点
            cut_id = int(row['id'])
        
        current_len += row_len
    
    return truncated_df, cut_id, total_tokens


def prepare_llm_inputs(df: pd.DataFrame, segments: list = None, threshold: int = 3000, max_start: int = 50, max_end: int = 10) -> list:
    """
    为 est_hierarchies_llm 准备输入数据
    
    功能：
    1. 如果有 segments（TOC存在），对每个 segment 进行处理
    2. 如果 segments 为空（无TOC），按 heading_tb_transfer 逻辑将整个 df 按阈值分割
    
    Args:
        df: 完整的 DataFrame
        segments: heading_split_tocs 返回的段列表，None 表示无 TOC
        threshold: token 阈值
        max_start: 截断时保留的开头字符数
        max_end: 截断时保留的结尾字符数
    
    Returns:
        llm_inputs: 列表，每个元素包含:
        {
            "preds_df": pd.DataFrame,  # 原始数据（用于后续处理）
            "cut_id": int              # 分界行 id（-1 表示无需截断）
        }
    """
    llm_inputs = []
    
    if segments:
        # 有 TOC 的情况：按 segment 处理
        for seg in segments:
            preds_df = seg["df"].copy()
            
            required_cols = ["id", "heading", "level"]
            if not all(col in preds_df.columns for col in required_cols):
                continue
            
            sub_df, cut_id, _ = segment_transfer(preds_df, threshold, max_start, max_end)
            
            llm_inputs.append({
                "preds_df": sub_df,
                "cut_id": cut_id
            })
    else:
        # 无 TOC 的情况：按 heading_tb_transfer 逻辑分割
        sub_dfs, cut_ids = heading_split_naive(df, threshold, max_start, max_end)
        for sub_df, cut_id in zip(sub_dfs, cut_ids):
            llm_inputs.append({
                "preds_df": sub_df,
                "cut_id": cut_id
            })
    
    return llm_inputs


def heading_split_naive(df: pd.DataFrame, threshold: int = 3000, max_start: int = 50, max_end: int = 10) -> tuple:
    """
    无 TOC 时的分割逻辑
    按累积 token 长度将 DataFrame 分割成多个子 DataFrame
    
    Args:
        df: 完整的 DataFrame
        threshold: token 阈值
        max_start: 截断时保留的开头字符数
        max_end: 截断时保留的结尾字符数
    
    Returns:
        tuple: (sub_dfs, cut_ids)
            - sub_dfs: 分割后的 DataFrame 列表
            - cut_ids: 每个子 df 的 cut_id（都是 -1，因为已经分割好了）
    """
    def truncate_text(text, start_limit, end_limit):
        text = str(text)
        total_limit = start_limit + end_limit
        if len(text) <= total_limit:
            return text
        start_part = text[:start_limit]
        end_part = text[-end_limit:] if end_limit > 0 else ''
        return f"{start_part}...{end_part}"
    
    # 截断 heading
    df = df.copy()
    df["heading"] = df["heading"].apply(lambda x: truncate_text(x, max_start, max_end))
    
    sub_dfs = []
    cut_ids = []
    current_rows = []
    current_len = 0
    
    for _, row in df.iterrows():
        row_filtered = row.drop(labels=["reason"], errors="ignore")
        row_len = sum(count_cn_en(str(v)) for v in row_filtered.values)
        
        if current_len + row_len > threshold and current_rows:
            sub_dfs.append(pd.DataFrame(current_rows, columns=df.columns))
            cut_ids.append(-1)  # 已分割，无需再截断
            current_rows = [row.tolist()]
            current_len = row_len
        else:
            current_rows.append(row.tolist())
            current_len += row_len
    
    if current_rows:
        sub_dfs.append(pd.DataFrame(current_rows, columns=df.columns))
        cut_ids.append(-1)
    
    return sub_dfs, cut_ids

# ======== 分析 basic_df 对其他 segments 的 reason 覆盖度 ========
def analyze_reason_coverage(llm_inputs: list) -> list:
    """返回: [(reason, first_heading), ...] 按出现顺序去重，且仅保留 neg_code 全为 0 的项"""
    if not llm_inputs:
        return []
    
    basic_df = llm_inputs[0]['preds_df']
    base_reasons = set(basic_df['reason'].dropna().unique())
    
    all_uncovered = []
    seen_reasons = set()
    
    for seg_info in llm_inputs[1:]:
        seg_df = seg_info['preds_df']
        for _, row in seg_df.iterrows():
            reason = row['reason']
            if pd.notna(reason) and reason not in base_reasons and reason not in seen_reasons:
                # check if neg_code is all zeros
                neg_match = re.search(r'NEG\s*\[([^\]]*)\]', str(reason))
                is_neg_zero = False
                if neg_match:
                    try:
                        nums = [int(x.strip()) for x in neg_match.group(1).split(',') if x.strip()]
                        if nums and all(x == 0 for x in nums):
                            is_neg_zero = True
                    except:
                        pass
                
                if is_neg_zero:
                    seen_reasons.add(reason)
                    all_uncovered.append((reason, row['heading']))    
    return all_uncovered


async def main():
    """
    主测试流程
    """
    print("\n" + "=" * 80)
    print("模拟 pred_titles 处理流程")
    print("=" * 80)
    
    # Step 1: 加载数据
    csv_path = "/Users/wuchengke/Desktop/sxjg/test_naive_2.csv"
    toc_json_path = "/Users/wuchengke/Desktop/sxjg/tmp/陕西建工/16.陕建控股制度下-1.pdf/toc_hierarchies.json"
    kb_dir = "/Users/wuchengke/Desktop/sxjg/tmp/陕西建工/16.陕建控股制度下-1.pdf"
    
    # LLM 配置参数
    model_name = "qwen3-max" #"deepseek-chat"
    max_depth = 6

    df = pd.read_csv(csv_path)
    toc_list = load_toc_hierarchies(toc_json_path)
    toc_exist = True

    # 边界情况：toc_list 为空
    if not toc_list:
        print(f"[INFO] 未检测到 TOC，使用 heading_split_naive 分割")
        toc_exist = False

        llm_inputs = prepare_llm_inputs(df, segments=None)
        return llm_inputs, None, None

    matched_tocs_df = filter_tocs(df, toc_list)
    if matched_tocs_df.empty:
        print(f"[INFO] TOC 匹配失败，使用 heading_split_naive 分割")
        toc_exist = False

        llm_inputs = prepare_llm_inputs(df, segments=None)
        return llm_inputs, None, None

    merged_tocs_df = merge_consecutive_tocs(matched_tocs_df)
    df = apply_tocs(df, merged_tocs_df)
    hierarchy_index = build_hierarchy_index(df)

    with open(os.path.join(kb_dir, "hierarchy_index.json"), "w", encoding="utf-8") as f:
        json.dump(hierarchy_index, f, ensure_ascii=False, indent=2)
    
    segments = heading_split_tocs(df, hierarchy_index)
    llm_inputs = prepare_llm_inputs(df, segments=segments)

    all_uncovered = analyze_reason_coverage(llm_inputs)
    print(f"\n[Reason 覆盖度] 共 {len(all_uncovered)} 种未被 basic_df 覆盖(仅统计无 NEG 触发):")
    for reason, heading in all_uncovered:
        print(f"  {reason}  =>  {heading[:50]}")
    

    # ======== 后续 LLM 处理 ========
    full_preds = []
    
    # 累积的 lvl_mapping，持续记录所有已知的 reason -> level 映射
    accumulated_mapping = {}
    known_reasons = set()
    
    basic_df = llm_inputs[0]['preds_df'][['id', 'heading', 'level', 'reason']]
    
    # 当 toc_exist 时，第一行是父标题，需要单独处理
    top_row = None
    if toc_exist:
        top_row = basic_df.iloc[[0]]  # 保留为 DataFrame 以便后续拼接
        top_title = top_row.iloc[0]['heading']
        df4llm = basic_df.iloc[1:].drop(columns=["reason"])
        basic_df_for_merge = basic_df.iloc[1:]
    else:
        top_title = None
        df4llm = basic_df.drop(columns=["reason"])
        basic_df_for_merge = basic_df

    layout_res = await hiearchy_llm(df4llm, top_title, model_name, max_depth)
    current_preds = pd.DataFrame(layout_res)
    current_preds.insert(1, "heading", basic_df_for_merge["heading"].values)
    current_preds["reason"] = basic_df_for_merge["reason"].values
    
    # 如果有 top_row，将其以 level=1 拼接回结果的最前面
    if top_row is not None:
        top_pred = pd.DataFrame([{
            "id": top_row.iloc[0]["id"],
            "heading": top_row.iloc[0]["heading"],
            "level": 1,  # 父标题固定为 level 1
            "reason": top_row.iloc[0]["reason"]
        }])
        current_preds = pd.concat([top_pred, current_preds], ignore_index=True)

    current_preds.to_csv(os.path.join(kb_dir, "./test_llm_base.csv"), index=False, encoding='utf-8-sig')
    current_preds = pd.read_csv(os.path.join(kb_dir, "./test_llm_base.csv"), encoding='utf-8-sig')

    # 建立初始映射并更新累积映射
    current_preds, lvl_mapping = build_level_mapping(current_preds, basic_df['level'].tolist(), mode="freq")
    accumulated_mapping.update(lvl_mapping)
    
    # 记录第一组数据中的所有 reason
    first_reasons = set(basic_df['reason'].dropna().unique())
    known_reasons.update(first_reasons)
    
    # 遍历所有 segment，动态检查并更新映射
    for seg_idx, seg_info in enumerate(llm_inputs):
        seg_df = seg_info['preds_df'][['id', 'heading', 'level', 'reason']].copy()
        top_title = seg_df.iloc[0]['heading']

        current_reasons = set(seg_df['reason'].dropna().unique())
        new_reasons = current_reasons - known_reasons

        if new_reasons:
            print(f"[Segment {seg_idx}] 发现 {len(new_reasons)} 个新的 reason 类型: {new_reasons}")
            print(f"[Segment {seg_idx}] 调用 hiearchy_llm 获取新映射...")
            
            # 准备 LLM 输入
            df4llm_new = seg_df.drop(columns=["reason"])
            layout_res_new = await hiearchy_llm(df4llm_new, top_title, model_name, max_depth)
            new_preds = pd.DataFrame(layout_res_new)
            new_preds["reason"] = seg_df["reason"].values
            
            # 建立新的映射
            new_preds, new_lvl_mapping = build_level_mapping(new_preds, seg_df['level'].tolist(), mode="freq")
            # 只更新新发现的 reason 对应的映射（避免覆盖已有映射）
            for reason in new_reasons:
                if reason in new_lvl_mapping:
                    accumulated_mapping[reason] = new_lvl_mapping[reason]
                    print(f"  -> 新增映射: {reason} => level {new_lvl_mapping[reason]['mapped_lvl']}")
            
            known_reasons.update(new_reasons)
        else:
            print(f"[Segment {seg_idx}] 所有 reason 类型已知，直接使用累积映射")
        
        # 使用累积映射执行 level mapping
        level_df = execute_level_mapping(seg_df, accumulated_mapping)
        full_preds.append(level_df)
    
    return llm_inputs, hierarchy_index, segments


if __name__ == "__main__":
    import asyncio
    llm_inputs, hierarchy_index, segments = asyncio.run(main())
