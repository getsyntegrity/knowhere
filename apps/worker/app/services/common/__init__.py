"""
通用服务模块
包含知识库工具函数等通用服务
"""

from app.utils.device_utils import check_internet
from app.utils.file_utils import clean_file, path_handle
from app.utils.gc_utils import gc_collect as _gc
# 以下函数已移到 shared-python，从 utils 导入
from app.utils.llm_utils import use_llm_api
from app.utils.math_utils import min_max_normalize
from app.utils.text_utils import (merge_non_chinese_until_chinese,
                                  remove_duplicates_orderkept,
                                  tokenize2stw_remove)

from .kb_utils import (build_tree_from_paths, cal_levenshtein_dis,
                       clean_contents, count_cn_en, create_reply,
                       expand_summary_paths, extract_keylevels, extract_know,
                       extract_nested_dic_vals, extract_window, file_lst,
                       find_frequent, find_images, find_matches_parsing,
                       find_similar_bychars, flatten_dic2paths, flatten_dict,
                       flatten_list, gen_sim_matrix, gen_str_codes,
                       get_node_level, get_str_time, html2txt, merge_df,
                       process_dup_paths_df, process_path_texts, remove_spaces,
                       restore_graph_by_paths, set_bottom_dic_val,
                       split_path_by_node, text_list2md, traverse_dict,
                       truncate_paths, unify_key)

__all__ = [
    "use_llm_api",
    "build_tree_from_paths",
    "count_cn_en",
    "clean_contents",
    "check_internet",
    "_gc",
    "get_node_level",
    "gen_str_codes",
    "get_str_time",
    "cal_levenshtein_dis",
    "clean_file",
    "create_reply",
    "unify_key",
    "expand_summary_paths",
    "extract_nested_dic_vals",
    "extract_know",
    "extract_window",
    "extract_keylevels",
    "file_lst",
    "find_frequent",
    "find_images",
    "find_similar_bychars",
    "find_matches_parsing",
    "flatten_list",
    "flatten_dict",
    "flatten_dic2paths",
    "gen_sim_matrix",
    "merge_df",
    "text_list2md",
    "min_max_normalize",
    "path_handle",
    "process_path_texts",
    "process_dup_paths_df",
    "remove_duplicates_orderkept",
    "remove_spaces",
    "restore_graph_by_paths",
    "set_bottom_dic_val",
    "split_path_by_node",
    "traverse_dict",
    "truncate_paths",
    "merge_non_chinese_until_chinese",
    "tokenize2stw_remove",
    "html2txt",
]

