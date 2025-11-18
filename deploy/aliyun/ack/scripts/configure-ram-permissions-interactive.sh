#!/bin/bash

# 交互式 RAM 用户权限配置脚本

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
log "RAM 用户权限配置工具"
log "=========================================="
echo ""

# 获取 RAM 用户列表
log "正在获取 RAM 用户列表..."
TEMP_FILE=$(mktemp)
aliyun ram ListUsers 2>/dev/null > "$TEMP_FILE"

# 尝试使用 Python 解析 JSON（如果可用）
if command -v python3 &> /dev/null; then
    USERS=$(python3 -c "import sys, json; data = json.load(sys.stdin); users = [u.get('UserName', '') for u in data.get('Users', {}).get('User', [])]; print('\n'.join(users))" < "$TEMP_FILE" 2>/dev/null)
fi

# 如果 Python 解析失败，使用 grep
if [ -z "$USERS" ]; then
    USERS=$(grep -o '"UserName"[[:space:]]*:[[:space:]]*"[^"]*"' "$TEMP_FILE" | sed 's/.*"\([^"]*\)".*/\1/' | sort -u)
fi

rm -f "$TEMP_FILE"

if [ -z "$USERS" ]; then
    error "未找到 RAM 用户，请检查是否有 RAM 管理权限"
fi

# 转换为数组
USER_ARRAY=($USERS)

echo ""
info "检测到以下 RAM 用户："
echo ""
for i in "${!USER_ARRAY[@]}"; do
    echo "  $((i+1)). ${USER_ARRAY[$i]}"
done
echo ""

# 如果提供了用户名参数，直接使用
if [ -n "$1" ]; then
    RAM_USER_NAME="$1"
    log "使用指定的 RAM 用户: ${RAM_USER_NAME}"
else
    # 交互式选择
    read -p "请选择要配置的用户（输入序号或用户名，或按 Enter 配置所有用户）: " SELECTION
    
    if [ -z "$SELECTION" ]; then
        log "将为所有用户配置权限"
        SELECTED_USERS=("${USER_ARRAY[@]}")
    elif [[ "$SELECTION" =~ ^[0-9]+$ ]]; then
        INDEX=$((SELECTION - 1))
        if [ $INDEX -ge 0 ] && [ $INDEX -lt ${#USER_ARRAY[@]} ]; then
            SELECTED_USERS=("${USER_ARRAY[$INDEX]}")
        else
            error "无效的序号"
        fi
    else
        # 检查是否是有效的用户名
        if [[ " ${USER_ARRAY[@]} " =~ " ${SELECTION} " ]]; then
            SELECTED_USERS=("$SELECTION")
        else
            error "用户不存在: ${SELECTION}"
        fi
    fi
fi

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

# 为每个选中的用户配置权限
for RAM_USER_NAME in "${SELECTED_USERS[@]}"; do
    echo ""
    log "=========================================="
    log "配置用户: ${RAM_USER_NAME}"
    log "=========================================="
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
    log "用户 ${RAM_USER_NAME} 配置完成"
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
done

log "=========================================="
log "权限配置完成"
log "=========================================="
echo ""
log "下一步："
echo "1. 确认所有权限已正确配置"
echo "2. 重新执行 terraform apply"
echo ""

