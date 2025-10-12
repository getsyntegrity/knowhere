"""
用户配置服务
处理用户配置相关的业务逻辑
"""
import os
import json
import shutil
import pandas as pd
import numpy as np
import math
import torch
from typing import Dict, Any, Optional
from loguru import logger

from app.core.config import settings
from app.utils.UrlFileReaderUtils import UrlFileReader
from app.utils.FileDownUpUtils import get_pub_fileurl
from app.services.common.kb_utils import clean_file, path_handle, check_internet
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
        subfolders = settings.DEFAULT_FOLDERS.split(",")
        
        # 检查主目录是否存在，不存在就创建
        if not os.path.exists(kb_data_folder):
            os.makedirs(kb_data_folder, exist_ok=True)
            os.makedirs(kb_vecs_folder, exist_ok=True)
            logger.info(f"创建主目录: {kb_data_folder} 以及 {kb_vecs_folder}")
            
            for sub in subfolders:
                sub_path = os.path.join(kb_data_folder, sub)
                if not os.path.exists(sub_path):
                    os.makedirs(sub_path)
                    logger.info(f"创建子目录: {sub_path}")
                else:
                    logger.info(f"子目录已存在: {sub_path}")
            
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
                        logger.info(f"复制元数据配置文件到: {dest_path}")
                    else:
                        logger.warning(f"元数据配置文件不存在: {meta_path}")
                else:
                    logger.info("跳过元数据配置文件复制（路径为空）")
                
                # 复制配置文件
                if settings.CONFIG_PATH:
                    config_path = get_absolute_path(settings.CONFIG_PATH)
                    if os.path.exists(config_path):
                        shutil.copy(config_path, os.path.join(kb_data_folder, 'config.txt'))
                        logger.info("复制配置文件到: config.txt")
                    else:
                        logger.warning(f"配置文件不存在: {config_path}")
                else:
                    logger.info("跳过配置文件复制（路径为空）")
            except Exception as e:
                logger.warning(f"复制配置文件失败: {str(e)}")
        else:
            logger.info(f"主目录已存在: {kb_data_folder}")
    
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
        
        # 设置各种路径
        user_info['USER_SETTINGS']['SUPP_FILE_PATH'] = os.path.join(
            user_info['KB_PATH'], 'Supplementary_Files'
        )
        user_info['USER_SETTINGS']['TEMP_FILE_PATH'] = os.path.join(
            user_info['KB_PATH'], 'Temporary_Files'
        )
        user_info['USER_SETTINGS']['TEMPLATE_DIR'] = os.path.join(
            user_info['KB_PATH'], 'templates'
        )
        user_info['USER_SETTINGS']['RAW_IMG_DIR'] = os.path.join(
            user_info['KB_PATH'], 'images'
        )
        user_info['USER_SETTINGS']['FRAGMENT_DIR'] = os.path.join(
            user_info['KB_PATH'], 'fragments'
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
            config_json = UserConfigService.init_user(user_id)
            return json.loads(config_json)
        except Exception as e:
            logger.error(f"获取用户配置失败: {user_id}, 错误: {str(e)}")
            return None
