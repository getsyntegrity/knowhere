"""
业务常量
"""


class BusinessConstants:
    """业务逻辑常量"""
    
    # 用户配置默认值
    USER_DEFAULT_CONFIG = {
        'TOP_K': 5,
        'BATCH_SIZE': 32,
        'N_EPOCHS': 3,
        'THRESHOLD': 0.5,
        'OCR_TIMEOUT': 30.0,
        'HYBRID_SEARCH': True,
        'USE_LOCAL_LLM': False,
        'USE_LOCAL_ENCODER': False,
        'USE_LOCAL_RERANKER': False,
        'USE_STOPWORDS': False,
        'LOCAL_SUMMARY': False,
        'API_NAME': "ds_api",
        'llm_histories': [],
        'train_multiplier': 1,
        'CLLM_THRESHOLD': 0,
        'REWRITE_THRESHOLD': 0,
        'SIZE': 1000,
        'TABLE_SIZE': 100,
        'SUMMARY_THRESHOLD': 0.5,
        'L_RATE': 0.001,
        'BN_RL': False,
        'LLM_QA_OUT_LIMIT': 50
    }
    
    # 模型相关常量
    MIN_CONFIDENCE_THRESHOLD = 0.05
    HIGH_IOU_THRESHOLD = 0.9
    DEFAULT_EMBEDDING_DIM = 1024
    DEFAULT_BATCH_SIZE = 32
    DEFAULT_EPOCHS = 3
    DEFAULT_LEARNING_RATE = 0.001
    DEFAULT_TOP_K = 5
    DEFAULT_THRESHOLD = 0.5
