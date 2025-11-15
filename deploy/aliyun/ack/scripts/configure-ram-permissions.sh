#!/bin/bash

# 为 RAM 用户快速配置部署所需权限

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

# 获取 RAM 用户名
RAM_USER_NAME=${1:-}

if [ -z "$RAM_USER_NAME" ]; then
    warn "未指定 RAM 用户名"
    echo ""
    echo "使用方法："
    echo "  ./configure-ram-permissions.sh <RAM_USER_NAME>"
    echo ""
    echo "或交互式输入："
    read -p "请输入 RAM 用户名: " RAM_USER_NAME
    if [ -z "$RAM_USER_NAME" ]; then
        error "RAM 用户名不能为空"
    fi
fi

log "=========================================="
log "配置 RAM 用户权限"
log "=========================================="
echo ""
log "RAM 用户名: ${RAM_USER_NAME}"
echo ""

# 必需的系统策略
POLICIES=(
    "AliyunVPCFullAccess"
    "AliyunECSFullAccess"
    "AliyunCSFullAccess"
    "AliyunSLBFullAccess"
    "AliyunRDSFullAccess"
    "AliyunKvstoreFullAccess"
    "AliyunAMQPFullAccess"
    "AliyunKMSFullAccess"
    "AliyunNASFullAccess"
    "AliyunOSSFullAccess"
    "AliyunRAMFullAccess"
)

log "开始配置权限..."
echo ""

SUCCESS_COUNT=0
FAILED_COUNT=0
SKIPPED_COUNT=0

for POLICY in "${POLICIES[@]}"; do
    log "检查策略: ${POLICY}"
    
    # 检查是否已附加
    if aliyun ram ListPoliciesForUser --UserName "${RAM_USER_NAME}" 2>/dev/null | grep -q "${POLICY}"; then
        warn "策略 ${POLICY} 已存在，跳过"
        SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    else
        log "添加策略: ${POLICY}"
        if aliyun ram AttachPolicyToUser \
            --PolicyType System \
            --PolicyName "${POLICY}" \
            --UserName "${RAM_USER_NAME}" &> /dev/null; then
            log "✅ 策略 ${POLICY} 添加成功"
            SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        else
            warn "策略 ${POLICY} 添加失败"
            FAILED_COUNT=$((FAILED_COUNT + 1))
        fi
    fi
    echo ""
done

log "=========================================="
log "配置完成"
log "=========================================="
echo ""
log "成功: ${SUCCESS_COUNT}"
log "跳过: ${SKIPPED_COUNT}"
log "失败: ${FAILED_COUNT}"
echo ""

if [ ${FAILED_COUNT} -gt 0 ]; then
    warn "部分策略添加失败，请检查："
    echo "1. RAM 用户是否存在"
    echo "2. 当前账号是否有 RAM 管理权限"
    echo "3. 策略名称是否正确"
    echo ""
fi

log "验证权限配置..."
echo ""

# 验证权限
log "测试 VPC 权限..."
if aliyun vpc DescribeVpcs --RegionId cn-guangzhou &> /dev/null; then
    log "✅ VPC 权限正常"
else
    warn "VPC 权限测试失败"
fi

log "测试 ECS 权限..."
if aliyun ecs DescribeRegions &> /dev/null; then
    log "✅ ECS 权限正常"
else
    warn "ECS 权限测试失败"
fi

log "测试 CS 权限..."
if aliyun cs DescribeClusters &> /dev/null; then
    log "✅ CS 权限正常"
else
    warn "CS 权限测试失败（如果还没有集群，这是正常的）"
fi

echo ""
log "=========================================="
log "权限配置完成"
log "=========================================="
echo ""
log "下一步："
echo "1. 确认所有权限已正确配置"
echo "2. 重新执行 terraform apply"
echo ""

