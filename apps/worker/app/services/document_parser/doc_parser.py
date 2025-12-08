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
from app.services.document_parser.table_parser import (extract_tb_keywords,
                                                       table2html)
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

def get_toc_level(elem, ns):
    style = elem.find('.//w:pPr/w:pStyle', namespaces=ns)
    if style is not None:
        val = style.get('{%s}val' % ns['w'])
        if val:
            val_lower = val.lower().strip()
            if "toc" in val_lower or "目录" in val:
                return True
    return False

def detect_doc_tocs(elem, ns):
    is_style = get_toc_level(elem, ns)
    is_field_start = False

    instrs = elem.findall('.//w:instrText', namespaces=ns)
    for instr in instrs:
        if instr.text:
            instr_text_lower = instr.text.lower()
            if 'toc' in instr_text_lower or 'table of contents' in instr_text_lower or '目录' in instr.text:
                is_field_start = True
                break

    is_field_end = False
    if not is_style:
        fldchars = elem.findall('.//w:fldChar', namespaces=ns)
        for fld in fldchars:
            if fld.get('{%s}fldCharType' % ns['w']) == 'end':
                is_field_end = True
                break
    return {
        'is_style': is_style,
        'is_field_start': is_field_start,
        'is_field_end': is_field_end
    }

async def handle_image(df_list, img_file, img_dir, headings_stack, current_heading, img_count, smart_summary=False):
    time_stamp = get_str_time()
    client = OpenAI(
        api_key=settings.ALI_API_KEY,
        base_url=settings.ALI_URL
    )

    try:
        last_context = (headings_stack[-1]['content'][-1]).strip()
        last_context = re.sub(re.compile(r'(TABLE_.*?_TABLE|IMAGE_.*?_IMAGE)'), '', last_context)
    except:
        last_context = ""

    img_ext = os.path.splitext(img_file["image_name"])[-1]
    raw_img_name = process_path_texts(f"图-{current_heading} {last_context}", last=30) + str(img_count)
    img_raw_path = os.path.join(img_dir, f'{raw_img_name}{img_ext}')

    with open(img_raw_path, 'wb') as image_file:
        image_file.write(img_file["data"])

    if smart_summary:
        image_summary = await ask_image(client, img_dir, [f'{raw_img_name}{img_ext}'], title_text=last_context)
        if image_summary is None:
            image_summary = f"图像所在章节: {current_heading}\n图像上下文: {last_context}"
    else:
        image_summary = f"图像所在章节: {current_heading}\n图像上下文: {last_context}"

    img_name = process_path_texts(f"图-{current_heading} {image_summary}", last=30) + str(img_count)
    img_path = os.path.join(img_dir, f'{img_name}{img_ext}')
    os.rename(img_raw_path, img_path)

    img_id = 'IMAGE_' + gen_str_codes(image_summary) + '_IMAGE'
    img_kid = gen_str_codes(img_id + str(uuid.uuid4()))
    img_bottom_content = img_id + '\n上图内容总结:\n' + image_summary + '\n'
    img_path = settings.SPLIT_CHAR.join(img_dir.split(os.sep) + [f"{img_name}{img_ext}"])

    headings_stack[-1]['content'].append(img_bottom_content)
    df_list.append([img_bottom_content, img_path, img_id, len(img_bottom_content), "", image_summary, img_kid, "", "", time_stamp])
    return headings_stack, df_list

async def handle_table(df_list, block, tb_dir, headings_stack, current_heading, table_count, smart_summary=False):
    time_stamp = get_str_time()
    tb_html_str = table2html(block)
    if not tb_html_str.strip():
        return headings_stack

    try:
        last_context = (headings_stack[-1]['content'][-1]).strip()
        last_context = re.sub(re.compile(r'(TABLE_.*?_TABLE|IMAGE_.*?_IMAGE)'), '', last_context)
    except:
        last_context = ''

    raw_tb_name = ' '.join([cell.text.strip() for cell in block.rows[0].cells]) if block.rows else f"表格{table_count}表头"
    tb_keywords = extract_tb_keywords(tb_html_str)
    if smart_summary:
        tb_summary = await extract_summary_keywords(tb_html_str, type_="summary")
        if tb_summary is None:
            tb_summary = f"表格所在章节: {current_heading}\n表格上下文: {last_context}\n表头信息: {raw_tb_name}"
    else:
        tb_summary = f"表格所在章节: {current_heading}\n表格上下文: {last_context}\n表头信息: {raw_tb_name}"

    tb_name = process_path_texts(f"表-{raw_tb_name} {tb_summary}", last=30) + str(table_count)
    table_id = 'TABLE_' + gen_str_codes(tb_html_str) + '_TABLE'
    table_kid = gen_str_codes(table_id + str(uuid.uuid4()))
    tb_bottom_content = table_id + '\n上表内容总结:\n' + tb_summary + '\n'
    tb_path = os.path.join(tb_dir, f'{tb_name}.html')

    soup = BeautifulSoup(tb_html_str, features='html.parser')
    tb_html_str = soup.prettify()
    with open(tb_path, 'w', encoding='utf-8') as f:
        f.write(tb_html_str)

    tb_path = settings.SPLIT_CHAR.join(tb_dir.split(os.sep) + [f"{tb_name}.html"])
    headings_stack[-1]['content'].append(tb_bottom_content)
    df_list.append([tb_bottom_content, tb_path, table_id, len(tb_bottom_content), tb_keywords, tb_summary, table_kid, "", "", time_stamp])
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
            # 跳过注释节点（Comment）和处理指令（PI） 注释节点的 tag 是一个函数对象，不是字符串
            if not isinstance(elem.tag, str):
                continue
            
            tag = etree.QName(elem.tag).localname

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

async def parse_docx(docx_path, llm_paras, kb_dir=None, filename="", file_url="", start_text="", end_text=""):
    doc_data = await load_file_bytes(docx_path, file_url=file_url)

    doc_structure = []
    heading_data = pd.DataFrame(columns=['text', 'level'])
    headings_stack = [{'level': -1, 'content': doc_structure}]
    current_heading = ''

    tb_dir = os.path.join(kb_dir, "tables")
    os.makedirs(tb_dir, exist_ok=True)
    img_dir = os.path.join(kb_dir, "images")
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
        heading_candidates = await pred_titles(heading_infos, doc_type="docx", enable_regx=True, smart_parse=smart_title_parse)

    if len(heading_candidates)>0:
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

        elif label == 'TABLE': #TODO 处理跨页表格
            headings_stack, df_list = await handle_table(
                df_list, block, tb_dir, headings_stack,
                current_heading, table_count, llm_paras["summary_table"]
            )
            table_count += 1
            current_heading = last_heading_before_block

        else: #TODO latex...
            pass

    # record training data
    # heading_data['binary_level'] = heading_data['level'].apply(lambda x: 1 if not x is None else 0)
    # heading_data.to_csv(os.path.join(kb_dir, 'table_train.csv'), encoding='utf-8-sig')
    return {'content' : doc_structure}, df_list

async def convert_doc2dics(parsed_structure, df_list, kb_dir, base_llm_paras):
    split_char = settings.SPLIT_CHAR
    leaf_dics = get_leaf_dics(parsed_structure)
    leaf_dics = await postprocess_leaf_dics(leaf_dics, base_llm_paras)

    doc_name = kb_dir.split(os.sep)[-1]  # 允许带上.docx方便graph后续建构
    if len(leaf_dics) == 0:
        raise '❌PROBABLY EMPTY FILE!'

    path_keys = []
    time_stamp = get_str_time()

    for _, row in leaf_dics.iterrows():
        key = row['path_identifier']
        path_keys.append((doc_name + split_char + key))
        bottom_content = '\n'.join(row['content_lst'])
        bottom_tokens = tokenize2stw_remove([bottom_content], base_llm_paras['stopwords'])
        match_type = find_matches_parsing(bottom_content, key)

        try:
            keywords = row['keywords']
            summary = row['local_summary']
            know_id = gen_str_codes(bottom_content + str(uuid.uuid4()))
            know_path = split_char.join(kb_dir.split(os.sep) + ([key] if key.strip() else []))
            df_list.append(
                [bottom_content, know_path, match_type, len(bottom_content), keywords, summary, know_id, bottom_tokens,
                 "", time_stamp])
        except Exception as e:
            logger.debug(f"❌解析docx文档失败 因为{e}")
            raise

    doc_df = pd.DataFrame(df_list, columns=settings.ALL_DF_COLS.split(','))
    doc_df = process_dup_paths_df(doc_df)
    doc_df_path = os.path.join(kb_dir, 'KB_PTXT.csv')
    doc_df.to_csv(doc_df_path, encoding='utf-8', index=False)

    # doc_graph, _ = restore_graph_by_paths(path_keys)
    # graph_path = os.path.join(kb_dir, 'hierarchy.json')
    # with open(graph_path, 'w', encoding='utf-8') as f:
    #     json.dump(doc_graph, f, ensure_ascii=False, indent=4)
    return doc_df

