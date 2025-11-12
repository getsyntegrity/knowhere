import io
import os
from urllib.parse import urlparse

import pandas as pd
import requests

from shared.core.config import settings


class UrlFileReader:
    """
    一个从 URL 读取并解析多种文件类型的工具类。
    支持的格式: .txt, .csv, .xlsx, .docx
    """

    def __init__(self, url: str):
        """
        初始化读取器。
        :param url: 文件的完整 URL。
        """
        if not url:
            raise ValueError("URL 不能为空")
        self.url = url
        self.file_type = self._get_file_type()

        self._readers = {
            '.txt': self._read_text,
            '.csv': self._read_csv,
            '.xlsx': self._read_excel
        }

    def _get_file_type(self) -> str:
        """从 URL 中解析文件扩展名，作为文件类型。"""
        path = urlparse(self.url).path
        # 分离路径和扩展名
        _, ext = os.path.splitext(path)
        return ext.lower()

    def _fetch_content(self) -> bytes:
        """从 URL 获取原始的二进制内容。"""
        try:
            from shared.core.constants import APIConstants
            response = requests.get(self.url, timeout=APIConstants.HTTP_TIMEOUT)
            response.raise_for_status()
            # 返回二进制内容，因为 Excel 和 Docx 是二进制文件
            return response.content
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"从 URL 获取内容失败: {e}") from e

    def _read_text(self, content: bytes):
        """以utf8读取并返回纯文本内容。"""
        return content.decode('utf-8')

    def _read_csv(self, content: bytes):
        """读取 CSV 文件并返回一个 pandas DataFrame。"""
        # io.BytesIO 将内存中的 bytes 模拟成一个二进制文件
        file_like_object = io.BytesIO(content)
        return pd.read_csv(file_like_object)

    def _read_excel(self, content: bytes):
        """读取 Excel (.xlsx) 文件并返回一个 pandas DataFrame。"""
        # 默认读取第一个 sheet
        file_like_object = io.BytesIO(content)
        return pd.read_excel(file_like_object, engine='openpyxl')



    def read(self):
        """
        主读取方法。根据文件类型选择合适的解析器。
        :return: 解析后的文件内容 (str, pandas.DataFrame, etc.)
        """
        if self.file_type not in self._readers:
            raise ValueError(f"不支持的文件类型: '{self.file_type}'. "
                             f"支持的类型: {list(self._readers.keys())}")

        # 1. 获取文件内容
        content_bytes = self._fetch_content()

        # 2. 根据文件类型调用对应的读取方法
        reader_func = self._readers[self.file_type]
        return reader_func(content_bytes)


# --- 使用示例 ---

if __name__ == 'aaaa':
    # 示例1：读取你提供的 CSV 文件 (这是一个预签名URL，有有效期)
    csv_url = settings.S3_PRIVATE_DOMAIN + "/uses/KB_DATA_user_id/Meta_setting.csv"
    print("--- 1. 正在读取 CSV 文件 ---")
    try:
        reader = UrlFileReader(csv_url)
        csv_data = reader.read()
        print("CSV 文件读取成功，类型为:", type(csv_data))
        print("内容预览:")
        print(csv_data.head())
    except (ValueError, ConnectionError) as e:
        print(f"错误: {e}")
    print("-" * 20)

    # 示例2：读取一个在线的 TXT 文件
    txt_url = "https://aaaaaaaaaaaaaaaaaaaa.txt"
    print("--- 2. 正在读取 TXT 文件 ---")
    try:
        reader = UrlFileReader(txt_url)
        text_content = reader.read()
        print("TXT 文件读取成功，类型为:", type(text_content))
        print("内容预览 (前 300 字符):")
        print(text_content[:300])
    except (ValueError, ConnectionError) as e:
        print(f"错误: {e}")
    print("-" * 20)

    excel_url = "https:/aaaaaaaaaaaaa.xlsx"
    print("--- 3. 正在读取 Excel 文件 ---")
    try:
        reader = UrlFileReader(excel_url)
        excel_data = reader.read()
        print("Excel 文件读取成功，类型为:", type(excel_data))
        print("内容预览:")
        print(excel_data.head())
    except (ValueError, ConnectionError) as e:
        print(f"错误: {e}")
    print("-" * 20)
