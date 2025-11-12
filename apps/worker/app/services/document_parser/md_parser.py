import os
import re
import uuid

import pandas as pd
from shared.core.config import settings
from app.services.common.kb_utils import (find_matches_parsing, gen_str_codes,
                                          get_str_time, process_dup_paths_df)
from app.services.document_parser.image_parser import (MD_IMAGE_PATTERN,
                                                       detect_summary_img_md)
from app.services.document_parser.layout_parser import (md_heading_match,
                                                        pred_titles)
from app.services.document_parser.table_parser import (extract_tables_by_forms,
                                                       extract_tb_keywords,
                                                       identify_tables)
from app.services.document_parser.txt_parser import (detect_tocs_in_texts,
                                                     extract_summary_keywords)
from shared.utils.file_utils import path_handle
from shared.utils.text_utils import tokenize2stw_remove
from bs4 import BeautifulSoup
from loguru import logger
from tqdm import tqdm


def find_surround_context(md_lines, lid):
    def is_skip(line):
        s = line.strip()
        is_image = re.findall(MD_IMAGE_PATTERN, line, flags=re.IGNORECASE)
        is_table, _, _ = identify_tables(line)
        return not s or is_image or is_table

    n = len(md_lines)
    prev_text = ""
    for i in range(max(lid - 5, 0), lid):
        if not is_skip(md_lines[i]):
            prev_text = md_lines[i].strip()
            break

    next_text = ""
    for i in range(lid + 1, min(lid + 6, n)):
        if not is_skip(md_lines[i]):
            next_text = md_lines[i].strip()
            break
    return f"{prev_text} {next_text}".strip()

def heading_md_relocate(md_lines, heading_preds):
    def remove_hash(txt):
        return re.sub(r'^\s*(#+)\s*', '', txt)

    for lid, line_txt in enumerate(md_lines):
        pred_level_df = heading_preds[heading_preds["id"] == lid]

        if pred_level_df.empty:
            line_txt = remove_hash(line_txt)
        else:
            match = re.match(r'^\s*(#+)\s*', line_txt)  # detect '#'s at the line beginning
            if match:
                original_hash_count = len(match.group(1)) # get the number of '#'
            else:
                original_hash_count = 0

            pred_level = pred_level_df['level'].iloc[0]
            # if the line is estimated as non-title, remove all '#'
            if pred_level < 0:
                line_txt = remove_hash(line_txt)
            # adjust the number of '#' based on preds
            else:
                if pred_level > original_hash_count:
                    line_txt = f"{'#' * int(pred_level - original_hash_count)}{line_txt.lstrip()}"
                elif pred_level < original_hash_count:
                    line_txt = f"{'#' * int(original_hash_count - pred_level)}{line_txt.lstrip('#').lstrip()}"
        # update lines
        md_lines[lid] = line_txt
    md_lines = [l for l in md_lines if l.strip()!=""]
    # with open("./output.md", "w", encoding="utf-8-sig") as f:
    #     f.write("\n".join(md_lines))
    return md_lines # note the length=original md_lines but contents/level are updated
    
async def eval_md_headings(md_lines, source_type, smart_parse=False):
    heading_preds = await pred_titles(md_lines, source_type, enable_regx=True, smart_parse=smart_parse)

    if len(heading_preds) == 0:
        lines_with_heading = md_lines
    else:
        lines_with_heading = heading_md_relocate(md_lines, heading_preds)
    return lines_with_heading

def clean_md_table_lines(table_lines, start_line_num):
    expected_columns = table_lines[0].count('|') - 1
    cleaned_lines = []
    error_lines = []  # To record line numbers that need cleaning

    for i, line in enumerate(table_lines):
        line_columns = line.count('|') - 1
        current_line_num = start_line_num + i  # Calculate the current line number in the original file
        if line_columns == expected_columns:
            cleaned_lines.append(line)
        else:
            error_lines.append(current_line_num)
            if line_columns > expected_columns:
                parts = line.split('|')
                cleaned_line = '|'.join(parts[:expected_columns + 1]) # If there are more columns, combine them (or drop extra columns)
                cleaned_lines.append(cleaned_line)
            elif line_columns < expected_columns:
                # If there are fewer columns, pad the line (or you could skip it)
                cleaned_line = line + '|' * (expected_columns - line_columns)
                cleaned_lines.append(cleaned_line)
    return cleaned_lines, error_lines

async def update_df_list(df_list, bottom_content, path, llm_paras, time_stamp, summary_len=1500):
    match_type = find_matches_parsing(bottom_content, path)
    know_id = gen_str_codes(bottom_content + str(uuid.uuid4()))
    bottom_tokens = tokenize2stw_remove([bottom_content], llm_paras['stopwords'])

    if len(bottom_content)>summary_len and llm_paras['summary_txt']:
        summary = await extract_summary_keywords(bottom_content, type_="summary")
        keywords = await extract_summary_keywords(bottom_content, type_="keywords")
    else:
        keywords = ''
        summary = ''

    df_list.append([bottom_content, path, match_type, len(bottom_content), keywords, summary, know_id, bottom_tokens, "", time_stamp])
    content = ''
    return df_list, content

async def parse_md(kb_dir, source_type, file_path=None, md_lines=None, base_llm_paras=None):
    if md_lines is None:
        with open(file_path, 'r', encoding='utf-8') as file:
            md_lines = file.readlines()

    md_lines = [l.strip() for l in md_lines if l.strip() != ""]
    tocs = detect_tocs_in_texts(md_lines)
    if tocs is not None:
        logger.debug(f"detected toc lines\n{tocs[-1]}")
        md_lines = md_lines[:tocs[0]] + md_lines[tocs[1]+1:]

    # create local storage
    tb_dir = os.path.join(kb_dir, "tables")
    os.makedirs(tb_dir, exist_ok=True)
    img_dir = os.path.join(kb_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    # initialize vars
    split_char = settings.SPLIT_CHAR or "-->"
    df_list = []
    path_stack = []
    inner_paths = []
    error_line_numbers = []
    table_lines = []
    current_pg_num = 0
    base_level = None
    content = ''
    path = split_char.join(kb_dir.split(os.sep))
    table_count = 0
    img_count = 0

    # estimate hierarchies
    lines_with_heading = await eval_md_headings(md_lines, source_type, base_llm_paras["smart_title_parse"])
    # with open("./output.md", 'r', encoding='utf-8') as file:
    #     lines_with_heading = file.readlines()

    time_stamp = get_str_time()
    for i, line in tqdm(enumerate(lines_with_heading), total=len(lines_with_heading), desc="Parsing md data..."):
        if '<!--' in line and '-->' in line: # 注释信息
            if 'page' in line or 'Slide number' in line: 
                current_pg_num += 1
                continue

        last_context = find_surround_context(lines_with_heading, i) # 记录当前line的上下各一个非 image/table的line
        current_heading, current_heading_level = md_heading_match(line, as_is=False)
        if not current_heading_level==-1: # indicate a new path should be evaluated or added
            if not content.strip()=='': # record contents of the last path and reset content
                df_list, content = await update_df_list(df_list, content, path, base_llm_paras, time_stamp)

            # update path based on path name and level
            if base_level is None:
                base_level = current_heading_level
            elif current_heading_level<base_level:
                base_level = current_heading_level
            
            adjusted_level = current_heading_level - base_level + 1
            while len(path_stack) >= adjusted_level:
                path_stack.pop()
            path_stack.append(current_heading)
            path = split_char.join(kb_dir.split(os.sep) + path_stack)
            inner_paths.append(split_char.join(path_stack))

        else: # no path change, remain in the same hierarchy
            # a. handle lines containing images
            img_name = path_handle(last_context[:10], mode="clean_single")
            img_name = f"图-{str(img_count)}-{img_name}"
            imgs = await detect_summary_img_md(line, img_name, kb_dir, mode=base_llm_paras['summary_image'])

            for img_path, img_summary in imgs:
                img_suffix = os.path.splitext(img_path)[-1]
                update_img_path = os.path.join(img_dir, f"{img_name}{img_suffix}")
                os.rename(os.path.join(kb_dir, img_path), update_img_path) # update image path, not using uuid

                img_id = 'IMAGE_' + gen_str_codes((img_summary + img_path.split(os.sep)[-1])) + '_IMAGE'
                img_kid = gen_str_codes(img_id + str(uuid.uuid4()))
                img_content = ('\n' + img_id + '\n' + img_summary + '\n')
                content = content + ('\n' + img_id + '\n' + img_summary + '\n')

                update_img_path = split_char.join(update_img_path.split(os.sep))
                df_list.append([img_content, update_img_path, img_id, len(img_content), "", img_summary, img_kid, "", "", time_stamp])
                img_count += 1

            # b. handle lines containing tables
            tb_bool, form, _ = identify_tables(line)
            if tb_bool:
                table_lines.append(line)
                if i+1 >= len(lines_with_heading):
                    tb_bool_next = False
                else:
                    tb_bool_next, _, _ = identify_tables(lines_with_heading[i+1].strip()) # 可以用来做跨页表优化

                if not tb_bool_next or i==len(lines_with_heading)-1: # 如果是html形式下一行自然不是table_line
                    if form=='md':
                        cleaned_table_lines, error_lines = clean_md_table_lines(table_lines, start_line_num=i)
                        tb_str = '\n'.join(cleaned_table_lines)
                        error_line_numbers.extend(error_lines)
                        tb_str = extract_tables_by_forms(tb_str, form='md')
                    
                    elif form=='html':
                        tb_str = line

                    tb_name = extract_tb_keywords(tb_str)
                    if base_llm_paras['summary_table']:
                        tb_summary = await extract_summary_keywords(tb_str, type_="summary")
                        tb_name = (tb_summary + " " + last_context)[:30]
                    else:
                        tb_summary = (last_context + " " + tb_name.strip()).strip()
                        tb_name = tb_name[:20]

                    tb_name = path_handle(f"表{str(table_count)}-{tb_name}", mode="clean_single")
                    table_id = 'TABLE_' + gen_str_codes(tb_str) + '_TABLE'
                    table_kid = gen_str_codes(table_id + str(uuid.uuid4()))
                    tb_content = ('\n' + table_id + '\n' + tb_summary + '\n')
                    content = content + ('\n' + table_id + '\n' + tb_summary + '\n')
                    tb_path = os.path.join(tb_dir, f"{tb_name}.html")

                    soup = BeautifulSoup(tb_str, 'html.parser')
                    tb_html_str = soup.prettify()
                    with open(tb_path, 'w', encoding='utf-8') as f:
                        f.write(tb_html_str)

                    tb_path = split_char.join(tb_path.split(os.sep))
                    df_list.append([tb_content, tb_path, table_id, len(tb_content), "", tb_summary, table_kid, "", "", time_stamp])
                    table_lines = [] # Reset table_lines after storing the DataFrame
                    table_count += 1

            # c. handle plain texts
            if len(imgs)==0 and not tb_bool:
                content = content + '\n' + line.strip() + '\n'
    
    if not content.strip()=='': # handle the remaining contents, append them to the last section
        df_list, content = await update_df_list(df_list, content, path, base_llm_paras, time_stamp)

    all_df_cols = (settings.ALL_DF_COLS or "content,path,type,length,keywords,summary,know_id,tokens,extra,addtime").split(',')
    doc_df = pd.DataFrame(df_list, columns=all_df_cols)
    doc_df = process_dup_paths_df(doc_df)
    doc_df_path = os.path.join(kb_dir, 'KB_PTXT.csv')
    doc_df.to_csv(doc_df_path, encoding='utf-8', index=False)

    # path_keys = [f"{base_llm_paras['doc_name']}{split_char}{k}" for k in inner_paths]
    # doc_graph, _ = restore_graph_by_paths(path_keys)
    #     with open(graph_path, 'w', encoding='utf-8') as f:
    #         json.dump(doc_graph, f, ensure_ascii=False, indent=4)
    # return doc_graph

    
    
    