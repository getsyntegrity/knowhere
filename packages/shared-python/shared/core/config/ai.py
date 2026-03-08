"""
AI模型配置
"""
from pydantic import BaseModel, Field


class AIConfig(BaseModel):
    """AI模型配置"""
    
    # AI模型配置
    DS_KEY: str = Field(..., description="DeepSeek API密钥")
    DS_URL: str = Field(..., description="DeepSeek API URL")
    GPT_API_KEY: str = Field(default="", description="OpenAI API密钥")
    EMBEDDING_MODEL: str = Field(default="", description="嵌入模型")
    NORMOL_MODEL: str = Field(default="", description="普通模型")
    IMAGE_MODEL: str = Field(default="", description="图像模型")
    
    # 模型参数配置
    MIN_CONFIDENCE_THRESHOLD: float = Field(default=0.05, description="最小置信度阈值")
    HIGH_IOU_THRESHOLD: float = Field(default=0.9, description="高IoU阈值")
    DEFAULT_EMBEDDING_DIM: int = Field(default=1024, description="默认嵌入维度")
    DEFAULT_TOP_K: int = Field(default=5, description="默认Top-K")
    DEFAULT_BATCH_SIZE: int = Field(default=32, description="默认批次大小")
    DEFAULT_EPOCHS: int = Field(default=3, description="默认训练轮数")
    DEFAULT_THRESHOLD: float = Field(default=0.5, description="默认阈值")
    
    # 兼容性字段（保留现有字段，逐步迁移）
    DX_KEy: str = Field(default="", description="DX密钥（兼容性字段）")
    ARK_API_KEY: str = Field(default="", description="ARK API密钥（兼容性字段）")
    ARK_URL: str = Field(default="", description="ARK URL（兼容性字段）")
    ALI_API_KEY: str = Field(default="sk-test-key", description="阿里云API密钥（兼容性字段）")
    ALI_URL: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1", description="阿里云URL（兼容性字段）")
    MINERU_API_KEYS: str = Field(
        default="",
        description="MinerU API key pool. Supports a JSON array or comma/newline-separated values; entries may use token_id=api_key format.",
    )
    MINERU_URL: str = Field(default="https://mineru.net/api/v4", description="MinerU API基础URL（不含端点路径，如 https://mineru.net/api/v4）")
    MINERU_TOKEN_RPM_LIMIT: int = Field(default=300, description="单个 MinerU token 每分钟请求上限")
    MINERU_TOKEN_DAILY_LIMIT: int = Field(default=10000, description="单个 MinerU token 每日请求上限")
    MINERU_TOKEN_COOLDOWN_SECONDS: int = Field(default=60, description="MinerU token 触发限流后的冷却时间")
    IMAGE_MODEL_MAX: str = Field(default="", description="最大图像模型（兼容性字段）")
    REASON_MODEL: str = Field(default="", description="推理模型（兼容性字段）")
    IMG_HEADER: str = Field(default="", description="图像头部（兼容性字段）")
    MINERU_CONFIG: str = Field(default="", description="MinerU配置（兼容性字段）")
    MINERU_SOURCE: str = Field(default="", description="MinerU源（兼容性字段）")
    CONFIG_PATH: str = Field(default="app/core/config/config.txt", description="配置路径（兼容性字段）")
    META_PATH: str = Field(default="app/core/config/Meta_setting.csv", description="元数据路径（兼容性字段）")
    IMG_TBL_PATTERN: str = Field(default="", description="图像表格模式（兼容性字段）")
    PATH_IMAGE_PATTERN: str = Field(default="", description="路径图像模式（兼容性字段）")
    SPLIT_CHAR: str = Field(default="/", description="路径分隔符")
    LIBER_OFFICE: str = Field(default="", description="LibreOffice（兼容性字段）")
    ILOVEAPI_PUBLIC_KEY: str = Field(default="", description="iLoveAPI 公钥 (PPTX转PDF)")
    ILOVEAPI_SECRET_KEY: str = Field(default="", description="iLoveAPI 密钥 (PPTX转PDF)")
    ILOVEAPI_BASE_URL: str = Field(default="https://api.ilovepdf.com/v1", description="iLoveAPI 基础URL")
    ILOVEAPI_TIMEOUT: int = Field(default=120, description="iLoveAPI 请求超时(秒)")
    PROD_URL: str = Field(default="", description="生产URL（兼容性字段）")
    
    # 业务配置字段（兼容性）
    ALL_DF_COLS: str = Field(default="content,path,type,length,keywords,summary,know_id,tokens,extra,addtime", description="所有数据框列（兼容性字段）")
    DEFAULT_FOLDERS: str = Field(default="Supplementary_Files,Temporary_Files,templates,images,fragments", description="默认文件夹（兼容性字段）")
    KB_TERM: str = Field(default="KB_DATA", description="知识库术语（兼容性字段）")
    KB_VEC_TERM: str = Field(default="KB_VECS", description="知识库向量术语（兼容性字段）")
