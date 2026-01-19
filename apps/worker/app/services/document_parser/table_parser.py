import io
import os
import re
import uuid
import datetime
import threading
import numpy as np
import pandas as pd
from collections import OrderedDict
from typing import List, Union

from shared.core.config import settings
from shared.services.ai import ai_query_service
from shared.services.ai.prompt_service import build_prompt
from shared.services.ai.response_process_service import eval_response
from app.services.common.kb_utils import (flatten_dic2paths, gen_str_codes,
                                          get_str_time, process_dup_paths_df,
                                          remove_spaces)
from shared.utils.text_utils import tokenize2stw_remove, remove_duplicates_orderkept

from app.services.document_parser.txt_parser import extract_summary_keywords
from shared.utils.CommonHelper import load_file_bytes
from bs4 import BeautifulSoup
from docx.table import Table as DocxTable
from loguru import logger
from pandasql import sqldf

from loguru import logger
from shared.core.exceptions.domain_exceptions import TableParsingException
from shared.core.exceptions.knowhere_exception import KnowhereException

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

def html2df(tb_html_path): # Process HTML file path, below is for HTML string
    dfs = pd.read_html(tb_html_path, encoding='utf-8')
    df = dfs[0]
    if isinstance(df.columns, pd.MultiIndex):
        # Flatten nested headers into single-level column names
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
    """Convert first table in HTML string to DataFrame"""
    soup = BeautifulSoup(html_str, "html.parser")
    table = soup.find("table")
    if not table:
        raise TableParsingException(
            user_message="No table structure found in the document",
            reason="INVALID_FORMAT",
            internal_message="No <table> found in the HTML string"
        )
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

    if not pd.isna(df_temp.columns).all(): # If columns are not all NaN, no need to add extra row
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
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": prompt}
            ]

            ctx_task_id = gen_str_codes((str(uuid.uuid4()) + tb_small_str))
            
            # Track task status via Redis (skip in LOCAL_DEBUG mode)
            import os
            if os.getenv("LOCAL_DEBUG", "0") != "1":
                from shared.services.redis import RedisServiceFactory
                redis_service = RedisServiceFactory.get_service()
                await redis_service.set(f"task:{ctx_task_id}:status", "processing", ttl=7200)
            
            # Use unified AI service
            header_res = await ai_query_service.query_ai(
                messages=messages,
                user_id=ctx_task_id,
                conversation_id=ctx_task_id,
                timeout=60
            )
            header_res = eval_response(header_res)
            # Extract answer field
            if isinstance(header_res, dict):
                answer = header_res.get('answer', [])
            else:
                answer = header_res if isinstance(header_res, list) else []
            
            # Check if answer is empty list
            if not answer or len(answer) == 0:
                logger.warning("AI returned empty list, cannot identify headers, falling back to traditional mode...")
                header_rows = parse_headers_nonsmart(df_temp)
            else:
                try:
                    header_id = answer[-1]
                    header_rows = list(range(header_id + 1))
                except Exception as e:
                    logger.warning(f"Failed to parse header row number: {e}, falling back to traditional mode...")
                    header_rows = parse_headers_nonsmart(df_temp)

        except Exception as e:
            logger.warning(f"Smart header parsing failed: {e}, falling back to traditional mode...")
            header_rows = parse_headers_nonsmart(df_temp)
    else:
        header_rows = parse_headers_nonsmart(df_temp)

    # improve table structure based on header rows
    if len(header_rows)==0 or (all(h is None for h in header_rows)):
        logger.warning("No valid headers detected, fallback to using row 0 as header")
        new_header = df_temp.iloc[0].ffill().bfill().tolist()
        df_temp.columns = new_header
        df_temp = df_temp.iloc[1:].reset_index(drop=True)
        return df_temp
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

def parse_tb_keywords(tb_df, kw_spit=">>>"):  # Extract keywords from headers (can also add LLM extraction)
    def parse_single_level_(cols, keywords):
        cols = [str(c) for c in cols]
        for col in cols:
            if kw_spit in col:
                tmp_kw = col.split(">>>")[0]
            else:  # May be first occurrence
                tmp_kw = col
            if tmp_kw not in keywords:
                keywords.append(col)
        keywords_a_level = list(set([k.strip() for k in keywords]))
        return keywords_a_level

    tb_keywords = []
    if isinstance(tb_df.columns, pd.MultiIndex):
        multi_cols = tb_df.columns
        cols_df = pd.DataFrame(multi_cols.tolist(), columns=[f"level_{i}" for i in range(multi_cols.nlevels)])
        for i in range(multi_cols.nlevels):  # Extract each level as list
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
        # Drop rows and columns that are all empty
        before_cols = set(df.columns)
        df = df.dropna(how='all')
        df = df.dropna(axis=1, how='all')
        after_cols = set(df.columns)
        dropped_columns = before_cols - after_cols
        logger.debug(f"Dropped columns: {list(dropped_columns)}")
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
        # Get head and tail rows
        head_df = df.head(num)
        tail_df = df.tail(num)
        # Middle portion excluding head and tail
        middle_df = df.iloc[num:len(df)-num]

        if len(middle_df) >= num:
            mid_sample_df = middle_df.sample(n=num, random_state=42)
        else:  # If middle has less than num rows, take all
            mid_sample_df = middle_df
        scope_df = pd.concat(objs=[head_df, mid_sample_df, tail_df], ignore_index=True)
    else:
        scope_df = df
    scope_df = scope_df.applymap(lambda x: str(x).strip() if pd.notnull(x) else x)
    scope_str = df2html(scope_df)
    return scope_str

# tabular agent
async def table_scope_analyze(query, tb_path, paras, num_row=7):
    # Extract original table HTML
    tb_df = html2df(tb_path)
    scope_str = format_tb_scope(tb_df, num_row)

    prompt, temperature, top_p, max_tokens = build_prompt(task="gen-table-query", texts=scope_str, query=query, paras=paras)
    messages = [
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": prompt}
    ]

    ctx_task_id = gen_str_codes((str(uuid.uuid4()) + query))
    
    # Track task status via Redis (skip in LOCAL_DEBUG mode)
    import os
    if os.getenv("LOCAL_DEBUG", "0") != "1":
        from shared.services.redis import RedisServiceFactory
        redis_service = RedisServiceFactory.get_service()
        await redis_service.set(f"task:{ctx_task_id}:status", "processing", ttl=7200)
    
    # Use unified AI query service
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
        logger.warning("No suitable rows/columns found in current table")
        return None

    try:
        tb_context = sqldf(tb_query, env={'df': tb_df})
        tb_context = df2html(tb_context)
    except Exception as e:
        logger.error(f"Auto table query generation failed: {e}")
        tb_context = None
    return tb_context

async def parse_xlsx(file_path, file_name, output_dir, baseurl, base_llm_paras=None, window_h=10, relative_root=None):
    split_char = settings.SPLIT_CHAR or "/"
    time_stamp = get_str_time()
    df_list = []

    table_data = await load_file_bytes(file_path, file_url=baseurl)
    table_stream = io.BytesIO(table_data)
    sheets_dict = pd.read_excel(table_stream, sheet_name=None)

    all_sheets = sheets_dict.items()

    tb_dir = os.path.join(output_dir, "tables")
    os.makedirs(tb_dir, exist_ok=True)
    all_tb_paths = []
    exist_sheets = []

    for sheet_name, sheet_content in all_sheets:
        sheet_name = sheet_name.strip()
        if sheet_name in exist_sheets:
            sheet_name = sheet_name + str(len(exist_sheets))
        else:
            exist_sheets.append(sheet_name)

        # TODO get sub tables (multiple tables in one sheet)
        sheet_tbs = [sheet_content]
        for tb in sheet_tbs:
            try:
                tb = postprocess_tb(tb, drop=True)
                if len(tb) == 0 or tb.empty or tb.isna().all().all():
                    continue

                # Parse headers with smart or traditional mode
                tb = await parse_headers(tb, paras=base_llm_paras)
                tb_paths, tb_strs = parse_tb_contents(tb, parent_dic={file_name: {sheet_name: {}}}, file_name=file_name, sheet_name=sheet_name)
                tb_keywords = parse_tb_keywords(tb)

                if base_llm_paras['summary_table']:
                    summary_context = format_tb_scope(tb, window_h)
                    summary_context = f"Table columns:\n{tb_keywords}\n\nFirst {window_h} rows:\n{summary_context}"
                    tb_summary = await extract_summary_keywords(summary_context, type_="summary", summary_len=100)
                else:
                    tb_summary = tb_keywords

                tb_name = remove_spaces('table-' + sheet_name) + '.html'
                tb_path = os.path.join(tb_dir, tb_name)
                soup = BeautifulSoup(tb_strs, features='html.parser')
                tb_html_str = soup.prettify()
                with open(tb_path, 'w', encoding='utf-8') as f:
                    f.write(tb_html_str)

                tb_id = 'TABLE_' + gen_str_codes(tb_strs) + '_TABLE'
                tb_bottom_content = f"{tb_id}\nTable summary:\n{tb_summary}\nMain columns:\n{tb_keywords}"
                know_id = gen_str_codes(tb_bottom_content + str(uuid.uuid4()))
                bottom_tokens = tokenize2stw_remove([tb_bottom_content], base_llm_paras['stopwords'])

                all_tb_paths.extend(tb_paths)
                # Use relative path for tables: "tables/xxx.html"
                relative_tb_path = f"tables/{tb_name}"
                df_list.append([tb_bottom_content, relative_tb_path, tb_id, len(tb_strs), tb_keywords, tb_summary, know_id, bottom_tokens, "", time_stamp])

            except KnowhereException:
                raise
            except Exception as e:
                logger.error(f"Table parsing failed: {e}")
                raise TableParsingException(
                    user_message="Failed to parse Excel table content",
                    reason="TABLE_PROCESSING_FAILED",
                    file_type="xlsx", 
                    internal_message=str(e),
                    original_exception=e
                )

    all_df_cols = (settings.ALL_DF_COLS or "content,path,type,length,keywords,summary,know_id,tokens,extra,addtime").split(',')
    table_df = pd.DataFrame(df_list, columns=all_df_cols)
    table_df = process_dup_paths_df(table_df)
    return table_df

