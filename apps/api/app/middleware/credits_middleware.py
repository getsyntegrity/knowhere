"""
Credits 扣费中间件
"""
import time
from typing import Callable

from shared.core.config import settings
from shared.core.database import get_db
from app.services.billing.credits_service import CreditsService
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession


class CreditsMiddleware:
    """Credits扣费中间件"""
    
    def __init__(self):
        self.credits_service = CreditsService()
        self.excluded_paths = [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/billing/credits",
            "/billing/usage",
            "/billing/history"
        ]
    
    async def __call__(self, request: Request, call_next: Callable):
        # 检查是否需要扣费
        if not self._should_charge_credits(request):
            return await call_next(request)
        
        # 获取用户信息
        user = getattr(request.state, 'user', None)
        if not user:
            return await call_next(request)
        
        # 检查Credits余额
        async with get_db() as db:
            balance = await self.credits_service.check_balance(db, str(user.id))
            if balance < settings.CREDITS_PER_API_CALL:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail=f"Credits余额不足，需要 {settings.CREDITS_PER_API_CALL} Credits，当前余额 {balance}"
                )
            
            # 记录请求开始时间
            start_time = time.time()
            
            # 执行API操作
            response = await call_next(request)
            
            # 计算响应时间
            response_time = int((time.time() - start_time) * 1000)
            
            # 扣除Credits
            api_key_id = getattr(request.state, 'api_key_id', None)
            success = await self.credits_service.deduct_credits(
                db,
                str(user.id),
                settings.CREDITS_PER_API_CALL,
                f"API调用: {request.method} {request.url.path}",
                api_key_id
            )
            
            if not success:
                # 如果扣费失败，记录错误但不影响响应
                print(f"用户 {user.id} Credits扣费失败")
            
            # 记录使用日志
            await self._log_usage(db, user, request, response, response_time, api_key_id)
            
            return response
    
    def _should_charge_credits(self, request: Request) -> bool:
        """判断是否需要扣费"""
        # 排除不需要扣费的路径
        if request.url.path in self.excluded_paths:
            return False
        
        # 只对API路径扣费
        if not request.url.path.startswith("/api/v1/"):
            return False
        
        # 排除认证相关路径
        auth_paths = ["/auth/", "/oauth/", "/billing/"]
        if any(request.url.path.startswith(path) for path in auth_paths):
            return False
        
        return True
    
    async def _log_usage(
        self, 
        db: AsyncSession, 
        user, 
        request: Request, 
        response, 
        response_time: int,
        api_key_id: Optional[str] = None
    ):
        """记录使用日志"""
        try:
            from datetime import datetime

            from shared.models.database.usage_log import UsageLog
            
            usage_log = UsageLog(
                user_id=str(user.id),
                api_key_id=api_key_id,
                endpoint=request.url.path,
                method=request.method,
                credits_used=settings.CREDITS_PER_API_CALL,
                response_time=response_time,
                status_code=response.status_code,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                created_at=datetime.utcnow()
            )
            
            db.add(usage_log)
            await db.commit()
            
        except Exception as e:
            print(f"记录使用日志失败: {e}")


# 创建中间件实例
credits_middleware = CreditsMiddleware()
