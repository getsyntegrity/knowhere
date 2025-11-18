#!/bin/bash

# 触发 ACR 构建的脚本
# 用于手动触发三个组件（backend/frontend/worker）的构建

set -e

# 配置变量
REGION=${REGION:-cn-shenzhen}
INSTANCE_ID=${ACR_INSTANCE_ID:-cri-z93nsm8wu1g4ibdx}
NAMESPACE=${NAMESPACE:-knowhere}
ENVIRONMENT=${ENVIRONMENT:-dev}
BRANCH=${BRANCH:-dev}  # 构建分支，根据构建规则配置

# 仓库ID（从 ACR 控制台获取）
REPO_IDS=(
    "crr-ua9mzfc25axbuov0"   # knowhereapi (backend)
    "crr-0q6lwm0detawy4im"   # knowhereweb (frontend)
    "crr-gxbxwfkvwzv62vre"   # knowhereworker (worker)
)

# 构建规则ID（从 ACR 控制台获取）
BUILD_RULE_IDS=(
    "crbr-qnqlnewzxj10ofxn"  # backend 构建规则
    "crbr-g4oqw2etcu7xj6ee"  # frontend 构建规则
    "crbr-oh25bn7qxylbbkia"  # worker 构建规则
)

# 组件名称
COMPONENTS=("backend" "frontend" "worker")

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

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

# 检查 aliyun CLI
check_aliyun_cli() {
    if ! command -v aliyun &> /dev/null; then
        error "aliyun CLI 未安装，请先安装: https://help.aliyun.com/document_detail/121851.html"
    fi
    log "aliyun CLI 检查通过"
}

# 触发单个构建
trigger_build() {
    local repo_id=$1
    local build_rule_id=$2
    local component=$3
    
    if [ -z "$repo_id" ] || [ -z "$build_rule_id" ]; then
        warn "仓库ID或构建规则ID未设置，跳过 $component"
        return 1
    fi
    
    log "触发 $component 构建..."
    log "  仓库ID: $repo_id"
    log "  构建规则ID: $build_rule_id"
    
    # 调用 ACR API 触发构建
    local result=$(aliyun cr CreateBuildRecordByRule \
        --region $REGION \
        --InstanceId $INSTANCE_ID \
        --RepoId $repo_id \
        --BuildRuleId $build_rule_id 2>&1)
    
    if [ $? -eq 0 ]; then
        # 提取 BuildRecordId
        local build_record_id=$(echo "$result" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('BuildRecordId', ''))" 2>/dev/null || echo "")
        
        if [ -n "$build_record_id" ]; then
            log "✅ $component 构建已触发"
            log "  构建记录ID: $build_record_id"
            echo "$build_record_id"
            return 0
        else
            warn "$component 构建触发响应异常: $result"
            return 1
        fi
    else
        warn "$component 构建触发失败: $result"
        return 1
    fi
}

# 查看构建状态
check_build_status() {
    local build_record_id=$1
    local component=$2
    
    if [ -z "$build_record_id" ]; then
        return 1
    fi
    
    log "查询 $component 构建状态 (记录ID: $build_record_id)..."
    
    # 注意：GetRepoBuildRecordStatus API 可能需要不同的参数
    # 这里先列出构建记录来查看状态
    local result=$(aliyun cr ListRepoBuildRecord \
        --region $REGION \
        --InstanceId $INSTANCE_ID \
        --RepoId ${REPO_IDS[0]} 2>&1 | python3 -m json.tool 2>/dev/null || echo "")
    
    if [ -n "$result" ]; then
        echo "$result" | grep -A 10 "$build_record_id" || true
    fi
}

# 主函数
main() {
    log "开始触发 ACR 构建..."
    log "地域: $REGION"
    log "实例ID: $INSTANCE_ID"
    log "命名空间: $NAMESPACE"
    log "环境: $ENVIRONMENT"
    log "分支: $BRANCH"
    echo ""
    
    check_aliyun_cli
    
    # 存储构建记录ID
    declare -a build_record_ids
    
    # 触发三个组件的构建
    for i in "${!COMPONENTS[@]}"; do
        component=${COMPONENTS[$i]}
        repo_id=${REPO_IDS[$i]}
        build_rule_id=${BUILD_RULE_IDS[$i]}
        
        build_record_id=$(trigger_build "$repo_id" "$build_rule_id" "$component")
        if [ -n "$build_record_id" ]; then
            build_record_ids+=("$build_record_id")
        fi
        echo ""
    done
    
    # 输出结果
    log "构建触发完成！"
    echo ""
    log "构建记录ID:"
    for i in "${!build_record_ids[@]}"; do
        echo "  ${COMPONENTS[$i]}: ${build_record_ids[$i]}"
    done
    echo ""
    log "请在 ACR 控制台查看构建日志:"
    log "  https://cr.console.aliyun.com/cn-shenzhen/instances/$INSTANCE_ID/build"
    echo ""
    log "或使用以下命令查看构建记录:"
    for i in "${!COMPONENTS[@]}"; do
        echo "  aliyun cr ListRepoBuildRecord --region $REGION --InstanceId $INSTANCE_ID --RepoId ${REPO_IDS[$i]}"
    done
}

# 运行主函数
main "$@"

