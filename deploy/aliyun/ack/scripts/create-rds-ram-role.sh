#!/bin/bash

# 创建 RDS 服务关联角色脚本
# 用于解决 RDS PostgreSQL 创建时的服务关联角色错误

set -e

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
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

# 检查阿里云 CLI
if ! command -v aliyun &> /dev/null; then
    error "阿里云 CLI 未安装，请先安装: brew install aliyun-cli"
fi

# 检查是否已配置
if ! aliyun configure get &> /dev/null; then
    error "阿里云 CLI 未配置，请先运行: aliyun configure"
fi

log "=========================================="
log "创建 RDS 服务关联角色"
log "=========================================="
echo ""

# RDS PostgreSQL 服务关联角色名称
RDS_ROLE_NAME="AliyunRDSRoleForPostgreSQL"

log "检查角色: ${RDS_ROLE_NAME}"

# 检查角色是否存在
if aliyun ram GetRole --RoleName "${RDS_ROLE_NAME}" &> /dev/null; then
    warn "角色 ${RDS_ROLE_NAME} 已存在，跳过"
else
    log "创建角色: ${RDS_ROLE_NAME}"
    
    # 创建信任策略文档
    TRUST_POLICY=$(cat <<EOF
{
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Effect": "Allow",
      "Principal": {
        "Service": [
          "rds.aliyuncs.com"
        ]
      }
    }
  ],
  "Version": "1"
}
EOF
)
    
    # 创建角色
    if aliyun ram CreateRole \
        --RoleName "${RDS_ROLE_NAME}" \
        --AssumeRolePolicyDocument "${TRUST_POLICY}" \
        --Description "Service-linked role for RDS PostgreSQL" &> /dev/null; then
        log "✅ 角色 ${RDS_ROLE_NAME} 创建成功"
    else
        error "角色 ${RDS_ROLE_NAME} 创建失败"
    fi
    
    # 附加系统策略
    log "附加系统策略: AliyunRDSFullAccess"
    if aliyun ram AttachPolicyToRole \
        --PolicyType System \
        --PolicyName "AliyunRDSFullAccess" \
        --RoleName "${RDS_ROLE_NAME}" &> /dev/null; then
        log "✅ 策略附加成功"
    else
        warn "策略附加失败（可能已存在）"
    fi
fi

echo ""
log "=========================================="
log "RDS 服务关联角色配置完成"
log "=========================================="
echo ""
log "下一步：重新执行 terraform apply"
echo ""

