"""Text utilities shared across services."""
import re
import warnings
from typing import List, Optional
from shared.utils.chunk_refs import CHUNK_REF_PATTERN

warnings.filterwarnings(
    "ignore",
    message=r"pkg_resources is deprecated as an API\..*",
    category=UserWarning,
    module=r"jieba\._compat",
)

import jieba


def remove_duplicates_orderkept(input_list: List) -> List:
    """
    Remove duplicates while preserving order.
    
    Args:
        input_list: Input list.
    
    Returns:
        Deduplicated list.
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
    """Count Chinese chars, English words, and numbers in one regex pass."""
    if not text:
        return 0
    return len(_CN_EN_NUM_RE.findall(str(text)))


def _is_meaningful_token(token: str) -> bool:
    """Check if a token is worth keeping: has useful characters and isn't pure noise."""
    if not _CN_EN_NUM_RE.search(token):
        return False
    # Filter single-character tokens such as one-letter units or standalone digits.
    # Keep longer English or Chinese word tokens when they carry semantic meaning.
    if len(token) == 1:
        return False
    return True


# Lazy-loaded default stopwords (module-level cache)
_DEFAULT_STOPWORDS: Optional[frozenset] = None

def _get_default_stopwords() -> frozenset:
    """Load default stopwords on first call, then return cached frozenset."""
    global _DEFAULT_STOPWORDS
    if _DEFAULT_STOPWORDS is None:
        from shared.core.constants.stopwords import DEFAULT_STOPWORDS
        _DEFAULT_STOPWORDS = DEFAULT_STOPWORDS
    return _DEFAULT_STOPWORDS


# Pre-clean: strip chunk reference markers before tokenization
_CHUNK_MARKER_RE = re.compile(
    rf'{CHUNK_REF_PATTERN}|image-\d+|table-\d+',
    re.IGNORECASE,
)

def tokenize2stw_remove(contents: List[str], stopwords: Optional[List[str]] = None, link_char: str = ';') -> List[str]:
    """
    Uses jieba for tokenization which handles both Chinese and English text natively:
    - Chinese: jieba word segmentation
    - English: space-delimited word splitting (e.g. "deep learning" → ["deep", "learning"])
    - Mixed: both handled correctly in one pass

    Args:
        stopwords: None → use built-in baidu stopwords (default);
                   []   → no stopword filtering;
                   [custom list] → use provided stopwords.
    """
    # Resolve stopwords: None → default, [] → skip, list → convert to set
    if stopwords is None:
        sw_set = _get_default_stopwords()
    elif stopwords:
        sw_set = set(stopwords)
    else:
        sw_set = None

    res_contents = []
    for content in contents:
        # Pre-clean: remove IMAGE_/TABLE_ markers and reference labels
        content = _CHUNK_MARKER_RE.sub('', content)
        if hasattr(jieba, "lcut"):
            raw_tokens = jieba.lcut(content)
        elif hasattr(jieba, "cut"):
            raw_tokens = list(jieba.cut(content))
        else:
            raw_tokens = re.split(r'[\s,;，；。！？、\-/]+', content)
        # Filter: keep only tokens with meaningful characters (Chinese/English/numbers)
        tokens = [t for t in raw_tokens if _is_meaningful_token(t)]
        # Remove stopwords
        if sw_set:
            tokens = [w for w in tokens if w not in sw_set]
        # Deduplicate while preserving order
        tokens = remove_duplicates_orderkept(tokens)
        res_contents.append(link_char.join(tokens))
    return res_contents
