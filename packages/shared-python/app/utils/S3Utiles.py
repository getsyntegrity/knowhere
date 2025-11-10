
from app.core.config import settings
from loguru import logger


"""
S3协议文件系统相关操作，
此处只涉及文件操作，与SQL相关的记录无关。
支持S3、OSS和MinIO的统一操作接口。
"""

def create_folder(folder_path) -> bool:
    """
    创建文件夹，如果文件夹已存在则跳过
    :param folder_path:
    :return:
    """
    adapter = settings.get_storage_adapter()
    # 确保路径以'/'结尾
    if not folder_path.endswith('/'):
        folder_path += '/'
    try:
        # 通过上传空对象来创建文件夹
        from io import BytesIO
        adapter.upload_fileobj(
            BytesIO(b''),
            folder_path,
            content_type='application/x-directory'
        )
        logger.debug(f"文件夹 {folder_path} 创建成功")
        return True
    except Exception as e:
        # 如果文件夹已存在，仍然认为成功
        if 'exists' in str(e).lower() or 'already' in str(e).lower():
            logger.debug(f"文件夹 '{folder_path}' 已存在")
            return True
        logger.error(f"创建文件夹 '{folder_path}' 时出错: {e}")
        return False


def delete_folder(folder_path) -> bool:
    """
    删除文件夹，默认删除文件夹下的所有文件
    1、列出文件夹下的所有文件
    2、删除所有文件
    3、删除文件夹
    :param folder_path:
    :return:
    """
    if not folder_path.endswith('/'):
        folder_path += '/'
    
    adapter = settings.get_storage_adapter()
    try:
        # 1. 列出文件夹下的所有对象
        objects_to_delete = list(adapter.list_objects(prefix=folder_path))
        
        if not objects_to_delete:
            logger.warning(f"没有这个文件夹 '{folder_path}'. ")
            return True
        
        # 2. 删除所有对象
        for obj_key in objects_to_delete:
            adapter.delete_object(obj_key)
        
        logger.info(
            f"Folder '{folder_path}' 其内容已成功从bucket中删除 '{settings.S3_BUCKET_NAME}'. 删除 {len(objects_to_delete)} 个对象.")
        return True
    except Exception as e:
        logger.error(f"删除文件夹时发生意外错误: '{folder_path}': {e}")
        return False


def list_files_in_folder(folder_path) -> list:
    """
    列出文件夹下的所有文件，含子文件夹
    :param folder_path:
    :return:
    """
    if not folder_path.endswith('/'):
        folder_path += '/'

    all_files = []
    try:
        adapter = settings.get_storage_adapter()
        
        for obj_key in adapter.list_objects(prefix=folder_path):
            all_files.append(obj_key)
            
        logger.info(f"从 '{settings.S3_BUCKET_NAME}'桶中列出 {len(all_files)} 文件夹中的文件: '{folder_path}' .")
        return all_files

    except Exception as e:
        logger.error(f"列出文件夹中的文件时发生意外错误: '{folder_path}': {e}")
        return []
