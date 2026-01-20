import os
import re
import unicodedata
import uuid
from collections import Counter, defaultdict

import pandas as pd
from app.services.common.kb_utils import count_cn_en
from app.services.document_parser.table_parser import df2html
from docx.oxml.ns import qn
from tqdm import tqdm

try:
    from markitdown import MarkItDown
except ImportError:
    # 如果markitdown不可用，使用替代方案
    class MarkItDown:
        def convert(self, content):
            return content
from shared.core.config import settings
# ARQ依赖已移除，使用Celery替代
from shared.services.ai import ai_query_service
# TaskRedis依赖已移除，使用Redis直接追踪
from shared.services.ai.prompt_service import build_prompt
from shared.services.ai.response_process_service import eval_response
from shared.services.ai.response_process_service import eval_response
from loguru import logger
from shared.core.exceptions.domain_exceptions import WorkerHandlingException


# ==================== Helper Functions ====================

def save_intermediate_csv(df: pd.DataFrame, output_dir: str, filename: str):
    """
    保存中间结果DataFrame为CSV文件，使用utf-8-sig编码以支持中英文
    
    Args:
        df: 要保存的DataFrame
        output_dir: 输出目录路径
        filename: 文件名（不含扩展名）
    """
    if output_dir is None or df is None or df.empty:
        return
    
    try:
        csv_path = os.path.join(output_dir, f"{filename}.csv")
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        logger.debug(f"📊 Saved intermediate result to {csv_path}, rows={len(df)}")
    except Exception as e:
        logger.warning(f"Failed to save intermediate CSV {filename}: {e}")


# ==================== Tree Structure Functions (from sxjg) ====================

def build_tree_from_dataframe(df):
    """
    从DataFrame构建纯嵌套JSON树结构
    
    Args:
        df: DataFrame，包含 id, heading, level 列
    
    Returns:
        tree: 纯嵌套字典结构
        node_to_id: 树节点到id的映射（使用唯一的节点key）
        id_to_row: id到原始行数据的映射
    """
    headings = df[df['level'] > -1].copy()
    
    node_to_id = {}  # {(tree_node_key, parent_path): id}
    id_to_node_info = {}  # {id: (tree_node_key, parent_path)}
    id_to_row = {}
    root = {}
    stack = [(0, root, "ROOT", "")]
    
    for _, row in headings.iterrows():
        heading_txt = row['heading']
        row_id = int(row['id'])
        level = int(row['level'])
        
        # 记录id到row的映射
        id_to_row[row_id] = row.to_dict()
        
        # 找到合适的父节点
        while len(stack) > 1 and stack[-1][0] >= level:
            stack.pop()
        
        # 获取父节点信息
        parent_level, parent_dict, parent_heading, parent_path = stack[-1]
        
        # 创建树节点的唯一key：如果同一父节点下有重复标题，加上ID后缀
        tree_node_key = heading_txt

        if tree_node_key in parent_dict:
            tree_node_key = f"{heading_txt}#{row_id}"
        
        # 建立映射：使用(tree_node_key, parent_path)作为key
        node_key = (tree_node_key, parent_path)
        node_to_id[node_key] = row_id
        id_to_node_info[row_id] = node_key
        
        parent_dict[tree_node_key] = {}
        current_path = f"{parent_path}/{tree_node_key}" if parent_path else tree_node_key
        stack.append((level, parent_dict[tree_node_key], tree_node_key, current_path))
    return root, node_to_id, id_to_row


def tree_to_dataframe(tree, node_to_id, original_df):
    """
    将处理后的树结构转换回DataFrame更新
    
    Args:
        tree: 处理后的纯嵌套字典结构
        node_to_id: 节点到id的映射 {(tree_node_key, parent_path): id}
        original_df: 原始DataFrame
    
    Returns:
        updated_df: 更新后的DataFrame
    """
    # 从树中提取所有保留的标题
    def extract_headings(node_dict, current_level=1, parent_path=""):
        """递归提取所有标题及其新层级"""
        results = []
        for tree_node_key, children in node_dict.items():
            # 使用 (tree_node_key, parent_path) 作为key查找ID
            node_key = (tree_node_key, parent_path)
            row_id = node_to_id.get(node_key, -1)
            
            if row_id >= 0:
                # 从tree_node_key中提取原始标题（去掉可能的ID后缀）
                original_heading = tree_node_key.split('#')[0] if '#' in tree_node_key else tree_node_key
                
                results.append({
                    "id": row_id,
                    "heading": original_heading,
                    "level": current_level,
                    "tree_key": tree_node_key,
                    "parent_path": parent_path
                })
                # 递归处理子节点
                if isinstance(children, dict) and children:
                    current_path = f"{parent_path}/{tree_node_key}" if parent_path else tree_node_key
                    results.extend(extract_headings(children, current_level + 1, current_path))
        return results
    
    preserved_headings = extract_headings(tree)
    preserved_ids = set([h['id'] for h in preserved_headings])
    
    updated_df = original_df.copy()
    removed_count = 0
    level_changed_count = 0

    for idx, row in original_df.iterrows():
        row_id = int(row['id'])
        old_level = int(row['level']) if row['level'] not in ['Not Sure', 'nan', -1] else -1
        
        if old_level > -1:  # 原来是标题
            if row_id in preserved_ids:
                # 找到新的level
                new_level = next((h['level'] for h in preserved_headings if h['id'] == row_id), old_level)
                updated_df.at[idx, 'level'] = new_level
                if new_level != old_level:
                    level_changed_count += 1
            else:
                updated_df.at[idx, 'level'] = -1
                removed_count += 1

    logger.debug(f"Tree变更摘要: 删除标题={removed_count}, 层级变更={level_changed_count}, 保留标题={len(preserved_ids)}")
    return updated_df


def remove_isolated_nodes(tree):
    """
    规则：如果一个标题下只有一个子标题，且该子标题下没有更下级标题，
         则删除这个孤悬的子标题
    
    Args:
        tree: 纯嵌套字典结构，格式为 {heading: {子heading: {...}}}
    
    Returns:
        processed_tree: 处理后的树结构
    """    
    def recursive_check_and_remove(node_dict, parent_path=""):
        """递归检查并删除孤悬标题（不修改原字典，返回新字典）"""
        if not isinstance(node_dict, dict):
            return node_dict
        
        result_dict = {}
        
        for heading, children in node_dict.items():
            if isinstance(children, dict) and len(children) == 1:
                child_heading = list(children.keys())[0]
                grandchildren = children[child_heading]
                
                if not grandchildren or (isinstance(grandchildren, dict) and len(grandchildren) == 0):
                    result_dict[heading] = {}
                    logger.debug(f"移除孤悬子标题: {parent_path}/{heading}/{child_heading}")
                else:
                    processed_children = recursive_check_and_remove(children, f"{parent_path}/{heading}" if parent_path else heading)
                    result_dict[heading] = processed_children
            elif isinstance(children, dict) and children:
                processed_children = recursive_check_and_remove(children, f"{parent_path}/{heading}" if parent_path else heading)
                result_dict[heading] = processed_children
            else:
                result_dict[heading] = children
        
        return result_dict
    
    processed_tree = recursive_check_and_remove(tree)
    return processed_tree


def if_no_pos_code(reason_str: str) -> bool:
    """
    检查 pos_code 是否全为 0
    reason 格式: "POS [0, 0, ...] NEG [...]"
    """
    if not reason_str or not isinstance(reason_str, str):
        return True
    
    pos_match = re.search(r'POS\s*\[([^\]]*)\]', reason_str)
    if not pos_match:
        return True
    pos_content = pos_match.group(1)
    try:
        nums = [int(x.strip()) for x in pos_content.split(',') if x.strip()]
        return all(x == 0 for x in nums)
    except:
        return True


# ==================== Level Mapping Functions ====================

def build_level_mapping(df, origin_lvls, mode="max"):
    """构建层级映射关系"""
    df = df.copy()
    df["origin_level"] = origin_lvls
    mask = df['reason'].apply(lambda x: not if_no_pos_code(x))

    filtered_df = df[mask]
    mapping = filtered_df.groupby("reason")["level"].apply(list).to_dict()

    processed_mapping = {}
    for reason, lvls in mapping.items():
        positive_lvls = [lvl for lvl in lvls if lvl > -1]
        counts = Counter(lvls)

        if not positive_lvls:
            mapped_lvl = -1
        elif mode == "max":
            mapped_lvl = max(positive_lvls)
        elif mode == "freq":
            mapped_lvl = counts.most_common(1)[0][0]
        else:
            raise WorkerHandlingException(
                internal_message=f"wrong input mode: {mode}. Must be 'max' or 'freq'"
            )

        processed_mapping[reason] = {
            "lvls": lvls,
            "positive_lvls": positive_lvls,
            "freqs": dict(counts),
            "mapped_lvl": mapped_lvl
        }
    return df, processed_mapping


def execute_level_mapping(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """执行层级映射"""
    def map_row(row):
        row_code = str(row["reason"]).strip()
        need_mapping = not if_no_pos_code(row_code)

        if need_mapping:
            reason = row["reason"]
            if reason in mapping:
                return mapping[reason]["mapped_lvl"]
            else:
                return row["level"]
        return row["level"]

    df = df.copy()
    origin_est_lvls = df["level"].tolist()
    df["level"] = df.apply(map_row, axis=1)
    df["origin_level"] = origin_est_lvls
    return df


def detect_outlines_md(line):
    pos_code = judge_by_conditions(line)
    any(x>0 for x in pos_code)


def get_max_lvl(code_str: str):
    match = re.search(r'\[([^]]+)]', code_str)
    if not match:
        return "Sure"

    nums = [int(x.strip()) for x in match.group(1).split(',')]
    max_val = int(max(nums))
    return max_val if max_val>1 else "Not Sure"


def heading_tb_transfer(df, threshold=3000, max_start=50, max_end=10):
    def truncate_text(text, start_limit, end_limit):
        text = str(text)
        total_limit = start_limit + end_limit
        if len(text) <= total_limit:
            return text
        start_part = text[:start_limit]
        end_part = text[-end_limit:] if end_limit > 0 else ''
        return f"{start_part}...{end_part}"

    raw_headings = df['heading'].tolist()
    df["heading"] = df["heading"].apply(lambda x: truncate_text(x, max_start, max_end))

    sub_dfs = []
    current_rows = []
    current_len = 0
    for _, row in df.iterrows():
        row_filtered = row.drop(labels=["reason"], errors="ignore")
        row_len = sum(count_cn_en(str(v)) for v in row_filtered.values)

        if current_len + row_len > threshold and current_rows:
            sub_dfs.append(pd.DataFrame(current_rows, columns=df.columns))
            current_rows = [row.tolist()]
            current_len = row_len
        else:
            current_rows.append(row.tolist())
            current_len += row_len

    if current_rows:
        sub_dfs.append(pd.DataFrame(current_rows, columns=df.columns))
    return sub_dfs, raw_headings


def judge_by_conditions(text, scope=20, return_detail=False, CN_SPECIAL_IDX=12):
    """
    判断文本的编号模式并返回特征码
    
    Args:
        text: 输入文本
        scope: 检查的文本范围
        return_detail: 是否返回详细信息（包括单位类型）
        CN_SPECIAL_IDX: 中文特殊编号的索引位置
    
    Returns:
        如果 return_detail=False: 返回 pos_triggered_code 列表
        如果 return_detail=True: 返回 (pos_triggered_code, detail_info) 元组
            其中 detail_info 是包含额外信息的字典，例如中文单位类型
    """
    text = text.replace("\u3000", " ")
    text = unicodedata.normalize("NFKC", text)[:scope]

    # ========== English Numbering ==========
    regex_en_num_dots = r"^\d+(?:\s*\.\s*\d+)+(?![、，。！？；：])(?=\s|$|\w|[一-龥])"
    regex_en_num_dun = r"^\d、\s{0,4}(?=\S|$)"  # 1、xxx
    regex_en_num_dots_dun = r"^\d+(?:\.\d+)*、\s*(?=[A-Za-z一-龥])"
    regex_en_num_single_dot = r"^\d+\.(?!\d)\s{0,4}(?=\S)"  # 1.xxx
    regex_en_num_space = r"^[0-9]{1,2}\s{1,8}(?=\S)"  # 1 xxx
    # ========== Chinese Numbering ==========
    regex_cn_num_dun = r"^[一二三四五六七八九十百千万]+、\s{0,4}(?=\S|$)"
    regex_cn_num_mix = r"^[一二三四五六七八九十百千万]+(?:\s*\.[一二三四五六七八九十百千万\d]+)+"
    regex_cn_num_plain = r"^[一二三四五六七八九十百千万]+(?=\s|$)"
    # ========== English Bracketing ==========
    regex_en_brac_paren = r"^[\(\（]\s*\d+(?:\.\d+)*(?!\.0)\s*[\)\）]"
    regex_en_brac_right = r"^\d+(?:\.\d+)*(?!\.0)\s*[\)\）]"
    # ========== Chinese Bracketing ==========
    regex_cn_brac_paren = r"^[\(\（]\s*[一二三四五六七八九十百千万]+(?:\.[一二三四五六七八九十百千万\d]+)*\s*[\)\）]"
    regex_cn_brac_right = r"^[一二三四五六七八九十百千万]+(?:\.[一二三四五六七八九十百千万\d]+)*\s*[\)\）]"
    # ========== Chinese Special (第x章/节/条/款/...) ==========
    regex_cn_special = r"^第[一二三四五六七八九十百千万\d]+(?:\.[一二三四五六七八九十百千万\d]+)*(章|节|条|部分|款|目|项|编|篇|卷|辑)?(?=$|\s|[A-Za-z0-9\u4e00-\u9fa5])"
    # ========== English Letter Numbering ==========
    regex_letter_dot = r"^[A-Za-z](?:\.\d+)*[\.、](?=\s*\S)"
    regex_letter_brac_paren = r"^[\(\（]\s*[A-Za-z](?:\.\d+)*(?!\.0)\s*[\)\）]"
    regex_letter_brac_right = r"^[A-Za-z](?:\.\d+)*(?!\.0)\s*[\)\）]"
    # ========== Appendix ==========
    regex_appendix = r"^((附件|附录|附表|附图)|(?i:appendix))[\s_\-—]{0,4}[[一二三四五六七八九十A-Za-z\d]"

    pos_regex_conditions = [
        # English Numbering
        regex_en_num_dots, regex_en_num_dun, regex_en_num_single_dot, regex_en_num_space, regex_en_num_dots_dun,
        # Chinese Numbering
        regex_cn_num_dun, regex_cn_num_mix, regex_cn_num_plain,
        # English Bracketing
        regex_en_brac_paren, regex_en_brac_right,
        # Chinese Bracketing
        regex_cn_brac_paren, regex_cn_brac_right,
        # Chinese Special
        regex_cn_special,
        # English Letter Numbering
        regex_letter_dot, regex_letter_brac_paren, regex_letter_brac_right,
        # Appendix
        regex_appendix
    ]

    pos_triggered_code = []
    reason_suffix_parts = []
    
    for idx, regex in enumerate(pos_regex_conditions):
        match = re.match(regex, text)
        if match:
            matched_text = match.group(0)
            symbols = ".-"
            count_ = (sum(matched_text.count(s) for s in symbols) + 1)
            
            # special handling for Chinese special characters (第x章/节/条/...)
            if idx == CN_SPECIAL_IDX and return_detail:
                unit_match = re.search(r'(章|节|条|部分|款|目|项|编|篇|卷|辑)', matched_text)
                if unit_match:
                    unit = unit_match.group(1)
                    reason_suffix_parts.append(f"[CN:{unit}]")
            pos_triggered_code.append(count_)
        else:
            pos_triggered_code.append(0)
    
    if return_detail:
        detail_info = {
            'reason_suffix': ' '.join(reason_suffix_parts) if reason_suffix_parts else ''
        }
        if detail_info['reason_suffix']:
            detail_info['reason_suffix'] = ' ' + detail_info['reason_suffix']
        return pos_triggered_code, detail_info
    return pos_triggered_code


def remove_by_conditions(text, include_punc=False):
    neg_condition_num = r"^\d{3,}"
    neg_condition_zero = r"^0\.\d+[\u4e00-\u9fa5A-Za-z\S]*"  # 0.2xxx
    neg_decimal_only = r"^\d*\.\d+$"  # 0.2 .23
    neg_condition_http = r"(?i)(^https?://\S+|^www\.\S+|^P\.S|^\b\d{0,2}\s*(?:a\.m|p\.m)\b)"
    neg_condition_latex = r"\$[^$]*\\[A-Za-z]+(?:\s*\{[^{}]*\})?[^$]*\$"
    neg_condition_punc_end = r"[.,;，。；]$"

    neg_conditions = [neg_condition_num, neg_condition_http, neg_condition_latex, neg_condition_zero, neg_decimal_only]

    neg_triggered_code = []
    for regex in neg_conditions:
        match = re.search(regex, text)
        neg_triggered_code.append(1 if match else 0)
        
    if include_punc:
        match = re.search(neg_condition_punc_end, text)
        neg_triggered_code.append(1 if match else 0)
    else:
        neg_triggered_code.append(0)
        
    return neg_triggered_code


def md_heading_match(line, as_is=True):
    '''handle markdown headings, considering # < ! [....'''
    match = re.match(r'^\s*(#+)\s*(.*)$', line)
    if match:
        level = len(match.group(1))  # count the number of '#'
        if as_is:  # determine if remove the '#'
            return line, level
        else:
            return line.lstrip('#').strip(), level
    else:
        return line, -1


def filter_md_headings(md_lines, num_pos=17, num_neg=6):
    """过滤Markdown标题候选"""
    raw_candidates = []
    for i, line in enumerate(md_lines):
        line = line.strip()
        if not line:
            continue

        if (
            ('<!--' in line and '-->' in line) or  # annotation line
            line.startswith("|") or                # table line
            line.startswith("<table>") or
            "![" in line and "](" in line          # image line
        ):
            est_lvl = -1
            zero_pos_code = [0] * num_pos
            zero_neg_code = [0] * num_neg
            str_lvl = f"POS {zero_pos_code} NEG {zero_neg_code}"
            line = "resource or annotation"
        else:
            line_clean, hash_lvl = md_heading_match(line, as_is=False)  # detect "#" in .md lines
            pos_code, detail_info = judge_by_conditions(line_clean, return_detail=True)
            neg_code = remove_by_conditions(line_clean)

            if any(x>0 for x in neg_code):
                code_lvl = -1
                code_str = f"POS {pos_code}{detail_info.get('reason_suffix', '')} NEG {neg_code}"

            elif any(x>0 for x in pos_code) and all(x==0 for x in neg_code):
                code_lvl = get_max_lvl(str(pos_code))
                code_str = f"POS {pos_code}{detail_info.get('reason_suffix', '')} NEG {neg_code}"

            else:
                code_lvl = -1
                code_str = f"POS {pos_code} NEG {neg_code}"

            if hash_lvl<=0:
                est_lvl = code_lvl
                str_lvl = code_str
            else:
                if isinstance(code_lvl, int):
                    est_lvl = max(hash_lvl, code_lvl)  # current miner tend to produce fewer #s
                else:
                    est_lvl = code_lvl  # code_lvl could be not sure
                str_lvl = f"{hash_lvl}# AND {code_str}"
        raw_candidates.append((i, line, est_lvl, str_lvl))

    preds_df = pd.DataFrame(raw_candidates, columns=["id", "heading", "level", "reason"], index=None)
    return preds_df


def filter_doc_headings(titles_material, enable_regx=True, enable_style_check=False):
    """过滤DOCX标题候选"""
    def find_docstyle(para_):
        try:
            style_name = para_.style.name
        except:
            style_name = "normal"
        if style_name.startswith('Heading') or style_name.startswith('标题'):
            try:
                outline_level = int(style_name.split(' ')[1])
            except:
                outline_level = "Not Sure"
            return outline_level
        else:
            return None

    def find_otsetting(para_):
        ppr = para_._element.find(qn('w:pPr'))
        if not (ppr is None):
            plvl = ppr.find(qn('w:outlineLvl'))
        else:
            return None

        if plvl is not None:
            outline_level = int(plvl.get(qn('w:val'))) + 1
            return outline_level
        else:
            return None

    def find_bold(para_):
        if para_.runs and all(run.bold for run in para_.runs if run.text.strip()):
            return True
        else:
            return None

    raw_candidates = []
    for ele_id, para, text in tqdm(titles_material, total=len(titles_material), desc=f"Filtering docx heading candidates..."):
        str_lvl = ""
        est_lvl = None
        style_lvl = find_docstyle(para)
        setting_lvl = find_otsetting(para)

        # 1. check .docx style settings
        if style_lvl is not None:
            est_lvl = style_lvl
            str_lvl = f"style-{style_lvl}"

        # 2. check .docx paragraph numbering settings
        elif setting_lvl is not None:
            est_lvl = setting_lvl
            str_lvl = f"outline-{setting_lvl}"

        # 3. check bold style existence
        if enable_style_check:
            bold_lvl = find_bold(para)
            if bold_lvl is not None and est_lvl is None:
                est_lvl = "Not Sure"
                str_lvl = f"bold-{bold_lvl}"

        # 4. proceed condition judge
        if enable_regx:
            pos_code, detail_info = judge_by_conditions(text, return_detail=True)
            neg_code = remove_by_conditions(text)

            if any(x > 0 for x in neg_code):
                code_lvl = -1
                code_str = f"POS {pos_code}{detail_info.get('reason_suffix', '')} NEG {neg_code}"
            elif any(x > 0 for x in pos_code) and all(x==0 for x in neg_code):
                code_lvl = get_max_lvl(str(pos_code))
                code_str = f"POS {pos_code}{detail_info.get('reason_suffix', '')} NEG {neg_code}"
            else:
                code_lvl = -1
                code_str = f"POS {pos_code} NEG {neg_code}"

            if est_lvl is None:
                est_lvl = code_lvl
                str_lvl = code_str
            else:
                str_lvl = f"{str_lvl} AND {code_str}"
        raw_candidates.append((ele_id, text, est_lvl, str_lvl))

    preds_df = pd.DataFrame(raw_candidates, columns=["id", "heading", "level", "reason"], index=None)

    # initial merge isolated and short texts
    preds_df = postprocess_headings(preds_df, task="merge_continuous")
    preds_df = postprocess_headings(preds_df, task="merge_short")
    return preds_df


async def hiearchy_llm(df, top_title=None, model_name=None, max_depth=6, max_len=8192, task="eval-headings", toc_context=None):
    """Apply LLM to analyze the hierarchy of headings
    
    Args:
        df: DataFrame with id, heading columns
        top_title: Optional top title for context
        model_name: LLM model name (optional, uses default if None)
        max_depth: Maximum hierarchy depth
        max_len: Maximum output tokens
        task: Prompt task type - "eval-headings" for general document, "eval-toc-headings" for TOC
        toc_context: Optional formatted TOC context string for guiding level assignment
    
    Returns:
        List of dicts with id and level
    """
    level_html = df2html(df)
    ot_limit = int(len(level_html) * 1.2)
    ot_limit = min(ot_limit, max_len)

    paras = {"max_tokens": ot_limit, "max_depth": max_depth, "top_title": top_title, "toc_context": toc_context or ""}
    prompt, temperature, top_p, max_tokens = build_prompt(task=task, texts=level_html, query="", paras=paras)
    messages = [
        {"role": "system", "content": "you are a document auditing expert"},
        {"role": "user", "content": prompt}
    ]
    
    try:
        answer = await ai_query_service.query_ai(
            messages=messages,
            user_id="layout_parser",
            model=model_name,
            stream=False,
            max_tokens=max_tokens,
            temperature=temperature
        )
        layout_res = eval_response(answer)
        return layout_res
    except Exception as e:
        logger.error(f"detect hierarchy by LLM failed: {e}")
        raise


async def pred_titles(infos, doc_type, toc_hierarchies=None, prompt_limt=4000, enable_regx=True, smart_parse=False, model_name=None, output_dir=None):
    """
    解析文档标题层级
    
    Args:
        infos: 文档信息
        doc_type: 文档类型 (pptx, md, docx)
        toc_hierarchies: TOC层级信息（如果有）
        prompt_limt: prompt字符限制
        enable_regx: 是否启用正则匹配
        smart_parse: 是否使用LLM智能解析
        model_name: LLM模型名称
        output_dir: 输出目录，用于保存中间结果CSV
    """
    logger.info(f"🔥 开始解析文档层级结构: doc_type={doc_type}, smart_parse={smart_parse}, 候选标题数={len(infos)}")
    
    if doc_type == "pptx":
        raw_preds = filter_md_headings(infos)
    elif doc_type == "md":
        raw_preds = filter_md_headings(infos)
    elif doc_type == "docx":
        raw_preds = filter_doc_headings(infos, enable_regx)
    else:
        raw_preds = pd.DataFrame(columns=["id", "heading", "level", "reason"])

    # 2. parse smart/not smart
    # Save raw_preds as preds_1
    save_intermediate_csv(raw_preds, output_dir, "preds_1_raw_filtered")
    heading_preds = est_hierarchies_naive(raw_preds, smart_parse, output_dir=output_dir)
    # Save heading_preds as preds_2
    save_intermediate_csv(heading_preds, output_dir, "preds_2_naive_processed")

    if smart_parse:
        heading_preds = await est_hierarchies_llm(heading_preds, prompt_limt, toc_hierarchies, model_name=model_name, output_dir=output_dir)
        logger.info("✅ LLM hierarchy parsing completed")

    # 3. final polishing for certain types
    if doc_type in ["docx"]:
        heading_preds = postprocess_headings(heading_preds, task="merge_continuous")
        heading_preds = postprocess_headings(heading_preds, task="merge_short")
        heading_preds = postprocess_headings(heading_preds, task="judge_negs")
        logger.debug("Docx hiearchy detection postprocessing completed")

    if heading_preds["level"].eq(-1).all(): # if non are estimated as headings
        logger.warning("⚠️ No valid headings estimated")
        heading_preds = pd.DataFrame()
    else:
        heading_preds['level'] = pd.to_numeric(heading_preds['level'], errors='coerce').fillna(-1).astype(int)
        
        # process isolated nodes
        try:
            tree, node_to_id, _ = build_tree_from_dataframe(heading_preds)
            processed_tree = remove_isolated_nodes(tree)
            heading_preds = tree_to_dataframe(processed_tree, node_to_id, heading_preds)
        except Exception as e:
            logger.warning(f"Tree structure optimization failed, skipping: {e}")
        
        logger.info(f"✅ Heading parsing completed, final {len(heading_preds[heading_preds['level'] > 0])} valid headings")
    
    # Save heading_preds as preds_5
    save_intermediate_csv(heading_preds, output_dir, "preds_5_final_output")
    return heading_preds


def est_hierarchies_naive(raw_preds, proceed_smart=True, output_dir=None):
    """Detect hierarchies by non-LLM
    
    Args:
        raw_preds: raw data
        proceed_smart: whether to proceed with smart parsing
        output_dir: output directory, used to save intermediate results CSV
    """
    logger.debug("🚀 non-llm parsing => recursive processing")
    save_preds = raw_preds.copy()

    heading_preds = postprocess_headings(raw_preds, task="collapse")
    save_preds.insert(save_preds.columns.get_loc('level')+1, 'lvl_cola', heading_preds['level'].tolist())

    heading_preds = postprocess_headings(heading_preds, task="judge_negs")
    save_preds.insert(save_preds.columns.get_loc('lvl_cola')+1, 'lvl_neg', heading_preds['level'].tolist())
    save_preds['reason'] = heading_preds['reason']

    # mapping based on freq
    if not proceed_smart:
        heading_preds['level'] = heading_preds['level'].map(lambda x: -1 if str(x)=='Not Sure' else x)
        heading_preds, lvl_mapping = build_level_mapping(heading_preds, heading_preds['level'].tolist(), mode="freq")
        heading_preds = execute_level_mapping(heading_preds, lvl_mapping)
        heading_preds.drop("origin_level", axis=1, inplace=True)
        save_preds.insert(save_preds.columns.get_loc('lvl_neg')+1, 'lvl_map', heading_preds['level'].tolist())

    return heading_preds


async def est_hierarchies_llm(raw_preds, prompt_limt, toc_hierarchies=None, max_len=30, max_depth=6, model_name=None, output_dir=None):
    """LLM-based hiearchy detection
    
    Args:
        raw_preds: raw data
        prompt_limt: prompt character limit
        toc_hierarchies: TOC hierarchies
        max_len: maximum heading length
        max_depth: maximum hierarchy depth
        model_name: LLM model name
        output_dir: output directory, used to save intermediate results CSV
    """
    if len(raw_preds) == 0:
        return pd.DataFrame(columns=["id", "heading", "level", "reason"])

    full_preds = []
    level_dfs, raw_headings = heading_tb_transfer(raw_preds, threshold=prompt_limt, max_start=max_len, max_end=5)

    basic_df = level_dfs[0]
    try:
        logger.debug("🚀 smart parse => interpreting hierarchy patterns...")
        df4llm = basic_df.drop(columns=["reason"])
        logger.debug(f"DataFrame transformation completed, rows: {len(df4llm)}")
        
        layout_res = await hiearchy_llm(df4llm, "", model_name, max_depth)
        
        base_preds = pd.DataFrame(layout_res)
        base_preds.insert(1, "heading", basic_df["heading"].values)  # insert original headings back
        base_preds["reason"] = basic_df["reason"].values

        base_preds, lvl_mapping = build_level_mapping(base_preds, basic_df['level'].tolist(), mode="freq")
        logger.debug(f"mapping development finished, there are {len(lvl_mapping)} rules")

        # Save base_preds as preds_3
        save_intermediate_csv(base_preds, output_dir, "preds_3_llm_base")

        if len(level_dfs) > 1:
            logger.debug(f"mapping dataframe to levels, there are {len(level_dfs)} dataframes...")
            for l, level_df in tqdm(enumerate(level_dfs), total=len(level_dfs), desc=f"mapping and post-processing..."):
                level_df = execute_level_mapping(level_df, lvl_mapping)  # record origin level for debug
                full_preds.append(level_df)
        else:
            full_preds.append(base_preds)

        full_preds = pd.concat(full_preds, ignore_index=True)
        full_preds['heading'] = raw_headings
        
        full_preds.drop("origin_level", axis=1, inplace=True)
        save_intermediate_csv(full_preds, output_dir, "preds_4_llm_final")

    except Exception as e:
        logger.warning(f"LLM-based parsing fails due to {e}, using non-llm pipeline...")
        full_preds = pd.concat(level_dfs, ignore_index=True)
        full_preds = est_hierarchies_naive(full_preds)
    return full_preds


def collapse_recursive(df, task, indices, merge_th=3, checked_pairs=None, depth=0):
    """递归折叠处理"""
    if checked_pairs is None:
        checked_pairs = set()

    if len(indices) < 2:
        return

    for k in range(len(indices) - 1):
        i, j = indices[k], indices[k + 1]
        if (i, j) in checked_pairs:
            continue
        checked_pairs.add((i, j))

        between = df.loc[i+1:j-1]
        i_txt = df.at[i, 'heading'].strip()
        j_txt = df.at[j, 'heading'].strip()

        if task == "merge_short" and len(between) > 0:
            between_lens = [count_cn_en(c) for c in between['heading'].tolist()]
            between_lvls = [bl for bl in between['level'].tolist()]
            i_half_len = int(count_cn_en(i_txt) / 2)
            too_short = sum(between_lens) <= merge_th or sum(between_lens) < i_half_len

            if too_short and all(bl == -1 for bl in between_lvls):  # only non-headings can be merged
                logger.debug(f"⚠️ too short between {i}=>{i_txt[:15]} and {j}=>{j_txt[:15]} => merge to {i}")
                between_txts = [
                    str(r["heading"]).strip()
                    for _, r in between.iterrows()
                    if isinstance(r.get("heading"), str) and r["heading"].strip()
                ]

                if between_txts:
                    joined_txt = "\n".join(between_txts)
                    df.at[i, "heading"] = f"{i_txt} {joined_txt}"

                for idx in between.index:
                    df.at[idx, "level"] = -1
                    df.at[idx, "reason"] = f"Merged into {i}"
                logger.debug(f"\tmerged texts: {joined_txt[:50]}...")

        elif task == "collapse" and len(between) == 0:
            logger.debug(f"⚠️ Empty between i={i_txt[:15]}, j={j_txt[:15]} => set i.level=-1, j.level=Not Sure")
            df.at[i, "level"] = "Not Sure"
            df.at[j, "level"] = "Not Sure"

        # ========== get subgroups for recursive tasks ==========
        sub_between = between[between["level"] != -1]
        code2sub = defaultdict(list)
        for idx, row in sub_between.iterrows():
            level = row["level"]
            reason = row["reason"]
            if level != -1:
                code2sub[(level, reason)].append(idx)

        for _, sub_indices in code2sub.items():
            collapse_recursive(df, task, sub_indices, merge_th, checked_pairs, depth+1)


def postprocess_headings(df, task, max_depth=-1):
    """标题后处理"""
    if task == "judge_negs":
        for i, row in df.iterrows():
            neg_code = remove_by_conditions(row['heading'], include_punc=True)
            if any(x > 0 for x in neg_code):
                current_code = str(df.loc[i, "reason"])
                
                neg_match = re.search(r'(.*NEG\s*)\[[^\]]*\](.*)', current_code)
                if neg_match:
                    update_code = f"{neg_match.group(1)}{neg_code}{neg_match.group(2)}"
                else:
                    update_code = f"{current_code} NEG {neg_code}"
                
                df.loc[i, "level"] = -1
                df.loc[i, "reason"] = update_code
        return df

    elif task == "merge_continuous":
        denoised_rows = []
        punc_pattern = re.compile(r'[.,!?;:，。！？；：）】〕｝〉》’”"]$')

        i = 0
        while i < len(df):
            row = df.iloc[i]
            current_content = str(row['heading']).strip()
            current_level = row['level']

            j = i + 1
            while j < len(df):
                next_row = df.iloc[j]
                next_content = str(next_row['heading']).strip()
                next_level = next_row['level']

                # both current and next rows are not heading & current row has no punctuation -> merge
                current_not_punc = not punc_pattern.search(current_content[-2:])
                if (current_level == -1 and next_level == -1) and current_not_punc:
                    current_content += " " + next_content
                    j += 1
                else:
                    break

            merge_row = row.copy()
            merge_row['heading'] = current_content
            denoised_rows.append(tuple(merge_row))
            i = j
        return pd.DataFrame(denoised_rows, columns=["id", "heading", "level", "reason"])

    elif task == "merge_short" or task == "collapse":
        group2indices = defaultdict(list)
        for idx, row in df.iterrows():
            level = row["level"]
            reason = row["reason"]
            if level != -1:
                group2indices[(level, reason)].append(idx)

        checked_pairs = set()
        for _, indices in group2indices.items():
            collapse_recursive(df, task, indices, merge_th=3, checked_pairs=checked_pairs, depth=0)

        if task == "merge_short":
            drop_between = df.index[df["reason"].astype(str).str.startswith("Merged into", na=False)].tolist()
            if drop_between:
                logger.debug(f"🛠️ Delete rows labeled as merged into, total {len(drop_between)} rows")
                df.drop(drop_between, inplace=True)
                df.reset_index(drop=True, inplace=True)
        return df

    else:
        return None


def parse_outline_hier(markdown_text):
    """
    将带缩进的 Markdown 列表转换为嵌套结构，适合one-off策略
    """
    lines = markdown_text.strip().splitlines()
    stack = []
    root = []
    for line in lines:
        line = line.replace('markdown', '')  # handle possible unexpected outputs
        if not line.strip():
            continue

        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        match = re.match(r"[-*+] (.+)", stripped)
        if not match:
            continue

        title = match.group(1).strip()
        node = {"chapter": title, "children": [], 'serial': 1}
        level = indent // 2  # 每两个空格作为一级（可根据实际情况调整）
        if level == 0:
            node['serial'] = len(root)+1
            root.append(node)
            stack = [(level, node)]
        else:
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                parent = stack[-1][1]
                node['serial'] = len(parent['children']) + 1
                parent["children"].append(node)
            stack.append((level, node))
    return root


def outline_to_markdown(nodes, level=0, path=""):
    """将大纲转换为Markdown格式"""
    rows = []
    def traverse(node_list, level, path_prefix):
        for node in node_list:
            split_char = settings.SPLIT_CHAR or "/"
            current_path = f"{path_prefix} {split_char} {node['chapter']}" if path_prefix else node['chapter']
            rows.append({
                "path": current_path,
                "title": node["chapter"],
                "thoughts": node.get("thoughts", "").strip(),
                "level": level
            })
            if node.get("children"):
                traverse(node["children"], level + 1, current_path)
    traverse(nodes, level, path)
    return pd.DataFrame(rows)
