"""
文本处理通用工具函数
这些函数被多个服务使用，保留在 shared-python 中
"""
import re
from typing import List, Optional

import jieba


def remove_duplicates_orderkept(input_list: List) -> List:
    """
    移除重复项但保持顺序
    
    Args:
        input_list: 输入列表
    
    Returns:
        去重后的列表
    """
    seen = set()
    output_list = []
    for item in input_list:
        if item not in seen:
            output_list.append(item)
            seen.add(item)
    return output_list


def merge_non_chinese_until_chinese(lst: List[str]) -> List[str]:
    """
    合并非中文字符直到遇到中文字符
    
    Args:
        lst: 字符串列表
    
    Returns:
        合并后的列表
    """
    # 去除空字符串
    lst = [item for item in lst if item.strip()]
    
    result = []
    temp = ""
    
    for item in lst:
        # 判断是否是中文字符
        if re.search(r'[\u4e00-\u9fff]', item):
            # 如果前面有非中文字符要先合并
            if temp:
                result.append(temp)
                temp = ""
            result.append(item)
        else:
            temp += item  # 合并非中文字符
    # 如果最后一个是非中文字符也要加到结果中
    if temp:
        result.append(temp)
    return result


def tokenize2stw_remove(contents: List[str], stopwords: Optional[List[str]] = None, link_char: str = '->') -> List[str]:
    """
    分词并移除停用词
    
    Args:
        contents: 文本内容列表
        stopwords: 停用词列表
        link_char: 连接字符
    
    Returns:
        处理后的文本列表
    """
    res_contents = []
    tokens = []
    for content in contents:
        tokens.append(merge_non_chinese_until_chinese(jieba.lcut(content)))
    for token in tokens:
        if stopwords is not None:
            filtered_tokens = [w for w in token if w not in stopwords and (not w.strip() == '')]
        else:
            filtered_tokens = token
        filtered_tokens = remove_duplicates_orderkept(filtered_tokens)
        res_contents.append(link_char.join(filtered_tokens))
    return res_contents

