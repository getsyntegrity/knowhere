#!/bin/bash

# 激活 RDS PostgreSQL 服务关联角色脚本
# 用于解决 RDS 创建时的服务关联角色授权问题

set -e

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# 检查阿里云 CLI
if ! command -v aliyun &> /dev/null; then
    error "阿里云 CLI 未安装，请先安装: brew install aliyun-cli"
fi

# 检查是否已配置
if ! aliyun configure get &> /dev/null; then
    error "阿里云 CLI 未配置，请先运行: aliyun configure"
fi

log "=========================================="
log "激活 RDS PostgreSQL 服务关联角色"
log "=========================================="
echo ""

# RDS PostgreSQL 服务关联角色名称
RDS_ROLE_NAME="AliyunRDSRoleForPostgreSQL"

log "检查角色: ${RDS_ROLE_NAME}"

# 检查角色是否存在
if aliyun ram GetRole --RoleName "${RDS_ROLE_NAME}" &> /dev/null; then
    log "✅ 角色 ${RDS_ROLE_NAME} 已存在"
    
    # 检查角色状态
    ROLE_INFO=$(aliyun ram GetRole --RoleName "${RDS_ROLE_NAME}" 2>/dev/null)
    
    echo ""
    info "角色信息："
    echo "$ROLE_INFO" | grep -E "(RoleName|Arn|Description|UpdateDate)" | head -5
    echo ""
    
    warn "注意：角色已创建，但可能需要通过控制台激活"
    echo ""
    info "激活方式："
    echo "1. 访问 RDS 控制台：https://rds.console.aliyun.com/"
    echo "2. 点击'创建实例'"
    echo "3. 在创建页面点击'PostgreSQL 授权' -> '前往授权'"
    echo "4. 系统会自动激活服务关联角色"
    echo ""
    info "或使用以下方式："
    echo "1. 访问 RAM 控制台：https://ram.console.aliyun.com/roles"
    echo "2. 找到 ${RDS_ROLE_NAME} 角色"
    echo "3. 确认角色状态"
    echo ""
else
    warn "角色 ${RDS_ROLE_NAME} 不存在"
    echo ""
    info "创建方式："
    echo "1. 访问 RDS 控制台：https://rds.console.aliyun.com/"
    echo "2. 点击'创建实例'"
    echo "3. 在创建页面点击'PostgreSQL 授权' -> '前往授权'"
    echo "4. 系统会自动创建并授权服务关联角色"
    echo ""
    info "或运行创建脚本："
    echo "  ./create-rds-ram-role.sh"
    echo ""
fi

# 检查数据库代理角色（可选）
DB_PROXY_ROLE="AliyunRDSRoleForDBProxy"
log "检查数据库代理角色: ${DB_PROXY_ROLE}"

if aliyun ram GetRole --RoleName "${DB_PROXY_ROLE}" &> /dev/null; then
    log "✅ 数据库代理角色 ${DB_PROXY_ROLE} 已存在"
else
    warn "数据库代理角色 ${DB_PROXY_ROLE} 不存在（如果不需要数据库代理，可忽略）"
fi

echo ""
log "=========================================="
log "说明"
log "=========================================="
echo ""
info "服务关联角色（SLR）说明："
echo ""
echo "1. **什么是 SLR？**"
echo "   - Service-Linked Role（服务关联角色）"
echo "   - 允许阿里云服务代表您访问其他资源"
echo "   - RDS 需要 SLR 来访问 VPC、ECS 等资源"
echo ""
echo "2. **PostgreSQL 授权**"
echo "   - 角色：${RDS_ROLE_NAME}"
echo "   - 用途：允许 RDS PostgreSQL 访问网络和计算资源"
echo "   - 状态：需要在 RDS 控制台显示为'已授权'"
echo ""
echo "3. **数据库代理授权**（可选）"
echo "   - 角色：${DB_PROXY_ROLE}"
echo "   - 用途：如果使用数据库代理功能"
echo "   - 如果不需要数据库代理，可以跳过"
echo ""
echo "4. **如何授权**"
echo "   - 最简单方式：在 RDS 创建页面点击'前往授权'"
echo "   - 系统会自动创建并激活服务关联角色"
echo "   - 授权后即可正常创建 RDS 实例"
echo ""

