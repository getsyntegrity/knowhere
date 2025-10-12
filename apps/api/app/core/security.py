"""
安全相关工具函数 - 已迁移到FastAPI Users
此文件保留用于向后兼容，但建议使用FastAPI Users的认证功能
"""

import bcrypt
from app.core.config import settings

def get_password_hash(password: str) -> str:
    """
    生成密码的哈希值
    注意：FastAPI Users有自己的密码处理机制，此函数仅用于向后兼容
    """
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_password_bytes.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码和哈希密码是否匹配
    注意：FastAPI Users有自己的密码验证机制，此函数仅用于向后兼容
    """
    plain_password_bytes = plain_password.encode('utf-8')
    hashed_password_bytes = hashed_password.encode('utf-8')
    try:
        return bcrypt.checkpw(plain_password_bytes, hashed_password_bytes)
    except ValueError:
        return False
