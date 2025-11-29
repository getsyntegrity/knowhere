#!/bin/bash

# 日志查看脚本 - 查看ACK集群中API和Worker服务的日志
# 用法: ./view-logs.sh [api|worker|--all|--interactive] [kubectl-logs-options]

# 注意：不使用 set -e，以便在部分Pod无法访问时继续处理其他Pod

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[✓] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[!] $1${NC}"
}

error() {
    echo -e "${RED}[✗] $1${NC}"
}

info() {
    echo -e "${BLUE}[i] $1${NC}"
}

# 显示使用帮助
show_help() {
    cat << EOF
用法: $0 [服务类型] [选项]

服务类型:
  api             查看API服务日志
  worker          查看Worker服务日志
  --all           查看所有服务日志（API + Worker）
  --interactive   交互式选择Pod查看日志

选项:
  -f, --follow              实时跟踪日志（类似tail -f）
  --tail=N                  显示最近N行日志（默认: 100）
  --since=TIME              显示指定时间之后的日志（如: 1h, 30m, 2024-01-01T10:00:00Z）
  --errors                  只显示错误日志（过滤ERROR、WARNING、Exception等）
  -n, --namespace=NAMESPACE 指定命名空间（默认: knowhere）
  -h, --help                显示此帮助信息

示例:
  # 查看所有API服务日志（最近100行）
  $0 api

  # 实时跟踪Worker服务日志
  $0 worker -f

  # 查看所有服务的错误日志
  $0 --all --errors

  # 查看最近1小时的API日志
  $0 api --since 1h

  # 查看最近500行日志
  $0 api --tail=500

  # 交互式选择Pod查看日志
  $0 --interactive

  # 组合使用：查看最近1小时的所有服务错误日志
  $0 --all --errors --since 1h --tail=200
EOF
}

# 从deploy-config.sh读取NAMESPACE（如果存在）
if [ -f "$(dirname "$0")/../../../deploy-config.sh" ]; then
    source "$(dirname "$0")/../../../deploy-config.sh" 2>/dev/null || true
fi

NAMESPACE=${NAMESPACE:-knowhere}

# 解析参数
SERVICE_TYPE=""
FOLLOW=false
TAIL=100
SINCE=""
ERRORS_ONLY=false
INTERACTIVE=false
KUBECTL_ARGS=()

# 解析第一个参数（服务类型或特殊选项）
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

FIRST_ARG="$1"
shift

case "$FIRST_ARG" in
    api|worker)
        SERVICE_TYPE="$FIRST_ARG"
        ;;
    --all)
        SERVICE_TYPE="all"
        ;;
    --interactive)
        INTERACTIVE=true
        ;;
    -h|--help)
        show_help
        exit 0
        ;;
    *)
        error "未知的服务类型: $FIRST_ARG"
        echo ""
        show_help
        exit 1
        ;;
esac

# 解析剩余参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        --tail=*)
            TAIL="${1#*=}"
            shift
            ;;
        --tail)
            TAIL="$2"
            shift 2
            ;;
        --since=*)
            SINCE="${1#*=}"
            KUBECTL_ARGS+=("--since=${SINCE}")
            shift
            ;;
        --since)
            SINCE="$2"
            KUBECTL_ARGS+=("--since=${SINCE}")
            shift 2
            ;;
        --errors)
            ERRORS_ONLY=true
            shift
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --namespace=*)
            NAMESPACE="${1#*=}"
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            # 其他参数直接传递给kubectl logs
            KUBECTL_ARGS+=("$1")
            shift
            ;;
    esac
done

# 检查命名空间是否存在
if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
    error "命名空间 '$NAMESPACE' 不存在"
    exit 1
fi

# 获取Pod列表
get_pods() {
    local app_label="$1"
    kubectl get pods -n "$NAMESPACE" -l "app=$app_label" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null
}

# 显示Pod日志
show_pod_logs() {
    local pod_name="$1"
    local service_type="$2"
    local color="$3"
    
    # 检查Pod是否存在
    if ! kubectl get pod "$pod_name" -n "$NAMESPACE" &>/dev/null; then
        warn "Pod '$pod_name' 不存在或无法访问"
        return 1
    fi
    
    echo -e "${color}=========================================="
    echo -e "Pod: $pod_name (${service_type})"
    echo -e "==========================================${NC}"
    
    local cmd_args=("kubectl" "logs" "$pod_name" "-n" "$NAMESPACE")
    
    if [ "$FOLLOW" = true ]; then
        cmd_args+=("-f")
    else
        cmd_args+=("--tail=$TAIL")
    fi
    
    # 添加其他kubectl参数
    cmd_args+=("${KUBECTL_ARGS[@]}")
    
    if [ "$ERRORS_ONLY" = true ]; then
        # 过滤错误日志
        if ! "${cmd_args[@]}" 2>&1 | grep -iE "error|warning|exception|fatal|critical|traceback|failed" --color=always; then
            echo -e "${YELLOW}未找到错误日志${NC}"
        fi
    else
        # 执行日志命令，即使失败也继续
        "${cmd_args[@]}" 2>&1 || {
            warn "无法获取Pod '$pod_name' 的日志（可能Pod未就绪或容器未启动）"
        }
    fi
    
    echo ""
}

# 显示所有Pod的日志（聚合显示）
show_all_pods_logs() {
    local app_label="$1"
    local service_type="$2"
    local color="$3"
    
    local pods=($(get_pods "$app_label"))
    
    if [ ${#pods[@]} -eq 0 ]; then
        warn "未找到 ${service_type} 服务的Pod"
        return
    fi
    
    echo -e "${color}=========================================="
    echo -e "${service_type} 服务日志 (${#pods[@]} 个Pod)"
    echo -e "==========================================${NC}"
    echo ""
    
    if [ ${#pods[@]} -eq 1 ]; then
        # 只有一个Pod，直接显示
        show_pod_logs "${pods[0]}" "$service_type" "$color"
    else
        # 多个Pod，逐个显示
        for pod in "${pods[@]}"; do
            show_pod_logs "$pod" "$service_type" "$color"
        done
    fi
}

# 交互式选择Pod
interactive_select() {
    echo "=========================================="
    echo "交互式Pod选择"
    echo "=========================================="
    echo ""
    
    # 获取所有API和Worker Pod
    local api_pods=($(get_pods "knowhere-api"))
    local worker_pods=($(get_pods "knowhere-worker"))
    
    local all_pods=()
    local pod_types=()
    
    # 添加API Pods
    for pod in "${api_pods[@]}"; do
        all_pods+=("$pod")
        pod_types+=("api")
    done
    
    # 添加Worker Pods
    for pod in "${worker_pods[@]}"; do
        all_pods+=("$pod")
        pod_types+=("worker")
    done
    
    if [ ${#all_pods[@]} -eq 0 ]; then
        error "未找到任何Pod"
        exit 1
    fi
    
    echo "可用的Pod列表:"
    echo ""
    local index=1
    for i in "${!all_pods[@]}"; do
        local pod="${all_pods[$i]}"
        local type="${pod_types[$i]}"
        local color="${CYAN}"
        if [ "$type" = "api" ]; then
            color="${BLUE}"
        elif [ "$type" = "worker" ]; then
            color="${MAGENTA}"
        fi
        echo -e "  ${color}[$index]${NC} $pod (${type})"
        ((index++))
    done
    echo ""
    echo -e "  ${GREEN}[a]${NC} 查看所有Pod日志"
    echo -e "  ${GREEN}[q]${NC} 退出"
    echo ""
    
    read -p "请选择Pod编号 (1-${#all_pods[@]}, a, q): " choice
    
    case "$choice" in
        q|Q)
            info "退出"
            exit 0
            ;;
        a|A)
            # 显示所有Pod日志
            for i in "${!all_pods[@]}"; do
                local pod="${all_pods[$i]}"
                local type="${pod_types[$i]}"
                local color="${BLUE}"
                if [ "$type" = "worker" ]; then
                    color="${MAGENTA}"
                fi
                show_pod_logs "$pod" "$type" "$color"
            done
            ;;
        [0-9]*)
            if [ "$choice" -ge 1 ] && [ "$choice" -le ${#all_pods[@]} ]; then
                local selected_index=$((choice - 1))
                local selected_pod="${all_pods[$selected_index]}"
                local selected_type="${pod_types[$selected_index]}"
                local color="${BLUE}"
                if [ "$selected_type" = "worker" ]; then
                    color="${MAGENTA}"
                fi
                show_pod_logs "$selected_pod" "$selected_type" "$color"
            else
                error "无效的选择: $choice"
                exit 1
            fi
            ;;
        *)
            error "无效的选择: $choice"
            exit 1
            ;;
    esac
}

# 主逻辑
main() {
    info "命名空间: $NAMESPACE"
    
    if [ "$INTERACTIVE" = true ]; then
        interactive_select
        return
    fi
    
    case "$SERVICE_TYPE" in
        api)
            show_all_pods_logs "knowhere-api" "API" "${BLUE}"
            ;;
        worker)
            show_all_pods_logs "knowhere-worker" "Worker" "${MAGENTA}"
            ;;
        all)
            show_all_pods_logs "knowhere-api" "API" "${BLUE}"
            echo ""
            show_all_pods_logs "knowhere-worker" "Worker" "${MAGENTA}"
            ;;
        *)
            error "未知的服务类型: $SERVICE_TYPE"
            exit 1
            ;;
    esac
}

# 执行主逻辑
main

