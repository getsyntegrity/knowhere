import io
import os
import json
import uuid
import zipfile
from openai import OpenAI
import pandas as pd
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from docx import Document
from loguru import logger
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.table import Table
from docx.text.paragraph import Paragraph
from app.core.config import settings
from app.services.document_parser.layout_parser import filter_doc_headings, pred_titles, heading_dic_trans
from app.services.common.kb_utils import remove_spaces, find_matches_parsing, gen_str_codes, process_dup_paths_df, process_path_texts, \
    restore_graph_by_paths, tokenize2stw_remove, get_str_time
from app.services.document_parser.txt_parser import postprocess_leaf_dics, extract_summary_keywords
from app.services.document_parser.image_parser import detect_images, ask_image
from app.services.document_parser.table_parser import table2html, extract_tb_keywords
from app.services.storage.file_encryptor_service import encryptor
from app.utils.CommonHelper import load_file_bytes


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

async def handle_image(df_list, doc_data, img_intra_name, img_dir, headings_stack, current_heading, img_count, smart_summary=False):
    time_stamp = get_str_time()
    doc_stream = io.BytesIO(doc_data)
    client = OpenAI(
        api_key=settings.ALI_API_KEY,
        base_url=settings.ALI_URL
    )

    try:
        last_context = (headings_stack[-1]['content'][-1]).strip()
    except:
        last_context = ""

    img_ext = os.path.splitext(img_intra_name)[-1] # 文件后缀拓展
    raw_img_name = (current_heading + ' ' + last_context).strip()
    img_raw_path = os.path.join(img_dir, f'{process_path_texts(raw_img_name)}{img_ext}')

    with zipfile.ZipFile(doc_stream, 'r') as zip_ref:
        img_data = zip_ref.read(img_intra_name)
        if encryptor.encrypt:
            encryptor.save_to_file(img_data, img_raw_path)
        else:
            with open(img_raw_path, 'wb') as image_file:
                image_file.write(img_data)

    if smart_summary:
        image_summary = await ask_image(client, img_dir, [f'{raw_img_name}{img_ext}'], title_text=last_context)
        if image_summary is None:
            image_summary = raw_img_name
    else:
        image_summary = raw_img_name

    img_name = process_path_texts(f"图-{raw_img_name} {image_summary}", last=30) + str(img_count)
    img_path = os.path.join(img_dir, f'{img_name}{img_ext}')
    os.rename(img_raw_path, img_path)

    img_id = 'IMAGE_' + gen_str_codes(image_summary) + '_IMAGE'
    img_kid = gen_str_codes(img_id + str(uuid.uuid4()))
    img_bottom_content = img_id + '\n上图内容总结:\n' + image_summary + '\n'
    split_char = settings.SPLIT_CHAR or ";"
    img_path = split_char.join(img_dir.split(os.sep) + [f"{img_name}{img_ext}"])

    headings_stack[-1]['content'].append(img_bottom_content)
    df_list.append([img_bottom_content, img_path, img_id, len(img_bottom_content), "", image_summary, img_kid, "", "", time_stamp])
    return headings_stack, df_list

async def handle_table(df_list, block, tb_dir, headings_stack, current_heading, table_count, smart_summary=False):
    time_stamp = get_str_time()
    split_char = settings.SPLIT_CHAR or "-->"
    tb_html_str = table2html(block)
    if not tb_html_str.strip():
        return headings_stack

    try:
        last_context = (headings_stack[-1]['content'][-1]).strip()
    except:
        last_context = ''

    raw_tb_name = ' '.join([cell.text.strip() for cell in block.rows[0].cells]) if block.rows else "表格表头"
    tb_keywords = extract_tb_keywords(tb_html_str)
    if smart_summary:
        tb_summary = await extract_summary_keywords(tb_html_str, type_="summary")
        if tb_summary is None:
            tb_summary = (current_heading + ' ' + last_context + ' ' + raw_tb_name).strip()
    else:
        tb_summary = (current_heading + ' ' + last_context + ' ' + raw_tb_name).strip()

    tb_name = process_path_texts(f"表-{raw_tb_name} {tb_summary}", last=30) + str(table_count)
    table_id = 'TABLE_' + gen_str_codes(tb_html_str) + '_TABLE'
    table_kid = gen_str_codes(table_id + str(uuid.uuid4()))
    tb_bottom_content = table_id + '\n上表内容总结:\n' + tb_summary + '\n'
    tb_path = os.path.join(tb_dir, f'{tb_name}.html')

    if encryptor.encrypt:
        encryptor.save_to_file(tb_html_str, tb_path)
    else:
        soup = BeautifulSoup(tb_html_str, features='html.parser')
        tb_html_str = soup.prettify()
        with open(tb_path, 'w', encoding='utf-8') as f:
            f.write(tb_html_str)

    tb_path = split_char.join(tb_dir.split(os.sep) + [f"{tb_name}.html"])
    headings_stack[-1]['content'].append(tb_bottom_content)
    df_list.append([tb_bottom_content, tb_path, table_id, len(tb_bottom_content), tb_keywords, tb_summary, table_kid, "", "", time_stamp])
    return headings_stack, df_list

def iter_block_items(doc):
    ele_num = 1
    for child in doc.element.body:
        if isinstance(child, CT_P):
            paragraph = Paragraph(child, doc)
            image_found = False
            for run in paragraph.runs:
                if 'graphicData' in run._element.xml:
                    ET.register_namespace('a', 'http://schemas.openxmlformats.org/drawingml/2006/main')
                    ET.register_namespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')
                    # Try to extract image relationship ID
                    blip = run._element.xpath('.//a:blip/@r:embed')
                    if blip:
                        image_id = blip[0]
                        # Get the image path from the document's relationships
                        image_part = doc.part.related_parts.get(image_id)
                        image_path = image_part.partname if image_part else None
                        yield (ele_num, paragraph, 'IMAGE', image_path)
                        image_found = True
            if not image_found:
                yield (ele_num, paragraph, 'PTXT')
                    
        elif isinstance(child, CT_Tbl):
            yield (ele_num, Table(child, doc), 'TABLE')
        ele_num += 1

async def parse_docx(docx_path, llm_paras, kb_dir=None, filename="", file_url="", start_text="", end_text=""):
    doc_data = await load_file_bytes(docx_path, file_url=file_url)
    doc_stream = io.BytesIO(doc_data)
    doc = Document(doc_stream)

    doc_structure = []
    heading_data = pd.DataFrame(columns=['text', 'level']) 
    headings_stack = [{'level': -1, 'content': doc_structure}]
    current_heading = ''
    if start_text=="" and end_text=="":
        start_processing = True
    else:
        start_processing =False

    tb_dir = os.path.join(kb_dir, "tables")
    os.makedirs(tb_dir, exist_ok=True)
    img_dir = os.path.join(kb_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    titles_material = []
    for block_tuple in iter_block_items(doc):
        ele_num = block_tuple[0]
        block = block_tuple[1]
        if isinstance(block, Paragraph):
            title_text = block.text.strip()
            if len(title_text) > 0:
                titles_material.append((ele_num, block, title_text, len(title_text)))

    heading_candidates = []
    if not llm_paras['doc_type'] in "templates":
        if llm_paras['smart_title_parse']:
            heading_candidates = await pred_titles(titles_material, "docx")
        else:
            heading_candidates = filter_doc_headings(titles_material, consider_len=False)
            heading_candidates = [(t[0], t[1], -1 if t[2] == "待定" else t[2]) for t in heading_candidates] # 非大模型模式下 待定的会被统一调整为-1
            heading_candidates = pd.DataFrame(heading_candidates, columns=["id", "heading", "level"])

    if len(heading_candidates) > 0:
        heading_candidates = heading_dic_trans(heading_candidates, "id", "heading", "level")

    if len(heading_candidates)==0: # 处理全文档没有title的情况
        text = filename.split('.')[0]
        outline_level = 1
        heading_data.loc[len(heading_data)] = [text, outline_level]
        current_heading = text
        new_content = {'heading': text, 'content': [], 'level': outline_level}
        headings_stack[-1]['content'].append(new_content)  # Add to parent's content
        headings_stack.append(new_content)  # Push onto the stack
        logger.debug('没有发现潜在标题 采用文件名作为标题或自主发现: ' + text)

    df_list = []
    table_count = 0
    image_count = 0
    doc_image_files = detect_images(docx_path)

    for block_tuple in iter_block_items(doc):
        ele_num = block_tuple[0]
        block = block_tuple[1]
        label = block_tuple[2]
        
        if isinstance(block, Paragraph):
            text = remove_spaces(block.text.strip())
            if (not start_text=="") and (start_text in text.strip()):
                start_processing = True
            if (not end_text=="") and (end_text in text.strip()):
                break

            if start_processing:
                if len(text.strip())==0 and label=='PTXT':
                    continue
                try:
                    outline_level = heading_candidates[f"{ele_num}_{block.text}"]
                except:
                    outline_level = -1

                if text.strip():
                    if isinstance(outline_level, int) and outline_level>0:
                        logger.debug(f'找到层级标题: {text} 当前等级是 {outline_level}')
                        try:
                            last_heading = headings_stack[-1]['heading']
                            if last_heading==text:
                                continue
                        except:
                            pass

                        while headings_stack[-1]['level'] >= outline_level:
                            headings_stack.pop()  # Find the correct parent level
                        current_heading = text                        
                        new_content = {'heading': text, 'content': [], 'level': outline_level}
                        headings_stack[-1]['content'].append(new_content)  # Add to parent's content
                        headings_stack.append(new_content)  # Push onto the stack
                    else:
                        headings_stack[-1]['content'].append(text)
                
                if label=='IMAGE':
                    if len(doc_image_files)>0:
                        img_file = doc_image_files.pop()
                        if img_file.file_size<10*1024:
                            continue
                        headings_stack, df_list = await handle_image(df_list, doc_data, img_file.filename, img_dir, headings_stack,
                                                                    current_heading, image_count, llm_paras["summary_image"])
                        image_count += 1

        elif isinstance(block, Table):
            if start_processing:
                headings_stack, df_list = await handle_table(df_list, block, tb_dir, headings_stack, current_heading, table_count, llm_paras["summary_table"])
                table_count += 1
        else:
            pass
    # record training data
    # heading_data['binary_level'] = heading_data['level'].apply(lambda x: 1 if not x is None else 0)
    # heading_data.to_csv(os.path.join(kb_dir, 'table_train.csv'), encoding='utf-8-sig')
    return {'content' : doc_structure}, df_list

async def convert_doc2dics(parsed_structure, df_list, kb_dir, base_llm_paras):
    split_char = settings.SPLIT_CHAR or ";"
    leaf_dics = get_leaf_dics(parsed_structure)
    leaf_dics = await postprocess_leaf_dics(leaf_dics, base_llm_paras)
    
    doc_name = kb_dir.split(os.sep)[-1] # 允许带上.docx方便graph后续建构
    if len(leaf_dics) == 0:
        logger.warning(f"文档 {doc_name} 解析后没有内容，可能是空文件或解析失败")
        # 创建一个空的DataFrame而不是抛出异常
        all_df_cols = (settings.ALL_DF_COLS or "content,path,type,length,keywords,summary,know_id,tokens,extra,addtime").split(',')
        doc_df = pd.DataFrame(columns=all_df_cols)
        doc_df_path = os.path.join(kb_dir, 'KB_PTXT.csv')
        doc_df.to_csv(doc_df_path, encoding='utf-8', index=False)
        return
    # doc_graph = {}

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
            df_list.append([bottom_content, know_path, match_type, len(bottom_content), keywords, summary, know_id, bottom_tokens, "", time_stamp])
        except Exception as e:
            logger.error(f"解析docx文档失败 因为{e}")
            raise

    all_df_cols = (settings.ALL_DF_COLS or "content,path,type,length,keywords,summary,know_id,tokens,extra,addtime").split(',')
    doc_df = pd.DataFrame(df_list, columns=all_df_cols)
    doc_df = process_dup_paths_df(doc_df)
    doc_df_path = os.path.join(kb_dir, 'KB_PTXT.csv')
    if encryptor.encrypt:
        encryptor.save_to_file(doc_df, doc_df_path)
    else:
        doc_df.to_csv(doc_df_path, encoding='utf-8', index=False)

    # doc_graph, _ = restore_graph_by_paths(path_keys)
    # graph_path = os.path.join(kb_dir, 'graph.json')
    # if encryptor.encrypt:
    #     encryptor.save_to_file(doc_graph, graph_path)
    # else:
    #     with open(graph_path, 'w', encoding='utf-8') as f:
    #         json.dump(doc_graph, f, ensure_ascii=False, indent=4)
    # return doc_graph
        
