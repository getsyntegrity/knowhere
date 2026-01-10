"""
Credits 扣费中间件
"""
import time
from typing import Callable, Optional, cast

from shared.core.config import settings
from shared.core.database import get_db_context
from app.core.dependencies import _authenticate_api_key, _authenticate_jwt
from app.services.billing.credits_service import CreditsService
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession


class CreditsMiddleware:
    """Credits扣费中间件"""
    
    def __init__(self):
        self.credits_service = CreditsService()
        # 目前仅对 POST /api/v1/jobs 收费
        self.chargeable_paths = {"/api/v1/jobs", "/v1/jobs"}
    
    async def __call__(self, request: Request, call_next: Callable):
        # 检查是否需要扣费（仅限 POST /api/v1/jobs）
        if not self._should_charge_credits(request):
            return await call_next(request)
        
        async with get_db_context() as db:
            session = cast(AsyncSession, db)
            # 获取用户信息（优先 request.state.user，其次尝试认证头）
            user = await self._get_user(request, session)
            if not user:
                return await call_next(request)
            
            try:
                # 检查Credits余额
                balance = await self.credits_service.check_balance(session, str(user.id))
                if balance < settings.CREDITS_PER_API_CALL:
                    raise HTTPException(
                        status_code=status.HTTP_402_PAYMENT_REQUIRED,
                        detail=f"Credits余额不足，需要 {settings.CREDITS_PER_API_CALL} Credits，当前余额 {balance}"
                    )
                
                # 记录请求开始时间
                start_time = time.time()
                
                # 执行API操作
                response = await call_next(request)
            except HTTPException as exc:
                # BaseHTTPMiddleware 抛出的 HTTPException 会被包装成 ExceptionGroup，需手动转成 Response
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=getattr(exc, "headers", None) or None,
                )
            
            # 计算响应时间
            response_time = int((time.time() - start_time) * 1000)
            
            # 扣除Credits
            api_key_id = getattr(request.state, 'api_key_id', None)
            if response.status_code != status.HTTP_200_OK:
                await self._log_usage(
                    session,
                    user,
                    request,
                    response,
                    response_time,
                    api_key_id,
                    credits_used=0,
                )
                return response
            
            success = await self.credits_service.deduct_credits(
                session,
                str(user.id),
                settings.CREDITS_PER_API_CALL,
                f"API调用: {request.method} {request.url.path}",
                api_key_id
            )
            
            if not success:
                # 如果扣费失败，记录错误但不影响响应
                print(f"用户 {user.id} Credits扣费失败")
            
            # 记录使用日志
            await self._log_usage(
                session,
                user,
                request,
                response,
                response_time,
                api_key_id,
                credits_used=settings.CREDITS_PER_API_CALL,
            )
            
            return response
    
    def _should_charge_credits(self, request: Request) -> bool:
        """判断是否需要扣费：仅 POST /api/v1/jobs"""
        if request.method != "POST":
            return False
        
        # 去掉尾部斜杠，兼容 /api/v1/jobs/
        normalized_path = request.url.path.rstrip("/") or "/"
        return normalized_path in self.chargeable_paths
    
    async def _get_user(self, request: Request, db: AsyncSession):
        """
        获取当前用户：
        - 优先 request.state.user
        - 否则尝试 API Key/JWT 认证
        """
        user = getattr(request.state, "user", None)
        if user:
            return user
        
        user = await _authenticate_api_key(request, db)
        if user:
            request.state.user = user
            request.state.auth_type = "api_key"
            return user
        
        user = await _authenticate_jwt(request, db)
        if user:
            request.state.user = user
            request.state.auth_type = "jwt"
            return user
        
        return None
    
    async def _log_usage(
        self, 
        db: AsyncSession, 
        user, 
        request: Request, 
        response, 
        response_time: int,
        api_key_id: Optional[str] = None,
        credits_used: int = settings.CREDITS_PER_API_CALL,
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
                credits_used=credits_used,
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
