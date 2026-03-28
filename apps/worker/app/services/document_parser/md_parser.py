import json
import os
import re
import uuid

import gevent
from gevent.pool import Pool as GeventPool
import pandas as pd
from shared.core.config import settings
from app.services.common.kb_utils import (find_matches_parsing, gen_str_codes,
                                          get_str_time, process_dup_paths_df)
from app.services.document_parser.image_parser import (MD_IMAGE_PATTERN,
                                                       ask_image,
                                                       detect_summary_img_md)
from app.services.document_parser.layout_parser import (md_heading_match,
                                                        pred_titles)
from app.services.document_parser.table_parser import (extract_tables_by_forms,
                                                       identify_tables)
from app.services.document_parser.html_parser import first_cols_rows_html, merge_html_tables
from app.services.document_parser.toc_parser import detect_tocs_in_texts
from app.services.document_parser.txt_parser import extract_summary_keywords, extract_title_keywords_summary
from shared.utils.file_utils import path_handle
from shared.utils.text_utils import tokenize2stw_remove
from bs4 import BeautifulSoup
from loguru import logger


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


def eval_md_headings(md_lines, source_type, toc_hierarchies=None, smart_parse=False, model_name=None, output_dir=None, layout_json_path=None):
    """Evaluate markdown headings with optional TOC hierarchies context"""
    heading_preds = pred_titles(
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

def update_df_list(df_list, bottom_content, path, llm_paras, time_stamp, page_nums="", summary_len=1500, skip_llm=False):
    match_type = find_matches_parsing(bottom_content, path)
    know_id = gen_str_codes(bottom_content + str(uuid.uuid4()))
    bottom_tokens = tokenize2stw_remove([bottom_content], llm_paras['stopwords'])

    keywords = ''
    summary = ''
    needs_llm = (not skip_llm and len(bottom_content) > summary_len and llm_paras['summary_txt'])
    if needs_llm:
        _title, keywords, summary = extract_title_keywords_summary(bottom_content, max_keywords=3, summary_len=summary_len)

    df_list.append([bottom_content, path, match_type, len(bottom_content), keywords, summary, know_id, bottom_tokens, "", time_stamp, page_nums])
    content = ''
    return df_list, content

def parse_md(output_dir, source_type, file_path=None, md_lines=None, base_llm_paras=None, relative_root=None):
    if md_lines is None and file_path is not None:
        from shared.utils.CommonHelperSync import load_file_bytes, is_remote
        if is_remote(file_path):
            file_bytes = load_file_bytes(file_path)
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
    toc_hierarchies, md_lines = detect_tocs_in_texts(md_lines, model_name=model_name)

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
    chunk_pages = set()  # collect all page numbers seen during current chunk
    base_level = None
    content = ''
    # Use relative_root as initial path (not absolute output_dir)
    path = relative_root if relative_root else ""
    table_count = 1
    img_count = 1
    path_counter = {}  # Track path occurrences for deduplication
    deferred_llm_tasks = []  # Collected during loop, executed in parallel after

    # Find layout.json path
    layout_json_path = os.path.join(output_dir, 'layout.json')
    if not os.path.exists(layout_json_path):
        layout_json_path = None
        logger.debug("layout.json not found, META features will not be added")

    # estimate hierarchies with toc_hierarchies context
    lines_with_heading = eval_md_headings(
        md_lines, 
        source_type, 
        toc_hierarchies=toc_hierarchies,
        smart_parse=base_llm_paras["smart_title_parse"], 
        model_name=model_name,
        output_dir=output_dir,
        layout_json_path=layout_json_path
    )

    time_stamp = get_str_time()
    logger.debug("Parsing md data... total_lines={}", len(lines_with_heading))
    for i, line in enumerate(lines_with_heading):
        if '<!--' in line and '-->' in line:
            if 'page' in line or 'Slide number' in line:
                # Parse actual page number from marker: <!-- page 5 -->
                pg_match = re.search(r'page\s+(\d+)', line)
                if pg_match:
                    current_pg_num = int(pg_match.group(1))
                else:
                    current_pg_num += 1  # fallback for Slide number or old format
                chunk_pages.add(current_pg_num)
                continue

        last_context = find_surround_context(lines_with_heading, i) # record the previous and next line which is not table/image
        current_heading, current_heading_level = md_heading_match(line, as_is=False)
        
        if not current_heading_level==-1: # indicate a new path should be evaluated or added
            if not content.strip()=='': # record contents of the last path and reset content
                # Build page_nums from collected pages during this chunk
                chunk_page_str = ",".join(str(p) for p in sorted(chunk_pages)) if chunk_pages else ""
                df_list, content = update_df_list(df_list, content, path, base_llm_paras, time_stamp, page_nums=chunk_page_str, skip_llm=True)
                chunk_pages = set()  # reset for next chunk
                if current_pg_num > 0:
                    chunk_pages.add(current_pg_num)  # carry current page into next chunk
            elif path and path != (relative_root or ""):
                # Consecutive headings with no body text between them:
                # Create a placeholder chunk so the previous heading's path
                chunk_page_str = ",".join(str(p) for p in sorted(chunk_pages)) if chunk_pages else ""
                df_list, content = update_df_list(df_list, "", path, base_llm_paras, time_stamp, page_nums=chunk_page_str, skip_llm=True)

            # update path based on path name and level
            if base_level is None:
                base_level = current_heading_level
            elif current_heading_level<base_level:
                base_level = current_heading_level
            
            adjusted_level = current_heading_level - base_level + 1
            path_stack = [(h, lvl) for h, lvl in path_stack if lvl < adjusted_level]
            
            # Build tentative path to check for duplicates
            # Sanitize heading: replace split_char in heading text to prevent path corruption
            current_heading = current_heading.replace(split_char, "∕") if split_char in current_heading else current_heading
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
            # a. handle lines containing images (LLM deferred to post-loop parallel batch)
            img_name_context = path_handle(last_context[:10], mode="clean_single")
            img_name = f"image-{str(img_count)}-{img_name_context}"
            # Always skip inline LLM — vision calls are deferred to parallel batch
            imgs = detect_summary_img_md(line, last_context, output_dir, mode=False)

            for img_path, img_title, img_summary in imgs:
                img_suffix = os.path.splitext(img_path)[-1]
                update_img_path = os.path.join(img_dir, f"{img_name}{img_suffix}")

                # Check if source image file exists before renaming
                source_path = os.path.join(output_dir, img_path)
                if not os.path.exists(source_path):
                    logger.warning(f"Image file not found, skipping rename: {source_path}")
                    img_count += 1
                    continue

                os.rename(source_path, update_img_path)

                # Image index (always present)
                image_index = f"image-{img_count}"
                
                # Fallback: LLM summary -> last_context -> None
                effective_summary = img_summary or last_context or None
                
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
                df_list.append([img_content, relative_img_path, img_id, len(img_content), "", img_summary_field, temp_uid, "", "", time_stamp, str(current_pg_num) if current_pg_num > 0 else ""])
                if base_llm_paras['summary_image']:
                    deferred_llm_tasks.append(("image", len(df_list) - 1, relative_img_path))
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

                # Extract first row and first column for fallback file naming only
                first_row_text, first_col_text = first_cols_rows_html(tb_str)
                
                # Table index (always present)
                table_index = f"table-{table_count}"
                
                # LLM title + keywords + summary deferred to post-loop parallel batch
                llm_title = None
                llm_summary = None
                tb_keywords = ""
                
                # Build tb_summary for df_list: table-n + optional LLM summary
                if llm_summary:
                    tb_summary = f"{table_index}\n{llm_summary}"
                else:
                    tb_summary = table_index
                
                raw_tb_name = first_row_text.replace(' | ', ' ') if first_row_text else ""
                # Use LLM title for filename when available, fallback to raw_tb_name
                effective_name = llm_title if llm_title else raw_tb_name
                tb_name = path_handle(f"table-{str(table_count)} {effective_name}", mode="clean_single")
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
                df_list.append([tb_str, relative_tb_path, table_id, len(tb_str), tb_keywords, tb_summary, temp_uid, "", "", time_stamp, str(current_pg_num) if current_pg_num > 0 else ""])
                if base_llm_paras['summary_table']:
                    deferred_llm_tasks.append(("table", len(df_list) - 1, tb_str))
                table_lines = [] # Reset table_lines after storing the DataFrame
                table_count += 1

            # c. handle plain texts
            if len(imgs)==0 and not tb_bool:
                content = content + '\n' + line.strip() + '\n'
                if current_pg_num > 0:
                    chunk_pages.add(current_pg_num)  # track page for this content line
    
    if not content.strip()=='': # handle the remaining contents, append them to the last section
        chunk_page_str = ",".join(str(p) for p in sorted(chunk_pages)) if chunk_pages else ""
        df_list, content = update_df_list(df_list, content, path, base_llm_paras, time_stamp, page_nums=chunk_page_str, skip_llm=True)

    # Collect text chunk deferred tasks (entries needing summary/keywords)
    summary_len = 1500
    if base_llm_paras.get('summary_txt'):
        for idx, entry in enumerate(df_list):
            marker = entry[2]  # col 2: match_type / img_id / table_id
            if isinstance(marker, str) and ('IMAGE_' in marker or 'TABLE_' in marker):
                continue
            if len(entry[0]) > summary_len and not entry[4] and not entry[5]:
                deferred_llm_tasks.append(("text", idx, entry[0]))

    # ── Post-loop: execute all deferred LLM calls in parallel via gevent ──
    if deferred_llm_tasks:
        logger.info(f"Running {len(deferred_llm_tasks)} deferred summary LLM calls in parallel")
        max_concurrent = getattr(settings, "SUMMARY_LLM_MAX_CONCURRENT", 10)

        def _run_deferred(task):
            task_type, idx = task[0], task[1]
            try:
                if task_type == "image":
                    relative_path = task[2]
                    from app.services.document_parser.image_parser import _get_vision_client
                    from app.services.document_parser.txt_parser import split_title_summary
                    client = _get_vision_client()
                    llm_resp = ask_image(client, output_dir, paths_=[relative_path])
                    if llm_resp:
                        img_title, img_summary = split_title_summary(llm_resp)
                    else:
                        img_title, img_summary = None, None
                    return idx, task_type, (img_title, img_summary)
                elif task_type == "table":
                    tb_html = task[2]
                    title, kw, summary = extract_title_keywords_summary(tb_html, max_keywords=3)
                    return idx, task_type, (title, kw, summary)
                elif task_type == "text":
                    text_content = task[2]
                    _t, kw, summary = extract_title_keywords_summary(text_content, max_keywords=3, summary_len=summary_len)
                    return idx, task_type, (kw, summary)
            except Exception as e:
                logger.warning(f"Deferred {task_type} LLM call failed for idx={idx}: {e}")
                return idx, task_type, None

        pool = GeventPool(size=min(max_concurrent, len(deferred_llm_tasks)))
        greenlets = [pool.spawn(_run_deferred, task) for task in deferred_llm_tasks]
        gevent.joinall(greenlets)

        for g in greenlets:
            if g.value is None:
                continue
            idx, task_type, result = g.value
            if result is None:
                continue
            if task_type == "image":
                img_title, img_summary = result
                if img_summary:
                    entry = df_list[idx]
                    image_index = entry[0].split('\n')[1] if '\n' in entry[0] else "image"
                    entry[5] = f"{image_index}\n{img_summary}"  # update summary col
            elif task_type == "table":
                title, kw, summary = result
                entry = df_list[idx]
                entry[4] = kw if isinstance(kw, str) else ""  # keywords col
                if summary:
                    table_index = entry[5] if not '\n' in entry[5] else entry[5].split('\n')[0]
                    entry[5] = f"{table_index}\n{summary}"  # update summary col
            elif task_type == "text":
                kw, summary = result
                df_list[idx][4] = kw if isinstance(kw, str) else ""  # keywords col
                df_list[idx][5] = summary if isinstance(summary, str) else ""  # summary col

        logger.info(f"Completed {len(deferred_llm_tasks)} deferred summary LLM calls")

    doc_df = pd.DataFrame(df_list, columns=settings.ALL_DF_COLS.split(','))
    doc_df = process_dup_paths_df(doc_df)

    return doc_df
