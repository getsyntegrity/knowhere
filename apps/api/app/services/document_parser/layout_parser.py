import re
import unicodedata
import uuid
import pandas as pd
from tqdm import tqdm
from collections import defaultdict, Counter
from docx.oxml.ns import qn
from app.services.common.kb_utils import count_cn_en
from app.services.document_parser.table_parser import df2html

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


def build_level_mapping(df, origin_lvls, mode="max"):
    df = df.copy()
    df["origin_level"] = origin_lvls
    mask = df['reason'] != "no pos conditions"

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
            raise "wrong input mode"

        processed_mapping[reason] = {
            "lvls": lvls,
            "positive_lvls": positive_lvls,
            "freqs": dict(counts),
            "mapped_lvl": mapped_lvl
        }
    return df, processed_mapping

def execute_level_mapping(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    def map_row(row):
        row_code = str(row["reason"]).strip()
        need_mapping = (row_code.strip() != "no pos conditions")
        if need_mapping:
            reason = row["reason"]
            if reason in mapping:
                return mapping[reason]["mapped_lvl"]
            else:
                return -1
        return row["level"]

    df = df.copy()
    origin_est_lvls = df["level"].tolist()
    df["level"] = df.apply(map_row, axis=1)
    df["origin_level"] = origin_est_lvls
    return df

def detect_outlines_md(line):
    pos_code = judge_by_conditions(line)
    any(x>0 for x in pos_code)
    pass

def get_max_lvl(code_str: str):
    match = re.search(r'\[([^]]+)]', code_str)
    if not match:
        return "Sure"

    nums = [int(x.strip()) for x in match.group(1).split(',')]
    max_val = int(max(nums))
    return max_val if max_val>1 else "Not Sure"

def heading_tb_transfer(df, threshold=3000, max_start=50, max_end=10):
    def truncate_text(text, start_limit, end_limit):
        #TODO use count_cn_en to define the scope
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

def judge_by_conditions(text, scope=20):
    text = text.replace("\u3000", " ")
    text = unicodedata.normalize("NFKC", text)[:scope]

    # TODO can be expanded to include more patterns, the more patterns, the more accurate mapping e.g.， 1.2、xxx
    # ========== 英文数字编号 ==========
    regex_en_num_dots = r"^\d+(?:\s*\.\s*\d+)+(?![、，。！？；：])(?=\s|$|\w|[一-龥])"
    regex_en_num_dun = r"^\d、\s{0,4}(?=\S|$)" # 1、xxx
    regex_en_num_dots_dun = r"^\d+(?:\.\d+)*、\s*(?=[A-Za-z一-龥])"
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
    # regex_cn_special = r"^第[一二三四五六七八九十百千万]+(?:\.[一二三四五六七八九十百千万\d]+)*(章|节|条|部分|款|目|项)?(?:\s{1,4}(?=\S)|$)"
    regex_cn_special = r"^第[一二三四五六七八九十百千万\d]+(?:\.[一二三四五六七八九十百千万\d]+)*(章|节|条|部分|款|目|项)?(?=$|\s|[A-Za-z0-9\u4e00-\u9fa5])"
    # ========== 英文字母编号 ==========
    regex_letter_dot = r"^[A-Za-z](?:\.\d+)*[\.、](?=\s*\S)"
    regex_letter_brac_paren = r"^[\(\（]\s*[A-Za-z](?:\.\d+)*(?!\.0)\s*[\)\）]"
    regex_letter_brac_right = r"^[A-Za-z](?:\.\d+)*(?!\.0)\s*[\)\）]"
    # ========== 附录 Appendix ==========
    regex_appendix = r"^((附件|附录|附表|附图)|(?i:appendix))[\s_\-—]{0,2}[A-Za-z\d]"

    pos_regex_conditions = [
        # 英文数字编号
        regex_en_num_dots, regex_en_num_dun, regex_en_num_single_dot, regex_en_num_space, regex_en_num_dots_dun,
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
            symbols = ".-" #TODO can be expanded to include more symbols indicating level depth
            count_ = (sum(match.group(0).count(s) for s in symbols) + 1)
            pos_triggered_code.append(count_)
        else:
            pos_triggered_code.append(0)
    return pos_triggered_code

def remove_by_conditions(text, include_punc=False):
    neg_condition_num = r"^\d{3,}"
    neg_condition_zero = r"^0\.\d+[\u4e00-\u9fa5A-Za-z\S]*" # 0.2xxx
    neg_decimal_only = r"^\d*\.\d+$" # 0.2 .23
    neg_condition_http = r"(?i)(^https?://\S+|^www\.\S+|^P\.S|^\b\d{0,2}\s*(?:a\.m|p\.m)\b)"
    neg_condition_latex = r"\$[^$]*\\[A-Za-z]+(?:\s*\{[^{}]*\})?[^$]*\$"
    neg_condition_punc_end = r"[.,;，。；]$"

    neg_conditions = [neg_condition_num, neg_condition_http, neg_condition_latex, neg_condition_zero, neg_decimal_only]
    if include_punc:
        neg_conditions.append(neg_condition_punc_end)

    neg_triggered_code = []
    for regex in neg_conditions:
        match = re.search(regex, text)
        neg_triggered_code.append(1 if match else 0)
    return neg_triggered_code

def md_heading_match(line, as_is=True):
    '''handle markdown headings, considering # < ! [....'''
    match = re.match(r'^\s*(#+)\s*(.*)$', line)
    if match:
        level = len(match.group(1))  # count the number of '#'
        if as_is: # determine if remove the '#'
            return line, level
        else:
            return line.lstrip('#').strip(), level
    else:
        return line, -1

def filter_md_headings(md_lines):
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
            str_lvl = "No pos conditions"
            line = "resource or annotation"
        else:
            line_clean, hash_lvl = md_heading_match(line, as_is=False) # detect "#" in .md lines
            pos_code = judge_by_conditions(line_clean)
            neg_code = remove_by_conditions(line_clean)

            if any(x>0 for x in neg_code):
                code_lvl = -1
                code_str = f"pos conditions {pos_code} BUT neg conditions {neg_code}"

            elif any(x>0 for x in pos_code) and all(x==0 for x in neg_code):
                code_lvl = get_max_lvl(str(pos_code))
                code_str = f"pos conditions {pos_code} AND no neg conditions"

            else:
                code_lvl = -1
                code_str = f"No pos conditions"

            if hash_lvl<=0:
                est_lvl = code_lvl
                str_lvl = code_str
            else:
                if isinstance(code_lvl, int):
                    est_lvl = max(hash_lvl, code_lvl) # current miner tend to produce fewer #s
                else:
                    est_lvl = code_lvl # code_lvl could be not sure
                str_lvl = f"{hash_lvl}# AND {code_str}"
        raw_candidates.append((i, line, est_lvl, str_lvl))

    preds_df = pd.DataFrame(raw_candidates, columns=["id", "heading", "level", "reason"], index=None)
    return preds_df

def filter_doc_headings(titles_material, enable_regx=True, enable_style_check=False):
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
                str_lvl = f"{str_lvl} AND bold-{bold_lvl}"

        # 4. proceed condition judge
        if enable_regx:
            pos_code = judge_by_conditions(text)
            neg_code = remove_by_conditions(text)

            if any(x > 0 for x in neg_code):
                code_lvl = -1
                code_str = f"pos conditions {pos_code} BUT neg conditions {neg_code}"
            elif any(x > 0 for x in pos_code) and all(x==0 for x in neg_code):
                code_lvl = get_max_lvl(str(pos_code))
                code_str = f"pos conditions {pos_code} AND no neg conditions"
            else:
                code_lvl = -1
                code_str = f"no pos conditions"

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

async def pred_titles(infos, doc_type, prompt_limt=4000, enable_regx=True, smart_parse=False):
    logger.info(f"🔥 开始解析文档层级结构: doc_type={doc_type}, smart_parse={smart_parse}, 候选标题数={len(infos)}")
    if doc_type == "pptx":
        raw_preds = filter_md_headings(infos)
    elif doc_type == "md":
        raw_preds = filter_md_headings(infos)
    elif doc_type=="docx":
        logger.debug("过滤docx标题候选...")
        raw_preds = filter_doc_headings(infos, enable_regx)
        logger.debug(f"过滤完成，保留 {len(raw_preds)} 个候选标题")
    else:
        raw_preds = []

    # 2. parse smart/not smart
    # raw_preds.to_csv(f"./test_naive_1.csv", index=False, encoding='utf-8-sig')
    logger.debug("使用非LLM方法进行初步层级解析...")
    heading_preds = est_hierarchies_naive(raw_preds, smart_parse)
    logger.debug(f"初步解析完成，识别 {len(heading_preds)} 个潜在标题")

    if smart_parse:
        logger.info("⏳ 启用智能解析模式，准备调用AI服务（这可能需要1-3分钟）...")
        heading_preds = await est_hierarchies_llm(heading_preds, prompt_limt)
        logger.info("✅ 智能解析完成")

    # 3. final polishing for certain types
    if doc_type in ["docx"]:
        logger.debug("对docx标题进行后处理优化...")
        heading_preds = postprocess_headings(heading_preds, task="merge_continuous")
        heading_preds = postprocess_headings(heading_preds, task="merge_short")
        heading_preds = postprocess_headings(heading_preds, task="judge_negs")
        logger.debug("后处理完成")

    if heading_preds["level"].eq(-1).all(): # non are estimated as headings
        logger.warning("⚠️ 未识别到任何有效标题")
        heading_preds = pd.DataFrame()
    else:
        mask = heading_preds["level"].map(lambda x: isinstance(x, str))
        heading_preds.loc[mask, "level"] = -1
        heading_preds["level"] = heading_preds["level"].fillna(-1).astype(int)
        logger.info(f"✅ 标题解析完成，最终识别 {len(heading_preds[heading_preds['level'] > 0])} 个有效标题")
    return heading_preds # 4-row dataframe

def est_hierarchies_naive(raw_preds, proceed_smart=True):
    logger.debug("🚀non-llm parsing => recursive processing")
    save_preds = raw_preds.copy()

    heading_preds = postprocess_headings(raw_preds, task="collapse")
    save_preds.insert(save_preds.columns.get_loc('level')+1, 'lvl_cola', heading_preds['level'].tolist())

    heading_preds = postprocess_headings(heading_preds, task="judge_negs", max_depth=-1)
    save_preds.insert(save_preds.columns.get_loc('lvl_cola')+1, 'lvl_neg', heading_preds['level'].tolist())

    # mapping based on freq
    if not proceed_smart:
        heading_preds['level'] = heading_preds['level'].map(lambda x: -1 if str(x)=='Not Sure' else x)
        heading_preds, lvl_mapping = build_level_mapping(heading_preds, heading_preds['level'].tolist(), mode="freq")
        heading_preds = execute_level_mapping(heading_preds, lvl_mapping)
        heading_preds.drop("origin_level", axis=1, inplace=True)
        save_preds.insert(save_preds.columns.get_loc('lvl_neg')+1, 'lvl_map', heading_preds['level'].tolist())

    # save_preds.to_csv(f"./test_naive_2.csv", index=False, encoding='utf-8-sig')
    return heading_preds

async def est_hierarchies_llm(raw_preds, prompt_limt, max_len=30, max_depth=6):
    if len(raw_preds)==0:
        return []

    full_preds = []
    level_dfs, raw_headings = heading_tb_transfer(raw_preds, threshold=prompt_limt, max_start=max_len, max_end=5)

    basic_df = level_dfs[0]
    try:
        logger.debug("🚀smart parse => interpreting hierarchy patterns...")
        logger.debug(f"正在将DataFrame转换为HTML，DataFrame大小: {len(basic_df)} 行")
        level_html = df2html(basic_df.drop(columns=["reason"]))
        logger.debug(f"HTML转换完成，长度: {len(level_html)} 字符")
        ot_limit = int(len(level_html)*1.2)  # min(int(len(level_html)*1.2), 8192) #int(len(level_html)*1.2)

        paras = {"max_tokens": ot_limit, "max_depth": max_depth}
        logger.debug(f"准备构建提示词，参数: max_tokens={ot_limit}, max_depth={max_depth}")
        prompt, temperature, top_p, max_tokens = build_prompt(task="eval-headings", texts=level_html, query="", paras=paras)
        logger.debug(f"✅ 提示词构建完成，长度: {len(prompt)} 字符，max_tokens={max_tokens}")
        messages = [
            {"role": "system", "content": "you are a document auditing expert"},
            {"role": "user", "content": prompt}
        ]

        ctx_task_id = str(uuid.uuid4())
        logger.debug(f"生成任务ID: {ctx_task_id}")
        
        # 使用Redis直接追踪任务状态，无需数据库持久化
        logger.debug("准备调用Redis服务保存任务状态...")
        from app.core.dependencies import get_redis_service
        redis_service = await get_redis_service()
        await redis_service.set(f"task:{ctx_task_id}:status", "processing", ttl=7200)
        logger.debug(f"任务状态已保存到Redis: task_id={ctx_task_id}")
        
        # 使用统一的AI查询服务
        logger.info(f"🤖 准备调用AI服务解析文档层级结构 (max_tokens={max_tokens}, 这可能需要1-3分钟)...")
        layout_res = await ai_query_service.query_ai(
            messages=messages,
            user_id=ctx_task_id,
            conversation_id=ctx_task_id,
            timeout=300,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens
        )
        logger.info(f"✅ AI服务调用完成，正在处理响应数据...")

        base_preds = pd.DataFrame(eval_response(layout_res))
        logger.debug(f"AI响应解析完成，获得 {len(base_preds)} 个层级预测")
        base_preds.insert(1, "heading", basic_df["heading"].values)  # insert original heading back
        base_preds["reason"] = basic_df["reason"].values
        # base_preds.to_csv(f"./test_llm_base.csv", index=False, encoding='utf-8-sig')
        logger.debug("开始构建层级映射...")
        base_preds, lvl_mapping = build_level_mapping(base_preds, basic_df['level'].tolist(), mode="freq")
        logger.debug(f"层级映射构建完成: {lvl_mapping}")

        if len(level_dfs)>1:
            logger.debug(f"处理多个层级DataFrame，共 {len(level_dfs)} 个...")
            for l, level_df in tqdm(enumerate(level_dfs), total=len(level_dfs), desc=f"mapping and post-processing..."):
                level_df = execute_level_mapping(level_df, lvl_mapping) # record origin level for debug
                full_preds.append(level_df)
            logger.debug("多层级处理完成")
        else:
            logger.debug("单层级数据，直接使用base_preds")
            full_preds.append(base_preds)

        logger.debug("合并所有预测结果...")
        full_preds = pd.concat(full_preds, ignore_index=True)
        full_preds['heading'] = raw_headings
        # full_preds.to_csv(f"./test_llm_full.csv", index=False, encoding='utf-8-sig')
        full_preds.drop("origin_level", axis=1, inplace=True)
        logger.info(f"✅ 文档层级结构解析完成，共识别 {len(full_preds)} 个标题")

    except Exception as e:
        logger.debug(f"[INFO] LLM-based parsing fails due to {e}\n"
          "using non-llm pipeline...")
        full_preds = pd.concat(level_dfs, ignore_index=True)
        full_preds = est_hierarchies_naive(full_preds)
    return full_preds

def collapse_recursive(df, task, indices, merge_th=3, checked_pairs=None, depth=0):
    if checked_pairs is None:
        checked_pairs = set()

    if len(indices)<2:
        return

    for k in range(len(indices) - 1):
        i, j = indices[k], indices[k + 1]
        if (i, j) in checked_pairs:
            continue
        checked_pairs.add((i, j))

        between = df.loc[i+1:j-1]
        i_txt = df.at[i, 'heading'].strip()
        j_txt = df.at[j, 'heading'].strip()

        if task=="merge_short" and len(between)>0:
            between_lens = [count_cn_en(c) for c in between['heading'].tolist()]
            between_lvls = [bl for bl in between['level'].tolist()]
            i_half_len = int(count_cn_en(i_txt) / 2)
            too_short = sum(between_lens) <= merge_th or sum(between_lens) < i_half_len

            if too_short and all(bl==-1 for bl in between_lvls): # only non-headings can be merged
                logger.debug(f"⚠️too short between {i}=>{i_txt[:15]} and {j}=>{j_txt[:15]} =>merge to {i}")
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
                logger.debug(f"\tmerged texts: {joined_txt}")

        elif task=="collapse" and len(between) == 0:
            logger.debug(f"⚠️Empty between i={i_txt[:15]}, j={j_txt[:15]} => set i.level=-1, j.level=Not Sure")
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
    if task=="judge_negs":
        for i, row in df.iterrows():
            neg_code = remove_by_conditions(row['heading'], include_punc=True)
            if any(x > 0 for x in neg_code):
                df.loc[i, "level"] = -1
                continue
        return df

    elif task=="merge_continuous":
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

    elif task=="merge_short" or task=="collapse":
        group2indices = defaultdict(list)
        for idx, row in df.iterrows():
            level = row["level"]
            reason = row["reason"]
            if level != -1:
                group2indices[(level, reason)].append(idx)

        checked_pairs = set()
        for _, indices in group2indices.items():
            collapse_recursive(df, task, indices, merge_th=3, checked_pairs=checked_pairs, depth=0)

        if task=="merge_short":
            drop_between = df.index[df["reason"].astype(str).str.startswith("Merged into", na=False)].tolist()
            if drop_between:
                logger.debug(f"🛠️Delete rows labeled as merged into, total {len(drop_between)} rows")
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

'''abandon codes'''
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
        
        

