from io import BytesIO
from pathlib import Path

import httpx
import pandas as pd
from starlette.datastructures import UploadFile as StarletteUploadFile

from shared.utils.FileDownUpUtils import s3_upload_file


def is_remote(path):
    """Check whether a path is a remote URL."""
    if path is None:
        return False
    if not isinstance(path, str):
        return False
    return path.startswith("http://") or path.startswith("https://")


async def load_file_bytes(file_path, *, file_url="", timeout=None):
    if isinstance(file_path, str) and is_remote(file_path):
        # If file_path is already a full URL, use it directly.
        url_to_use = file_path
        if not isinstance(file_url, str):
            file_url = file_url.geturl()
        # Prefer file_url when provided; otherwise keep file_path.
        if file_url:
            url_to_use = file_url
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url_to_use)  # Fetch the resolved URL.
            r.raise_for_status()
            return r.content
    else:
        p = Path(file_path)
        return p.read_bytes()


async def upload_dataframe_to_s3(df: pd.DataFrame, filename: str, prefix: str):
    # Write the DataFrame into an in-memory BytesIO buffer.
    buffer = BytesIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)  # Reset the cursor to the buffer start.

    upload_file = StarletteUploadFile(
        filename=filename, file=buffer, content_type="text/csv"
    )
    s3_upload_file(upload_file, prefix)
