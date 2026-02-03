import io
import os
import re
import uuid
import zipfile

import pandas as pd
from shared.core.config import settings
from app.services.common.kb_utils import (find_matches_parsing, gen_str_codes,
                                          get_str_time, process_dup_paths_df,
                                          process_path_texts, remove_spaces)
from shared.utils.text_utils import tokenize2stw_remove
from app.services.document_parser.image_parser import ask_image
from app.services.document_parser.layout_parser import pred_titles
from app.services.document_parser.table_parser import extract_tb_keywords
from app.services.document_parser.html_parser import table2html
from app.services.document_parser.toc_parser import (detect_doc_tocs,
                                                     detect_sdt_toc,
                                                     get_toc_level)
from app.services.document_parser.txt_parser import (extract_summary_keywords,
                                                     postprocess_leaf_dics)
from shared.utils.CommonHelper import load_file_bytes
from bs4 import BeautifulSoup
from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from loguru import logger
from lxml import etree
from openai import OpenAI
from tqdm import tqdm
from shared.core.exceptions.domain_exceptions import DocxParsingException
from shared.core.exceptions.knowhere_exception import KnowhereException


def get_leaf_dics(node, path=[]):
    '''
        :function find all bottom-level knowledge pieces and flat them into a list, each element contains the path from root to bottom
    '''
    leaf_dic_paths = []
    if isinstance(node, dict) and 'content' in node:
        current_path = path + [node['heading']] if 'heading' in node else path
        if any(isinstance(item, dict) for item in node['content']):
            for item in node['content']:
                leaf_dic_paths.extend(get_leaf_dics(item, current_path))
        else:
            leaf_dic_paths.append((current_path, node))
    # if there is no 'content' key, it exists between higher-level and the lower-level sections
    else:
        iso_node = {'heading': path, 'content': [node]}
        leaf_dic_paths.append((path, iso_node))
    return leaf_dic_paths


def _find_img_context(headings_stack, max_chars=100):
    """Find the nearest non-table/image text context by looking backward in headings_stack.
    
    Args:
        headings_stack: Stack of heading dicts with 'content' lists
        max_chars: Maximum characters to return (truncated if exceeded)
        
    Returns:
        The nearest valid text context, or empty string if none found
    """
    from app.services.common.kb_utils import truncate_text
    
    try:
        content_list = headings_stack[-1].get('content', [])
        # Traverse backward to find non-table/image content
        for item in reversed(content_list):
            item_stripped = str(item).strip()
            # Skip TABLE_ and IMAGE_ identifiers
            if item_stripped.startswith('TABLE_') or item_stripped.startswith('IMAGE_'):
                continue
            # Found valid text
            if item_stripped:
                return truncate_text(item_stripped, max_chars, 0)
        return ""
    except Exception as e:
        raise DocxParsingException(
            user_message="Failed to process document content",
            reason="CONTENT_PROCESSING_FAILED",
            internal_message=str(e),
            original_exception=e
        )


async def handle_image(df_list, img_file, img_dir, headings_stack, current_heading, img_count, smart_summary=False):
    time_stamp = get_str_time()
    client = OpenAI(
        api_key=settings.ALI_API_KEY,
        base_url=settings.ALI_URL
    )

    last_context = _find_img_context(headings_stack)

    img_ext = os.path.splitext(img_file["image_name"])[-1]
    raw_img_name = process_path_texts(f"image-{str(img_count+1)} {current_heading} {last_context}", last=30)
    img_raw_path = os.path.join(img_dir, f'{raw_img_name}{img_ext}')

    with open(img_raw_path, 'wb') as image_file:
        image_file.write(img_file["data"])

    if smart_summary:
        image_summary = await ask_image(client, img_dir, [f'{raw_img_name}{img_ext}'], title_text=last_context)
        if image_summary is None:
            image_summary = last_context
    else:
        image_summary = last_context

    img_name = process_path_texts(f"image-{str(img_count+1)} {current_heading} {image_summary}", last=30)
    img_path = os.path.join(img_dir, f'{img_name}{img_ext}')
    os.rename(img_raw_path, img_path) # if summary fails, renaming is not applied

    temp_uid = gen_str_codes(image_summary)
    img_id = 'IMAGE_' + temp_uid + '_IMAGE'

    img_bottom_content = img_id + '\nImage Summary:\n' + image_summary + '\n'
    img_path = f"images/{img_name}{img_ext}"

    headings_stack[-1]['content'].append(img_bottom_content)
    df_list.append([img_bottom_content, img_path, img_id, len(img_bottom_content), "", image_summary, temp_uid, "", "", time_stamp])
    return headings_stack, df_list


def _first_cols_rows(table_block, max_items=10, max_chars=20):
    """Extract deduplicated first row and first column texts from a table block.
    
    Args:
        table_block: python-docx Table object
        max_items: Maximum number of items to extract (default 10)
        max_chars: Maximum characters per item (default 20)
        
    Returns:
        Tuple of (first_row_text, first_col_text) with ' | ' as separator
    """
    from app.services.common.kb_utils import truncate_text
    
    first_row_text = ""
    first_col_text = ""
    
    if not table_block.rows:
        return first_row_text, first_col_text
    
    # First row extraction (deduplicated, order preserved, max items, truncated)
    seen_row = set()
    unique_row_cells = []
    for cell in table_block.rows[0].cells:
        if len(unique_row_cells) >= max_items:
            break
        cell_text = cell.text.strip()
        if cell_text and cell_text not in seen_row:
            seen_row.add(cell_text)
            unique_row_cells.append(truncate_text(cell_text, max_chars, 0))
    first_row_text = ' | '.join(unique_row_cells) if unique_row_cells else ""
    
    # First column extraction (deduplicated, order preserved, max items, truncated)
    seen_col = set()
    unique_col_cells = []
    for row in table_block.rows:
        if len(unique_col_cells) >= max_items:
            break
        if row.cells:
            cell_text = row.cells[0].text.strip()
            if cell_text and cell_text not in seen_col:
                seen_col.add(cell_text)
                unique_col_cells.append(truncate_text(cell_text, max_chars, 0))
    first_col_text = ' | '.join(unique_col_cells) if unique_col_cells else ""
    
    return first_row_text, first_col_text


async def handle_table(df_list, block, tb_dir, headings_stack, current_heading, table_count, smart_summary=False):
    time_stamp = get_str_time()
    tb_html_str = table2html(block)
    if not tb_html_str.strip():
        return headings_stack, df_list

    # Extract first row and first column headers
    first_row_text, first_col_text = _first_cols_rows(block)
    
    
    tb_keywords = ';'.join(filter(None, [first_row_text.replace(' | ', ';') if first_row_text else '']))
    if smart_summary:
        tb_summary = await extract_summary_keywords(tb_html_str, type_="summary")
        if tb_summary is None:
            tb_summary = f"First Row: {first_row_text}\nFirst Column: {first_col_text}"
    else:
        tb_summary = f"First Row: {first_row_text}\nFirst Column: {first_col_text}"

    temp_uid = gen_str_codes((tb_html_str + str(table_count)))
    table_id = 'TABLE_' + temp_uid + '_TABLE'

    raw_tb_name = first_row_text.replace(' | ', ' ') if first_row_text else ""
    tb_name = process_path_texts(f"table-{str(table_count+1)} {raw_tb_name}", last=30)
    tb_path = os.path.join(tb_dir, f'{tb_name}.html')

    with open(tb_path, 'w', encoding='utf-8') as f:
        f.write(tb_html_str)

    # Use relative path for tables (avoid absolute path in path column)
    tb_path = f"tables/{tb_name}.html"
    headings_stack[-1]['content'].append(table_id)
    df_list.append([tb_html_str, tb_path, table_id, len(tb_html_str), tb_keywords, tb_summary, temp_uid, "", "", time_stamp])
    return headings_stack, df_list


def iter_block_items(doc_data):
    doc_stream = io.BytesIO(doc_data)
    doc = Document(doc_stream)

    # python-docx mapping
    p_tbl_map = []
    for child in doc.element.body:
        if isinstance(child, CT_P):
            p_tbl_map.append(("p", child))
        elif isinstance(child, CT_Tbl):
            p_tbl_map.append(("tbl", child))

    with zipfile.ZipFile(io.BytesIO(doc_data), 'r') as docx:
        xml = docx.read('word/document.xml')
        rels = etree.fromstring(docx.read('word/_rels/document.xml.rels'))
        rel_map = {r.get('Id'): r.get('Target') for r in rels.findall('.//{*}Relationship')}
        ns = {
            'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
            'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
            'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        }

        root = etree.fromstring(xml)
        body = root.find('.//w:body', namespaces=ns)

        ele_num = 1
        map_index = 0  # point to p_tbl_map
        toc_field_active = False

        for elem in body.iterchildren():
            if not isinstance(elem.tag, str):
                continue
            
            tag = etree.QName(elem.tag).localname

            # --- SDT (Structured Document Tag) container ---
            # TOC generated by MS Word is usually in sdt
            if tag == 'sdt':
                sdt_toc_info = detect_sdt_toc(elem, ns)
                is_toc_sdt = sdt_toc_info['is_toc_sdt']
                
                sdt_content = elem.find('.//w:sdtContent', namespaces=ns)
                if sdt_content is not None:
                    for p_elem in sdt_content.findall('.//w:p', namespaces=ns):
                        texts = p_elem.xpath('.//w:t/text()', namespaces=ns)
                        text = ''.join(texts).strip()
                        
                        if is_toc_sdt:
                            label = 'TOC-AREA'
                        else:
                            toc_info = detect_doc_tocs(p_elem, ns)
                            if toc_info['is_style'] or toc_info['is_field_start']:
                                label = 'TOC-AREA'
                            else:
                                label = 'PTXT'
                        
                        if text:
                            yield ele_num, text, label, None
                            ele_num += 1
                continue

            # --- text paras ---
            if tag == 'p':
                texts = elem.xpath('.//w:t/text()', namespaces=ns)
                text = ''.join(texts).strip()

                if map_index < len(p_tbl_map) and p_tbl_map[map_index][0] == "p":
                    p_obj = Paragraph(p_tbl_map[map_index][1], doc)
                else:
                    p_obj = None

                toc_info = detect_doc_tocs(elem, ns)
                if toc_info['is_field_start']:
                    toc_field_active = True

                if toc_info['is_style'] or toc_field_active:
                    label = 'TOC-AREA'
                else:
                    label = 'PTXT'

                if text or p_obj is not None:
                    yield ele_num, p_obj or text, label, None
                    ele_num += 1

                # images
                blips = elem.xpath('.//a:blip', namespaces=ns)
                for b in blips:
                    rid = b.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                    target = rel_map.get(rid)
                    if not target or not target.startswith('media/'):
                        continue
                    data = docx.read('word/' + target)
                    yield (ele_num, None, 'IMAGE', {
                        'image_name': target.split('/')[-1],
                        'from': 'paragraph',
                        'size': len(data),
                        'data': data
                    })
                    ele_num += 1
                map_index += 1

                if toc_info['is_field_end']:
                    toc_field_active = False

            # --- tables ---
            elif tag == 'tbl':
                if map_index < len(p_tbl_map) and p_tbl_map[map_index][0] == "tbl":
                    tbl = Table(p_tbl_map[map_index][1], doc)
                else:
                    tbl = Table(elem, doc)

                yield ele_num, tbl, 'TABLE', None
                ele_num += 1
                map_index += 1

                blips = elem.xpath('.//a:blip', namespaces=ns)
                for b in blips:
                    rid = b.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                    target = rel_map.get(rid)
                    if not target or not target.startswith('media/'):
                        continue
                    data = docx.read('word/' + target)
                    yield (ele_num, tbl, 'IMAGE', {
                        'image_name': target.split('/')[-1],
                        'from': 'table',
                        'size': len(data),
                        'data': data
                    })
                    ele_num += 1
            else:
                continue

        # --- handle p_tbl_map at the end ---
        while map_index < len(p_tbl_map):
            tag, node = p_tbl_map[map_index]
            if tag == 'p':
                lvl = get_toc_level(node, ns)
                label = f'TOC-{int(lvl)}' if lvl is not None else 'PTXT'
                yield ele_num, Paragraph(node, doc), label, None
            elif tag == 'tbl':
                yield ele_num, Table(node, doc), 'TABLE', None
            ele_num += 1
            map_index += 1


async def parse_docx(docx_path, llm_paras, output_dir=None, filename="", file_url="", start_text="", end_text="", relative_root=None):
    doc_data = await load_file_bytes(docx_path, file_url=file_url)

    doc_structure = []
    heading_data = pd.DataFrame(columns=['text', 'level'])
    headings_stack = [{'level': -1, 'content': doc_structure}]
    current_heading = ''

    tb_dir = os.path.join(output_dir, "tables")
    os.makedirs(tb_dir, exist_ok=True)
    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    block_tuples = list(iter_block_items(doc_data))
    # tocs = [b for b in block_tuples if "TOC" in b[2]]
    block_tuples = [b for b in block_tuples if not "TOC" in b[2]] #TODO temporary remove toc area

    heading_infos = []
    for block_tuple in block_tuples:
        block = block_tuple[1]
        if isinstance(block, Paragraph):
            title_text = block.text.strip()
            if len(title_text) > 0:
                heading_infos.append((block_tuple[0], block, title_text))

    heading_candidates = []
    outline_dic = {-1:-1}
    smart_title_parse = llm_paras['smart_title_parse']
    if not llm_paras['doc_type'] in "templates":
        model_name = llm_paras.get("model_name", "deepseek-chat") if llm_paras else "deepseek-chat"
        heading_candidates = await pred_titles(heading_infos, doc_type="docx", enable_regx=True, smart_parse=smart_title_parse, model_name=model_name, output_dir=output_dir)

    if len(heading_candidates) > 0 and not (heading_candidates['level'] == -1).all():
        assert heading_candidates['id'].is_unique
        outline_dic = dict(zip(heading_candidates['id'], heading_candidates['level']))
    else:
        text = filename.split('.')[0]
        outline_level = 1
        heading_data.loc[len(heading_data)] = [text, outline_level]
        current_heading = text
        new_content = {'heading': text, 'content': [], 'level': outline_level}
        headings_stack[-1]['content'].append(new_content)
        headings_stack.append(new_content)
        logger.debug('⚠️no headings detected, using file name or mine a heading=>', text)

    df_list = []
    table_count = 0
    image_count = 0

    for block_tuple in tqdm(block_tuples, total=len(block_tuples), desc="Parsing docx file..."):
        ele_num, block, label, meta = block_tuple
        last_heading_before_block = current_heading

        if label == 'PTXT': # block could be doc para or plain string
            text = getattr(block, "text", str(block)).strip()
            if not text:
                continue

            outline_level = outline_dic.get(ele_num, -1)
            if outline_level > 0:
                # logger.debug('Found a title: ', text, ' current level: ', outline_level)
                try:
                    last_heading = headings_stack[-1]['heading']
                    if last_heading == text:
                        continue
                except:
                    pass

                while headings_stack and headings_stack[-1]['level'] >= outline_level:
                    headings_stack.pop()

                current_heading = text
                new_content = {'heading': text, 'content': [], 'level': outline_level}
                headings_stack[-1]['content'].append(new_content)
                headings_stack.append(new_content)
            # plain texts
            else:
                text = remove_spaces(text)
                headings_stack[-1]['content'].append(text)

        elif label == 'IMAGE':
            if meta and meta.get("size", 0) < 10 * 1024:
                continue

            headings_stack, df_list = await handle_image(
                df_list, meta, img_dir, headings_stack,
                current_heading, image_count, llm_paras["summary_image"]
            )
            image_count += 1
            current_heading = last_heading_before_block

        elif label == 'TABLE': 
            # TODO: handle cross-page tables
            headings_stack, df_list = await handle_table(
                df_list, block, tb_dir, headings_stack,
                current_heading, table_count, llm_paras["summary_table"]
            )
            table_count += 1
            current_heading = last_heading_before_block

        else: # TODO: handle latex, etc.
            pass

    return {'content' : doc_structure}, df_list


async def convert_doc2dics(parsed_structure, df_list, output_dir, base_llm_paras, relative_root=None):
    split_char = settings.SPLIT_CHAR or "/"
    leaf_dics = get_leaf_dics(parsed_structure)
    leaf_dics = await postprocess_leaf_dics(leaf_dics, base_llm_paras)

    # Use relative_root for path construction instead of absolute output_dir
    doc_name = relative_root if relative_root else output_dir.split(os.sep)[-1]
    if len(leaf_dics) == 0:
        raise DocxParsingException(
            user_message="Document content could not be extracted",
            reason="EMPTY_CONTENT",
            internal_message="Parsed leaf_dics is empty after processing"
        )

    path_keys = []
    time_stamp = get_str_time()
    path_counter = {}  # Track path occurrences for deduplication

    for _, row in leaf_dics.iterrows():
        key = row['path_identifier']
        
        # Build tentative path to check for duplicates
        tentative_path = doc_name + split_char + key
        
        # Deduplicate: if path already exists, add suffix
        if tentative_path in path_counter:
            path_counter[tentative_path] += 1
            suffix = path_counter[tentative_path]
            key = f"{key}_{suffix}"  # Modify key with suffix
        else:
            path_counter[tentative_path] = 1
        
        path_keys.append((doc_name + split_char + key))
        bottom_content = '\n'.join(row['content_lst'])
        bottom_tokens = tokenize2stw_remove([bottom_content], base_llm_paras['stopwords'])
        match_type = find_matches_parsing(bottom_content, key)

        try:
            keywords = row['keywords']
            summary = row['local_summary']
            know_id = gen_str_codes(bottom_content + str(uuid.uuid4()))
            # Use relative_root for path instead of absolute kb_dir
            path_suffix = key if key.strip() else ""
            know_path = split_char.join([relative_root, path_suffix]) if relative_root and path_suffix else (relative_root or path_suffix)
            df_list.append(
                [bottom_content, know_path, match_type, len(bottom_content), keywords, summary, know_id, bottom_tokens,
                 "", time_stamp])
        except KnowhereException:
            raise
        except Exception as e:
            logger.debug(f"❌Failed to parse docx document: {e}")
            raise DocxParsingException(
                user_message="Failed to process document content",
                reason="CONTENT_PROCESSING_FAILED",
                internal_message=str(e),
                original_exception=e
            )

    doc_df = pd.DataFrame(df_list, columns=settings.ALL_DF_COLS.split(','))
    doc_df = process_dup_paths_df(doc_df)
    return doc_df

