"""
API Key 管理 API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.core.permissions import current_user
from app.models.database.user import User
from app.services.auth.api_key_service import APIKeyService
from app.models.schemas.api_key import (
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
    APIKeyResponse,
    RegenerateAPIKeyRequest,
    RevokeAPIKeyRequest,
    APIKeyListResponse
)
from app.core.response.ResponseResult import ResponseResult

router = APIRouter(tags=["API Key Management"])


@router.post("/create", summary="创建API Key")
async def create_api_key(
    request: CreateAPIKeyRequest,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建API Key"""
    api_key_service = APIKeyService()
    
    try:
        api_key = await api_key_service.create_api_key(
            session=db,
            user_id=str(current_user.id),
            name=request.name,
            enabled_modules=request.enabled_modules,
            expires_at=request.expires_at
        )
        
        return ResponseResult.ok_data(data=CreateAPIKeyResponse(
            api_key=api_key,
            name=request.name,
            enabled_modules=request.enabled_modules,
            expires_at=request.expires_at
        ).dict())
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建API Key失败: {str(e)}"
        )


@router.get("/list", summary="获取API Key列表")
async def list_api_keys(
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取API Key列表"""
    api_key_service = APIKeyService()
    
    try:
        api_keys_data = await api_key_service.list_user_api_keys(db, str(current_user.id))
        
        api_keys = [
            APIKeyResponse(
                id=key["id"],
                name=key["name"],
                enabled_modules=key["enabled_modules"],
                is_active=key["is_active"],
                created_at=key["created_at"],
                last_used_at=key["last_used_at"],
                expires_at=key["expires_at"]
            )
            for key in api_keys_data
        ]
        
        return ResponseResult.ok_data(data=APIKeyListResponse(
            api_keys=api_keys,
            total=len(api_keys)
        ).dict())
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取API Key列表失败: {str(e)}"
        )


@router.post("/regenerate", summary="重新生成API Key")
async def regenerate_api_key(
    request: RegenerateAPIKeyRequest,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    """重新生成API Key"""
    api_key_service = APIKeyService()
    
    try:
        new_api_key = await api_key_service.regenerate_api_key(
            session=db,
            api_key_id=request.api_key_id,
            user_id=str(current_user.id)
        )
        
        return ResponseResult.ok_data(data={
            "api_key": new_api_key,
            "message": "API Key已重新生成"
        })
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重新生成API Key失败: {str(e)}"
        )


@router.post("/revoke", summary="撤销API Key")
async def revoke_api_key(
    request: RevokeAPIKeyRequest,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    """撤销API Key"""
    api_key_service = APIKeyService()
    
    try:
        success = await api_key_service.revoke_api_key(
            session=db,
            api_key_id=request.api_key_id,
            user_id=str(current_user.id)
        )
        
        if success:
            return ResponseResult.ok_data(data={"message": "API Key已撤销"})
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="撤销API Key失败"
            )
            
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"撤销API Key失败: {str(e)}"
        )


@router.get("/{api_key_id}", summary="获取API Key详情")
async def get_api_key(
    api_key_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取单个API Key详情"""
    api_key_service = APIKeyService()
    
    try:
        api_key = await api_key_service.get_api_key(db, str(current_user.id), api_key_id)
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API Key不存在"
            )
        
        return ResponseResult.ok_data(data={
            "id": str(api_key.id),
            "name": api_key.name,
            "enabled_modules": api_key.enabled_modules,
            "is_active": api_key.is_active,
            "created_at": api_key.created_at,
            "last_used_at": api_key.last_used_at,
            "expires_at": api_key.expires_at
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取API Key失败: {str(e)}"
        )


@router.put("/{api_key_id}/toggle", summary="启用/禁用API Key")
async def toggle_api_key(
    api_key_id: str,
    current_user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db)
):
    """启用/禁用API Key"""
    api_key_service = APIKeyService()
    
    try:
        success = await api_key_service.toggle_api_key(db, str(current_user.id), api_key_id)
        if success:
            return ResponseResult.ok_data(data={"message": "API Key状态更新成功"})
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API Key状态更新失败"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新API Key状态失败: {str(e)}"
        )
