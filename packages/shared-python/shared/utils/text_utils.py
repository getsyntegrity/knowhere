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


# Regex for filtering: keep Chinese chars, English words, numbers
_MEANINGFUL_TOKEN_RE = re.compile(r'[\u4e00-\u9fffA-Za-z0-9]')


def _is_meaningful_token(token: str) -> bool:
    """Check if a token contains at least one Chinese char, letter, or digit."""
    return bool(_MEANINGFUL_TOKEN_RE.search(token))


def tokenize2stw_remove(contents: List[str], stopwords: Optional[List[str]] = None, link_char: str = '->') -> List[str]:
    """
    分词并移除停用词。
    
    Uses jieba for tokenization which handles both Chinese and English text natively:
    - Chinese: jieba word segmentation (e.g. "项目成本" → ["项目", "成本"])
    - English: space-delimited word splitting (e.g. "deep learning" → ["deep", "learning"])
    - Mixed: both handled correctly in one pass
    
    Args:
        contents: 文本内容列表
        stopwords: 停用词列表
        link_char: 连接字符
    
    Returns:
        处理后的文本列表
    """
    res_contents = []
    for content in contents:
        raw_tokens = jieba.lcut(content)
        # Filter: keep only tokens with meaningful characters (Chinese/English/numbers)
        tokens = [t for t in raw_tokens if _is_meaningful_token(t)]
        # Remove stopwords
        if stopwords:
            tokens = [w for w in tokens if w not in stopwords]
        # Deduplicate while preserving order
        tokens = remove_duplicates_orderkept(tokens)
        res_contents.append(link_char.join(tokens))
    return res_contents


# ── Deprecated ────────────────────────────────────────────────────────────────
# Kept for backward compatibility. No longer called by tokenize2stw_remove.

def merge_non_chinese_until_chinese(lst: List[str]) -> List[str]:
    """
    合并非中文字符直到遇到中文字符

    .. deprecated::
        This function is no longer used by tokenize2stw_remove().
        jieba handles mixed CJK/English text natively; no manual merging needed.
    """
    lst = [item for item in lst if item.strip()]
    result = []
    temp = ""
    for item in lst:
        if re.search(r'[\u4e00-\u9fff]', item):
            if temp:
                result.append(temp)
                temp = ""
            result.append(item)
        else:
            temp += item
    if temp:
        result.append(temp)
    return result
