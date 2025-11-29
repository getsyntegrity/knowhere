"""
用户目录服务
处理用户目录和文件的创建（Worker服务专用）
"""
import os
import shutil
from typing import List

from shared.core.config import settings
from loguru import logger


class UserDirectoryService:
    """用户目录服务类（Worker服务专用）"""

    @staticmethod
    def ensure_user_directories(kb_data_folder: str, kb_vecs_folder: str) -> None:
        """
        确保用户目录结构存在
        
        Args:
            kb_data_folder: 知识库数据文件夹
            kb_vecs_folder: 知识库向量文件夹
        """
        # 解析默认文件夹配置，处理特殊字符
        subfolders = [folder.strip() for folder in settings.DEFAULT_FOLDERS.split(",") if folder.strip()]

        # 创建主目录
        UserDirectoryService._ensure_directory_exists(kb_data_folder, "数据目录")
        UserDirectoryService._ensure_directory_exists(kb_vecs_folder, "向量目录")

        # 创建所有必需的子目录
        UserDirectoryService._create_subfolders(kb_data_folder, subfolders)

        # 复制配置文件（仅在数据目录不存在或为空时）
        if not os.path.exists(kb_data_folder) or not os.listdir(kb_data_folder):
            UserDirectoryService._copy_config_files(kb_data_folder)

        # 验证目录结构
        UserDirectoryService._validate_directory_structure(kb_data_folder, kb_vecs_folder, subfolders)

        logger.info(f"用户目录结构检查完成 - 数据目录: {kb_data_folder}, 向量目录: {kb_vecs_folder}")

    @staticmethod
    def _ensure_directory_exists(directory_path: str, directory_type: str) -> None:
        """
        确保目录存在

        Args:
            directory_path: 目录路径
            directory_type: 目录类型（用于日志）
        """
        if not os.path.exists(directory_path):
            os.makedirs(directory_path, exist_ok=True)
            logger.debug(f"创建{directory_type}: {directory_path}")
        else:
            logger.debug(f"{directory_type}已存在: {directory_path}")

    @staticmethod
    def _create_subfolders(parent_folder: str, subfolders: List[str]) -> None:
        """
        创建子目录

        Args:
            parent_folder: 父目录路径
            subfolders: 子目录名称列表
        """
        for subfolder in subfolders:
            sub_path = os.path.join(parent_folder, subfolder)
            UserDirectoryService._ensure_directory_exists(sub_path, f"子目录({subfolder})")

    @staticmethod
    def _copy_config_files(kb_data_folder: str) -> None:
        """
        复制配置文件到用户目录

        Args:
            kb_data_folder: 知识库数据文件夹
        """
        try:
            # 处理相对路径，确保从项目根目录开始
            def get_absolute_path(relative_path: str) -> str:
                if not relative_path:
                    return ""
                if os.path.isabs(relative_path):
                    return relative_path
                # 从当前文件所在目录开始计算相对路径
                current_dir = os.path.dirname(os.path.abspath(__file__))
                # 回到项目根目录 (apps/worker)
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_dir))))
                return os.path.join(project_root, relative_path)

            # 复制元数据配置文件
            if settings.META_PATH:
                meta_path = get_absolute_path(settings.META_PATH)
                if os.path.exists(meta_path):
                    dest_path = os.path.join(kb_data_folder, os.path.basename(meta_path))
                    # 如果目标文件已存在，跳过复制
                    if not os.path.exists(dest_path):
                        shutil.copy(meta_path, dest_path)
                        logger.debug(f"复制元数据配置文件到: {dest_path}")
                    else:
                        logger.debug(f"元数据配置文件已存在，跳过复制: {dest_path}")
                else:
                    logger.warning(f"元数据配置文件不存在: {meta_path}")
            else:
                logger.debug("跳过元数据配置文件复制（路径为空）")

            # 复制配置文件
            if settings.CONFIG_PATH:
                config_path = get_absolute_path(settings.CONFIG_PATH)
                if os.path.exists(config_path):
                    dest_config_path = os.path.join(kb_data_folder, 'config.txt')
                    # 如果目标文件已存在，跳过复制
                    if not os.path.exists(dest_config_path):
                        shutil.copy(config_path, dest_config_path)
                        logger.debug("复制配置文件到: config.txt")
                    else:
                        logger.debug("配置文件已存在，跳过复制: config.txt")
                else:
                    logger.warning(f"配置文件不存在: {config_path}")
            else:
                logger.debug("跳过配置文件复制（路径为空）")
        except Exception as e:
            logger.warning(f"复制配置文件失败: {str(e)}")

    @staticmethod
    def _validate_directory_structure(kb_data_folder: str, kb_vecs_folder: str, subfolders: List[str]) -> None:
        """
        验证目录结构是否完整

        Args:
            kb_data_folder: 知识库数据文件夹
            kb_vecs_folder: 知识库向量文件夹
            subfolders: 子目录名称列表
        """
        # 验证主目录
        if not os.path.exists(kb_data_folder):
            raise Exception(f"无法创建数据目录: {kb_data_folder}")
        if not os.path.exists(kb_vecs_folder):
            raise Exception(f"无法创建向量目录: {kb_vecs_folder}")

        # 验证子目录
        missing_folders = []
        for subfolder in subfolders:
            sub_path = os.path.join(kb_data_folder, subfolder)
            if not os.path.exists(sub_path):
                missing_folders.append(subfolder)

        if missing_folders:
            logger.warning(f"以下子目录创建失败: {missing_folders}")
        else:
            logger.debug("所有必需目录已成功创建")

    @staticmethod
    def ensure_directory_for_file(file_path: str) -> None:
        """
        确保文件所在目录存在
        
        Args:
            file_path: 文件路径
        """
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            logger.debug(f"创建文件目录: {directory}")

