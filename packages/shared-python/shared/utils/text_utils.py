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


# Single regex for Chinese chars, English words, and number groups
_CN_EN_NUM_RE = re.compile(r'[\u4e00-\u9fff]|[A-Za-z]+|\d+(?:\.\d+)?')

def count_cn_en(text: str) -> int:
    """统计中英文单词和数字的数量（单次正则扫描）"""
    if not text:
        return 0
    return len(_CN_EN_NUM_RE.findall(str(text)))


def _is_meaningful_token(token: str) -> bool:
    """Check if a token contains at least one Chinese char, letter, or digit."""
    return bool(_CN_EN_NUM_RE.search(token))


# Pre-clean: strip chunk reference markers before tokenization
_CHUNK_MARKER_RE = re.compile(
    r'IMAGE_\S+_IMAGE|TABLE_\S+_TABLE|image-\d+|table-\d+',
    re.IGNORECASE,
)

def tokenize2stw_remove(contents: List[str], stopwords: Optional[List[str]] = None, link_char: str = ';') -> List[str]:
    """
    Uses jieba for tokenization which handles both Chinese and English text natively:
    - Chinese: jieba word segmentation
    - English: space-delimited word splitting (e.g. "deep learning" → ["deep", "learning"])
    - Mixed: both handled correctly in one pass
    """
    res_contents = []
    for content in contents:
        # Pre-clean: remove IMAGE_/TABLE_ markers and reference labels
        content = _CHUNK_MARKER_RE.sub('', content)
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

