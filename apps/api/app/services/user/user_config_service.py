"""
用户配置服务
处理用户配置相关的业务逻辑
"""
import os
import json
import shutil
import pandas as pd
import math
from typing import Dict, Any, Optional
from loguru import logger

from app.core.config import settings
from app.services.common.kb_utils import clean_file, path_handle
from app.services.common.model_service import ModelService


class UserConfigService:
    """用户配置服务类"""
    
    @staticmethod
    def init_user(user_id: str, root_dir: str = 'users') -> str:
        """
        初始化用户配置
        
        Args:
            user_id: 用户ID
            root_dir: 根目录
            
        Returns:
            用户配置的JSON字符串
        """
        logger.info(f"初始化用户配置: {user_id}")
        
        basic_user_info = {
            "user": user_id,
            "parent": os.path.join(".", root_dir),
            "kb_term": settings.KB_TERM,
            "kb_vec_term": settings.KB_VEC_TERM
        }
        
        user_info = UserConfigService.run_settings(basic_user_info)
        return json.dumps(user_info)
    
    @staticmethod
    def check_create_user(kb_data_folder: str, kb_vecs_folder: str) -> None:
        """
        检查并创建用户目录结构
        
        Args:
            kb_data_folder: 知识库数据文件夹
            kb_vecs_folder: 知识库向量文件夹
        """
        # 解析默认文件夹配置，处理特殊字符
        subfolders = [folder.strip() for folder in settings.DEFAULT_FOLDERS.split(",") if folder.strip()]
        
        # 创建主目录
        UserConfigService._ensure_directory_exists(kb_data_folder, "数据目录")
        UserConfigService._ensure_directory_exists(kb_vecs_folder, "向量目录")
        
        # 创建所有必需的子目录
        UserConfigService._create_subfolders(kb_data_folder, subfolders)
        
        # 复制配置文件（仅在数据目录不存在时）
        if not os.path.exists(kb_data_folder) or not os.listdir(kb_data_folder):
            UserConfigService._copy_config_files(kb_data_folder)
        
        # 验证目录结构
        UserConfigService._validate_directory_structure(kb_data_folder, kb_vecs_folder, subfolders)
        
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
    def _create_subfolders(parent_folder: str, subfolders: list) -> None:
        """
        创建子目录
        
        Args:
            parent_folder: 父目录路径
            subfolders: 子目录名称列表
        """
        for subfolder in subfolders:
            sub_path = os.path.join(parent_folder, subfolder)
            UserConfigService._ensure_directory_exists(sub_path, f"子目录({subfolder})")
    
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
                # 回到项目根目录 (apps/api)
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
                return os.path.join(project_root, relative_path)
            
            # 复制元数据配置文件
            if settings.META_PATH:
                meta_path = get_absolute_path(settings.META_PATH)
                if os.path.exists(meta_path):
                    dest_path = os.path.join(kb_data_folder, os.path.basename(meta_path))
                    shutil.copy(meta_path, dest_path)
                    logger.debug(f"复制元数据配置文件到: {dest_path}")
                else:
                    logger.warning(f"元数据配置文件不存在: {meta_path}")
            else:
                logger.debug("跳过元数据配置文件复制（路径为空）")
            
            # 复制配置文件
            if settings.CONFIG_PATH:
                config_path = get_absolute_path(settings.CONFIG_PATH)
                if os.path.exists(config_path):
                    shutil.copy(config_path, os.path.join(kb_data_folder, 'config.txt'))
                    logger.debug("复制配置文件到: config.txt")
                else:   
                    logger.warning(f"配置文件不存在: {config_path}")
            else:
                logger.debug("跳过配置文件复制（路径为空）")
        except Exception as e:
            logger.warning(f"复制配置文件失败: {str(e)}")
    
    @staticmethod
    def _validate_directory_structure(kb_data_folder: str, kb_vecs_folder: str, subfolders: list) -> None:
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
    def load_meta_settings(user_info: Dict[str, Any], split_char: str = ';') -> Dict[str, Any]:
        """
        加载元数据设置（完整版本，包含所有配置项）
        
        Args:
            user_info: 用户信息字典
            split_char: 分隔符
            
        Returns:
            更新后的用户信息字典
        """
        meta_path = os.path.join(user_info['KB_PATH'], "Meta_setting.csv")
        
        # 读取CSV文件
        try:
            if os.path.exists(meta_path):
                meta_df = pd.read_csv(meta_path, encoding='gbk')
                meta_dic = {}
                for _, row in meta_df.iterrows():
                    key = row['variable']
                    val = row['value']
                    if isinstance(val, float) and math.isnan(val):
                        continue
                    if ';' in val:
                        val = val.split(split_char)
                    elif 'TRUE' in val:
                        val = True
                    elif 'FALSE' in val:
                        val = False
                    elif 'COLOR' in key:
                        val = tuple(int(v) for v in val)
                    else:
                        pass
                    meta_dic.update({key: val})
            else:
                # 如果文件不存在，使用默认配置
                meta_dic = UserConfigService._get_default_meta_settings()
        except Exception as e:
            logger.warning(f"加载元数据设置失败: {str(e)}")
            meta_dic = UserConfigService._get_default_meta_settings()
        
        # 处理数值类型转换
        meta_dic['ROOT_LEN'] = len(path_handle(user_info['KB_PATH'], 'split'))
        meta_dic['TOP_K'] = int(meta_dic.get('TOP_K', 5))
        meta_dic['N_TRIGGER'] = int(meta_dic.get('N_TRIGGER', 10))
        meta_dic['BATCH_SIZE'] = int(meta_dic.get('BATCH_SIZE', 32))
        meta_dic['N_EPOCHS'] = int(meta_dic.get('N_EPOCHS', 3))
        meta_dic['CLLM_THRESHOLD'] = int(meta_dic.get('CLLM_THRESHOLD', 0))
        meta_dic['REWRITE_THRESHOLD'] = int(meta_dic.get('REWRITE_THRESHOLD', 0))
        meta_dic['SIZE'] = int(meta_dic.get('SIZE', 1000))
        meta_dic['TABLE_SIZE'] = int(meta_dic.get('TABLE_SIZE', 100))
        meta_dic['THRESHOLD'] = float(meta_dic.get('THRESHOLD', 0.5))
        meta_dic['SUMMARY_THRESHOLD'] = float(meta_dic.get('SUMMARY_THRESHOLD', 0.5))
        meta_dic['L_RATE'] = float(meta_dic.get('L_RATE', 0.001))
        meta_dic['OCR_TIMEOUT'] = float(meta_dic.get('OCR_TIMEOUT', 30.0))
        
        # 检查GPU和网络
        device_info = ModelService.check_device_capabilities()
        if not device_info['has_internet']:
            meta_dic['USE_LOCAL_LLM'] = True
        meta_dic['device'] = device_info['device']
        
        if meta_dic['device'] == "cpu":
            meta_dic['USE_LOCAL_LLM'] = False
            meta_dic['LOCAL_SUMMARY'] = False
        
        meta_dic['API_NAME'] = "ds_api"  # 默认调用deepseek
        meta_dic['llm_histories'] = []
        meta_dic['train_multiplier'] = 1
        
        # 加载配置文件
        config_path = os.path.join(user_info['KB_PATH'], "config.txt")
        model_config = {}
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                text_content = f.read()
            
            lines = text_content.split("\n")
            for current_line in lines:
                if '\t' in current_line:
                    key, value = current_line.split('\t')
                    model_config[key.strip()] = value.strip()
            
            if 'HISTORY_K' in model_config:
                model_config['HISTORY_K'] = int(model_config['HISTORY_K'])
        except Exception as e:
            logger.warning(f"加载配置文件失败: {str(e)}")
        
        user_info['USER_SETTINGS'] = meta_dic
        user_info['model_config'] = model_config
        return user_info
    
    @staticmethod
    def _get_default_meta_settings() -> Dict[str, Any]:
        """获取默认元数据设置"""
        from app.core.constants import BusinessConstants
        return BusinessConstants.USER_DEFAULT_CONFIG.copy()
    
    @staticmethod
    def run_settings(user_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        运行用户设置初始化
        
        Args:
            user_info: 基础用户信息
            
        Returns:
            完整的用户信息字典
        """
        # 确保 user 字段是字符串，处理可能的 UUID 对象
        user_info['user'] = str(user_info['user'])
        
        logger.info(f"初始化用户设置: {user_info['user']}")
        
        user_info['KB'] = f"{user_info['kb_term']}_{user_info['user']}"
        user_info['KB_PATH'] = os.path.join(user_info['parent'], user_info['KB'])
        user_info['KB_VECS_PATH'] = os.path.join(
            user_info['parent'], 
            (user_info['kb_vec_term'] + "_" + user_info['user'])
        )
        
        UserConfigService.check_create_user(user_info['KB_PATH'], user_info['KB_VECS_PATH'])
        logger.info("创建或分析基础路径完成")
        
        user_info = UserConfigService.load_meta_settings(user_info)
        
        # 设置各种路径 - 使用统一的路径映射
        path_mapping = {
            'SUPP_FILE_PATH': 'Supplementary_Files',
            'TEMP_FILE_PATH': 'Temporary_Files', 
            'TEMPLATE_DIR': 'templates',
            'RAW_IMG_DIR': 'images',
            'FRAGMENT_DIR': 'fragments',
            'DEFAULT_DIR': '默认目录'  # 直接使用原始名称
        }
        
        for setting_key, folder_name in path_mapping.items():
            user_info['USER_SETTINGS'][setting_key] = os.path.join(
                user_info['KB_PATH'], folder_name
            )
        user_info['USER_SETTINGS']['MATCH_DF'] = os.path.join(
            user_info['KB_VECS_PATH'], 'temp_match_df.csv'
        )
        user_info['USER_SETTINGS']['KB_VEC_PATH'] = os.path.join(
            user_info['KB_VECS_PATH'], 'all_vec.npy'
        )
        user_info['USER_SETTINGS']['KB_PATH_VEC_PATH'] = os.path.join(
            user_info['KB_VECS_PATH'], 'all_path_vec.npy'
        )
        user_info['USER_SETTINGS']['KB_CONTENT_PATH'] = os.path.join(
            user_info['KB_VECS_PATH'], 'all_contents.csv'
        )
        user_info['USER_SETTINGS']['RESOURCE_PATH'] = os.path.join(
            user_info['KB_VECS_PATH'], 'resources.json'
        )
        user_info['USER_SETTINGS']['LLM_QA_OUT_LIMIT'] = 50
        user_info['USER_SETTINGS']['PATHS_IGNORE'] = ['Temporary_Files', 'Temporary Files']
        
        # 设置更多路径
        user_info['USER_SETTINGS']['CORPUS'] = os.path.join(
            user_info['KB_VECS_PATH'], 'general_corpus.pkl'
        )
        user_info['USER_SETTINGS']['CORPUS_META'] = os.path.join(
            user_info['KB_VECS_PATH'], 'general_corpus_meta.pkl'
        )
        user_info['USER_SETTINGS']['LOCAL_LEARN_DIR'] = os.path.join(
            user_info['KB_VECS_PATH'], 'userlearn_chk'
        )
        user_info['USER_SETTINGS']['TRAIN_DATA_GEN_QUERIES'] = os.path.join(
            user_info['KB_VECS_PATH'], 'fintune_data_gen_queries.jsonl'
        )
        user_info['USER_SETTINGS']['TRAIN_DATA_PATH'] = os.path.join(
            user_info['KB_VECS_PATH'], 'fintune_data_path.jsonl'
        )
        user_info['USER_SETTINGS']['TRAIN_DATA_CONTENT'] = os.path.join(
            user_info['KB_VECS_PATH'], 'fintune_data_content.jsonl'
        )
        user_info['USER_SETTINGS']['TRAIN_DATA_BOTH'] = os.path.join(
            user_info['KB_VECS_PATH'], 'fintune_data_both.jsonl'
        )
        user_info['USER_SETTINGS']['TRAIN_DATA_ALL_CONTENTS'] = os.path.join(
            user_info['KB_VECS_PATH'], 'fintune_data_all_contents.jsonl'
        )
        
        # 加载停用词
        if user_info['USER_SETTINGS']['USE_STOPWORDS']:
            stw_path = os.path.join(
                user_info['USER_SETTINGS']['LOCAL_MODELS_DIR'], 
                user_info['USER_SETTINGS']['STOP_WORDS']
            )
            try:
                with open(stw_path, 'r', encoding='utf-8') as file:
                    user_info['stopwords'] = set(line.strip() for line in file)
            except Exception as e:
                logger.warning(f"加载停用词失败: {str(e)}")
                user_info['stopwords'] = None
        else:
            user_info['stopwords'] = None
        
        # 清理临时文件
        clean_file(user_info['USER_SETTINGS']['MATCH_DF'], mode='clean')
        logger.info(f"用户配置初始化完成: {user_info['user']}")
        
        return user_info
    
    @staticmethod
    def get_user_config(user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取用户配置
        
        Args:
            user_id: 用户ID
            
        Returns:
            用户配置字典或None
        """
        try:
            config_json = UserConfigService.init_user(str(user_id))
            return json.loads(config_json)
        except Exception as e:
            logger.error(f"获取用户配置失败: {user_id}, 错误: {str(e)}")
            return None
