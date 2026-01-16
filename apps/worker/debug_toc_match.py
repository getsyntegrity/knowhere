"""
测试脚本：基于 toc_hierarchies.json 对 test_naive_1.csv 中的层级结构进行微调

核心逻辑：
1) 在 test_naive_1.csv 的行中定位出现在 toc_hierarchies.json 中的行
2) 只要 test_naive_1 中的行文本 in toc_hierarchies 中的行，就作为命中
3) 把这些命中的行过滤出来，作为一个粗粒度的小 dataframe
"""

import pandas as pd
import json
from pathlib import Path
import re

def normalize_md(s):
    s = re.sub(r"^\s*#+\s*", "", s)
    s = re.sub(r"\s+", "", s)
    return s.lower()

def load_test_csv(csv_path: str) -> pd.DataFrame:
    """加载 test_naive_1.csv"""
    df = pd.read_csv(csv_path)
    print(f"[DEBUG] CSV 总行数: {len(df)}")
    print(f"[DEBUG] CSV 列名: {list(df.columns)}")
    return df

def load_toc_hierarchies(json_path: str) -> list:
    """
    加载 toc_hierarchies.json 并提取所有 content -> level 的列表
    返回 list[dict]，保留顺序，支持重复项，带使用标记
    结构: [{'normalized': str, 'original': str, 'path': str, 'level': int, 'toc_idx': int, 'used': bool}]
    
    路径逻辑:
    - level 1 (顶级节点): path 为空字符串 ""
    - level 2+ (子节点): path 为其父级节点的 content (从根到父的链)
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    toc_list = []
    toc_idx_counter = 0
    
    for item in data:
        if 'toc_with_level' not in item:
            continue
            
        toc_items = item['toc_with_level']
        
        # 用于追踪各层级的最近节点 {level: content}
        # 层级规则:
        # - 正常层级: level 1 < level 2 < level 3... (数字越大层级越深)
        # - level -1 特殊: 始终是最深层级，附加在前一个节点下
        parent_stack = {}
        
        for toc_item in toc_items:
            content = toc_item.get('content', '').strip()
            level = toc_item.get('level', -999)
            
            if not content:
                continue
            
            # 构建路径: 找到所有祖先节点
            ancestors = []
            
            if level == -1:
                # level -1 特殊处理: 取所有 parent_stack 中的节点作为祖先
                for lvl in sorted(parent_stack.keys()):
                    ancestors.append(parent_stack[lvl])
            else:
                # 正常层级: 取所有 level < 当前 level 的节点作为祖先
                for lvl in sorted(parent_stack.keys()):
                    if lvl != -1 and lvl < level:  # 排除 -1，因为它是最深层级
                        ancestors.append(parent_stack[lvl])
            
            # 完整路径 = 所有祖先 + 当前节点
            path_parts = ancestors + [content]
            full_path = "-->".join(path_parts)
            
            # 更新 parent_stack: 当前节点可能成为后续节点的父节点
            parent_stack[level] = content
            
            # 清理策略: 移除所有"更深"的节点
            if level == -1:
                # level -1 不清理任何节点（它是最深的）
                pass
            else:
                # 正常层级: 移除所有 level >= 当前 level 的节点（除了当前节点）和 level -1
                for old_level in list(parent_stack.keys()):
                    if old_level == -1 or (old_level >= level and old_level != level):
                        del parent_stack[old_level]
            
            normalized = normalize_md(content)
            toc_list.append({
                'normalized': normalized,
                'original': content,
                'path': full_path,
                'level': level,
                'toc_idx': toc_idx_counter,
                'used': False
            })
            toc_idx_counter += 1
    
    print(f"[DEBUG] TOC 总条目数: {len(toc_list)}")
    return toc_list


def filter_tocs(df: pd.DataFrame, toc_list: list) -> pd.DataFrame:
    """
    过滤出 df 中 heading 列文本出现在 toc_list 中任一条目的行
    匹配逻辑：
    1. 遍历原文行
    2. 只有当 heading_normalized 是某个【未占用】TOC 条目的子串时，才算匹配
    3. 如果匹配到多个未占用的 TOC 条目，取 toc_idx 最小的（即最靠前的）
    4. 匹配后将该 TOC 条目标记为 used=True (占用机制)
    """
    matched_data = []  # (idx, map_level)
    
    for idx, row in df.iterrows():
        heading = str(row.get('heading', '')).strip()
        if not heading:
            continue
        
        heading_normalized = normalize_md(heading)
        # 查找所有候选的、未被占用的 TOC 条目
        candidates = []
        for toc_item in toc_list:
            if not toc_item['used'] and heading_normalized in toc_item['normalized']:
                candidates.append(toc_item)
        #TODO 是否考虑增加字符串覆盖度等其他计算方法
        #TODO 如果上面第一次检索是空的candidaes 是否考虑反过来 toc_item in heading or 其他计算方法

        if candidates:
            # 严格模式：取第一个匹配的未占用条目
            # 因为 toc_list 本身是有序的，遍历找到的第一个就是 toc_idx 最小的
            best_match = candidates[0]
            
            # 记录匹配
            matched_data.append((idx, best_match['level']))
            
            # 占用该条目
            best_match['used'] = True
    
    # --- 验证占用情况 ---
    used_count = sum(1 for item in toc_list if item['used'])
    total_count = len(toc_list)
    print(f"[DEBUG] TOC 占用统计: {used_count}/{total_count} (未占用: {total_count - used_count})")
    
    if total_count - used_count > 0:
         print("[DEBUG] 部分未占用的 TOC 条目示例 (前5个):")
         unused_examples = [item['original'] for item in toc_list if not item['used']]
         for ex in unused_examples:
             print(f"  - {ex}")

    if not matched_data:
        return pd.DataFrame()
    
    matched_indices = [item[0] for item in matched_data]
    matched_levels = [item[1] for item in matched_data]
    
    matched_df = df.loc[matched_indices].copy()
    matched_df['map_level'] = matched_levels
    
    if 'reason' in matched_df.columns:
        matched_df = matched_df.drop(columns=['reason'])
    return matched_df


def merge_consecutive_tocs(df: pd.DataFrame) -> pd.DataFrame:
    """
    滑动窗口合并逻辑：
    如果连续行（id 连续）且 map_level 相同，则把后一行的 heading 拼接到前一行
    支持多行连续的情况
    返回的 DataFrame 会增加 collected_ids (此为误称，实为 absorbed_ids) 用于后续删除
    """
    if df.empty or len(df) < 2:
        if not df.empty:
             df['absorbed_ids'] = [[] for _ in range(len(df))]
        return df
    
    # 重置索引以便按顺序遍历
    df = df.reset_index(drop=True)
    
    merged_rows = []
    i = 0
    
    while i < len(df):
        current_row = df.iloc[i].to_dict()
        current_id = current_row['id']
        current_level = current_row['map_level']
        merged_heading = current_row['heading']
        absorbed_ids = []
        
        # 向后查找连续的行
        j = i + 1
        while j < len(df):
            next_row = df.iloc[j]
            next_id = next_row['id']
            next_level = next_row['map_level']
            
            # 检查是否连续（id差1）且 map_level 相同
            if next_id == current_id + 1 and next_level == current_level:
                # 拼接 heading
                merged_heading = merged_heading + " " + next_row['heading']
                absorbed_ids.append(next_id)
                current_id = next_id  # 更新当前 id 以继续检查下一行
                j += 1
            else:
                break
        
        # 更新合并后的 heading
        current_row['heading'] = merged_heading
        current_row['absorbed_ids'] = absorbed_ids
        merged_rows.append(current_row)
        
        # 跳到下一个未处理的行
        i = j
    
    result_df = pd.DataFrame(merged_rows)
    print(f"[DEBUG] 合并后行数: {len(result_df)} (合并前: {len(df)})")
    return result_df


def apply_tocs(original_df: pd.DataFrame, merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    将合并后的行应用回原 DataFrame：
    1. 根据 id 更新 heading
    2. 添加 map_level 列（保持独立，不合并到 level）
    3. 删除被合并掉的行 (absorbed_ids)
    """
    if merged_df.empty:
        return original_df

    # 1. 识别需要删除的行 ID
    ids_to_drop = []
    # 构建更新映射 {id: {col: val}}
    update_map = {}
    
    for _, row in merged_df.iterrows():
        # 收集被合并的ID
        if 'absorbed_ids' in row and isinstance(row['absorbed_ids'], list):
            ids_to_drop.extend(row['absorbed_ids'])
        
        # 收集更新信息 (保持 map_level 独立)
        update_map[row['id']] = {
            'heading': row['heading'],
            'map_level': row['map_level']
        }
    
    print(f"[DEBUG] 将从原表删除的行数 (已合并): {len(ids_to_drop)}")
    
    # 2. 添加 map_level 列 (初始化为 NaN)
    if 'map_level' not in original_df.columns:
        original_df['map_level'] = float('nan')
    
    # 3. 应用更新
    updated_count = 0
    for idx in original_df.index:
        r_id = original_df.at[idx, 'id']
        if r_id in update_map:
            updates = update_map[r_id]
            original_df.at[idx, 'heading'] = updates['heading']
            original_df.at[idx, 'map_level'] = updates['map_level']
            updated_count += 1
            
    print(f"[DEBUG] 已更新行数 (Head 节点): {updated_count}")
    
    # 4. 删除被合并的行
    original_count = len(original_df)
    final_df = original_df[~original_df['id'].isin(ids_to_drop)].copy()
        
    print(f"[DEBUG] 最终行数: {len(final_df)} (删除前: {original_count})")
    return final_df


def build_hierarchy_index(df: pd.DataFrame) -> dict:
    """
    基于 map_level 构建层次化索引字典。
    返回一个嵌套字典，结构如下：
    {
        "modules": [
        {
            "heading": "模块1标题",
            "id": 4,
            "start_id": 4,   # 对应 DataFrame 中 id 列的值
            "end_id": 84,    # 对应 DataFrame 中 id 列的值 (含)
            "children": [
            {
                "heading": "子模块1标题",
                "id": 5,
                "start_id": 5,
                "end_id": 84
            },
            ...
            ]
        },
        ...
        ]
    }
    """
    # 重置索引以便顺序遍历
    df = df.reset_index(drop=True)
    
    # 构建 id 列表用于查找边界
    id_list = df['id'].tolist()
    
    # 找到所有有 map_level 的行及其位置
    toc_rows = []
    for iloc_idx, row in df.iterrows():
        if pd.notna(row.get('map_level')):
            toc_rows.append({
                'iloc_idx': iloc_idx,
                'id': row['id'],
                'heading': row['heading'],
                'map_level': int(row['map_level'])
            })
    
    if not toc_rows:
        return {"modules": []}
    
    # 获取所有层级
    all_levels = sorted(set(r['map_level'] for r in toc_rows))
    print(f"[DEBUG] 发现的层级: {all_levels}")
    
    if len(all_levels) == 0:
        return {"modules": []}
    
    top_level = all_levels[0]  # 最高层级 (数值最小)
    
    # 构建模块列表
    modules = []
    total_rows = len(df)
    
    # 找到所有顶级模块的位置
    top_level_indices = [i for i, r in enumerate(toc_rows) if r['map_level'] == top_level]
    
    for i, toc_idx in enumerate(top_level_indices):
        toc_row = toc_rows[toc_idx]
        module = {
            "heading": toc_row['heading'],
            "id": toc_row['id'],
            "map_level": toc_row['map_level'],
            "start_id": toc_row['id'],  # 使用 id 列的值
            "end_id": None,  # 稍后计算
            "children": []
        }
        
        # 确定模块结束位置：下一个顶级模块前一行的 id，或者 DataFrame 最后一行的 id
        if i + 1 < len(top_level_indices):
            next_top_toc_idx = top_level_indices[i + 1]
            next_top_iloc = toc_rows[next_top_toc_idx]['iloc_idx']
            # 结束 id 是下一个顶级模块前一行的 id
            module['end_id'] = id_list[next_top_iloc - 1]
        else:
            module['end_id'] = id_list[total_rows - 1]
        
        # 收集此模块内的子级 TOC
        children_tocs = []
        for j in range(toc_idx + 1, len(toc_rows)):
            child_row = toc_rows[j]
            # 如果遇到下一个顶级，停止
            if child_row['map_level'] == top_level:
                break
            # 如果在当前模块范围内 (按 id 判断)
            if child_row['id'] <= module['end_id']:
                children_tocs.append((j, child_row))
        
        # 构建子级模块
        for k, (child_toc_idx, child_row) in enumerate(children_tocs):
            child = {
                "heading": child_row['heading'],
                "id": child_row['id'],
                "map_level": child_row['map_level'],
                "start_id": child_row['id'],  # 使用 id 列的值
                "end_id": None
            }
            
            # 确定子模块结束位置
            if k + 1 < len(children_tocs):
                next_child_id = children_tocs[k + 1][1]['id']
                # 结束 id 是下一个子模块 id 前一行的 id
                next_child_iloc = children_tocs[k + 1][1]['iloc_idx']
                child['end_id'] = id_list[next_child_iloc - 1]
            else:
                # 最后一个子模块，延伸到父模块结束
                child['end_id'] = module['end_id']
            
            module['children'].append(child)
        
        modules.append(module)
    
    hierarchy = {"modules": modules}
    print(f"[DEBUG] 构建层次索引: {len(modules)} 个顶级模块")
    
    return hierarchy


def main():
    # 文件路径配置
    csv_path = "/Users/wuchengke/Desktop/sxjg/test_naive_1.csv"
    json_path = "/Users/wuchengke/Desktop/sxjg/tmp/陕西建工/16.陕建控股制度下-1.pdf/toc_hierarchies.json"
    
    # 1. 加载数据
    df = load_test_csv(csv_path)
    toc_list = load_toc_hierarchies(json_path)
    
    # 2. 过滤匹配的行
    matched_df = filter_tocs(df, toc_list)
    if matched_df.empty:
        print("[INFO]: No matching rows found")
        return

    # 3. 合并连续行
    merged_df = merge_consecutive_tocs(matched_df)

    # 4. 应用 TOC (保持 map_level 独立)
    final_df = apply_tocs(df, merged_df)
    
    # 5. 构建层次化索引
    hierarchy_index = build_hierarchy_index(final_df)
    
    # 6. 输出结果
    print("\n[结果] 层次化索引:")
    print(json.dumps(hierarchy_index, ensure_ascii=False, indent=2))
    
    # 7. 保存层次索引到 JSON 文件
    with open("hierarchy_index.json", "w", encoding="utf-8") as f:
        json.dump(hierarchy_index, f, ensure_ascii=False, indent=2)
    print("\n[INFO] 层次索引已保存到 hierarchy_index.json")
    
    # 8. 保存处理后的 DataFrame
    final_df.to_csv("test_naive_1_merged.csv", index=False, encoding="utf-8-sig")
    print("[INFO] 处理后的 DataFrame 已保存到 test_naive_1_merged.csv")
    
    return final_df, hierarchy_index

if __name__ == "__main__":
    main()

