import re
import unicodedata
import uuid
import numpy as np
import pandas as pd
from collections import defaultdict
from openai import OpenAI
from docx.oxml.ns import qn
try:
    from markitdown import MarkItDown
except ImportError:
    # 如果markitdown不可用，使用替代方案
    class MarkItDown:
        def convert(self, content):
            return content
from app.core.database import get_db_context
from app.core.config import settings
# TaskRedis依赖已移除，使用Redis直接追踪
from app.services.ai.prompt_service import build_prompt
from app.services.ai.response_process_service import eval_response
# ARQ依赖已移除，使用Celery替代
from app.services.ai import ai_query_service
from loguru import logger


def cal_heading_len_threshold(lines_, pct=50, pre_min=30):
    lengths = [len(l) for l in lines_]
    # 保留长度<Q2的标题
    q1 = np.percentile(lengths, pct)
    return np.max((q1, pre_min))

def denoise_doc_contents(preds_):
    punc_pattern = re.compile(r'[.,!?;:，。！？；：）】〕｝〉》’”"]$')
    denoise_rows = []

    i = 0
    while i < len(preds_):
        curr_row = list(preds_[i])  # 转 list，便于修改
        current_content = str(curr_row[2]).rstrip()
        current_len = int(curr_row[3])

        style_ = find_docstyle(curr_row[1]) # 获取para
        outset_ = find_otsetting(curr_row[1])

        j = i + 1
        while j < len(preds_):
            next_row = preds_[j]
            next_content = str(next_row[2]).lstrip()
            next_len = int(next_row[3])

            is_punc = punc_pattern.search(current_content[-1]) if current_content else None
            next_pos_code = judge_by_conditions(next_content)
            # 满足合并条件就拼接，并继续往下检查
            if (style_ is None and outset_ is None) and all(x == 0 for x in next_pos_code) and (not is_punc):
                current_content = current_content + " " + next_content
                current_len = current_len + next_len
                j += 1
            else:
                break

        # 更新合并后的 heading
        curr_row[2] = current_content
        curr_row[3] = current_len
        denoise_rows.append(tuple(curr_row))
        # 跳到未合并的下一行
        i = j
    return denoise_rows

def denoise_md_contents(texts):
    punc_pattern = re.compile(r'[.,!?;:，。！？；：）】〕｝〉》’”"]$')
    denoise_texts = []
    exist_tocs = []
    toc_zone = False

    i = 0
    while i < len(texts):
        current_content = str(texts[i]).rstrip()





        j = i + 1
        while j < len(texts):
            next_content = str(texts[j]).lstrip()

            is_punc = punc_pattern.search(current_content[-1]) if current_content else None
            next_pos_code = judge_by_conditions(next_content)
            if all(x == 0 for x in next_pos_code) and (not is_punc):
                current_content = current_content + " " + next_content
                j += 1
            else:
                break

        denoise_texts.append(current_content)
        i = j
    return denoise_texts

def heading_tb_transfer(df, max_length=80, include_reason=False, threshold=3000):
    def clean_md_txt(text):
        if isinstance(text, str) and re.search(r'!\[.*\]\(.*\)', text):  # 替换图片为占位
            return "【图像】"
        text = text.replace("|", "｜")  # 替换竖线
        if len(text) > max_length:  # 截断
            return text[:max_length] + "..."
        return text

    headers = ["原始序号", "原始内容", "初步层级估计"]
    if include_reason:
        headers.append("估计的原因")

    separator = ["-" * len(h) for h in headers]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(separator) + " |"] # 初始行

    for _, row in df.iterrows():
        row_items = [
            str(row["id"]),
            clean_md_txt(str(row["heading"])),
            str(row["level"]) if pd.notna(row["level"]) else "null"
        ]
        if include_reason:
            row_items.append(str(row["reason"]) if pd.notna(row["reason"]) else "null")

        new_line = "| " + " | ".join(row_items) + " |"
        lines.append(new_line)
    return "\n".join(lines)

def judge_by_conditions(text, scope=20):
    text = text.replace("\u3000", " ")
    text = unicodedata.normalize("NFKC", text)[:scope]

    # ========== 英文数字编号 ==========
    regex_en_num_dots = r"^\d+(?:\s*\.\s*\d+)+(?![、，。！？；：])(?=\s|$|\w|[一-龥])"
    regex_en_num_dun = r"^\d、\s{0,4}(?=\S|$)" # 1、xxx
    regex_en_num_single_dot = r"^\d+\.(?!\d)\s{0,4}(?=\S)" # 1.xxx
    regex_en_num_space = r"^[0-9]{1,2}\s{1,8}(?=\S)" # 1 xxx
    # ========== 中文数字编号 ==========
    regex_cn_num_dun = r"^[一二三四五六七八九十百千万]+、\s{0,4}(?=\S|$)"
    regex_cn_num_mix = r"^[一二三四五六七八九十百千万]+(?:\s*\.[一二三四五六七八九十百千万\d]+)+"
    regex_cn_num_plain = r"^[一二三四五六七八九十百千万]+(?=\s|$)"
    # ========== 英文括号编号 ==========
    regex_en_brac_paren = r"^[\(\（]\s*\d+(?:\.\d+)*(?!\.0)\s*[\)\）]"
    regex_en_brac_right = r"^\d+(?:\.\d+)*(?!\.0)\s*[\)\）]"
    # ========== 中文括号编号 ==========
    regex_cn_brac_paren = r"^[\(\（]\s*[一二三四五六七八九十百千万]+(?:\.[一二三四五六七八九十百千万\d]+)*\s*[\)\）]"
    regex_cn_brac_right = r"^[一二三四五六七八九十百千万]+(?:\.[一二三四五六七八九十百千万\d]+)*\s*[\)\）]"
    # ========== 中文特殊（第x章/节/条/款/...） ==========
    regex_cn_special = r"^第[一二三四五六七八九十百千万]+(?:\.[一二三四五六七八九十百千万\d]+)*(章|节|条|部分|款|目|项)?(?:\s{1,4}(?=\S)|$)"
    # ========== 英文字母编号 ==========
    regex_letter_dot = r"^[A-Za-z](?:\.\d+)*[\.、](?=\s*\S)"
    regex_letter_brac_paren = r"^[\(\（]\s*[A-Za-z](?:\.\d+)*(?!\.0)\s*[\)\）]"
    regex_letter_brac_right = r"^[A-Za-z](?:\.\d+)*(?!\.0)\s*[\)\）]"
    # ========== 附录 Appendix ==========
    regex_appendix = r"^((附件|附录|附表|附图)|(?i:appendix))[\s_\-—]{0,2}[A-Za-z\d]"

    pos_regex_conditions = [
        # 英文数字编号
        regex_en_num_dots, regex_en_num_dun, regex_en_num_single_dot, regex_en_num_space,
        # 中文数字编号
        regex_cn_num_dun, regex_cn_num_mix, regex_cn_num_plain,
        # 英文括号编号
        regex_en_brac_paren, regex_en_brac_right,
        # 中文括号编号
        regex_cn_brac_paren, regex_cn_brac_right,
        # 中文特殊
        regex_cn_special,
        # 英文字母编号
        regex_letter_dot, regex_letter_brac_paren, regex_letter_brac_right,
        # 附录
        regex_appendix
    ]

    pos_triggered_code = []
    for idx, regex in enumerate(pos_regex_conditions):
        match = re.match(regex, text)
        if match:
            pos_triggered_code.append(1)
        else:
            pos_triggered_code.append(0)
    return pos_triggered_code

def remove_by_conditions(text, len_threshold=None):
    neg_condition_num = r"^\d{3,}"
    neg_condition_http = r"(?i)(^https?://\S+|^www\.\S+|^P\.S|^\b\d{0,2}\s*(?:a\.m|p\.m)\b)"
    neg_condition_latex = r"\$[^$]*\\[A-Za-z]+(?:\s*\{[^{}]*\})?[^$]*\$"
    neg_condition_punc_end = r"[.,!?;，。！？；）】〕｝〉》’”]$"

    neg_conditions = [neg_condition_num, neg_condition_http, neg_condition_latex] #neg_condition_punc_end

    neg_triggered_code = []
    for regex in neg_conditions:
        match = re.search(regex, text)
        neg_triggered_code.append(1 if match else 0)

    if len_threshold is not None:
        neg_triggered_code.append(1 if len(text) > len_threshold else 0)
    return neg_triggered_code

'''处理markdown headings 考虑#<![等特殊规则'''
def md_heading_match(line, as_is=True):
    match = re.match(r'^\s*(#+)\s*(.*)$', line)  # 允许 `#` 后面有空格或直接跟文字
    if match:
        level = len(match.group(1))  # 计算 `#` 的数量
        if as_is:
            return line, level
        else:
            return line.lstrip('#').strip(), level  # 删除 `#` 并去除前后空格
    else:
        return line, -1

def filter_md_headings(md_lines, consider_len=False):
    md_lines = denoise_md_contents(md_lines)

    if consider_len:
        threshold = cal_heading_len_threshold(md_lines)
        print(f"[INFO] 长度超过 {threshold} 的标题会被降格")
    else:
        threshold = None

    raw_candidates = []
    for i, line in enumerate(md_lines):
        line = line.strip()
        if (
            not line or
            ('<!--' in line and '-->' in line) or  # 注释
            line.startswith("|") or                # 表格行
            "![" in line and "](" in line          # 图片行
        ):
            raw_candidates.append((i, "md注释 表格 或图片", -1, "发现md格式特殊占位行"))
        else:
            heading, raw_level = md_heading_match(line) # md 专项条件查询pos
            pos_code = judge_by_conditions(line)
            neg_code = remove_by_conditions(line, threshold)

            if any(x>0 for x in neg_code):
                raw_candidates.append((i, heading, -1, f"pos条件{pos_code} BUT neg条件{neg_code}"))
            elif raw_level>0 and all(x==0 for x in pos_code):
                raw_candidates.append((i, heading, raw_level, "发现MD符号"))
            elif raw_level<0 and any(x>0 for x in pos_code):
                raw_candidates.append((i, heading, "待定", f"pos条件{pos_code}"))
    return raw_candidates

'''处理docx headings 考虑para style'''
def find_docstyle(para_):
    try:
        style_name = para_.style.name
    except:
        style_name = "normal"
    
    # 处理style_name为None的情况
    if style_name is None:
        style_name = "normal"
    
    if style_name.startswith('Heading') or style_name.startswith('标题'):
        try:
            outline_level = int(style_name.split(' ')[1])
        except:
            outline_level = "待定"
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

def filter_doc_headings(titles_material, consider_len=False):
    titles_material = denoise_doc_contents(titles_material)  # 这个也会合并部分不合规标题

    text_lens = [tm[3] for tm in titles_material]
    if consider_len:
        threshold = cal_heading_len_threshold(text_lens)
        logger.debug(f"[INFO] 长度超过 {threshold} 的标题会被降格")
    else:
        threshold = None

    raw_candidates = []
    for id, para, text, _ in titles_material:
        style_lvl = find_docstyle(para)
        setting_lvl = find_otsetting(para)
        bold_lvl = find_bold(para)

        # 1. check .docx style settings
        if style_lvl is not None:
            raw_candidates.append((id, text, style_lvl, f"docx style {style_lvl}"))
        # 2. check .docx paragraph numbering settings
        elif setting_lvl is not None:
            raw_candidates.append((id, text, setting_lvl, f"outline setting {setting_lvl}"))
        # 3. check bold style existence
        # elif bold_lvl is not None:
        #     raw_candidates.append((id, text, "待定", f"bold style"))
        # 4. proceed condition judge
        else:
            pos_code = judge_by_conditions(text)
            neg_code = remove_by_conditions(text, threshold)
            if any(x > 0 for x in neg_code):
                raw_candidates.append((id, text, -1, f"pos条件{pos_code} BUT neg条件{neg_code}"))
            elif any(x > 0 for x in pos_code):
                raw_candidates.append((id, text, "待定", f"pos条件{pos_code}"))
            else:
                raw_candidates.append((id, text, -1, "无pos条件"))
    return raw_candidates

async def pred_titles(infos, doc_type, len_threshold=3000):
    logger.debug("🔥 正在解析文档层级结构")
    if doc_type == "pptx":
        raw_preds = filter_md_headings(infos, consider_len=False)
    elif doc_type == "md":
        raw_preds = filter_md_headings(infos, consider_len=False)
    elif doc_type=="docx":
        raw_preds = filter_doc_headings(infos, consider_len=False)
    else:
        raw_preds = []

    # raw_preds = denoise_contents(raw_preds) # 这个也会合并部分不合规标题
    level_df = clean_redundant_headings(raw_preds)

    if len(level_df)==0:
        return []

    level_txts = heading_tb_transfer(level_df, threshold=len_threshold)
    try:
        basic_preds = ""
        full_preds = []
        # for level_txt in level_txts:
        paras = {"max_tokens": len(level_txts), "basic_preds":basic_preds}
        prompt, temperature, top_p, max_tokens = build_prompt(task="eval-headings", texts=level_txts, query="", paras=paras)
        messages = [
            {"role": "system", "content": "你是一个有帮助的助手"},
            {"role": "user", "content": prompt}
        ]

        ctx_task_id = str(uuid.uuid4())
        
        # 使用Redis直接追踪任务状态，无需数据库持久化
        from app.core.dependencies import get_redis_service
        redis_service = await get_redis_service()
        await redis_service.set(f"task:{ctx_task_id}:status", "processing", ttl=7200)
        
        # 使用统一的AI查询服务
        layout_res = await ai_query_service.query_ai(
            messages=messages,
            user_id=ctx_task_id,
            conversation_id=ctx_task_id,
            timeout=300,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens
        )

        heading_preds = eval_response(layout_res)
        heading_preds = pd.DataFrame(heading_preds)
        if not basic_preds.strip(): # 只用第一次解析的作为参考
            basic_preds = heading_tb_transfer(heading_preds, threshold=len_threshold)[0]

        full_preds.append(heading_preds)
        heading_preds = pd.concat(full_preds, ignore_index=True)

    except Exception as e:
            logger.debug(f"[INFO] 大模型解析标题层级失败 原因是{e}\n所有待定标题均被降格为-1")
            level_df.rename(columns={"level": 'level'}, inplace=True)
            level_df['final_level'] = level_df['level'].replace('待定', -1)
            heading_preds = level_df.iloc[:, :3]

    if (not isinstance(heading_preds, pd.DataFrame)) or heading_preds["level"].eq(-1).all(): #如果解析失败或者全部解析为不适合做标题
        heading_preds = pd.DataFrame()
    return heading_preds

def mark_level_boundary(idx, df_):
    level = df_.loc[idx, 'level']
    if str(level) == "-1":
        return -1  # 本身是正文

    if idx + 1 >= len(df_):
        return 0  # 最后一行不是正文，也无法比较

    next_level = str(df_.loc[idx + 1, 'level'])
    if next_level == "-1":
        return 0  # 下一行是正文，不算边界

    current_code = df_.loc[idx, 'reason']
    next_code = df_.loc[idx + 1, 'reason']
    if current_code != next_code:
        return 1
    else:
        return 0

def collapse_recursive(df, indices, depth=0):
    indent = "  " * depth
    logger.debug(f"{indent}进入递归，indices={indices}")

    for k in range(len(indices) - 1):
        i, j = indices[k], indices[k + 1]
        logger.debug(f"{indent}检查标题对 i={i} ({df.at[i, 'heading']}) -> j={j} ({df.at[j, 'heading']})")

        between = df.loc[i+1:j-1]

        if between.empty:
            logger.debug(f"{indent}  between 为空, 行 {i} ({df.at[i,'heading']}) 坍缩")
            df.loc[i, "level"] = -1
            df.loc[i, "reason"] = "触发坍缩规则"
        else:
            logger.debug(f"{indent}  between 行范围 {between.index[0]}~{between.index[-1]} (共 {len(between)} 行)")
            # 在 between 内部 reason 一致的标题递归划为一组
            code2sub = defaultdict(list)
            for idx, row in between.iterrows():
                if row["level"] != -1:  # 是标题
                    code2sub[row["reason"]].append(idx)

            for sub_code, sub_indices in code2sub.items():
                logger.debug(f"{indent}  递归处理子组 reason={sub_code}, indices={sub_indices}")
                collapse_recursive(df, sub_indices, depth+1)
    logger.debug(f"{indent}退出递归，indices={indices}")

def clean_redundant_headings(data):
    df_cleaned = pd.DataFrame(data, columns=["id", "heading", "level", "reason"], index=None)
    df_cleaned['boundary'] = [mark_level_boundary(i, df_cleaned) for i in range(len(df_cleaned))]
    df_cleaned['pre_level'] = df_cleaned['level']
    df_cleaned.to_csv(f"./test.csv", index=False, encoding='utf-8-sig')

    code2indices = defaultdict(list)
    for idx, row in df_cleaned.iterrows():
        level, code = row["level"], row["reason"]
        if str(level) != "-1":  # 标题
            code2indices[code].append(idx)

    for code, indices in code2indices.items():
        collapse_recursive(df_cleaned, indices)

    # 处理边界标题
    for i, row in df_cleaned.iterrows():
        if i<1 or i==len(df_cleaned)-1:
            continue
        else:
            boundary = df_cleaned.at[i, 'boundary']
            pre_row_reason = df_cleaned.at[i-1, 'reason']
            pos_row_level = df_cleaned.at[i+1, 'level']
            if (pre_row_reason=="触发坍缩规则" and pos_row_level!=-1) and boundary==1:
                df_cleaned.at[i, 'level'] = -1
                df_cleaned.at[i, 'reason'] = "触发边界规则"

    df_cleaned.to_csv(f"./test2.csv", index=False, encoding='utf-8-sig')
    df_cleaned = df_cleaned[df_cleaned["level"] != -1].copy()  # 仅保留不是-1的部分
    return df_cleaned

def parse_outline_hier(markdown_text):
    """
    将带缩进的 Markdown 列表转换为嵌套结构，适合one-off策略
    """
    lines = markdown_text.strip().splitlines()
    stack = []
    root = []
    for line in lines:
        line = line.replace('markdown', '') # handle possible unexpected outputs
        if not line.strip():
            continue

        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        match = re.match(r"[-*+] (.+)", stripped)
        if not match:
            continue

        title = match.group(1).strip()
        node = {"chapter": title, "children": [], 'serial':1}
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
    rows = []
    def traverse(node_list, level, path_prefix):
        for node in node_list:
            split_char = settings.SPLIT_CHAR or "-->"
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

def heading_dic_trans(df, col1, col2, col3):
    result = {
        f"{row[col1]}_{row[col2]}": int(row[col3])
        for _, row in df.iterrows()
    }
    return result


'''暂时废弃代码'''
# def matches_number_dot_pattern(text):
#     # primary_regex = r"^(\d+(\.\d+)+)(\s+.+)?$"
#     primary_regex = r"^([A-Za-z0-9]+(\s*\.\s*[A-Za-z0-9]+)+)(.*)?$"
#     primary_match = re.match(primary_regex, text)
#
#     if primary_match:
#         number_dot_pattern = primary_match.group(1)
#         num_dots = number_dot_pattern.count('.')
#         return True, num_dots + 1
#     else:
#         secondary_regex = r"^(\d+\.)(\s+.+)?$"
#         secondary_match = re.match(secondary_regex, text)
#         if secondary_match:
#             return True, 1
#         else:
#             return False, 0
        
        

