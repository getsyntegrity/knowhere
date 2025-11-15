#!/bin/bash

# 创建 ACK 服务关联角色脚本
# 用于解决 ACK 集群创建时的 RAM 角色错误

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
log "创建 ACK 服务关联角色"
log "=========================================="
echo ""

# ACK 需要的服务关联角色
ROLES=(
    "AliyunCSManagedKubernetesRole"
    "AliyunCSManagedKubernetesRoleForVK"
    "AliyunCSManagedKubernetesRoleForSLB"
    "AliyunCSManagedKubernetesRoleForSLS"
    "AliyunCSManagedKubernetesRoleForARMS"
    "AliyunCSManagedKubernetesRoleForECI"
)

log "检查并创建 ACK 服务关联角色..."
echo ""

for ROLE in "${ROLES[@]}"; do
    log "检查角色: ${ROLE}"
    
    # 检查角色是否存在
    if aliyun ram GetRole --RoleName "${ROLE}" &> /dev/null; then
        warn "角色 ${ROLE} 已存在，跳过"
    else
        log "创建角色: ${ROLE}"
        
        # 创建信任策略文档
        TRUST_POLICY=$(cat <<EOF
{
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Effect": "Allow",
      "Principal": {
        "Service": [
          "cs.aliyuncs.com"
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
            --RoleName "${ROLE}" \
            --AssumeRolePolicyDocument "${TRUST_POLICY}" \
            --Description "Service-linked role for ACK managed Kubernetes" &> /dev/null; then
            log "✅ 角色 ${ROLE} 创建成功"
        else
            warn "角色 ${ROLE} 创建失败，可能需要手动创建"
        fi
    fi
    echo ""
done

log "=========================================="
log "检查默认服务角色"
log "=========================================="
echo ""

# 检查默认服务角色
DEFAULT_ROLE="AliyunCSDefaultRole"
log "检查默认服务角色: ${DEFAULT_ROLE}"

if aliyun ram GetRole --RoleName "${DEFAULT_ROLE}" &> /dev/null; then
    log "✅ 默认服务角色 ${DEFAULT_ROLE} 已存在"
else
    warn "默认服务角色 ${DEFAULT_ROLE} 不存在"
    warn "这通常会在首次创建 ACK 集群时自动创建"
    warn "如果创建失败，请通过控制台手动创建"
fi

echo ""
log "=========================================="
log "完成"
log "=========================================="
echo ""
log "如果仍有问题，请："
echo "1. 访问控制台：https://ram.console.aliyun.com/roles"
echo "2. 点击'创建角色'"
echo "3. 选择'阿里云服务'"
echo "4. 选择'容器服务 Kubernetes 版'"
echo "5. 完成创建"
echo ""

