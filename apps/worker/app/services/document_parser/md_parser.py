import json
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
from app.services.document_parser.html_parser import first_cols_rows_html, merge_html_tables
from app.services.document_parser.toc_parser import detect_tocs_in_texts
from app.services.document_parser.txt_parser import extract_summary_keywords
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
    """Relocate markdown headings based on predicted levels (sxjg simplified logic)"""
    def remove_hash(txt):
        return re.sub(r'^\s*(#+)\s*', '', txt)

    for lid, line_txt in enumerate(md_lines):
        pred_level_df = heading_preds[heading_preds["id"] == lid]

        if pred_level_df.empty:  # if the line does not enter predicting
            line_txt = remove_hash(line_txt)
        else:
            pred_level = pred_level_df['level'].iloc[0]
            if pred_level < 0:
                line_txt = remove_hash(line_txt)
            else:
                # sxjg simplified: remove all #, then add correct number of #
                clean_text = line_txt.lstrip('#').lstrip()
                line_txt = f"{'#' * int(pred_level)} {clean_text}"
        # update lines
        md_lines[lid] = line_txt.strip()
    
    md_lines = [l for l in md_lines if l.strip() != ""]
    return md_lines  # note the length=original md_lines but contents/level are updated


async def eval_md_headings(md_lines, source_type, toc_hierarchies=None, smart_parse=False, model_name=None, output_dir=None, layout_json_path=None):
    """Evaluate markdown headings with optional TOC hierarchies context"""
    heading_preds = await pred_titles(
        md_lines, source_type, 
        toc_hierarchies=toc_hierarchies,
        enable_regx=True, 
        smart_parse=smart_parse,
        model_name=model_name,
        output_dir=output_dir,
        layout_json_path=layout_json_path
    )

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

async def parse_md(output_dir, source_type, file_path=None, md_lines=None, base_llm_paras=None, relative_root=None):
    if md_lines is None and file_path is not None:
        from shared.utils.CommonHelper import load_file_bytes, is_remote
        if is_remote(file_path):
            file_bytes = await load_file_bytes(file_path)
            md_content = file_bytes.decode('utf-8')
            md_lines = md_content.splitlines()
        else:
            with open(file_path, 'r', encoding='utf-8') as file:
                md_lines = file.readlines()

    md_lines = [l.strip() for l in md_lines if l.strip() != ""]
    
    # Preprocess: merge multi-line HTML tables into single lines
    md_lines = merge_html_tables(md_lines)
    
    # Detect TOC using async LLM-based detection (sxjg logic)
    model_name = base_llm_paras.get("model_name", "deepseek-chat") if base_llm_paras else "deepseek-chat"
    toc_hierarchies, md_lines = await detect_tocs_in_texts(md_lines, model_name=model_name)

    # Save toc_hierarchies.json to output_dir (will be included in final zip package)
    if toc_hierarchies:
        toc_json_path = os.path.join(output_dir, 'toc_hierarchies.json')
        with open(toc_json_path, 'w', encoding='utf-8') as f:
            json.dump(toc_hierarchies, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved TOC hierarchies to {toc_json_path}")

    # create local storage
    tb_dir = os.path.join(output_dir, "tables")
    os.makedirs(tb_dir, exist_ok=True)
    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    # initialize vars
    split_char = settings.SPLIT_CHAR or "/"
    df_list = []
    path_stack = []  # sxjg: uses (heading, level) tuples
    inner_paths = []
    error_line_numbers = []
    table_lines = []
    current_pg_num = 0
    base_level = None
    content = ''
    # Use relative_root as initial path (not absolute output_dir)
    path = relative_root if relative_root else ""
    table_count = 1
    img_count = 1
    path_counter = {}  # Track path occurrences for deduplication

    # Find layout.json path
    layout_json_path = os.path.join(output_dir, 'layout.json')
    if not os.path.exists(layout_json_path):
        layout_json_path = None
        logger.debug("layout.json not found, META features will not be added")

    # estimate hierarchies with toc_hierarchies context
    lines_with_heading = await eval_md_headings(
        md_lines, 
        source_type, 
        toc_hierarchies=toc_hierarchies,
        smart_parse=base_llm_paras["smart_title_parse"], 
        model_name=model_name,
        output_dir=output_dir,
        layout_json_path=layout_json_path
    )

    time_stamp = get_str_time()
    for i, line in tqdm(enumerate(lines_with_heading), total=len(lines_with_heading), desc="Parsing md data..."):
        if '<!--' in line and '-->' in line:
            if 'page' in line or 'Slide number' in line: 
                current_pg_num += 1
                continue

        last_context = find_surround_context(lines_with_heading, i) # record the previous and next line which is not table/image
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
            path_stack = [(h, lvl) for h, lvl in path_stack if lvl < adjusted_level]
            
            # Build tentative path to check for duplicates
            tentative_heading = current_heading
            tentative_names = [h for h, lvl in path_stack] + [tentative_heading]
            tentative_path_parts = [relative_root] if relative_root else []
            tentative_path_parts.extend(tentative_names)
            tentative_path = split_char.join(tentative_path_parts)
            
            # Deduplicate: if path already exists, add suffix
            if tentative_path in path_counter:
                path_counter[tentative_path] += 1
                suffix = path_counter[tentative_path]
                current_heading = f"{current_heading}_{suffix}"  # Modify heading with suffix
            else:
                path_counter[tentative_path] = 1
            
            path_stack.append((current_heading, adjusted_level))
            
            # Extract pure heading names for path construction
            heading_names = [h for h, lvl in path_stack]
            # Use relative_root as prefix
            path_parts = [relative_root] if relative_root else []
            path_parts.extend(heading_names)
            inner_paths.append(split_char.join(heading_names))
            path = split_char.join(path_parts)  # path with relative root

        else: # no path change, remain in the same hierarchy
            # a. handle lines containing images
            img_name_context = path_handle(last_context[:10], mode="clean_single")
            img_name = f"image-{str(img_count)}-{img_name_context}"
            # Pass semantic context (not img_name) to avoid "image-" prefix duplication
            imgs = await detect_summary_img_md(line, last_context, output_dir, mode=base_llm_paras['summary_image'])

            for img_path, img_summary in imgs:
                img_suffix = os.path.splitext(img_path)[-1]
                update_img_path = os.path.join(img_dir, f"{img_name}{img_suffix}")
                os.rename(os.path.join(output_dir, img_path), update_img_path) # update image path, not using uuid
                
                # Image index (always present)
                image_index = f"image-{img_count}"
                
                # Fallback: LLM summary -> last_context -> None
                if img_summary:
                    effective_summary = img_summary
                elif last_context:
                    effective_summary = last_context
                else:
                    effective_summary = None
                
                temp_uid = gen_str_codes((effective_summary or image_index) + img_path.split(os.sep)[-1] + str(img_count))
                img_id = 'IMAGE_' + temp_uid + '_IMAGE'
                
                # Build img_summary_field for df_list: image-n + optional summary
                if effective_summary:
                    img_summary_field = f"{image_index}\n{effective_summary}"
                else:
                    img_summary_field = image_index
                
                # Build image_ref for content: image-n + optional summary + image_id
                if effective_summary:
                    img_content = f"\n{image_index}\n{effective_summary}\n{img_id}\n"
                else:
                    img_content = f"\n{image_index}\n{img_id}\n"
                
                content = content + img_content

                relative_img_path = f"images/{img_name}{img_suffix}"
                df_list.append([img_content, relative_img_path, img_id, len(img_content), "", img_summary_field, temp_uid, "", "", time_stamp])
                img_count += 1

            # b. handle lines containing tables
            tb_bool, form, _ = identify_tables(line)
            if tb_bool:
                if form == 'html':
                    # each line is a complete table - process immediately
                    tb_str = line
                elif form == 'md':
                    # For MD tables, accumulate lines until table ends
                    table_lines.append(line)
                    if i+1 >= len(lines_with_heading):
                        tb_bool_next = False
                    else:
                        tb_bool_next, _, _ = identify_tables(lines_with_heading[i+1].strip())
                    
                    if not tb_bool_next or i==len(lines_with_heading)-1:
                        cleaned_table_lines, error_lines = clean_md_table_lines(table_lines, start_line_num=i)
                        tb_str = '\n'.join(cleaned_table_lines)
                        error_line_numbers.extend(error_lines)
                        tb_str = extract_tables_by_forms(tb_str, form='md')
                    else:
                        continue  # Keep accumulating MD table lines
                else:
                    continue  # Unknown form, skip

                # Extract first row and first column for summary (consistent with docx)
                first_row_text, first_col_text = first_cols_rows_html(tb_str)
                
                # Combine first row and first column as keywords for table retrieval (with dedup)
                row_kw = first_row_text.replace(' | ', ';') if first_row_text else ''
                col_kw = first_col_text.replace(' | ', ';') if first_col_text else ''
                # Cross-dedup: remove col keywords already present in row keywords
                row_set = set(row_kw.split(';')) if row_kw else set()
                col_parts = [k for k in col_kw.split(';') if k and k not in row_set]
                tb_keywords = ';'.join(filter(None, [row_kw] + col_parts))
                
                # Table index (always present)
                table_index = f"table-{table_count}"
                
                # LLM summary (optional, only when summary_table is enabled and succeeds)
                llm_summary = None
                if base_llm_paras['summary_table']:
                    llm_summary = await extract_summary_keywords(tb_str, type_="summary")
                
                # Build tb_summary for df_list: table-n + optional LLM summary
                if llm_summary:
                    tb_summary = f"{table_index}\n{llm_summary}"
                else:
                    tb_summary = table_index
                
                raw_tb_name = first_row_text.replace(' | ', ' ') if first_row_text else ""
                tb_name = path_handle(f"table-{str(table_count)} {raw_tb_name}", mode="clean_single")
                temp_uid = gen_str_codes((tb_str + str(table_count)))
                table_id = 'TABLE_' + temp_uid + '_TABLE'

                # Build table_ref for content: table-n + optional LLM summary + table_id
                if llm_summary:
                    content = content + f'\n{table_index}\n{llm_summary}\n{table_id}\n'
                else:
                    content = content + f'\n{table_index}\n{table_id}\n'
                tb_path = os.path.join(tb_dir, f"{tb_name}.html")
                # Add border to HTML tables for consistent display
                tb_str_with_border = tb_str.replace('<table>', "<table border='1'>").replace('<table ', "<table border='1' ")
                with open(tb_path, 'w', encoding='utf-8') as f:
                    f.write(tb_str_with_border)

                relative_tb_path = f"tables/{tb_name}.html"
                df_list.append([tb_str, relative_tb_path, table_id, len(tb_str), tb_keywords, tb_summary, temp_uid, "", "", time_stamp])
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

    return doc_df
