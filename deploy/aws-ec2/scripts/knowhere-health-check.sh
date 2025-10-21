#!/bin/bash
# Knowhere应用健康检查脚本

set -e

# 配置变量
API_URL="http://localhost:5005"
WEB_URL="http://localhost:3000"
API_HEALTH_ENDPOINT="/health"
WEB_HEALTH_ENDPOINT="/api/health"

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

# 检查服务是否运行
check_service() {
    local service_name=$1
    local port=$2
    local url=$3
    
    log "检查 $service_name 服务..."
    
    # 检查端口是否监听
    if ! netstat -tlnp | grep -q ":$port "; then
        error "$service_name 服务未在端口 $port 上监听"
        return 1
    fi
    
    # 检查HTTP响应
    if command -v curl >/dev/null 2>&1; then
        local health_endpoint
        if [ "$service_name" = "API" ]; then
            health_endpoint="$API_HEALTH_ENDPOINT"
        else
            health_endpoint="$WEB_HEALTH_ENDPOINT"
        fi
        
        if curl -s -f "$url$health_endpoint" >/dev/null 2>&1; then
            log "$service_name 健康检查通过"
        else
            warn "$service_name 健康检查端点无响应，但服务正在运行"
        fi
    else
        log "$service_name 服务正在运行（端口 $port）"
    fi
    
    return 0
}

# 检查systemd服务状态
check_systemd_service() {
    local service_name=$1
    
    if systemctl is-active --quiet "$service_name"; then
        log "$service_name systemd服务正在运行"
        return 0
    else
        error "$service_name systemd服务未运行"
        return 1
    fi
}

# 主检查函数
main() {
    log "开始健康检查..."
    
    local exit_code=0
    
    # 检查API服务
    if ! check_systemd_service "knowhere-api"; then
        exit_code=1
    fi
    
    if ! check_service "API" "5005" "$API_URL"; then
        exit_code=1
    fi
    
    # 检查Web服务
    if ! check_systemd_service "knowhere-web"; then
        exit_code=1
    fi
    
    if ! check_service "Web" "3000" "$WEB_URL"; then
        exit_code=1
    fi
    
    # 检查Worker服务
    if ! check_systemd_service "knowhere-worker"; then
        exit_code=1
    fi
    
    
    # 检查系统资源
    log "检查系统资源..."
    
    # 检查内存使用
    local memory_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    if (( $(echo "$memory_usage > 90" | bc -l) )); then
        warn "内存使用率过高: ${memory_usage}%"
    else
        log "内存使用率正常: ${memory_usage}%"
    fi
    
    # 检查磁盘空间
    local disk_usage=$(df /opt | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ "$disk_usage" -gt 90 ]; then
        warn "磁盘使用率过高: ${disk_usage}%"
    else
        log "磁盘使用率正常: ${disk_usage}%"
    fi
    
    if [ $exit_code -eq 0 ]; then
        log "所有健康检查通过！"
    else
        error "部分健康检查失败"
    fi
    
    exit $exit_code
}

# 运行主函数
main "$@"
