import os
import re
import uuid
from datetime import datetime
import pandas as pd
from shared.core.config import settings
from shared.utils.file_utils import path_handle
from bs4 import BeautifulSoup
from loguru import logger
from shared.core.exceptions.domain_exceptions import WorkerHandlingException, ValidationException


def count_cn_en(text: str):
    """统计中英文单词和数字的数量"""
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', str(text))
    cn_counts = len(chinese_chars)

    english_words = re.findall(r'[A-Za-z]+', str(text))
    en_counts = len(english_words)

    numbers = re.findall(r'\d+(?:\.\d+)?', text)
    number_count = len(numbers)
    return cn_counts + en_counts + number_count

def gen_str_codes(input_string):
    """生成字符串的UUID5编码"""
    namespace = uuid.NAMESPACE_DNS
    return str(uuid.uuid5(namespace, input_string))

def get_str_time():
    """获取当前时间字符串"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

def find_images(folder_path):
    """查找文件夹中的图片文件"""
    image_extensions = {'.png', '.jpg', '.jpeg'}
    image_files = []

    for _, _, files in os.walk(folder_path):
        files.sort()
        for file in files:
            if os.path.splitext(file)[1].lower() in image_extensions:
                image_files.append(file)
    return image_files

def find_matches_parsing(content, path):
    """解析内容中的表格和图片标记"""
    pattern = re.compile(r'(TABLE_.*?_TABLE|IMAGE_.*?_IMAGE)')
    matches = pattern.findall(content)
    if len(matches) == 0:
        match_type = 'PTXT'
    else:
        matches.append('PTXT')
        match_type = '\n'.join((['PTXT'] + matches))
    
    split_char = settings.SPLIT_CHAR or ";"
    if f'{split_char}摘要总结' in path:
        parent_path = path.split(split_char)[-2]
        match_type = ('SUMMARY_' + parent_path + '_SUMMARY')
    return match_type

def flatten_list(nested_list):
    """将嵌套列表展平"""
    flat_list = []
    for item in nested_list:
        if isinstance(item, list):
            flat_list.extend(flatten_list(item))
        else:
            flat_list.append(item)
    return flat_list

def flatten_dic2paths(d, current_path=None, result=None):
    """将嵌套字典展平为路径列表"""
    if result is None:
        result = []
    if current_path is None:
        current_path = []

    for key, value in d.items():
        if not isinstance(key, str):
            continue
        new_path = current_path + [key]
        if isinstance(value, dict) and value:
            flatten_dic2paths(value, new_path, result)
        else:
            split_char = settings.SPLIT_CHAR or ";"
            result.append(split_char.join(new_path))
    return result

def merge_df(input_df):
    """合并同路径的DataFrame行"""
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

def process_path_texts(path_, last=50):
    """处理路径文本"""
    temp_path = path_handle(path_, mode='sanitize')
    return '_'.join(temp_path.split(os.sep))[:last]

def process_dup_paths_df(df):
    """
    de-duplicate kbs dataframe for final output
    
    Args:
        df: initial dataframe after all heading stacking
    
    Returns:
        Dataframe without any duplicate paths
    """
    if 'path' not in df.columns:
        return df
    
    split_char = settings.SPLIT_CHAR or "/"
    
    # Step 1: detect if there are any duplicated paths
    dup_mask = df['path'].duplicated(keep=False)
    if not dup_mask.any():
        return df
    
    # Step 2: record ids of duplicated paths as a mapping
    path_occurrences = {}  # path -> list of row indices
    for idx, path in enumerate(df['path']):
        if path not in path_occurrences:
            path_occurrences[path] = []
        path_occurrences[path].append(idx)
    
    # path_renames: row_index -> new_path (recording rows renamed)
    # parent_rename_map: original_path -> {row_index: new_path}
    path_renames = {}
    parent_rename_map = {}
    
    for path, indices in path_occurrences.items():
        if len(indices) > 1:  # only process duplicated paths
            parent_rename_map[path] = {}
            for occurrence, idx in enumerate(indices):
                if occurrence == 0:
                    # keep the first appearance as it is
                    path_renames[idx] = path
                else:
                    # add suffix to subsequent appearances
                    new_path = f"{path}_{occurrence + 1}"
                    path_renames[idx] = new_path
                    parent_rename_map[path][idx] = new_path
    
    # Step 3: process all rows, update paths
    new_paths = []
    
    for idx, row in df.iterrows():
        path = row['path']
        
        # 检查这行本身是否需要重命名
        new_path = path_renames.get(idx, path)
        path_parts = new_path.split(split_char)
        
        # 检查这行的路径是否是某个被重命名父路径的子路径
        for parent_path, rename_info in parent_rename_map.items():
            parent_parts = parent_path.split(split_char)
            
            # 检查当前路径是否以此父路径开头（且不是父路径本身）
            if (len(path_parts) > len(parent_parts) and 
                path_parts[:len(parent_parts)] == parent_parts):
                
                # 找到在当前行之前、最近的被重命名的父路径
                matching_parent_idx = None
                for parent_idx in sorted(rename_info.keys(), reverse=True):
                    if parent_idx < idx:
                        matching_parent_idx = parent_idx
                        break
                
                if matching_parent_idx is not None:
                    renamed_parent = rename_info[matching_parent_idx]
                    renamed_parent_parts = renamed_parent.split(split_char)
                    new_path_parts = renamed_parent_parts + path_parts[len(parent_parts):]
                    new_path = split_char.join(new_path_parts)
                    break    
        new_paths.append(new_path)
    
    df = df.copy()
    df['path'] = new_paths
    return df

def remove_spaces(text, handle_punctuation=False):
    """移除中文之间的空格，保留英文单词间的空格"""
    if handle_punctuation:
        punctuation = r"""!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~，。、【】《》？；：''""（）…—-！"""
        res_text = re.sub(f"[{re.escape(punctuation)}]", "", text)
    else:
        pattern = re.compile(r'([\u4e00-\u9fff])\s+|(?<=\s)([\u4e00-\u9fff])')
        def replacer(match):
            return match.group(1) or match.group(2)
        res_text = pattern.sub(replacer, text)
    
    res_text = re.sub(r'\s+', ' ', res_text)
    return res_text.strip()

def traverse_dict(d, parent=None):
    """遍历字典生成描述文本"""
    dic_texts = []
    for key, value in d.items():
        if value:
            child_keys = ', '.join(value.keys())
            text = f"'{key}' 包括 {child_keys}"
            dic_texts.append(text)
            dic_texts.extend(traverse_dict(value, key))
    return dic_texts

def restore_graph_by_paths(paths):
    """从路径列表重建图结构"""
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

def html2txt(html_text):
    """将HTML转换为纯文本"""
    soup = BeautifulSoup(html_text, 'html.parser')
    text = soup.get_text()
    return text