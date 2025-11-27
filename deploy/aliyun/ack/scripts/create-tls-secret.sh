#!/bin/bash

# 创建 TLS Secret 脚本
# 支持两种方式：
# 1. 从阿里云证书服务通过证书ID获取证书
# 2. 从本地证书文件创建 Secret

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

# 默认配置
NAMESPACE=${NAMESPACE:-knowhere}
SECRET_NAME=${SECRET_NAME:-knowhere-tls}
CERT_ID=${CERT_ID:-1872946667951752_19ab0485602_935740748_-1131298329}
CERT_FILE=${CERT_FILE:-}
KEY_FILE=${KEY_FILE:-}

# 检查 kubectl 是否可用
if ! command -v kubectl &> /dev/null; then
    error "kubectl 未安装或不在 PATH 中"
fi

# 检查命名空间是否存在
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    error "命名空间 $NAMESPACE 不存在，请先创建命名空间"
fi

# 方式1: 从本地证书文件创建
if [ -n "$CERT_FILE" ] && [ -n "$KEY_FILE" ]; then
    log "从本地证书文件创建 TLS Secret..."
    
    if [ ! -f "$CERT_FILE" ]; then
        error "证书文件不存在: $CERT_FILE"
    fi
    
    if [ ! -f "$KEY_FILE" ]; then
        error "私钥文件不存在: $KEY_FILE"
    fi
    
    # 创建或更新 Secret
    kubectl create secret tls "$SECRET_NAME" \
        --cert="$CERT_FILE" \
        --key="$KEY_FILE" \
        --namespace="$NAMESPACE" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    log "TLS Secret $SECRET_NAME 已创建/更新（从本地文件）"
    exit 0
fi

# 方式2: 从阿里云证书服务获取证书（需要证书文件）
# 注意：证书ID格式可能是SLB证书ID，需要通过控制台下载证书文件
if [ -n "$CERT_ID" ]; then
    log "检测到证书ID: $CERT_ID"
    warn "阿里云证书服务API获取证书需要特殊权限，建议使用证书文件方式"
    warn ""
    warn "请按以下步骤操作："
    warn "1. 登录阿里云控制台"
    warn "2. 进入 证书管理服务 或 SLB证书管理"
    warn "3. 找到证书ID: $CERT_ID"
    warn "4. 下载证书文件（.crt 和 .key）"
    warn "5. 使用以下命令创建 Secret："
    warn ""
    warn "   CERT_FILE=/path/to/cert.crt KEY_FILE=/path/to/cert.key $0"
    warn ""
    warn "或者手动创建："
    warn "   kubectl create secret tls $SECRET_NAME \\"
    warn "     --cert=/path/to/cert.crt \\"
    warn "     --key=/path/to/cert.key \\"
    warn "     --namespace=$NAMESPACE"
    warn ""
    
    # 尝试使用 aliyun CLI（如果可用）
    if command -v aliyun &> /dev/null; then
        log "尝试使用 aliyun CLI 获取证书信息..."
        
        # 创建临时目录
        TEMP_DIR=$(mktemp -d)
        trap "rm -rf $TEMP_DIR" EXIT
        
        # 尝试从证书服务获取（CAS）
        CERT_INFO=$(aliyun cas DescribeUserCertificateDetail \
            --CertId "$CERT_ID" \
            --output json 2>/dev/null || echo "")
        
        if [ -n "$CERT_INFO" ]; then
            # 检查是否有 jq
            if command -v jq &> /dev/null; then
                CERT_CONTENT=$(echo "$CERT_INFO" | jq -r '.Certificate // .Cert // empty' 2>/dev/null || echo "")
                KEY_CONTENT=$(echo "$CERT_INFO" | jq -r '.PrivateKey // .Key // empty' 2>/dev/null || echo "")
                
                if [ -n "$CERT_CONTENT" ] && [ -n "$KEY_CONTENT" ] && [ "$CERT_CONTENT" != "null" ] && [ "$KEY_CONTENT" != "null" ]; then
                    log "成功从API获取证书内容"
                    echo "$CERT_CONTENT" > "$TEMP_DIR/cert.crt"
                    echo "$KEY_CONTENT" > "$TEMP_DIR/cert.key"
                    
                    # 创建 Secret
                    kubectl create secret tls "$SECRET_NAME" \
                        --cert="$TEMP_DIR/cert.crt" \
                        --key="$TEMP_DIR/cert.key" \
                        --namespace="$NAMESPACE" \
                        --dry-run=client -o yaml | kubectl apply -f -
                    
                    log "TLS Secret $SECRET_NAME 已创建/更新（从阿里云API）"
                    exit 0
                fi
            fi
        fi
        
        warn "无法通过API自动获取证书，请使用证书文件方式"
    else
        warn "aliyun CLI 未安装，无法尝试API方式"
    fi
    
    error "请使用证书文件方式创建 Secret（见上方说明）"
fi

# 如果都没有提供，显示帮助信息
error "请提供以下方式之一来创建证书 Secret：

方式1: 使用本地证书文件
  CERT_FILE=/path/to/cert.crt KEY_FILE=/path/to/cert.key $0

方式2: 使用阿里云证书ID（需要 aliyun CLI 配置）
  CERT_ID=your_cert_id $0

方式3: 手动创建 Secret
  kubectl create secret tls $SECRET_NAME \\
    --cert=/path/to/cert.crt \\
    --key=/path/to/cert.key \\
    --namespace=$NAMESPACE"
