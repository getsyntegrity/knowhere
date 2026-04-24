"""Common worker services, including reusable knowledge-base helpers."""

from shared.utils.device_utils import check_internet
from shared.utils.file_utils import clean_file, path_handle
from shared.utils.gc_utils import gc_collect as _gc
from shared.utils.math_utils import min_max_normalize
from shared.utils.text_utils import remove_duplicates_orderkept, tokenize2stw_remove

from .kb_utils import (
    count_cn_en,
    find_images,
    find_matches_parsing,
    flatten_dic2paths,
    flatten_list,
    gen_str_codes,
    get_str_time,
    html2txt,
    merge_df,
    process_dup_paths_df,
    process_path_texts,
    remove_spaces,
    restore_graph_by_paths,
    traverse_dict,
)

__all__ = [
    # From kb_utils
    "count_cn_en",
    "find_images",
    "find_matches_parsing",
    "flatten_dic2paths",
    "flatten_list",
    "gen_str_codes",
    "get_str_time",
    "html2txt",
    "merge_df",
    "process_dup_paths_df",
    "process_path_texts",
    "remove_spaces",
    "restore_graph_by_paths",
    "traverse_dict",
    # From shared-python
    "check_internet",
    "clean_file",
    "min_max_normalize",
    "path_handle",
    "remove_duplicates_orderkept",
    "tokenize2stw_remove",
    "_gc",
]
