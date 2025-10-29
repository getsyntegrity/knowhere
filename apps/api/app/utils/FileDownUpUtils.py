import os
import uuid
import zipfile
import aiohttp
from pathlib import Path
from urllib.parse import urljoin
from typing import Optional, Union
from botocore.exceptions import ClientError
from fastapi import UploadFile, HTTPException
from app.core.config import settings
from app.models.schemas.s3_file import FliesDownload
import requests


def s3_upload_file(file: UploadFile , prefix: str ):
    """
    根据文件和文件路径上传文件到S3存储。
    :param file: 文件 abc15sa25ww.doc
    :param prefix: 文件真实路径 upload/123
    :return:
    """
    if prefix and not prefix.endswith('/'):
        prefix += '/'
    object_key = f"{prefix}{file.filename}"
    adapter = settings.get_storage_adapter()
    try:
        # 使用 upload_fileobj 可以高效地以流式方式上传，避免占用过多内存
        adapter.upload_fileobj(
            file.file,
            object_key,
            content_type="application/octet-stream"
        )
        public_url = f"{settings.S3_PRIVATE_DOMAIN}/{object_key}" if settings.S3_PRIVATE_DOMAIN else f"storage/{object_key}"
        content={
            "message": "文件上传成功",
            "bucket": settings.S3_BUCKET_NAME,
            "file_key": object_key,
            "public_url_for_reference": public_url
        }
        return content

    except Exception as e:
        # 捕获存储上传错误
        raise HTTPException(status_code=500, detail=f"存储上传失败: {e}")

def s3_download_extract_zip(url: str, dest_dir: Union[str, os.PathLike], *, filename: str = "parsed.zip", headers: Optional[dict] = None,
        timeout: int = None, chunk_size: int = None, keep_exts: tuple[str, ...] = (".md", ".json"), clean_empty_dirs: bool = True):
    from app.core.constants import APIConstants, ProcessingConstants
    
    # 使用默认值
    if timeout is None:
        timeout = APIConstants.ZIP_DOWNLOAD_TIMEOUT
    if chunk_size is None:
        chunk_size = ProcessingConstants.IMG_CHUNK_SIZE
        
    dest_dir = Path(dest_dir).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / filename

    # 1) 下载到 zip_path 并解压
    with requests.get(url, headers=headers or {}, timeout=timeout, stream=True, allow_redirects=True) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)

    # 2) 删除非 keep_exts 文件
    kept_files = []
    for p in dest_dir.rglob("*"):
        if p.is_file():
            if p.suffix.lower() in keep_exts:
                kept_files.append(p)
            else:
                p.unlink()
    # 4) 删除空目录（可选）
    if clean_empty_dirs:
        for d in sorted([p for p in dest_dir.rglob("*") if p.is_dir()],
                        key=lambda x: len(x.parts), reverse=True):
            try:
                next(d.iterdir())
            except StopIteration:
                d.rmdir()
    # 5) 删除 zip 文件
    zip_path.unlink(missing_ok=True)

def s3_get_download_url(file_key: str, expires_in: int = 3600):
    """
    根据文件路径和文件名获得文件url
    :param file_key: 文件路径与完整的文件名
    :param expires_in: 你希望的有效时间
    :return:
    """
    s3_client = settings.get_s3_client()
    try:
        # 生成预签名 URL (pre-signed URL)
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.S3_BUCKET_NAME, 'Key': file_key},
            ExpiresIn=expires_in  # URL 有效期
        )
        fsdl = FliesDownload(message="已经成功签名", file_key=file_key, download_url=presigned_url, expires_in_seconds=expires_in)
        return fsdl

    except ClientError as e:
        # 如果文件不存在，boto3 不会立即报错，但生成的链接访问时会404
        raise HTTPException(status_code=404,detail=f"无法生成URL。检查文件是否正确或S3配置是否有效: {e}")

def get_url_file(path):
    file_sig = s3_get_download_url(path, expires_in=3600)
    #组装url
    file_url = file_sig.download_url
    response = requests.get(file_url, verify=True)
    response.raise_for_status() # 确保请求成功
    return response

def get_pub_fileurl(path):
    """
    根据文件路径返回公共路径
    :param path:
    :return:
    """
    base_url = settings.S3_PRIVATE_DOMAIN.rstrip('/')
    clean_path = path.replace('\\','/').strip()
    full_url = urljoin(base_url + '/', clean_path)
    return full_url

def s3_public_file_url(file_key: str) -> str:
    permanent_url = f"{settings.S3_PRIVATE_DOMAIN}/{settings.S3_BUCKET_NAME}/{file_key}"
    return permanent_url

async def download_and_upload_image(img_url: str, prefix: str="images/", temp_store_path=None) -> dict:
    """
    下载图片，重命名后上传到S3存储，并返回新的下载链接，上传完成后自动删除本地文件
    :param img_url: 图片的URL地址
    :param prefix: S3存储的前缀路径
    :return: 包含上传结果和下载链接的字典
    """
    # 生成唯一的文件名
    unique_filename = f"{uuid.uuid4()}.jpg"
    #临时文件夹
    if temp_store_path is None:
        temp_store_path = r'/Volumes/U/temp/output/'
    local_file_path = Path(f'{settings.S3_TEMP_PATH or "/tmp"}{unique_filename}')
    # Path(f"{temp_store_path}{unique_filename}")
    try:
        # 异步下载图片
        async with aiohttp.ClientSession() as session:
            async with session.get(img_url) as response:
                response.raise_for_status()
                with open(local_file_path, "wb") as f:
                    f.write(await response.read())

        # 创建一个模拟的UploadFile对象
        from fastapi import UploadFile
        upload_file = UploadFile(filename=unique_filename, file=open(local_file_path, "rb"))

        # 上传到S3
        result = s3_upload_file(upload_file, prefix)

        # 关闭文件并删除本地文件
        upload_file.file.close()
        os.remove(local_file_path)
        return result

    except Exception as e:
        # 确保即使出错也删除本地文件
        if local_file_path.exists():
            os.remove(local_file_path)
        raise HTTPException(status_code=500, detail=f"下载并上传图片失败: {e}")
