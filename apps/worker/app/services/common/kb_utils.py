import os
import re
import uuid
from datetime import datetime
import pandas as pd
from shared.core.config import settings
from shared.utils.file_utils import path_handle
from shared.utils.chunk_refs import extract_chunk_refs
from bs4 import BeautifulSoup
from loguru import logger
from shared.core.exceptions.domain_exceptions import WorkerHandlingException, ValidationException


from shared.utils.text_utils import count_cn_en, _CN_EN_NUM_RE


SUMMARY_PATH_MARKERS: tuple[str, ...] = ("summary", "\u6458\u8981\u603b\u7ed3")


def gen_str_codes(input_string):
    """Generate a UUID5 code from a string."""
    namespace = uuid.NAMESPACE_DNS
    return str(uuid.uuid5(namespace, input_string))

def get_str_time():
    """Get the current time as a string."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

def find_images(folder_path):
    """Find image files inside a folder tree."""
    image_extensions = {'.png', '.jpg', '.jpeg'}
    image_files = []

    for _, _, files in os.walk(folder_path):
        files.sort()
        for file in files:
            if os.path.splitext(file)[1].lower() in image_extensions:
                image_files.append(file)
    return image_files

def find_matches_parsing(content, path):
    """Parse table and image markers from content."""
    matches = extract_chunk_refs(content)
    if len(matches) == 0:
        match_type = 'PTXT'
    else:
        match_type = '\n'.join((['PTXT'] + matches))
    
    split_char = settings.SPLIT_CHAR or ";"
    if any(f"{split_char}{summary_marker}" in path for summary_marker in SUMMARY_PATH_MARKERS):
        parent_path = path.split(split_char)[-2]
        match_type = ('SUMMARY_' + parent_path + '_SUMMARY')
    return match_type

def flatten_list(nested_list):
    """Flatten a nested list."""
    flat_list = []
    for item in nested_list:
        if isinstance(item, list):
            flat_list.extend(flatten_list(item))
        else:
            flat_list.append(item)
    return flat_list

def flatten_dic2paths(d, current_path=None, result=None):
    """Flatten a nested dict into path strings."""
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
    """Merge DataFrame rows that share the same path."""
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
    """Normalize path text for downstream use."""
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
        
        # Check whether this row itself needs renaming.
        new_path = path_renames.get(idx, path)
        path_parts = new_path.split(split_char)
        
        # Check whether this row is under a renamed parent path.
        for parent_path, rename_info in parent_rename_map.items():
            parent_parts = parent_path.split(split_char)
            
            # Check whether the current path starts with that parent path.
            if (len(path_parts) > len(parent_parts) and 
                path_parts[:len(parent_parts)] == parent_parts):
                
                # Find the nearest renamed parent path that appears earlier.
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
    """Remove spaces between Chinese chars while keeping English word spacing."""
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
    """Traverse a dictionary and generate description text."""
    dic_texts = []
    for key, value in d.items():
        if value:
            child_keys = ', '.join(value.keys())
            text = f"'{key}' includes {child_keys}"
            dic_texts.append(text)
            dic_texts.extend(traverse_dict(value, key))
    return dic_texts

def restore_graph_by_paths(paths):
    """Rebuild a graph structure from path strings."""
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
    """Convert HTML into plain text."""
    soup = BeautifulSoup(html_text, 'html.parser')
    text = soup.get_text()
    return text


def normalize_md(s: str) -> str:
    """Normalize markdown string for comparison
    
    Removes heading markers (###) and whitespace, converts to lowercase.
    Used for TOC keyword matching.
    """
    s = re.sub(r"^\s*#+\s*", "", s)
    s = re.sub(r"\s+", "", s)
    return s.lower()


# ---------------------------------------------------------------------------
# truncate_text (character-based) — KEPT for table-cell display callers in
# doc_parser.py and html_parser.py where a per-character limit is intentional.
# Do NOT use for heading / semantic text truncation; use truncate_text_by_tokens.
# ---------------------------------------------------------------------------
def truncate_text(text: str, start_limit: int, end_limit: int) -> str:
    """Truncate text by raw character count, keeping start and end parts.

    Intended for short display values (table headers, file names, etc.) where
    a fixed character budget is appropriate.  For heading / semantic text where
    English words must not be split mid-word, use ``truncate_text_by_tokens``.

    Args:
        text: Text to truncate.
        start_limit: Number of characters to keep from start.
        end_limit: Number of characters to keep from end (0 = no tail).

    Returns:
        Truncated text with '...' in the middle if it exceeds the limits.
    """
    text = str(text)
    total_limit = start_limit + end_limit
    if len(text) <= total_limit:
        return text
    start_part = text[:start_limit]
    end_part = text[-end_limit:] if end_limit > 0 else ''
    return f"{start_part}...{end_part}"


# ---------------------------------------------------------------------------
# Language detection & language-aware token truncation
# ---------------------------------------------------------------------------

_CN_CHAR_RE = re.compile(r'[\u4e00-\u9fff]')

EN_START_LIMIT = 15   # token budget for English-dominant headings
CN_RATIO_THRESHOLD = 0.3  # if ≥30 % of tokens are Chinese chars → "Chinese"

def detect_primary_lang(text: str) -> str:
    """Detect whether *text* is primarily Chinese or English/other.

    Uses the semantic tokens already defined by ``_CN_EN_NUM_RE``
    (Chinese chars, English word runs, number groups).  If Chinese
    characters account for at least ``CN_RATIO_THRESHOLD`` of all
    tokens the text is classified as ``'zh'``; otherwise ``'en'``.

    Args:
        text: Input text (heading or any short string).

    Returns:
        ``'zh'`` for Chinese-dominant text, ``'en'`` otherwise.
    """
    if not text:
        return 'en'
    tokens = _CN_EN_NUM_RE.findall(text)
    if not tokens:
        return 'en'
    cn_count = sum(1 for t in tokens if _CN_CHAR_RE.fullmatch(t))
    return 'zh' if (cn_count / len(tokens)) >= CN_RATIO_THRESHOLD else 'en'


def truncate_text_by_tokens(
    text: str,
    start_limit: int,
    end_limit: int,
    lang_aware: bool = True,
) -> str:
    """Truncate text by semantic token count, preserving whole words.

    Uses the same token definition as ``count_cn_en``:

    - each Chinese character  = 1 token
    - each run of English letters = 1 token
    - each number group = 1 token
    - punctuation and whitespace are excluded from the count but
      preserved in the output up to the split point.

    When *lang_aware* is ``True`` (default), the function auto-detects
    whether the text is English-dominant and caps ``start_limit`` at
    ``EN_START_LIMIT`` (15) in that case.  Chinese-dominant text keeps
    the caller-supplied ``start_limit`` (typically 30).  This prevents
    over-long English heading chunks while still allowing a generous
    budget for dense Chinese text.

    Cut points are placed *after* the last character of the start
    token and *before* the first character of the first tail token,
    so no word is ever split in the middle.

    Args:
        text: Text to truncate.
        start_limit: Max tokens to keep from the start.  When
            *lang_aware* is True and the text is English-dominant,
            this is silently capped at ``EN_START_LIMIT``.
        end_limit: Max tokens to keep from the end (0 = no tail).
        lang_aware: When True, auto-detect language and apply a tighter
            budget for English text.  Set to False to use raw limits.

    Returns:
        Truncated text with ``'...'`` in the middle when the token
        count exceeds ``start_limit + end_limit``.  Returns the
        original text unchanged when the count is within the budget.
    """
    text = str(text)
    matches = list(_CN_EN_NUM_RE.finditer(text))
    total = len(matches)

    if lang_aware and total > 0:
        lang = detect_primary_lang(text)
        if lang == 'en':
            start_limit = min(start_limit, EN_START_LIMIT)

    if total <= start_limit + end_limit:
        return text
    # Cut position: end of the start_limit-th token
    cut_start = matches[start_limit - 1].end() if start_limit > 0 else 0
    # Tail position: start of the (total - end_limit)-th token
    cut_end = matches[total - end_limit].start() if end_limit > 0 else len(text)
    if cut_start >= cut_end:
        return text
    return text[:cut_start] + '...' + text[cut_end:]
