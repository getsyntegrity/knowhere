#!/bin/bash
# Knowhere应用日志查看脚本

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

usage() {
    echo "用法: $0 [service] [options]"
    echo ""
    echo "服务:"
    echo "  api       - 查看API服务日志"
    echo "  web       - 查看Web服务日志"
    echo "  worker    - 查看Worker服务日志"
    echo "  all       - 查看所有服务日志"
    echo ""
    echo "选项:"
    echo "  -f, --follow     - 实时跟踪日志"
    echo "  -n, --lines N    - 显示最后N行日志"
    echo "  -e, --errors     - 只显示错误日志"
    echo "  -h, --help       - 显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 api -f          # 实时跟踪API日志"
    echo "  $0 web -n 100      # 显示Web服务最后100行日志"
    echo "  $0 all -e          # 显示所有服务的错误日志"
}

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

# 默认参数
SERVICE=""
FOLLOW=false
LINES=50
ERRORS_ONLY=false

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -n|--lines)
            LINES="$2"
            shift 2
            ;;
        -e|--errors)
            ERRORS_ONLY=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        api|web|worker|all)
            SERVICE="$1"
            shift
            ;;
        *)
            error "未知参数: $1"
            usage
            exit 1
            ;;
    esac
done

# 检查服务参数
if [ -z "$SERVICE" ]; then
    error "请指定要查看的服务"
    usage
    exit 1
fi

# 构建journalctl命令
build_journalctl_cmd() {
    local service_name=$1
    local cmd="journalctl -u $service_name"
    
    if [ "$FOLLOW" = true ]; then
        cmd="$cmd -f"
    else
        cmd="$cmd -n $LINES"
    fi
    
    if [ "$ERRORS_ONLY" = true ]; then
        cmd="$cmd --priority=err"
    fi
    
    echo "$cmd"
}

# 显示服务日志
show_service_logs() {
    local service_name=$1
    local service_display_name=$2
    
    log "显示 $service_display_name 服务日志..."
    
    if ! systemctl list-units --type=service | grep -q "$service_name"; then
        warn "$service_display_name 服务未安装或未运行"
        return 1
    fi
    
    local cmd=$(build_journalctl_cmd "$service_name")
    echo -e "${BLUE}=== $service_display_name 服务日志 ===${NC}"
    eval "$cmd"
    echo ""
}

# 主函数
main() {
    case $SERVICE in
        api)
            show_service_logs "knowhere-api" "API"
            ;;
        web)
            show_service_logs "knowhere-web" "Web"
            ;;
        worker)
            show_service_logs "knowhere-worker" "Worker"
            ;;
        all)
            show_service_logs "knowhere-api" "API"
            show_service_logs "knowhere-web" "Web"
            show_service_logs "knowhere-worker" "Worker"
            ;;
        *)
            error "未知服务: $SERVICE"
            usage
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"
