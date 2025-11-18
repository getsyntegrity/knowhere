#!/bin/bash
# 创建 GitHub Container Registry Secret 脚本
# 使用方法: ./create-ghcr-secret.sh dev [github-username] [github-token]
#
# 参数说明：
#   $1: 环境名称 (dev/test/prod)
#   $2: GitHub 用户名或组织名（可选，如果不提供会尝试从 git remote 获取）
#   $3: GitHub Personal Access Token（可选，如果不提供会提示输入）

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

# 检查环境参数
ENVIRONMENT=${1:-dev}
if [[ ! "$ENVIRONMENT" =~ ^(dev|test|prod)$ ]]; then
    error "环境必须是: dev, test, 或 prod"
fi

# 获取 GitHub 用户名
GITHUB_USERNAME=${2:-}
if [[ -z "$GITHUB_USERNAME" ]]; then
    # 尝试从 git remote 获取
    if command -v git &> /dev/null; then
        GIT_REMOTE=$(git remote -v 2>/dev/null | head -1 | grep -oP 'github\.com[:/]\K[^/]+' || echo "")
        if [[ -n "$GIT_REMOTE" ]]; then
            GITHUB_USERNAME="$GIT_REMOTE"
            log "从 git remote 检测到 GitHub 用户名: $GITHUB_USERNAME"
        fi
    fi
    
    if [[ -z "$GITHUB_USERNAME" ]]; then
        error "无法自动检测 GitHub 用户名，请提供：./create-ghcr-secret.sh $ENVIRONMENT <github-username>"
    fi
fi

# 获取 GitHub Token
GITHUB_TOKEN=${3:-}
if [[ -z "$GITHUB_TOKEN" ]]; then
    info "需要 GitHub Personal Access Token 来访问私有镜像仓库"
    info "创建 Token 步骤："
    info "  1. 访问：https://github.com/settings/tokens"
    info "  2. 点击 'Generate new token (classic)'"
    info "  3. 设置权限：read:packages"
    info "  4. 生成并复制 token"
    echo ""
    read -sp "请输入 GitHub Personal Access Token: " GITHUB_TOKEN
    echo ""
    
    if [[ -z "$GITHUB_TOKEN" ]]; then
        error "GitHub Token 不能为空"
    fi
fi

# 设置 kubeconfig
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export KUBECONFIG=~/.kube/config-knowhere-$ENVIRONMENT

# 检查 kubeconfig
if [ ! -f "$KUBECONFIG" ]; then
    error "kubeconfig 文件不存在: $KUBECONFIG"
    error "请先运行: cd $SCRIPT_DIR/../terraform && terraform output -raw kubeconfig > $KUBECONFIG"
fi

# 验证 kubeconfig
if ! kubectl cluster-info &> /dev/null; then
    error "无法连接到 Kubernetes 集群，请检查 kubeconfig 配置"
fi

# 创建命名空间（如果不存在）
kubectl create namespace knowhere --dry-run=client -o yaml | kubectl apply -f -

# 创建 Secret
log "创建 GitHub Container Registry Secret..."
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username="$GITHUB_USERNAME" \
  --docker-password="$GITHUB_TOKEN" \
  --namespace=knowhere \
  --dry-run=client -o yaml | kubectl apply -f -

log "✅ GitHub Container Registry Secret 创建成功！"
echo ""
log "验证："
kubectl get secret ghcr-secret -n knowhere
echo ""
info "Secret 名称: ghcr-secret"
info "命名空间: knowhere"
info "镜像仓库: ghcr.io"
info "用户名: $GITHUB_USERNAME"

