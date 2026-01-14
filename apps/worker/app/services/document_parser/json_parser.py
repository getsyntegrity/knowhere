import json
import os
from collections import Counter

import pandas as pd
from file_encryptor import encryptor
from image_parser import image_summary
from md_parser import update_df_list
from table_parser import (extract_tables_by_forms, extract_tb_keywords,
                          identify_tables)
from txt_parser import clean_texts_by_form
# from knowledge_generator import process_full_contents
from utlis import (gen_str_codes, know_df_cols)


def get_common_keys(json_data):
    """
        :function: parse keys in a specific level, get common keys (keys existing in all dics), which will be the core of clustering and hierarchy generation
        :return: a dataframe with 2 columns, one records the key names, the other records their frequencies (counts)
    """
    key_counts = Counter()
    total_entries = len(json_data)

    for entry in json_data:
        if isinstance(entry, dict):
            key_counts.update(entry.keys())

    common_keys = {key for key, count in key_counts.items() if count == total_entries}
    df_keys = pd.DataFrame(list(dict(key_counts).items()), columns=["Key", "Count"])
    df_keys["Is_Common"] = df_keys["Key"].isin(common_keys)
    df_keys = df_keys.sort_values(by=["Is_Common", "Count"], ascending=[False, False])
    return df_keys


def extract_level_contents(content_ids, img_ids, current_d, inner_key, img_record, img_record_pth, tb_record, tb_record_pth, call_llm=None, llm_histories=None, local_llm_name=None, local_llm=None, local_llm_tz=None, model_config=None, local_summary=False):
    content = ''
    for key in (content_ids + img_ids):
        try:
            raw_content = current_d[key]
            # ****UNDER DEVELOPMENT**** handle list and list of dicts (probably tables), utilize LLMs to recognize and translate
            # by default only handle texts, if raw_content is in other forms, the code will enter exception and ignore the current key
            if raw_content.strip()=='':
                continue
            # a. handle images
            img_match = key in img_ids
            if img_match:
                img_summary = image_summary(raw_content, call_llm, llm_histories, local_llm_name, local_llm, local_llm_tz, model_config, local_summary)
                # ****UNDER DEVELOPMENT**** download the image using the url, save it to the file system
                img_id = 'IMAGE_' + gen_str_codes(img_summary) + '_IMAGE'
                # update the local image dictionary
                img_record.update({img_id : img_summary}) # in md file, the url often contains the .format
                if encryptor.encrypt:
                    encryptor.save_to_file(img_record, img_record_pth)
                else:
                    with open(img_record_pth, 'w', encoding='utf-8') as f:
                        json.dump(img_record, f, ensure_ascii=False, indent=4)
                # generate content used in KB_PTXT
                content = content + '\n' + img_id + '\n'
            # b. handle tables
            tb_bool, form, tables = identify_tables(raw_content)
            if tb_bool:
                for tb_txt in tables:
                    tb_df = extract_tables_by_forms(tb_txt, form)
                    tb_str = tb_df.to_csv(index=False)
                    table_id = 'TABLE_' + gen_str_codes(tb_str) + '_TABLE'

                    tb_summary = extract_tb_keywords(tb_df)
                    tb_path = os.path.join(kb_dir, tb_summary + '.csv')
                    if encryptor.encrypt:
                        encryptor.save_to_file(tb_df, tb_path)
                    else:
                        tb_df.to_csv(tb_path, encoding='utf-8', index=False)
                    # update global table directory for reusing
                    tb_record.update({table_id : tb_summary + '.csv'})
                    if encryptor.encrypt:
                        encryptor.save_to_file(tb_record, tb_record_pth)
                    else:
                        with open(tb_record_pth, 'w', encoding='utf-8') as f:
                            json.dump(tb_record, f, ensure_ascii=False, indent=4)
                    # generate content used in KB_PTXT
                    content = content + '\n' + table_id + '\n'              
            # c. handle texts
            if not img_match and not tb_bool:
                raw_content = clean_texts_by_form(raw_content)
                content = content + '\n' + raw_content.strip() + '\n'
        except Exception as e:
            print(e)
            continue
    return content


def parse_json(file_path, kb_dir, llm_paras, content_key='content', local_summary=False):
    '''
        :key function -- use LLM to intelligently parse json keys (the keys are highly uncertain, which cannot be predefined)
    '''
    # parsing--bfs-based handling
    def dfs_parse(current_dic, content_ids, img_ids, path_stack, inner_key, img_record, img_record_pth, tb_record, tb_record_pth, llm_paras, local_summary):
        # 1.1 evaluate keys
        common_keys = get_common_keys(json_data)
        # 1.2 determine which key-values are merged and which key-values should be used to go deeper
        dig_ids = ['childQuestionList'] # parsed results
        content_ids = ['paperName', 'quesTitle', 'quesAnswer', 'intention', 'subjectAbilities'] # adaptive parsed results, notice that we also parse and include image
        img_ids = ['quesImgUrl']

        # 2. generate contents at the current dict level
        path = '-->'.join(path_stack)
        content = extract_level_contents(content_ids, img_ids, current_dic, inner_key, img_record, img_record_pth, tb_record, tb_record_pth, call_llm, llm_histories, local_llm_name, local_llm, local_llm_tz, model_config, local_summary)
        node = {'id':path, 'content': content, 'children': []}
        df_list, content, _ = update_df_list(df_list, content, inner_key, path, local_summary, llm_paras)

        for key in dig_ids:
            if key in current_dic and isinstance(current_dic[key], list):
                for i, child in enumerate(current_dic[key]):
                    if isinstance(child, dict):
                        child_path_stack = path_stack + [f"{key}[{i}]"]
                        child_node = dfs(child, key, child_path_stack)
                        node['children'].append(child_node)
        return node

    # read .json files
    with open(file_path, 'r', encoding='utf-8') as f:
        filename = file_path.split(os.sep)[-1]
        json_data = json.load(f)            

    # initialize-- open the local directories for images and tables
    img_record_pth = os.path.join(kb_dir, 'image_record.json')
    try:
        if encryptor.encrypt:
            img_record = encryptor.load_from_file(img_record_pth)
        else:
            with open(img_record_pth, 'r', encoding='utf-8') as f:
                img_record = json.load(f)
    except Exception as e:
        img_record = {}
    
    tb_record_pth = os.path.join(kb_dir, ('table_record.json'))
    try:
        if encryptor.encrypt:
            tb_record = encryptor.load_from_file(tb_record_pth)
        else:
            with open(tb_record_pth, 'r', encoding='utf-8') as f:
                tb_record = json.load(f)
    except Exception as e:
        tb_record = {}

    # initialize-- create vars
    doc_df = pd.DataFrame(columns=know_df_cols)
    df_list = []
    results = []

    # parsing--handle json boundary condition
    root_key = filename
    if isinstance(json_data, list):
        for idx, item in enumerate(json_data):
            if isinstance(item, dict):
                path_stack= [f"{root_key}[{idx}]"] # set file name as the root key
                results.append(dfs_parse(item, root_key, path_stack))

    elif isinstance(json_data, dict):
        results.append(dfs_parse(json_data, root_key, [root_key]))
    else:
        raise ValueError("Input JSON must be a dictionary or a list of dictionaries!")
            

    doc_df = pd.concat(df_list, ignore_index=True)
    
    return doc_df



if __name__ =="__main__":    
    kb_dir = '..' + os.sep + '知识固化库_DEMO\默认目录'
    # file_path = r'C:\Users\DELL\Desktop\testdir\地理试题-1.json'
    file_path = r'C:\Users\chengke\Desktop\testdir\地理试题-2.json'
    parse_json(file_path, kb_dir)

    
    
    