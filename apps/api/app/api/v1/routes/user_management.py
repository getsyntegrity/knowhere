"""
用户管理 API
"""

from shared.core.database import get_db
from app.core.permissions import current_user
from shared.models.database.user import User
from shared.models.schemas.user import UserResponse, UserUpdateRequest
from app.services.billing.credits_service import CreditsService
from app.services.user.user_service import UserService
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from shared.core.exceptions.domain_exceptions import WorkerHandlingException
from shared.core.billing import MicroDollar

router = APIRouter()

# 初始化服务
user_service = UserService()
credits_service = CreditsService()


@router.get("/profile", response_model=UserResponse)
async def get_profile(
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户资料"""
    try:
        user_data = await user_service.get_user_profile(db, current_user.id)
        return UserResponse.model_validate(user_data)
    except Exception as e:
        raise WorkerHandlingException(
            internal_message=f"获取用户资料失败: {str(e)}"
        )


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    user_update: UserUpdateRequest,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新用户资料"""
    try:
        updated_user = await user_service.update_user_profile(
            db, current_user.id, user_update
        )
        return UserResponse.model_validate(updated_user)
    except Exception as e:
        raise WorkerHandlingException(
            internal_message=f"更新用户资料失败: {str(e)}"
        )


@router.get("/credits/balance")
async def get_credits_balance(
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户Credits余额"""
    try:
        balance = await credits_service.get_balance(db, current_user.id)
        return {"user_id": current_user.id, "credits_balance": MicroDollar(balance).to_credit()}
    except Exception as e:
        raise WorkerHandlingException(
            internal_message=f"获取Credits余额失败: {str(e)}"
        )


@router.get("/credits/transactions")
async def get_credits_transactions(
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0
):
    """获取用户Credits交易记录"""
    try:
        transactions = await credits_service.get_user_transactions(
            db, current_user.id, limit, offset
        )
        # Convert micro-credits to display credits in transactions
        display_transactions = [
            {
                **tx,
                "credits_amount": MicroDollar(tx["credits_amount"]).to_credit()
            }
            for tx in transactions
        ]
        return {
            "user_id": current_user.id,
            "transactions": display_transactions,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        raise WorkerHandlingException(
            internal_message=f"获取交易记录失败: {str(e)}"
        )


@router.delete("/account")
async def delete_account(
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除用户账户"""
    try:
        success = await user_service.delete_user(db, current_user.id)
        if success:
            return {"message": "账户删除成功"}
        else:
            raise WorkerHandlingException(
                internal_message="删除账户失败"
            )
    except Exception as e:
        raise WorkerHandlingException(
            internal_message=f"删除账户失败: {str(e)}"
        )
