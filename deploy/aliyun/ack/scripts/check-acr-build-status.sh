#!/bin/bash

# 查看 ACR 构建状态的脚本

set -e

# 配置变量
REGION=${REGION:-cn-shenzhen}
INSTANCE_ID=${ACR_INSTANCE_ID:-cri-z93nsm8wu1g4ibdx}

# 仓库ID
REPO_IDS=(
    "crr-ua9mzfc25axbuov0"   # knowhereapi (backend)
    "crr-0q6lwm0detawy4im"   # knowhereweb (frontend)
    "crr-gxbxwfkvwzv62vre"   # knowhereworker (worker)
)

# 组件名称
COMPONENTS=("backend" "frontend" "worker")

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

# 查看单个仓库的构建记录
check_repo_builds() {
    local repo_id=$1
    local component=$2
    local page_size=${3:-5}
    
    log "查询 $component 构建记录..."
    
    local result=$(aliyun cr ListRepoBuildRecord \
        --region $REGION \
        --InstanceId $INSTANCE_ID \
        --RepoId $repo_id \
        --PageSize $page_size 2>&1)
    
    if [ $? -eq 0 ]; then
        local records=$(echo "$result" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if data.get('IsSuccess') and 'BuildRecords' in data:
        records = data['BuildRecords']
        for record in records:
            build_id = record.get('BuildRecordId', '')
            status = record.get('BuildStatus', '')
            start_time = record.get('StartTime', 0)
            image = record.get('Image', {})
            repo_name = image.get('RepoName', '')
            image_tag = image.get('ImageTag', '')
            
            # 转换时间戳
            from datetime import datetime
            if start_time:
                dt = datetime.fromtimestamp(start_time / 1000)
                time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            else:
                time_str = 'N/A'
            
            print(f\"BuildRecordId: {build_id}\")
            print(f\"Status: {status}\")
            print(f\"StartTime: {time_str}\")
            print(f\"Image: {repo_name}:{image_tag}\")
            print('---')
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null)
        
        if [ -n "$records" ]; then
            echo "$records"
        else
            info "$component 暂无构建记录"
        fi
    else
        warn "$component 查询失败: $result"
    fi
}

# 查看构建日志
view_build_log() {
    local repo_id=$1
    local build_record_id=$2
    local component=$3
    
    if [ -z "$build_record_id" ]; then
        error "构建记录ID未提供"
        return 1
    fi
    
    log "查看 $component 构建日志 (记录ID: $build_record_id)..."
    
    local result=$(aliyun cr ListRepoBuildRecordLog \
        --region $REGION \
        --InstanceId $INSTANCE_ID \
        --RepoId $repo_id \
        --BuildRecordId $build_record_id 2>&1)
    
    if [ $? -eq 0 ]; then
        echo "$result" | python3 -m json.tool 2>/dev/null || echo "$result"
    else
        warn "获取构建日志失败: $result"
    fi
}

# 主函数
main() {
    local action=${1:-status}  # status 或 log
    local component=${2:-}     # 组件名称（可选）
    local build_record_id=${3:-}  # 构建记录ID（查看日志时需要）
    
    log "ACR 构建状态查询"
    log "地域: $REGION"
    log "实例ID: $INSTANCE_ID"
    echo ""
    
    case $action in
        status)
            # 查看所有组件的构建状态
            for i in "${!COMPONENTS[@]}"; do
                component_name=${COMPONENTS[$i]}
                repo_id=${REPO_IDS[$i]}
                
                if [ -z "$component" ] || [ "$component" == "$component_name" ]; then
                    check_repo_builds "$repo_id" "$component_name"
                    echo ""
                fi
            done
            ;;
        log)
            # 查看构建日志
            if [ -z "$build_record_id" ]; then
                error "查看日志需要提供构建记录ID"
                echo "用法: $0 log <component> <build_record_id>"
                exit 1
            fi
            
            # 根据组件名称找到对应的仓库ID
            local repo_id=""
            for i in "${!COMPONENTS[@]}"; do
                if [ "${COMPONENTS[$i]}" == "$component" ]; then
                    repo_id=${REPO_IDS[$i]}
                    break
                fi
            done
            
            if [ -z "$repo_id" ]; then
                error "未知的组件名称: $component"
                echo "支持的组件: ${COMPONENTS[*]}"
                exit 1
            fi
            
            view_build_log "$repo_id" "$build_record_id" "$component"
            ;;
        *)
            echo "用法: $0 [status|log] [component] [build_record_id]"
            echo ""
            echo "示例:"
            echo "  $0 status              # 查看所有组件的构建状态"
            echo "  $0 status backend     # 查看 backend 的构建状态"
            echo "  $0 log backend <id>   # 查看 backend 的构建日志"
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"

