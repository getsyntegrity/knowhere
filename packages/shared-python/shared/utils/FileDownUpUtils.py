import os
import uuid
import zipfile
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urljoin

import aiohttp
import requests
from botocore.exceptions import ClientError
from fastapi import UploadFile

from shared.core.config import settings
from shared.core.config.storage import get_cached_storage_adapter
from shared.core.exceptions.domain_exceptions import StorageServiceException, NotFoundException, KnowhereException
from shared.models.schemas.s3_file import FliesDownload


def s3_upload_file(file: UploadFile , prefix: str ):
    """
    Upload a file object to S3 storage.
    :param file: Input file such as ``abc15sa25ww.doc``
    :param prefix: Storage prefix such as ``upload/123``
    :return: Upload result payload
    """
    if prefix and not prefix.endswith('/'):
        prefix += '/'
    object_key = f"{prefix}{file.filename}"
    adapter = get_cached_storage_adapter()
    try:
        # ``upload_fileobj`` streams efficiently and avoids large in-memory copies.
        adapter.upload_fileobj(
            file.file,
            object_key,
            content_type="application/octet-stream"
        )
        public_url = f"{settings.S3_PRIVATE_DOMAIN}/{object_key}" if settings.S3_PRIVATE_DOMAIN else f"storage/{object_key}"
        content={
            "message": "File uploaded successfully",
            "bucket": settings.S3_BUCKET_NAME,
            "file_key": object_key,
            "public_url_for_reference": public_url
        }
        return content

    except KnowhereException:
        raise
    except Exception as e:
        # Wrap storage upload failures in a domain exception.
        raise StorageServiceException(
            internal_message=f"Storage upload failed: {str(e)}",
            operation="upload",
            original_exception=e
        )

def s3_download_extract_zip(url: str, dest_dir: Union[str, os.PathLike], *, filename: str = "parsed.zip", headers: Optional[dict] = None,
        timeout: int = None, chunk_size: int = None, keep_exts: tuple[str, ...] = (".md", ".json"), 
        exclude_patterns: tuple[str, ...] = (), clean_empty_dirs: bool = True):
    """
    Download and extract a zip file, keeping only specific file types.
    
    Args:
        exclude_patterns: Tuple of filename patterns to exclude (e.g., ("content_list", "middle.json"))
    """
    from shared.core.constants import APIConstants, ProcessingConstants
    import fnmatch

    # Use defaults when optional arguments are omitted.
    if timeout is None:
        timeout = APIConstants.S3_FILE_DOWNLOAD_TIMEOUT
    if chunk_size is None:
        chunk_size = ProcessingConstants.IMG_CHUNK_SIZE
        
    dest_dir = Path(dest_dir).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / filename

    # 1) Download to zip_path and extract.
    with requests.get(url, headers=headers or {}, timeout=timeout, stream=True, allow_redirects=True) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)

    # 2) Remove files outside keep_exts or matching exclude_patterns.
    kept_files = []
    for p in dest_dir.rglob("*"):
        if p.is_file():
            # Check if file should be excluded by pattern
            should_exclude = False
            for pattern in exclude_patterns:
                if pattern in p.name or fnmatch.fnmatch(p.name, pattern):
                    should_exclude = True
                    break
            
            if should_exclude:
                p.unlink()
            elif p.suffix.lower() in keep_exts:
                kept_files.append(p)
            else:
                p.unlink()
    
    # 4) Remove empty directories when requested.
    if clean_empty_dirs:
        for d in sorted([p for p in dest_dir.rglob("*") if p.is_dir()],
                        key=lambda x: len(x.parts), reverse=True):
            try:
                next(d.iterdir())
            except StopIteration:
                d.rmdir()
    # 5) Delete the downloaded zip file.
    zip_path.unlink(missing_ok=True)

def s3_get_download_url(file_key: str, expires_in: int = 3600):
    """
    Get a file download URL from its storage key.
    :param file_key: Full file path and name
    :param expires_in: Desired URL lifetime
    :return: Signed download payload
    """
    s3_client = settings.get_s3_client()
    try:
        # Generate a pre-signed URL.
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.S3_BUCKET_NAME, 'Key': file_key},
            ExpiresIn=expires_in  # URL lifetime.
        )
        fsdl = FliesDownload(
            message="URL signed successfully",
            file_key=file_key,
            download_url=presigned_url,
            expires_in_seconds=expires_in,
        )
        return fsdl

    except ClientError as e:
        # boto3 may still sign missing objects; the resulting URL can later 404.
        raise NotFoundException(
            resource="File",
            resource_id=file_key,
            internal_message=(
                f"Could not generate the URL. Check whether the file is correct "
                f"or the S3 configuration is valid: {str(e)}"
            )
        )

def get_url_file(path):
    file_sig = s3_get_download_url(path, expires_in=3600)
    # Assemble the final URL.
    file_url = file_sig.download_url
    response = requests.get(file_url, verify=True)
    response.raise_for_status() # Ensure the request succeeds.
    return response

def get_pub_fileurl(path):
    """
    Build a public URL from a storage path.
    :param path:
    :return: Public URL
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
    Download an image, rename it, upload it to S3, and clean up locally.
    :param img_url: Image URL
    :param prefix: S3 storage prefix
    :return: Dict containing upload results and the new download reference
    """
    # Generate a unique filename.
    unique_filename = f"{uuid.uuid4()}.jpg"
    # Temporary directory.
    if temp_store_path is None:
        temp_store_path = r'/Volumes/U/temp/output/'
    local_file_path = Path(f'{settings.S3_TEMP_PATH or "/tmp"}{unique_filename}')
    # Path(f"{temp_store_path}{unique_filename}")
    try:
        # Download the image asynchronously.
        async with aiohttp.ClientSession() as session:
            async with session.get(img_url) as response:
                response.raise_for_status()
                with open(local_file_path, "wb") as f:
                    f.write(await response.read())

        # Create a temporary UploadFile wrapper.
        from fastapi import UploadFile
        upload_file = UploadFile(filename=unique_filename, file=open(local_file_path, "rb"))

        # Upload to S3.
        result = s3_upload_file(upload_file, prefix)

        # Close the file handle and delete the local file.
        upload_file.file.close()
        os.remove(local_file_path)
        return result

    except KnowhereException:
        if local_file_path.exists():
            os.remove(local_file_path)
        raise
    except Exception as e:
        # Always remove the local file on failure as well.
        if local_file_path.exists():
            os.remove(local_file_path)
        raise StorageServiceException(
            internal_message=f"Failed to download and upload the image: {str(e)}",
            operation="download_and_upload",
            original_exception=e
        )
