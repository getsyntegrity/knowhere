"""
邮件服务工具函数
"""
import asyncio
from typing import Any, Callable, List, Tuple, TypeVar

from email_validator import validate_email, EmailNotValidError
from loguru import logger

T = TypeVar("T")


class EmailRetryHandler:
    """邮件重试处理器"""
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """
        初始化重试处理器
        
        Args:
            max_retries: 最大重试次数
            retry_delay: 初始重试延迟（秒），使用指数退避
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    async def execute_with_retry(
        self,
        func: Callable[[], Any],
        *args,
        **kwargs
    ) -> Any:
        """
        执行函数并自动重试
        
        Args:
            func: 要执行的异步函数
            *args: 函数位置参数
            **kwargs: 函数关键字参数
            
        Returns:
            函数执行结果
            
        Raises:
            最后一次执行的异常
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)  # 指数退避
                    logger.warning(
                        f"邮件发送失败，{delay:.2f}秒后重试 "
                        f"(尝试 {attempt + 1}/{self.max_retries + 1}): {str(e)}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"邮件发送失败，已达到最大重试次数 {self.max_retries}: {str(e)}"
                    )
        
        raise last_exception


class EmailValidator:
    """邮箱验证器"""
    
    @staticmethod
    def validate(email: str) -> bool:
        """
        验证邮箱格式
        
        Args:
            email: 邮箱地址
            
        Returns:
            是否有效
        """
        try:
            validate_email(email, check_deliverability=False)
            return True
        except EmailNotValidError:
            return False
    
    @staticmethod
    def validate_list(emails: List[str]) -> Tuple[List[str], List[str]]:
        """
        验证邮箱列表
        
        Args:
            emails: 邮箱地址列表
            
        Returns:
            (有效邮箱列表, 无效邮箱列表)
        """
        valid_emails = []
        invalid_emails = []
        
        for email in emails:
            if EmailValidator.validate(email):
                valid_emails.append(email)
            else:
                invalid_emails.append(email)
        
        return valid_emails, invalid_emails

