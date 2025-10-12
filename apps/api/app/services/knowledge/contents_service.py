
"""
处理知识库的all_contents.csv相关的业务
"""
import csv
import json

import pandas as pd
# ARQ依赖已移除，使用Celery替代
from loguru import logger


def create_json_path_list_from_csv(file_path: str, user_id:str,row_num:int):
    """
    根据标题和标书需求生产AI关于章节的思考和提纲
    生产完成后自动存档
    :param file_path: 文件路径
    :param user_id: 用户ID
    :param row_num: 读第几行，n-1，如果是第三行输入2，第五行输入4，
    :return: 格式化后的路径
    """
    try:
        all_contents_df = pd.read_csv(file_path, encoding="utf-8")
        path_list = all_contents_df['path'].tolist()
        transformed_result = transform_data_structure(path_list,user_id)
        return transformed_result
    except FileNotFoundError:
        return f"错误：文件 '{file_path}' 未找到。"
    except Exception as e:
        return f"处理文件时发生严重错误: {e}"


def transform_data_structure(data_list: list,user_id:str) -> list:
    """
    将扁平化的路径列表转换为嵌套的树状字典结构。

    Args:
        data_list: 包含路径字符串的列表。
        user_id: 用户ID

    Returns:
        一个列表，其中包含转换后的顶层节点字典。
    """
    # 使用一个字典来辅助构建树，方便快速查找节点
    tree_root = {}
    prefix_to_remove = f'.-->users-->KB_DATA_{user_id}-->'

    for item in data_list:
        # 1. 移除前缀并按 '-->' 分割路径
        clean_path = item.replace(prefix_to_remove, '')
        parts = clean_path.split('-->')

        # 从根节点开始遍历或创建节点
        current_level = tree_root
        current_path_parts = []

        for part in parts:
            # 累积当前路径，用于生成 "path" 键的值
            current_path_parts.append(part)

            # 检查当前部分是否已作为子节点存在
            # 如果不存在，则创建新的节点
            if part not in current_level:
                new_node = {
                    # 使用 "_children" 作为临时的子节点容器，避免与最终输出的 "children" 混淆
                    "_children": {},
                    # "path" 是从顶层到当前节点的完整路径
                    "path": '-->'.join(current_path_parts),
                    # "title" 是当前节点的名称
                    "title": part
                }
                current_level[part] = new_node

            # 移动到下一层级
            current_level = current_level[part]["_children"]

    # 递归函数，将我们构建的辅助树结构转换为最终需要的格式
    def convert_to_final_format(node_dict: dict) -> list:
        """将使用字典存储子节点的树转换为使用列表存储子节点的格式。"""
        result_list = []
        for key, value in node_dict.items():
            # 最终的节点结构
            final_node = {
                "path": value["path"],
                "title": value["title"],
                # 递归转换子节点
                "children": convert_to_final_format(value["_children"])
            }
            result_list.append(final_node)
        return result_list

    # 从根节点开始转换
    final_structure = convert_to_final_format(tree_root)

    return final_structure