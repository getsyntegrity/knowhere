from io import BytesIO
from pathlib import Path

import httpx
import pandas as pd
from starlette.datastructures import UploadFile as StarletteUploadFile

from shared.utils.FileDownUpUtils import s3_upload_file


def is_remote(path):
    """检查路径是否为远程URL"""
    if path is None:
        return False
    if not isinstance(path, str):
        return False
    return path.startswith("http://") or path.startswith("https://")

async def load_file_bytes(file_path, *, file_url="", timeout=None):
    if isinstance(file_path, str) and is_remote(file_path):
        # 如果 file_path 已经是完整的URL，直接使用它
        url_to_use = file_path
        if not isinstance(file_url, str):
            file_url = file_url.geturl()
        # 如果 file_url 不为空，使用 file_url；否则使用 file_path
        if file_url:
            url_to_use = file_url
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url_to_use)  # 使用正确的URL
            r.raise_for_status()
            return r.content
    else:
        p = Path(file_path)
        return p.read_bytes()

async def upload_dataframe_to_s3(df: pd.DataFrame, filename: str, prefix: str):
    # 将 DataFrame 写入内存中的 BytesIO 缓冲区
    buffer = BytesIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)  # 重置游标到起始位置

    upload_file = StarletteUploadFile(
        filename=filename,
        file=buffer,
        content_type="text/csv"
    )
    s3_upload_file(upload_file, prefix)