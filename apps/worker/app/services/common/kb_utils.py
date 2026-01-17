import copy
import os
import re
import uuid
from collections import Counter
from datetime import datetime

import Levenshtein
import numpy as np
import pandas as pd
import requests
from shared.core.config import settings
from shared.utils.file_utils import path_handle
# 通用工具函数从 shared-python 导入
from shared.utils.text_utils import remove_duplicates_orderkept
from bs4 import BeautifulSoup
from loguru import logger
from shared.core.exceptions.domain_exceptions import WorkerHandlingException, ValidationException


def build_tree_from_paths(paths):
    """把 path list 转换为嵌套 dict"""
    root = {}
    for p in paths:
        parts = p.split("-->")
        cur = root
        for part in parts:
            cur = cur.setdefault(part, {})
    return root

def count_cn_en(text: str):
    # Chinese words: \u4e00-\u9fff
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', str(text))
    cn_counts = len(chinese_chars)

    # English words continuous alphabets
    english_words = re.findall(r'[A-Za-z]+', str(text))
    en_counts = len(english_words)

    numbers = re.findall(r'\d+(?:\.\d+)?', text)
    number_count = len(numbers)
    return cn_counts + en_counts + number_count

def clean_contents(contents):
    pattern = re.compile(r'(TABLE_.*?_TABLE|IMAGE_.*?_IMAGE)')
    cleaned_contents = []
    for c in contents:
        cleaned_contents.append(pattern.sub('', c).strip())
    return cleaned_contents

def check_internet(url='http://www.baidu.com'):
    try:
        from shared.core.constants import APIConstants
        response = requests.get(url, timeout=APIConstants.REQUEST_TIMEOUT)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"网络连接失败: {e}")
        return False

# _gc 已移到 shared-python 的 gc_utils，重命名为 gc_collect


def get_node_level(tree, target_node, current_level=0):
    if target_node in tree:
        return current_level
    
    for child, subtree in tree.items():
        if subtree is not None:  # Check if the child has children
            level = get_node_level(subtree, target_node, current_level + 1)
            if level is not None:
                return level
    return None

def gen_str_codes(input_string):
    namespace = uuid.NAMESPACE_DNS
    return str(uuid.uuid5(namespace, input_string))

def get_str_time():
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

def cal_levenshtein_dis(text, target):
    distance = Levenshtein.distance(text, target)
    max_len = max(len(text), len(target))
    similarity = 1 - (distance / max_len)
    return similarity

    
def create_reply(contents, intentions):
    reply = '为你找到如下信息：\n'
    for i, content in enumerate(contents):
        reply += '【' + str(i+1) + '】' + content +'  \n'
    reply = reply.strip()
    print('\n用户意图：{} \n{}'.format(intentions, reply), '\n')
    return reply

def unify_key(item_: str, record_ref: dict) -> str:
    """
    确保 path_item 在 record_path_ref 中唯一。
    如果已存在，则自动在后面添加递增的后缀 _1, _2, _3...
    """
    if item_ not in record_ref:
        return item_
    # 如果已存在，递增计数直到唯一
    counter = 1
    new_key = f"{item_}_{counter}"
    while new_key in record_ref:
        counter += 1
        new_key = f"{item_}_{counter}"
    return new_key

def expand_summary_paths(df, node, summary_term=''):
    paths = df['path'].to_list()
    filtered_paths = []
    cut_filtered_paths = []
    
    split_char = settings.SPLIT_CHAR or ";"
    for path in paths:
        nodes = path.split(split_char)
        if node in nodes and (not summary_term in path):
            idx = nodes.index(node)
            filtered_paths.append(path)
            cut_filtered_paths.append(split_char.join(nodes[idx: ]))
            
    filtered_df = df[df['path'].isin(filtered_paths)]
    cut_filtered_paths = remove_duplicates_orderkept(cut_filtered_paths)
    return cut_filtered_paths, filtered_df

def extract_nested_dic_vals(obj, values_list=None):
    if values_list is None:
        values_list = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == 'id':  # skip key-value pairs where key is 'id'
                continue
            if isinstance(value, dict):
                extract_nested_dic_vals(value, values_list)
            elif isinstance(value, list):
                for item in value:
                    extract_nested_dic_vals(item, values_list)
            elif isinstance(value, str):
                values_list.append(value)
    values_list = [v for v in values_list if not v.strip()=='']
    return values_list

def extract_know(match_dfs, KB_PATH="", placeholders=['HHF']):
    raw_texts = []
    for i, row in match_dfs.iterrows():
        kg_contents_ = row['content']
        type = row['type']
        
        if type=='PTXT':
            raw_texts.append(kg_contents_)
        
        elif type=='TABLE':
            tb_path = os.path.join(KB_PATH, 'tables', (type + '.csv'))
            tb_df = pd.read_csv(tb_path, encoding='utf-8')
            raw_texts.append(tb_df.to_string(index=False))
             
        elif type=='IMAGE':
            continue
    
    content_ = '\n'.join(raw_texts)
    pattern = r'|'.join(re.escape(p) for p in placeholders if not p=='')
    content_ = re.sub(pattern, '', content_)
    return content_, raw_texts

def extract_window(lst, index, num, return_lst=False):
    proceedings = lst[max(0, index - num):index]  # Extract proceeding elements
    succeedings = lst[index + 1:min(len(lst), index + num + 1)]  # Extract succeeding elements
    if return_lst:
        return proceedings, succeedings
    else:
        return '\n'.join(proceedings), '\n'.join(succeedings)

def extract_keylevels(dic, level=0, result=None):
    if result is None:
        result = []
    for key, value in dic.items():
        result.append((key, level))
        if isinstance(value, dict):  # If the value is a dictionary, recurse
            extract_keylevels(value, level+1, result)
    return result

'''methods for file processing'''
def file_lst(origin_path):
    paths = os.walk(origin_path)
    res_paths = []
    for root, _, file_lst in paths:
        if not root==origin_path:
            break
        for f_name in file_lst:
            temp_path = os.path.join(origin_path, f_name)
            res_paths.append(temp_path)
    return res_paths

def find_frequent(lst):
    counter = Counter(lst)
    most_common = counter.most_common(1)[0][0]
    return most_common

def find_images(folder_path):
    image_extensions = {'.png', '.jpg', '.jpeg'}
    image_files = []

    for _, _, files in os.walk(folder_path):
        files.sort()
        for file in files:
            if os.path.splitext(file)[1].lower() in image_extensions:
                image_files.append(file)
    return image_files

def find_similar_bychars(reference, strings):
    min_distance = float('inf')
    most_similar = None

    for string in strings:
        distance = Levenshtein.distance(reference, string)
        if distance < min_distance:
            min_distance = distance
            most_similar = string
    return most_similar

def find_matches_parsing(content, path):
    pattern = re.compile(r'(TABLE_.*?_TABLE|IMAGE_.*?_IMAGE)')
    matches = pattern.findall(content)
    if len(matches)==0:
        match_type = 'PTXT'
    else:
        matches.append('PTXT')
        match_type = '\n'.join((['PTXT'] + matches))
    
    split_char = settings.SPLIT_CHAR or ";"
    if f'{split_char}摘要总结' in path:
        parent_path = path.split(split_char)[-2] # -1是 term "摘要总结"
        match_type = ('SUMMARY_' + parent_path + '_SUMMARY')
    return match_type

def flatten_list(nested_list):
    """Helper function to flatten a nested list."""
    flat_list = []
    for item in nested_list:
        if isinstance(item, list):
            flat_list.extend(flatten_list(item))
        else:
            flat_list.append(item)
    return flat_list

def flatten_dict(d, parent_key=()):
    """Helper function to flatten a nested dictionary. for converting dictionary to dataframe"""
    items = []
    for k, v in d.items():
        new_key = parent_key + (k,)
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key).items())
        else:
            items.append((new_key, v))
    return dict(items)

def flatten_dic2paths(d, current_path=None, result=None):
    if result is None:
        result = []
    if current_path is None:
        current_path = []

    for key, value in d.items():
        if not isinstance(key, str):
            continue
        new_path = current_path + [key]  # Add the current key to the path
        if isinstance(value, dict) and value:  # If the value is a non-empty dictionary, recurse
            flatten_dic2paths(value, new_path, result)
        else:
            split_char = settings.SPLIT_CHAR or ";"
            result.append(split_char.join(new_path))
    return result

async def gen_sim_matrix(vecs_, self_ids, k=10, use_cosine=True, pre_threshold=0.2, q=0.9):
    logger.debug(f"开始生成相似度矩阵，向量数量: {len(vecs_)}, k: {k}, 使用余弦相似度: {use_cosine}")
    logger.debug(f"预阈值: {pre_threshold}, 分位数: {q}, 自身ID数量: {len(self_ids)}")

    try:
        if use_cosine:
            logger.debug("对向量进行余弦归一化")
            norms = np.linalg.norm(vecs_, axis=1, keepdims=True)
            vecs_ = vecs_ / (norms + 1e-10)
            logger.debug("余弦归一化完成")

        logger.debug("计算相似度矩阵")
        sim_matrix = vecs_ @ vecs_.T  # 由于vecs本身ids总是012 所以得到的topids就是dataframe的行号
        n = sim_matrix.shape[0]
        logger.debug(f"相似度矩阵形状: {sim_matrix.shape}")

        topk_indices = np.zeros((n, k), dtype=int)
        topk_values = np.zeros((n, k))

        logger.debug(f"开始计算每个向量的top-{k}相似向量")
        for i in range(n):
            sim_matrix[i, i] = -np.inf  # 去除自身
            idx = np.argpartition(-sim_matrix[i], k)[:k]
            idx = idx[np.argsort(-sim_matrix[i, idx])]  # 再次排序，保证从大到小

            topk_indices[i] = idx
            topk_values[i] = sim_matrix[i, idx]

        logger.debug(f"top-{k}计算完成，开始阈值过滤")
        threshold = np.max((np.quantile(topk_values, q), pre_threshold))
        logger.debug(f"计算得到的阈值: {threshold:.4f}")

        filtered_indices = topk_indices.copy()  # 拷贝，避免原地修改
        mask = topk_values < threshold
        filtered_count = np.sum(mask)
        filtered_indices[mask] = -1
        logger.debug(f"阈值过滤完成，过滤掉 {filtered_count} 个相似度低于阈值的项")

        if len(self_ids) > 0:  # 凡是候选属于 self_ids 的置 -1
            logger.debug(f"过滤自身ID: {self_ids}")
            invalid_mask = np.isin(filtered_indices, self_ids)
            self_filtered_count = np.sum(invalid_mask)
            filtered_indices[invalid_mask] = -1
            logger.debug(f"自身ID过滤完成，过滤掉 {self_filtered_count} 个自身项")

        logger.debug(f"相似度矩阵生成完成，最终阈值: {threshold:.4f}")
        return filtered_indices, threshold

    except Exception as e:
        logger.error(f"生成相似度矩阵过程中发生异常: {str(e)}")
        logger.error(f"异常类型: {type(e).__name__}")
        import traceback
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise WorkerHandlingException(original_exception=e)

def merge_df(input_df):
    dfs_by_path = list(input_df.groupby('path', sort=False))
    processed_dfs = []

    for key, df in dfs_by_path:
        content_to_merge = []
        types_to_merge = []
        total_length = 0

        for i, row in df.iterrows():
            content_to_merge.append(row['content'])
            types_to_merge.extend(row['type'].split('\n'))
            total_length += len(row['content'])

        content_to_merge = "\n".join(content_to_merge)
        temp_merge_df = pd.DataFrame([{
            'content': content_to_merge,
            'type': '\n'.join(list(set(types_to_merge))),
            'path': key,
            'length': total_length,
            'know_id': gen_str_codes(content_to_merge)
        }])
        processed_dfs.append(temp_merge_df)

    final_df = pd.concat(processed_dfs, axis=0, ignore_index=True)
    return final_df

def text_list2md(text_list, headers, splitchar="\t"):
    col_count = len(headers)
    # 添加序号列
    full_headers = ["序号"] + headers
    md_lines = ["| " + " | ".join(full_headers) + " |"]
    md_lines.append("|" + "|".join(["------"] * len(full_headers)) + "|")

    for idx, line in enumerate(text_list, 1):
        parts = [p.strip().replace("\n", "<br>") for p in line.split(splitchar)]
        if len(parts) < col_count:
            parts += ["-"] * (col_count - len(parts))
        else:
            parts = parts[:col_count]
        row = [str(idx)] + parts
        md_lines.append("| " + " | ".join(row) + " |")
    return "\n".join(md_lines)


def process_path_texts(path_, last=50):
    temp_path = path_handle(path_, mode='sanitize')
    return '_'.join(temp_path.split(os.sep))[:last]

def process_dup_paths_df(df):
    if df['path'].duplicated(keep=False).any():
        df['count'] = df.groupby('path').cumcount() + 1
        df['path'] = df.apply(lambda x: f"{x['path']}_{x['count']}" if x['count'] > 1 else x['path'], axis=1)
        df.drop(columns=['count'], inplace=True)
    return df
    
def remove_spaces(text, handle_punctuation=False):
    '''
        :function remove empty spaces between Chinese words and keep such spaces between English words and numbers
        :input
            :text raw texts
        :output
            :res_text texts after space removing
    '''
    if handle_punctuation==True:
        punctuation = r"""!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~，。、【】《》？；：‘’“”（）…—-！"""
        res_text = re.sub(f"[{re.escape(punctuation)}]", "", text)
    else:
        pattern = re.compile(r'([\u4e00-\u9fff])\s+|(?<=\s)([\u4e00-\u9fff])')
        def replacer(match):
            return match.group(1) or match.group(2)
        res_text = pattern.sub(replacer, text)
    
    res_text = re.sub(r'\s+', ' ', res_text)
    return res_text.strip()

def restore_graph_by_paths(paths):
    root_dict = {}
    split_char = settings.SPLIT_CHAR or ";"
    for path in paths:
        nodes = path.split(split_char)
        current_dict = root_dict
        for node in nodes:
            if node not in current_dict:
                current_dict[node] = {}
            current_dict = current_dict[node]
    dic_texts = traverse_dict(root_dict)
    return root_dict, dic_texts

def set_bottom_dic_val(d, path, val, mode='replace'):
    modified_dict = copy.deepcopy(d)  # Create a deep copy of the dictionary
    split_char = settings.SPLIT_CHAR or ";"
    keys = path.split(split_char)
    current = modified_dict
    for key in keys[:-1]:  # Traverse to the second-to-last key
        if key not in current or not isinstance(current[key], dict):
            raise WorkerHandlingException(
                internal_message=f"Invalid path: node '{key}' not found in dictionary for path '{path}'"
            )
        current = current[key]
    
    if mode=='replace':
        current[keys[-1]] = val  # Directly replace the value at the final key
    elif mode=='add':
        current[keys[-1]] += val
    elif mode=='extract':
        return ','.join(keys[1:]), current[keys[-1]]
    else:
        pass
    return modified_dict

def split_path_by_node(s: str, target: str):
    parts = s.split("-->")
    if target not in parts:
        return s, ""  # 如果找不到target，返回原串和空串

    idx = parts.index(target)
    left = "-->".join(parts[:idx])       # target之前（不含）
    right = "-->".join(parts[idx:])      # target及之后
    return left, right

def traverse_dict(d, parent=None):
    dic_texts = []
    for key, value in d.items():
        if value:
            child_keys = ', '.join(value.keys())
            text = f"'{key}' 包括 {child_keys}"
            dic_texts.append(text)
            dic_texts.extend(traverse_dict(value, key))
    return dic_texts

def truncate_paths(elements: list[str], keyword: str) -> list[str]:
    split_char = settings.SPLIT_CHAR or ";"  # 默认分隔符
    new_list = []

    for elem in elements:
        parts = elem.split(split_char)
        # 找到第一个包含 keyword 的 part
        idx = next((i for i, p in enumerate(parts) if keyword in p), None)
        if idx is not None:
            new_elem = split_char.join(parts[:idx + 1])  # 保留 keyword
            new_list.append(new_elem)
    return new_list

def html2txt(html_text):
    soup = BeautifulSoup(html_text, 'html.parser')
    text = soup.get_text()
    return text


'''
    some temporary functions
'''
# def secure_filename(input_name):
#     safe_name = re.sub(r'[<>:"/\\|?*,]', '_', input_name)
#     safe_name = safe_name.rstrip('. ')

#     reserved_names = ["CON", "PRN", "AUX", "NUL",
#                       "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
#                       "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"]
    
#     if safe_name.upper() in reserved_names:
#         safe_name = "_" + safe_name
#     return safe_name

# def get_key_levels(d, level=1):
#     key_levels = []
#     for key, value in d.items():
#         key_levels.append((key, level))
#         if isinstance(value, dict):
#             key_levels.extend(get_key_levels(value, level + 1))
#     return key_levels

# def handle_unique_dfcols(df):
#     if df.columns.duplicated().any():
#         new_columns = []
#         for i, col in enumerate(df.columns):
#             if df.columns.duplicated()[i]:
#                 new_columns.append(f"{col}_{i}")
#             else:
#                 new_columns.append(col)
#         df.columns = new_columns
#     return df

# elif mode == 'convert':
# illegal_pattern = re.compile(f'[<>"|?*\x00-\x1F\t]')
# path = illegal_pattern.sub('', path)
# try:
#     separator = os.sep
#     path = path.replace('/', separator).replace('\\', separator)
#     return path.replace('\n', '')
# except:
#     return path.replace('\n', '')
#
# elif mode == 'clean':  # remove all non-Chinese or English characters at the beginning of the text, also remove all non-necessary suffix
# # re_pattern = r'^[^\u4e00-\u9fff]*([\u4e00-\u9fff].*)'
# # match = re.search(re_pattern, path)
# # p_item = match.group(1) if match else path
# p_item = path
# if len(suffixes) > 0:
#     for suffix in suffixes:
#         p_item = p_item.replace(suffix, '')
# return p_item

# def postprocess_tb(df):
#     # Replace '\n' in column headers
#     df.columns = [str(col).replace('\n', '') for col in df.columns]
#     # Replace '\n' in each cell
#     df = df.applymap(lambda x: x.replace('\n', '') if isinstance(x, str) else x)
#     # Convert date values that can cause errors
#     for col in df.columns:
#         if pd.api.types.is_datetime64_any_dtype(df[col]):
#             df[col] = df[col].astype(str)
#     return df

# def flatten_dic_dfs(d, parent_key=''):
#     """Helper function to flatten a nested dictionary by screening keys from top to bottom levels, keeping their order"""
#     keys = []
#     for k, v in d.items():
#         full_key = k
#         keys.append(full_key)
#         if isinstance(v, dict) and v:
#             keys.extend(flatten_dic_dfs(v))
#     return keys

# def parse_fragment_path(user, KB_PATH, fragment_path):
#     type = 2
#     fragment_path = fragment_path.removeprefix(user + SPLIT_CHAR)
#     fragment_paths = fragment_path.split(SPLIT_CHAR)
#     fragment_name = fragment_paths[-1]
#     if fragment_paths[0] == 'images':
#         type = 3
#         fragment_paths.pop(0)
#
#     i = 0
#     real_file_dir = ''
#     for path in fragment_paths:
#         temp_path = os.path.join(real_file_dir, path)
#         if not os.path.isdir(os.path.join(KB_PATH, temp_path)):
#             break
#         real_file_dir = temp_path
#         i += 1
#
#     if real_file_dir == '':
#         raise ValueError('路径错误')
#     file_dir = f'{SPLIT_CHAR}'.join(fragment_paths[:i])
#     sub_path = f'{SPLIT_CHAR}'.join(fragment_paths[i:])
#     return type, os.path.join(KB_PATH, real_file_dir), file_dir, sub_path, fragment_name
#
# def parser_context(html_text):
#     # 使用BeautifulSoup解析HTML
#     soup = BeautifulSoup(html_text, 'lxml')
#
#     # 初始化结果列表
#     result = []
#
#     # 遍历解析后的内容
#     for element in soup.recursiveChildGenerator():
#         if element.name == 'img':  # 图片
#             result.append(('image', element.get('src')))
#         elif element.name == 'table':  # 表格
#             try:
#                 tbl_str = str(element)
#                 df = pd.read_html(tbl_str)[0]
#                 result.append(('table', df))
#             except Exception as e:
#                 print(f'tbl_str:{tbl_str}, e:{e}')
#                 continue
#         elif isinstance(element, str) and element.strip():  # 文本
#             # 检查当前文本是否在表格内部
#             parent = element.parent
#             while parent:
#                 if parent.name == 'table':
#                     break  # 如果在表格内部，跳过
#                 parent = parent.parent
#             else:
#                 # 如果不在表格内部，添加到结果
#                 result.append(('text', element.strip()))
#     return result

# def post_request(url, req_body=None, files=None, timeout=60):
#     try:
#         rsp = requests.post(url, json=req_body, files=files, timeout=timeout)
#         rsp.raise_for_status()
#     except requests.exceptions.Timeout:
#         return '请求超时，请稍后重试', 408
#     except requests.exceptions.ConnectionError:
#         return '网络连接错误，请检查您的网络', 503
#     except requests.exceptions.HTTPError as e:
#         return f'HTTP错误: {str(e)}', rsp.status_code
#     except requests.exceptions.RequestException as e:
#         return f'请求异常: {str(e)}', 500
#     return rsp.json(), 200
#
#
# def han_tok(contents):
#     req_body = {'querys': contents}
#     msg, status_code = post_request('http://218.17.187.47:35010/tokenizer', req_body)
#     if status_code != 200:
#         raise ConnectionError(msg)
#     tokens = msg['tokens']
#     return tokens

# def convert_file_tree_to_nested_list(input_data):
#     output_list = []
#     # 递归处理每个节点
#     def process_node(title_key, node_data):
#         # 判断是否是最终内容节点（即包含 __know_id__ 和 __content__ 的叶子节点）
#         if isinstance(node_data, dict) and "__know_id__" in node_data and "__content__" in node_data:
#             return {
#                 "title": title_key,
#                 "isFile": None,
#                 "isFragments": True,
#                 "content": node_data.get("__content__", ""),
#                 "childerId": node_data.get("__know_id__", ""),
#             }
#         else:
#             # 这是一个中间节点（文件夹或章节）
#             children_nodes = []
#             if isinstance(node_data, dict):
#                 for sub_title, sub_data in node_data.items():
#                     children_nodes.append(process_node(sub_title, sub_data))
#
#             return {
#                 "title": title_key,
#                 "isFile": None,
#                 "isFragments": True,
#                 "children": children_nodes,
#                 "childerId": str(uuid.uuid4()),  # 为每个中间节点生成一个唯一的 childerId
#             }
#
#     # 从 "file_tree" 的顶层开始处理
#     if "file_tree" in input_data and isinstance(input_data["file_tree"], dict):
#         for top_level_title, top_level_data in input_data["file_tree"].items():
#             output_list.append(process_node(top_level_title, top_level_data))
#     return output_list

# def merge_texts_by_threshold(text_list, threshold, merge_term='\n'):
#     merged_texts = []
#     current_text = []
#     current_word_count = 0
#
#     for text in text_list:
#         word_count = len(text)  # Count words in the current text
#         # If the current block is already over the threshold, finalize it before adding a new text
#         if current_word_count >= threshold:
#             merged_texts.append(merge_term.join(current_text))
#             current_text = []  # Reset for the next batch
#             current_word_count = 0
#         # Add the current text to the buffer
#         current_text.append(text)
#         current_word_count += word_count
#     # Ensure the last accumulated text is added
#     if current_text:
#         last_text = merge_term.join(current_text)
#         last_word_count = len(last_text)
#
#         if merged_texts and last_word_count < threshold:
#             merged_texts[-1] += (merge_term + last_text)
#         else:
#             merged_texts.append(last_text)
#     return merged_texts