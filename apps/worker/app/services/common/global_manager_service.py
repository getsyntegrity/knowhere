import threading
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd
from shared.core.exceptions.domain_exceptions import WorkerHandlingException


class GlobalDataFrameManager:
    """
    用于全局管理用户相关的 DataFrame 数据。
    支持添加、更新、获取、删除以及清空操作，线程安全。
    """
    def __init__(self):
        self._user_dataframes: Dict[str, pd.DataFrame] = {}
        self._lock = threading.Lock()
        print("GlobalDataFrameManager initialized.")

    def add_or_update_dataframe(self, user_id: str, df: pd.DataFrame):
        """
        添加或更新用户的 DataFrame 数据。
        """
        if not isinstance(df, pd.DataFrame):
            raise WorkerHandlingException(
                internal_message=f"Provided data is not a DataFrame for user '{user_id}'. Received: {type(df)}. Must be a pandas DataFrame."
            )

        if df.empty:
            print(f"Warning: Provided DataFrame for user '{user_id}' is empty. Not added.")
            return

        with self._lock:
            self._user_dataframes[user_id] = df.copy()
            # print(f"DataFrame added/updated for user '{user_id}'.")

    def get_dataframe(self, user_id: str) -> Optional[pd.DataFrame]:
        """
        获取指定用户的 DataFrame。若不存在则返回 None。
        """
        with self._lock:
            df = self._user_dataframes.get(user_id)
            return df.copy() if df is not None else None

    def remove_dataframe(self, user_id: str):
        """
        删除指定用户的 DataFrame。
        """
        with self._lock:
            if user_id in self._user_dataframes:
                del self._user_dataframes[user_id]
                # print(f"DataFrame removed for user '{user_id}'.")

    def clear_all_dataframe(self):
        """
        清空所有 DataFrame 数据。
        """
        with self._lock:
            self._user_dataframes.clear()
            print("All DataFrames cleared.")


# 定义存储AI向量的类型，可以是列表或NumPy数组
AIVector = Union[List[float], np.ndarray]
class GlobalVectorManager:
    def __init__(self):
        self._user_ai_vectors: Dict[str, AIVector] = {}
        self._lock = threading.Lock()  # 用于保护 _user_ai_vectors 字典的锁
        print("AIVectorManager initialized.")

    def add_or_update_vector(self, user_id: str, vector: AIVector):
        """
        根据user_id和提供的AI向量数据添加或更新向量。
        向量可以是List[float]或np.ndarray。
        """
        is_empty = False
        if isinstance(vector, list):
            if not vector: # 检查列表是否为空
                is_empty = True
        elif isinstance(vector, np.ndarray):
            if vector.size == 0: # 检查NumPy数组是否为空（元素数量为0）
                is_empty = True
        else:
            # 如果传入的不是我们预期的List或ndarray类型，可以抛出错误或记录警告
            raise WorkerHandlingException(
                 internal_message=f"Unsupported vector type for user '{user_id}': {type(vector)}. Expected List[float] or np.ndarray."
            )

        if is_empty:
            print(f"Warning: Provided vector for user '{user_id}' is empty. Vector not added.")
            return
        # 传入的 `vector` 参数就是我们要存储的AI向量数据，
        # 所以直接赋值即可。如果希望内部统一存储为np.ndarray，可以进行转换。
        if isinstance(vector, list):
            vector_to_store = np.array(vector) # 统一转换为NumPy数组存储
        else:
            vector_to_store = vector # 已经是NumPy数组

        with self._lock:
            self._user_ai_vectors[user_id] = vector_to_store
            # print(f"Added/Updated vector for user '{user_id}'. Current size: {len(self._user_ai_vectors)}")

    def get_vector(self, user_id: str) -> AIVector | None:
        """
        获取指定user_id的AI向量。
        """
        with self._lock:
            return self._user_ai_vectors.get(user_id)

    def remove_vector(self, user_id: str):
        """
        移除指定user_id的AI向量。
        """
        with self._lock:
            if user_id in self._user_ai_vectors:
                del self._user_ai_vectors[user_id]
                # print(f"Removed vector for user '{user_id}'. Current size: {len(self._user_ai_vectors)}")

    def clear_all_vectors(self):
        """
        清空所有存储的向量。
        """
        with self._lock:
            self._user_ai_vectors.clear()
            print("All AI vectors cleared.")

class GlobalDictManager:
    """
    用于全局管理用户相关的字典数据（key-value）。
    支持添加、更新、获取、删除以及清空操作，线程安全。
    """
    def __init__(self):
        self._user_dicts: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        print("GlobalDictManager initialized.")

    def add_or_update_dict(self, user_id: str, data: Dict[str, Any]):
        """
        添加或更新指定用户的字典数据。
        """
        if not isinstance(data, dict):
            raise WorkerHandlingException(
                internal_message=f"Provided data is not a dictionary for user '{user_id}'. Received: {type(data)}. Must be a dictionary."
            )

        if not data:
            print(f"Warning: Provided dictionary for user '{user_id}' is empty. Not added.")
            return

        with self._lock:
            self._user_dicts[user_id] = data.copy()
            # print(f"Dictionary added/updated for user '{user_id}'.")

    def get_dict(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定用户的字典数据，若不存在则返回 None。
        """
        with self._lock:
            data = self._user_dicts.get(user_id)
            return data.copy() if data is not None else None

    def remove_dict(self, user_id: str):
        """
        删除指定用户的字典数据。
        """
        with self._lock:
            if user_id in self._user_dicts:
                del self._user_dicts[user_id]
                # print(f"Dictionary removed for user '{user_id}'.")

    def clear_all_dicts(self):
        """
        清空所有字典数据。
        """
        with self._lock:
            self._user_dicts.clear()
            print("All dictionaries cleared.")

global_vector_manager = GlobalVectorManager()
global_df_manager = GlobalDataFrameManager()
global_dict_manager = GlobalDictManager()