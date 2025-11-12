"""
文件操作通用工具函数
这些函数被多个服务使用，保留在 shared-python 中
"""
import os

import pandas as pd


def clean_file(path_, mode='remove', cols=None):
    """
    清理文件
    
    Args:
        path_: 文件路径
        mode: 清理模式 ('remove' 删除文件, 'clean' 清空内容)
        cols: 列名（用于 CSV 文件）
    """
    try:
        if mode == 'remove':
            os.remove(path_)
        elif mode == 'clean':
            if '.txt' in path_:
                pass
            elif '.csv' in path_:
                exist_df = pd.read_csv(path_, encoding='utf-8', keep_default_na=False)
                if not cols == None:
                    empty_df = pd.DataFrame(columns=cols)
                else:
                    empty_df = pd.DataFrame(columns=exist_df.columns)
                empty_df.to_csv(path_, index=False)
        else:
            pass
    except:
        pass


def path_handle(path, mode):
    """
    路径处理工具函数
    
    Args:
        path: 路径字符串
        mode: 处理模式 ('split', 'extract-base', 'sanitize', 'clean_single')
    
    Returns:
        处理后的路径或路径列表
    """
    import re
    illegal_chars = r'[\t\n<>：:;；"　/\\|?*]'
    safe_char = '_'

    if mode == 'split':
        path_lst = path.split(os.sep)
        return path_lst

    elif mode == 'extract-base':
        base_name = os.path.basename(path)
        base_name = os.path.splitext(base_name)[0]
        return base_name

    elif mode == 'sanitize':
        path = path.replace("\\", "/")
        parts = path.split("/")
        sanitized_parts = []
        for part in parts:  # 用正则替换掉非法字符（包括 / 本身）
            clean_part = re.sub(illegal_chars, safe_char, part)
            sanitized_parts.append(clean_part)
        return os.sep.join(sanitized_parts)

    elif mode == 'clean_single':
        path = re.sub(illegal_chars, safe_char, path)
        return path
    return None

