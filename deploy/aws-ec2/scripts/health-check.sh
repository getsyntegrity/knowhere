#!/bin/bash
# 健康检查脚本

set -e

# 配置变量
API_URL="http://localhost:5005"
WEB_URL="http://localhost:3000"
HEALTH_URL="$API_URL/health"

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
}

# 检查服务状态
check_service_status() {
    local service_name=$1
    local status=$(systemctl is-active $service_name)
    
    if [ "$status" = "active" ]; then
        log "$service_name: 运行中"
        return 0
    else
        error "$service_name: 未运行 (状态: $status)"
        return 1
    fi
}

# 检查HTTP端点
check_http_endpoint() {
    local url=$1
    local name=$2
    
    if curl -f -s --max-time 10 "$url" > /dev/null; then
        log "$name: 可访问"
        return 0
    else
        error "$name: 不可访问"
        return 1
    fi
}

# 检查端口
check_port() {
    local port=$1
    local name=$2
    
    if netstat -tlnp | grep ":$port " > /dev/null; then
        log "$name: 端口 $port 正在监听"
        return 0
    else
        error "$name: 端口 $port 未监听"
        return 1
    fi
}

# 检查磁盘空间
check_disk_space() {
    local usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    
    if [ "$usage" -lt 80 ]; then
        log "磁盘空间: 正常 ($usage%)"
        return 0
    elif [ "$usage" -lt 90 ]; then
        warn "磁盘空间: 警告 ($usage%)"
        return 1
    else
        error "磁盘空间: 严重 ($usage%)"
        return 1
    fi
}

# 检查内存使用
check_memory() {
    local usage=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
    
    if [ "$usage" -lt 80 ]; then
        log "内存使用: 正常 ($usage%)"
        return 0
    elif [ "$usage" -lt 90 ]; then
        warn "内存使用: 警告 ($usage%)"
        return 1
    else
        error "内存使用: 严重 ($usage%)"
        return 1
    fi
}

# 检查CPU负载
check_cpu_load() {
    local load=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//')
    local cores=$(nproc)
    local load_percent=$(echo "$load * 100 / $cores" | bc)
    
    if [ "$load_percent" -lt 80 ]; then
        log "CPU负载: 正常 ($load_percent%)"
        return 0
    elif [ "$load_percent" -lt 90 ]; then
        warn "CPU负载: 警告 ($load_percent%)"
        return 1
    else
        error "CPU负载: 严重 ($load_percent%)"
        return 1
    fi
}

# 主健康检查
main() {
    local exit_code=0
    
    log "开始健康检查..."
    log "=================="
    
    # 检查服务状态
    log "检查服务状态:"
    check_service_status "knowhere-api" || ((exit_code++))
    check_service_status "knowhere-web" || ((exit_code++))
    check_service_status "knowhere-worker" || ((exit_code++))
    check_service_status "nginx" || ((exit_code++))
    
    log ""
    
    # 检查端口
    log "检查端口:"
    check_port 5005 "API" || ((exit_code++))
    check_port 3000 "Web" || ((exit_code++))
    check_port 80 "Nginx HTTP" || ((exit_code++))
    check_port 443 "Nginx HTTPS" || ((exit_code++))
    
    log ""
    
    # 检查HTTP端点
    log "检查HTTP端点:"
    check_http_endpoint "$HEALTH_URL" "API健康检查" || ((exit_code++))
    check_http_endpoint "$WEB_URL" "Web前端" || ((exit_code++))
    
    log ""
    
    # 检查系统资源
    log "检查系统资源:"
    check_disk_space || ((exit_code++))
    check_memory || ((exit_code++))
    check_cpu_load || ((exit_code++))
    
    log ""
    log "=================="
    
    if [ $exit_code -eq 0 ]; then
        log "所有检查通过！系统健康。"
    else
        error "发现 $exit_code 个问题，请检查上述错误。"
    fi
    
    exit $exit_code
}

# 运行主函数
main "$@"
