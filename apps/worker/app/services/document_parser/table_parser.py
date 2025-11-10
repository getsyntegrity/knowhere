import io
import os
import re
import json
import uuid
import pandas as pd
import numpy as np
import datetime
import threading
from typing import Union, List
from pandasql import sqldf
from bs4 import BeautifulSoup
from docx.table import Table as DocxTable
from collections import OrderedDict
from app.core.config import settings
# TaskRedis依赖已移除，使用Redis直接追踪
from app.services.document_parser.txt_parser import extract_summary_keywords
from app.services.common.kb_utils import gen_str_codes, flatten_dic2paths, remove_spaces, restore_graph_by_paths, \
    remove_duplicates_orderkept, tokenize2stw_remove, get_str_time, process_dup_paths_df
from app.services.ai.prompt_service import build_prompt
from app.services.ai.response_process_service import eval_response
# ARQ依赖已移除，使用Celery替代
from app.services.ai import ai_query_service
from app.utils.CommonHelper import load_file_bytes

g_tbl_lock = threading.Lock()

def identify_tables(line):
    html_tb_pattern = r'<table.*?>.*?</table>'
    tables = re.findall(html_tb_pattern, line, re.DOTALL)
    if bool(tables):
        form = 'html'
        return True, form, tables
    
    md_tb_match = line.startswith('|') and line.endswith('|')
    if md_tb_match:
        form = 'md'
        return True, form, tables
    else:
        return False, None, None
    # UNDER DEVELOPMENT other forms of tables...

def df2html(tb_df: pd.DataFrame,
    *,
    index: bool = False,
    classes: Union[str, List[str], None] = "table table-striped",
    na_rep: str = "—",
    escape: bool = False
    ):
    table_html = tb_df.to_html(
        index=index,
        na_rep=na_rep,
        classes=classes,
        escape=escape,
        border=0,
        justify="center",
    )
    return table_html

def table2html(table: DocxTable) -> str:
    html = "<table border='1'>"
    for row in table.rows:
        html += "<tr>"
        for cell in row.cells:
            html += "<td>"
            if cell.tables:
                for nested_table in cell.tables:
                    html += table2html(nested_table)
            else:
                html += cell.text.strip().replace('\n', '<br>')
            html += "</td>"
        html += "</tr>"
    html += "</table>"
    return html

def html2df(tb_html_path): # 这是处理html path 下面是处理html字符串
    dfs = pd.read_html(tb_html_path, encoding='utf-8')
    df = dfs[0]
    if isinstance(df.columns, pd.MultiIndex):
        # 将嵌套表头合并成扁平字符串列名
        df.columns = ['-'.join(filter(None, map(str, col))) for col in df.columns]
    return df

    # with open(tb_html_path, "r", encoding="utf-8") as f:
    #     soup = BeautifulSoup(f, "html.parser")
    # table = soup.find("table")
    # nested_list = parse_nested_htmltb(table)
    # try:
    #     df = pd.DataFrame(nested_list[1:], columns=nested_list[0])
    # except Exception:
    #     df = pd.DataFrame(nested_list)
    # return df

def tb_htmlstr_to_df(html_str):
    """将 HTML 字符串中的第一个表格转换成 DataFrame"""
    soup = BeautifulSoup(html_str, "html.parser")
    table = soup.find("table")
    if not table:
        raise ValueError("No <table> found in the HTML string")
    nested_list = parse_nested_htmltb(table)
    try:
        df = pd.DataFrame(nested_list[1:], columns=nested_list[0])
    except Exception:
        df = pd.DataFrame(nested_list)
    return df

def parse_nested_htmltb(table):
    rows = []
    for tr in table.find_all("tr", recursive=False):
        row = []
        for td in tr.find_all(["td", "th"], recursive=False):
            inner_table = td.find("table")
            if inner_table:
                row.append(parse_nested_htmltb(inner_table))
            else:
                row.append(td.get_text(strip=True))
        if row:
            rows.append(row)
    return rows

def html_to_md_lines(html: str):
    soup = BeautifulSoup(html, 'html.parser')
    lines = []
    for row in soup.find_all("tr"):
        row_text = []
        for cell in row.find_all("td", recursive=False):
            text = cell.get_text(separator=' ', strip=True)
            if text:
                row_text.append(text)
        if row_text:
            lines.append(" | ".join(row_text))
    lines = remove_duplicates_orderkept(lines)
    return lines

def clean_html_tb(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    for row in soup.find_all("tr"):
        seen = set()
        unique_cells = []
        for cell in row.find_all("td", recursive=False):
            content = cell.encode_contents()
            if content not in seen:
                seen.add(content)
                unique_cells.append(cell)
        row.clear()
        for cell in unique_cells:
            row.append(cell)
    return soup.prettify()

def extract_tables_by_forms(tb_txt, form):
    if form=='html':
        return tb_txt
    elif form=='md':
        tb_df = pd.read_table(pd.io.common.StringIO(tb_txt), sep='|', engine='python', on_bad_lines='skip')
        tb_df = tb_df.drop(columns=tb_df.columns[0])  # Drop extra leading column
        tb_df = tb_df.drop(columns=tb_df.columns[-1]) # Drop extra trailing column
        tb_df.columns = tb_df.columns.str.strip()  # Clean up headers
        tb_strs = tb_df.to_html(index=False)
    else:
        tb_strs = None # UNDER DEVELOPMENT other forms of tables...
    return tb_strs

async def parse_headers(df_temp, paras=None, header_window=5, smart_headers=True):
    def parse_headers_nonsmart(df_):
        non_na_row = df_[df_.notna().any(axis=1)].head(1)
        header_id = non_na_row.index[-1] if not non_na_row.empty else None
        header_rows = list(range(header_id+1))
        return header_rows

    if not pd.isna(df_temp.columns).all(): # 如果本身表头全是nan 无必要多加1行
        df_temp.loc[-1] = df_temp.columns
        df_temp.index = df_temp.index + 1
        df_temp = df_temp.sort_index()
        df_temp.columns = [np.nan] * df_temp.shape[1]

    if paras['summary_table'] and smart_headers:
        try:
            tb_small = df_temp.head(header_window)
            tb_small_str = df2html(tb_small)
            prompt, temperature, top_p, max_tokens = build_prompt(task="detect-table-headers", texts=tb_small_str, query="", paras=paras)

            messages = [
                {"role": "system", "content": "你是一个有帮助的助手"},
                {"role": "user", "content": prompt}
            ]

            ctx_task_id = gen_str_codes((str(uuid.uuid4()) + tb_small_str))
            
            # 使用Redis直接追踪任务状态，无需数据库持久化
            from app.core.dependencies import get_redis_service
            redis_service = await get_redis_service()
            await redis_service.set(f"task:{ctx_task_id}:status", "processing", ttl=7200)
            
            # 使用统一的AI查询服务
            header_res = await ai_query_service.query_ai(
                messages=messages,
                user_id=ctx_task_id,
                conversation_id=ctx_task_id,
                timeout=60
            )
            header_res = eval_response(header_res)
            try:
                header_id = header_res['answer'][-1]
                header_rows = list(range(header_id+1))
            except Exception as e:
                print(f"⚠️ 可能无表头被识别到  {e}")
                raise

        except Exception as e:
            print(f"❌智能解析表头失败 原因 {e}\t采用传统模式解析...")
            header_rows = parse_headers_nonsmart(df_temp)
    else:
        header_rows = parse_headers_nonsmart(df_temp)

    # 根据得到的header rows优化table
    if len(header_rows)==0 or (all(h is None for h in header_rows)):
        return None
    elif len(header_rows)>1:
        head_lst = []
        for i in range(0, len(header_rows)):
            temp_lst = df_temp.iloc[i].ffill().bfill().tolist()
            head_lst.append(temp_lst)
        new_header = pd.MultiIndex.from_arrays(np.array(head_lst))
    else:
        new_header = df_temp.iloc[header_rows[-1]].ffill().bfill().tolist()

    df_temp.columns = new_header
    df_temp = df_temp.iloc[(header_rows[-1])+1:]
    df_temp = df_temp.reset_index(drop=True)
    return df_temp

def extract_tb_keywords(tb_str, form="html"):
    if form=='html':
        tb_df = tb_htmlstr_to_df(tb_str)
    else:
        tb_lines = html_to_md_lines(tb_str)
        tb_df = pd.DataFrame(tb_lines)
    tb_keywords = parse_tb_keywords(tb_df)
    return tb_keywords

def parse_tb_keywords(tb_df, kw_spit=">>>"): # 基于表头获取关键词（也可以考虑再加上由大模型提取的）
    def parse_single_level_(cols, keywords):
        cols = [str(c) for c in cols]
        for col in cols:
            if kw_spit in col:
                tmp_kw = col.split(">>>")[0]
            else: # 可能是第一次出现
                tmp_kw = col
            if tmp_kw not in keywords:
                keywords.append(col)
        keywords_a_level = list(set([k.strip() for k in keywords]))
        return keywords_a_level

    tb_keywords = []
    if isinstance(tb_df.columns, pd.MultiIndex):
        multi_cols = tb_df.columns
        cols_df = pd.DataFrame(multi_cols.tolist(), columns=[f"level_{i}" for i in range(multi_cols.nlevels)])
        for i in range(multi_cols.nlevels): # 每列提取为 list
            level_kws = []
            level_kws = parse_single_level_(cols_df[f"level_{i}"].tolist(), level_kws)
            tb_keywords.extend(level_kws)
    else:
        tb_keywords = parse_single_level_(tb_df.columns, tb_keywords)
    return ';'.join(tb_keywords)

def parse_tb_contents(df_temp, parent_dic=None, file_name='', sheet_name=''):
    if parent_dic is None:
        parent_dic = {}

    tb_res = df_temp.fillna('').infer_objects(copy=False)
    tb_strs = df2html(tb_res)

    tb_tree = tb_columns_to_tree(df_temp, parent_dic, file_name, sheet_name)
    tb_paths = flatten_dic2paths(tb_tree)
    return tb_paths, tb_strs

def tb_columns_to_tree(df, parent_dic, file_name, sheet_name):
    if isinstance(df.columns, pd.MultiIndex):
        # Convert MultiIndex columns to a nested dictionary (tree-like structure)
        columns = pd.DataFrame(df.columns.tolist())
        for level in range(columns.shape[1]):
            columns[level] = process_duplicate_cols(columns[level])

        new_columns = pd.MultiIndex.from_frame(columns)
        tree_structure = multiindex_to_tree(new_columns)
    else:
        # If columns are not MultiIndex, convert them to a dictionary with empty dictionaries as values
        new_columns = process_duplicate_cols(df.columns)
        tree_structure = {col: {} for col in new_columns}
    
    df.columns = new_columns
    if (not file_name=='') and (not sheet_name==''):
        parent_dic[file_name][sheet_name] = tree_structure
    elif not sheet_name == '':
        parent_dic[sheet_name] = tree_structure
    elif not file_name == '':
        parent_dic[file_name] = tree_structure
    else:
        parent_dic = tree_structure
    return parent_dic
        
def multiindex_to_tree(multiindex):
    """ Convert a MultiIndex to a tree-like nested dictionary structure. """
    def tree():
        return OrderedDict()
    
    root = tree()
    for keys in multiindex:
        current_level = root
        for key in keys:
            if key not in current_level:
                current_level[key] = tree()
            current_level = current_level[key]

    def convert_to_dict(d):
        if isinstance(d, OrderedDict):
            d = {k: convert_to_dict(v) for k, v in d.items()}
        return d
    return convert_to_dict(root)

def postprocess_tb(df, drop=False):
    if drop:
        # 删除全为空的行列
        before_cols = set(df.columns)
        df = df.dropna(how='all')
        df = df.dropna(axis=1, how='all')
        after_cols = set(df.columns)
        dropped_columns = before_cols - after_cols
        print("被删除的列:", list(dropped_columns))
        df.reset_index(drop=True, inplace=True)

    df.columns = [str(col).replace('\n', '') for col in df.columns] # Replace '\n' in column headers which can cause unexpected errors
    df.columns = [np.nan if 'Unnamed' in col else col for col in df.columns] # Replace Unnamed strs with nan values in columns for downstream processing
    df = df.map(lambda x: x.replace('\n', '') if isinstance(x, str) else x) # Replace '\n' in each cell
    df = process_datetime_cells(df)
    return df

def process_datetime_cells(df):
    df = df.copy()
    def convert(x):
        if isinstance(x, (pd.Timestamp, datetime.datetime)):
            return x.strftime("%Y-%m-%d %H:%M:%S")
        return x
    return df.apply(lambda col: col.map(convert))

def process_duplicate_cols(columns):
    col_count = {}
    new_columns = []
    for col in columns:
        if col in col_count:
            new_columns.append(f"{col}>>>{col_count[col]}")
            col_count[col] += 1
        else:
            new_columns.append(col)
            col_count[col] = 1
    return new_columns

def format_tb_scope(df, num):
    if len(df) > int(num*3+1):
        # 取前&后num行
        head_df = df.head(num)
        tail_df = df.tail(num)
        # 排除前后行后的中间部分
        middle_df = df.iloc[num:len(df)-num]

        if len(middle_df) >= num:
            mid_sample_df = middle_df.sample(n=num, random_state=42)
        else: # 若中间不足num行，则直接取全部
            mid_sample_df = middle_df
        scope_df = pd.concat(objs=[head_df, mid_sample_df, tail_df], ignore_index=True)
    else:
        scope_df = df
    scope_df = scope_df.applymap(lambda x: str(x).strip() if pd.notnull(x) else x)
    scope_str = df2html(scope_df)
    return scope_str

# tabular agent
async def table_scope_analyze(query, tb_path, paras, num_row=7):
    # 提取原始表格html
    tb_df = html2df(tb_path)
    scope_str = format_tb_scope(tb_df, num_row)

    prompt, temperature, top_p, max_tokens = build_prompt(task="gen-table-query", texts=scope_str, query=query, paras=paras)
    messages = [
        {"role": "system", "content": "你是一个有帮助的助手"},
        {"role": "user", "content": prompt}
    ]

    ctx_task_id = gen_str_codes((str(uuid.uuid4()) + query))
    
    # 使用Redis直接追踪任务状态，无需数据库持久化
    from app.core.dependencies import get_redis_service
    redis_service = await get_redis_service()
    await redis_service.set(f"task:{ctx_task_id}:status", "processing", ttl=7200)
    
    # 使用统一的AI查询服务
    scope_res = await ai_query_service.query_ai(
        messages=messages,
        user_id=ctx_task_id,
        conversation_id=ctx_task_id,
        timeout=60
    )
    scope_res = eval_response(scope_res)
    if not scope_res['answer']=="null":
        tb_query = scope_res['answer']
    else:
        print("当前表格中无合适行列")
        return None

    try:
        tb_context = sqldf(tb_query, env={'df': tb_df})
        tb_context = df2html(tb_context)
    except Exception as e:
        print(f'自动生成表格查询失败 原因：{e}')
        tb_context = None
    return tb_context

async def parse_xlsx(file_path, file_name, kb_dir, baseurl, base_llm_paras=None, window_h=10):
    split_char = settings.SPLIT_CHAR or "-->"
    time_stamp = get_str_time()
    df_list = []

    table_data = await load_file_bytes(file_path, file_url=baseurl)
    table_stream = io.BytesIO(table_data)
    sheets_dict = pd.read_excel(table_stream, sheet_name=None)

    all_sheets = sheets_dict.items()
    print(f'该xlsx文件包含{len(all_sheets)}个sheet表')

    tb_dir = os.path.join(kb_dir, "tables")
    os.makedirs(tb_dir, exist_ok=True)
    all_tb_paths = []
    exist_sheets = []

    for sheet_name, sheet_content in all_sheets:
        sheet_name = sheet_name.strip()
        if sheet_name in exist_sheets:
            sheet_name = sheet_name + str(len(exist_sheets))
        else:
            exist_sheets.append(sheet_name)  # 避免重名sheet

        # ****UNDER DEVELOPMENT**** analyzing table structure vertical/horizontal, get sub tables (multiple tables in one sheet)
        sheet_tbs = [sheet_content]
        for tb in sheet_tbs:
            try:
                tb = postprocess_tb(tb, drop=True)
                if len(tb) == 0 or tb.empty or tb.isna().all().all():
                    continue

                # 解析表头 支持智能和传统规则模式
                tb = await parse_headers(tb, paras=base_llm_paras)
                tb_paths, tb_strs = parse_tb_contents(tb, parent_dic={file_name: {sheet_name: {}}}, file_name=file_name, sheet_name=sheet_name)
                tb_keywords = parse_tb_keywords(tb)

                if base_llm_paras['summary_table']:
                    summary_context = format_tb_scope(tb, window_h)
                    summary_context = f"表格列名如下:\n{tb_keywords}\n\n表格前{window_h}行内容如下:\n{summary_context}"
                    tb_summary = await extract_summary_keywords(summary_context, type_="summary", summary_len=100)
                else:
                    tb_summary = tb_keywords

                tb_name = remove_spaces('表-' + sheet_name) + '.html'
                tb_path = os.path.join(tb_dir, tb_name)
                soup = BeautifulSoup(tb_strs, features='html.parser')
                tb_html_str = soup.prettify()
                with open(tb_path, 'w', encoding='utf-8') as f:
                    f.write(tb_html_str)

                tb_id = 'TABLE_' + gen_str_codes(tb_strs) + '_TABLE'
                tb_bottom_content = f"{tb_id}\n上表主要内容如下:\n{tb_summary}\n表内主要列名如下:\n{tb_keywords}"
                know_id = gen_str_codes(tb_bottom_content + str(uuid.uuid4()))
                bottom_tokens = tokenize2stw_remove([tb_bottom_content], base_llm_paras['stopwords'])

                all_tb_paths.extend(tb_paths)
                tb_path = split_char.join(tb_path.split(os.sep))
                df_list.append([tb_bottom_content, tb_path, tb_id, len(tb_strs), tb_keywords, tb_summary, know_id, bottom_tokens, "", time_stamp])

            except Exception as e:
                print(f'parse table fails, because {e}')
                raise

    all_df_cols = (settings.ALL_DF_COLS or "path,content,summary,type,addtime").split(',')
    table_df = pd.DataFrame(df_list, columns=all_df_cols)
    table_df = process_dup_paths_df(table_df)

    # tb_graph, _ = restore_graph_by_paths(all_tb_paths)
    # graph_path = os.path.join(kb_dir, 'graph.json')
    table_df.to_csv(os.path.join(kb_dir, 'KB_PTXT.csv'), encoding='utf-8', index=False)
    #     with open(graph_path, 'w', encoding='utf-8') as f:
    #         json.dump(tb_graph, f, ensure_ascii=False, indent=4)
    # return tb_graph


# def table_structure_recog(filename=None, tb_path=None):
#     # tb_path = os.path.join(USER_SETTINGS['KB_PATH'], 'templates', filename)
#     df_temp = parse_headers(tb_path=tb_path, mode='fill')
#     _, tb_paths, search_keys = parse_tb_contents(df_temp, mode='fill', return_lst=True)
#     tb_structure, _ = restore_graph_by_paths(tb_paths)
#     return search_keys, tb_structure

# def process_nan4records(df):
#     df = process_datetime_cells(df)
#     df = df.astype(object)
#     df = df.where(pd.notnull(df), None)
#     tb_json = df.to_dict(orient="records")
#     return tb_json


