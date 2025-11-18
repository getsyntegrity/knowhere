"""
处理相关常量
"""


class ProcessingConstants:
    """处理相关常量"""
    
    # 文件处理
    MAX_THRESHOLD = 2000
    MIN_THRESHOLD = 500
    SUMMARY_LEN = 200
    KEYWORDS_NUM = 3
    POSTPROCESS_SUMMARY_LEN = 1500
    IMG_MAX_TOKENS = 200
    IMG_OCR_MAX_TOKENS = 2000
    MAX_TOKENS_MULTIPLIER = 1.3
    MAX_TOKENS_HEADER_MULTIPLIER = 1.5
    MAX_TOKENS_REWRITE_MULTIPLIER = 1.2
    MAX_TOKENS_SUMMARY_MULTIPLIER = 1.2
    MAX_TOKENS_JUDGE = 20
    MAX_TOKENS_TITLE_MULTIPLIER = 200
    MAX_TOKENS_SUBS_MULTIPLIER = 1.2
    MAX_TOKENS_REWRITE_SENTENCE_MULTIPLIER = 1.3
    MAX_TOKENS_QA_MULTIPLIER = 1.5
    MAX_TOKENS_QA_OUTPUT_MULTIPLIER = 1.2
    MAX_TOKENS_QA_OUTPUT_LIMIT = 20
    
    # 图像处理
    IMG_MIN_SIZE = 10 * 1024  # 10KB
    IMG_MAX_SIZE = 5 * 1024 * 1024  # 5MB
    IMG_QUALITY = 100
    IMG_CHUNK_SIZE = 1024 * 1024  # 1MB
    
    # PostgreSQL 数据库连接池配置
    # 基础连接池大小 - 根据CPU核心数调整
    DB_POOL_SIZE = 20
    # 最大溢出连接数 - 允许在高峰期创建额外连接
    DB_MAX_OVERFLOW = 30
    # 连接回收时间（秒）- 30分钟，避免长时间连接
    DB_POOL_RECYCLE = 1800
    # 连接超时时间（秒）
    DB_CONNECT_TIMEOUT = 30
    # 连接池超时时间（秒）- 获取连接的最大等待时间
    DB_POOL_TIMEOUT = 30
    # 连接预检查 - 确保连接有效
    DB_POOL_PRE_PING = True
    # 连接池重置时间（秒）- 定期重置连接池
    DB_POOL_RESET_ON_RETURN = "commit"
    # 最大连接生命周期（秒）- 连接最大存活时间
    DB_MAX_CONNECTION_LIFETIME = 3600
    
    # PostgreSQL 性能优化配置
    # 查询缓存大小
    DB_QUERY_CACHE_SIZE = 1000
    # 批量操作大小
    DB_BATCH_SIZE = 1000
    # 事务隔离级别
    DB_ISOLATION_LEVEL = "READ_COMMITTED"
    # 自动提交模式
    DB_AUTOCOMMIT = False
    # 连接池预热
    DB_POOL_PREWARM = True
    # 连接验证查询
    DB_VALIDATION_QUERY = "SELECT 1"
    # 连接验证超时
    DB_VALIDATION_TIMEOUT = 5
    
    # 训练参数
    TRAIN_BATCH_SIZE = 16
    MEMORY_K = 2
    MEMORY_LR = 0.001
    MEMORY_BATCH_SIZE = 2
    MEMORY_N_EPOCHS = 3
    MEMORY_MAX_INPUT_LENGTH = 2048
