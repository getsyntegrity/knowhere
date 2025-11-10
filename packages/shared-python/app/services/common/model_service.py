"""
模型管理服务
处理本地模型设置和微调器初始化
"""
import os
import time
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForCausalLM
from loguru import logger

from app.core.config import settings
from app.services.knowledge.user_learner_service import CBD_Memory, SequencePredictor, MarkerPredictor
# 注意：encoder_finetuner是Worker专用的，改为延迟导入
# from app.services.knowledge.encoder_finetuner import EncoderFinetuner, gen_train_data_from_queries, gen_queries, load_gen_queries, gen_train_data_from_contents, gen_corpus
from app.services.common.kb_utils import check_internet


class LocalModelSetting:
    """本地模型设置类"""
    
    def __init__(self, user_info):
        """初始化本地模型设置"""
        self._init_local_llm(user_info)
        self._init_local_encoder(user_info)
    
    def _init_local_llm(self, user_info):
        """初始化本地大语言模型"""
        if user_info['USER_SETTINGS']['USE_LOCAL_LLM']:
            try:
                from app.services.ai.Local_API.call_locals import call_local_llm, call_local_stream
                self.local_llm_path = os.path.join(
                    user_info['USER_SETTINGS']['LOCAL_MODELS_DIR'], 
                    user_info['USER_SETTINGS']['LOCAL_LLM_NAME']
                )
                self.local_reranker_path = os.path.join(
                    user_info['USER_SETTINGS']['LOCAL_MODELS_DIR'], 
                    user_info['USER_SETTINGS']['LOCAL_RERANKER']
                )
                self.local_llm_tz = AutoTokenizer.from_pretrained(
                    self.local_llm_path, 
                    trust_remote_code=True
                )
                self.local_llm = AutoModelForCausalLM.from_pretrained(
                    self.local_llm_path,
                    torch_dtype="auto",
                    low_cpu_mem_usage=True,
                    trust_remote_code=True,
                ).to(user_info['device']).eval()
                self.call_local_llm = call_local_llm
                self.call_local_stream = call_local_stream
                logger.info("本地大语言模型初始化成功")
            except Exception as e:
                logger.error(f"本地大语言模型初始化失败: {str(e)}")
                self.local_llm_tz = None
                self.local_llm = None
                self.call_local_llm = None
                self.call_local_stream = None
        else:
            self.local_llm_tz = None
            self.local_llm = None
            self.call_local_llm = None
            self.call_local_stream = None
    
    def _init_local_encoder(self, user_info):
        """初始化本地编码器"""
        if user_info['USER_SETTINGS']['USE_LOCAL_ENCODER']:
            try:
                encoder_path = os.path.join(
                    user_info['USER_SETTINGS']['LOCAL_MODELS_DIR'], 
                    user_info['USER_SETTINGS']['LOCAL_ENCODER_NAME']
                )
                self.tokenizer = AutoTokenizer.from_pretrained(
                    encoder_path, 
                    trust_remote_code=True
                )
                model_kwargs = {'device': user_info['device']}
                self.encoder_ = SentenceTransformer(
                    encoder_path, 
                    model_kwargs, 
                    device=user_info['device']
                )
                logger.info("本地编码器初始化成功")
            except Exception as e:
                logger.error(f"本地编码器初始化失败: {str(e)}")
                self.tokenizer = None
                self.encoder_ = None
        else:
            self.tokenizer = None
            self.encoder_ = None


class ModelService:
    """模型管理服务类"""
    
    @staticmethod
    def init_finetuner(user_info, model, tokenizer):
        """
        初始化微调器
        
        Args:
            user_info: 用户信息
            model: 模型
            tokenizer: 分词器
            
        Returns:
            微调器相关对象
        """
        try:
            opt_memory = CBD_Memory(
                user_info['USER_SETTINGS']['TOP_K'],
                int(user_info['USER_SETTINGS']['EMBEDDING_LEN']),
                model,
                tokenizer,
                user_info['USER_SETTINGS']['N_TRIGGER'],
                user_info['USER_SETTINGS']['L_RATE'],
                user_info['USER_SETTINGS']['BATCH_SIZE'],
                user_info['USER_SETTINGS']['N_EPOCHS'],
                user_info['USER_SETTINGS']['LOCAL_LEARN_DIR']
            )

            if user_info['USER_SETTINGS']['BN_RL']:
                # 延迟导入encoder_finetuner（Worker专用）
                try:
                    from app.services.knowledge.encoder_finetuner import EncoderFinetuner
                    st_time = time.time()
                    fine_tuner = EncoderFinetuner(user_info['USER_SETTINGS'])
                    logger.info(f'词嵌入微调模型载入完成 耗时 {np.round(time.time()-st_time, 2)}s')
                    sequence_reasoner = opt_memory.marker_learner
                    marker_reasoner = opt_memory.marker_learner
                    st_time = time.time()
                    logger.info(f'自动偏好推理模型载入完成 耗时 {np.round(time.time()-st_time, 2)}s')
                except ImportError as e:
                    logger.warning(f"无法导入encoder_finetuner（可能不在Worker服务中）: {e}")
                    fine_tuner = None
                    marker_reasoner = None
                    sequence_reasoner = None
            else:
                fine_tuner = None
                marker_reasoner = None
                sequence_reasoner = None
            
            return fine_tuner, marker_reasoner, sequence_reasoner
        except Exception as e:
            logger.error(f"微调器初始化失败: {str(e)}")
            return None, None, None
    
    @staticmethod
    def check_device_capabilities():
        """
        检查设备能力
        
        Returns:
            设备信息字典
        """
        device_info = {
            'device': "cuda" if torch.cuda.is_available() else "cpu",
            'has_internet': check_internet(),
            'can_use_local_llm': False,
            'can_use_local_summary': False
        }
        
        if device_info['device'] == "cuda":
            device_info['can_use_local_llm'] = True
            device_info['can_use_local_summary'] = True
        elif device_info['device'] == "cpu":
            device_info['can_use_local_llm'] = False
            device_info['can_use_local_summary'] = False
        
        return device_info
