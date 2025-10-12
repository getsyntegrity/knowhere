
from botocore.exceptions import ClientError

from app.core.config import settings
from loguru import logger


"""
S3协议文件系统相关操作，
此处只涉及文件操作，与SQL相关的记录无关。
"""

def create_folder(folder_path) -> bool:
    """
    创建文件夹，如果文件夹已存在则跳过
    :param folder_path:
    :return:
    """
    s3_client = settings.get_s3_client()
    #确保路径以'/'结尾
    folder_path = f'{settings.S3_BUCKET_NAME}/{folder_path}'
    if not folder_path.endswith('/'):
        folder_path += '/'
    try:
        s3_client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=folder_path,
            Body=b''  # 空内容
        )
        logger.debug(f"文件夹 {folder_path} 创建成功")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'EntityAlreadyExists':
            logger.warning(f"文件夹 '{folder_path}' 已存在")
            return True  # 如果已存在，也可以认为创建成功
        logger.error(f"Error 创建文件夹 '{folder_path}': {e}")
        return False
    except Exception as e:
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
    folder_path = f'{settings.S3_BUCKET_NAME}/{folder_path}'
    if not folder_path.endswith('/'):
        folder_path += '/'
    s3_client = settings.get_s3_client()
    try:
        # 1. 列出文件夹下的所有对象
        objects_to_delete = []
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=settings.S3_BUCKET_NAME, Prefix=folder_path)
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    objects_to_delete.append({'Key': obj['Key']})
                    # 这里的 Key 就是文件或伪文件夹本身
        if not objects_to_delete:
            logger.warning(f"没有这个文件夹 '{folder_path}'. ")
            return True
        response = s3_client.delete_objects(
            Bucket=settings.S3_BUCKET_NAME,
            Delete={'Objects': objects_to_delete}
        )
        if 'Errors' in response:
            logger.error(f"删除文件夹 '{folder_path}' 时出错: {response['Errors']}")
            return False
        else:
            logger.info(
                f"Folder '{folder_path}' 其内容已成功从bucket中删除 '{settings.S3_BUCKET_NAME}'. 删除 {len(objects_to_delete)} 个对象.")
            return True
    except ClientError as e:
        logger.error(f"删除文件夹时出错: '{folder_path}': {e}")
        return False
    except Exception as e:
        logger.error(f"删除文件夹时发生意外错误: {e}")
        return False

def list_files_in_folder(folder_path) -> list:
    """
    列出文件夹下的所有文件，含子文件夹
    :param folder_path:
    :return:
    """
    folder_path = f'{settings.S3_BUCKET_NAME}/{folder_path}'
    if not folder_path.endswith('/'):
        folder_path += '/'

    all_files = []
    try:
        s3_client = settings.get_s3_client()
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=settings.S3_BUCKET_NAME, Prefix=folder_path)

        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    all_files.append(obj['Key'])
        logger.info(f"从 '{settings.S3_BUCKET_NAME}'桶中列出 {len(all_files)} 文件夹中的文件: '{folder_path}' .")
        return all_files

    except ClientError as e:
        logger.error(f"列出文件夹中的文件时出错: '{folder_path}': {e}")
        return []
    except Exception as e:
        logger.error(f"列出文件夹中的文件时发生意外错误: {e}")
        return []