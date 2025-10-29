#!/bin/bash
# 完整部署脚本
# 部署基础设施和应用

set -e

# 配置变量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"
PROJECT_NAME="knowhere"
ENVIRONMENT="test"

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

# 检查必要的工具
check_requirements() {
    log "检查环境要求..."
    
    if ! command -v terraform &> /dev/null; then
        error "Terraform未安装"
    fi
    
    if ! command -v aliyun &> /dev/null; then
        warn "阿里云CLI未安装，某些功能可能不可用"
    fi
    
    if ! command -v git &> /dev/null; then
        error "Git未安装"
    fi
    
    log "环境检查通过"
}

# 检查阿里云凭证
check_aliyun_credentials() {
    log "检查阿里云凭证..."
    
    if [ -z "$ALICLOUD_ACCESS_KEY" ] && [ -z "$ALICLOUD_SECRET_KEY" ]; then
        warn "未设置环境变量ALICLOUD_ACCESS_KEY和ALICLOUD_SECRET_KEY，请确保在terraform.tfvars中配置"
    fi
    
    log "凭证检查完成"
}

# 部署基础设施
deploy_infrastructure() {
    log "部署基础设施..."
    
    cd "$TERRAFORM_DIR"
    
    # 初始化Terraform
    log "初始化Terraform..."
    terraform init
    
    # 规划部署
    log "规划Terraform变更..."
    terraform plan -out=tfplan
    
    # 应用配置
    log "应用Terraform配置..."
    terraform apply tfplan
    
    # 获取输出
    INSTANCE_IP=$(terraform output -raw instance_public_ip)
    API_URL=$(terraform output -raw api_url)
    WEB_URL=$(terraform output -raw web_url)
    
    log "基础设施部署完成"
    log "实例IP: $INSTANCE_IP"
    log "API URL: $API_URL"
    log "Web URL: $WEB_URL"
}

# 等待实例就绪
wait_for_instance() {
    log "等待实例就绪..."
    
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no root@$INSTANCE_IP "echo 'Instance is ready'" &> /dev/null; then
            log "实例已就绪"
            return 0
        fi
        
        log "等待实例就绪... ($attempt/$max_attempts)"
        sleep 10
        ((attempt++))
    done
    
    error "实例在预期时间内未就绪"
}

# 部署应用
deploy_application() {
    log "部署应用..."
    
    # 复制部署脚本到实例
    log "复制部署脚本到实例..."
    scp -o StrictHostKeyChecking=no -r "$SCRIPT_DIR" root@$INSTANCE_IP:/tmp/
    
    # 在实例上运行配置脚本
    log "在实例上运行配置脚本..."
    ssh -o StrictHostKeyChecking=no root@$INSTANCE_IP "
        sudo cp -r /tmp/scripts /opt/knowhere/deploy/aliyun-ecs/
        sudo chmod +x /opt/knowhere/deploy/aliyun-ecs/scripts/*.sh
        sudo /opt/knowhere/deploy/aliyun-ecs/scripts/provision-instance.sh
    "
    
    log "应用部署完成"
}

# 配置DNS（提示用户）
configure_dns() {
    log "DNS配置提示..."
    
    info "请在DNS服务提供商中配置以下DNS记录："
    info "A记录: apitest.knowhereto.ai -> $INSTANCE_IP"
    info "A记录: test.knowhereto.ai -> $INSTANCE_IP"
    info ""
    info "配置完成后，可以访问："
    info "API: $API_URL"
    info "Web: $WEB_URL"
}

# 健康检查
health_check() {
    log "执行健康检查..."
    
    # 等待服务启动
    sleep 30
    
    # 检查API健康
    if curl -f -s "$API_URL/health" > /dev/null; then
        log "API健康检查通过"
    else
        warn "API健康检查失败"
    fi
    
    # 检查Web健康
    if curl -f -s "$WEB_URL" > /dev/null; then
        log "Web健康检查通过"
    else
        warn "Web健康检查失败"
    fi
}

# 显示部署信息
show_deployment_info() {
    log "部署完成！"
    log ""
    log "部署信息："
    log "  实例IP: $INSTANCE_IP"
    log "  API URL: $API_URL"
    log "  Web URL: $WEB_URL"
    log ""
    log "SSH连接命令："
    log "  ssh root@$INSTANCE_IP"
    log ""
    log "服务管理命令："
    log "  sudo systemctl status knowhere-api"
    log "  sudo systemctl status knowhere-web"
    log "  sudo systemctl status knowhere-worker"
    log ""
    log "查看日志："
    log "  knowhere-logs.sh api"
    log "  knowhere-logs.sh web"
    log "  knowhere-logs.sh worker"
}

# 主函数
main() {
    log "开始Knowhere部署..."
    
    check_requirements
    check_aliyun_credentials
    deploy_infrastructure
    wait_for_instance
    deploy_application
    configure_dns
    health_check
    show_deployment_info
    
    log "部署完成！"
}

# 运行主函数
main "$@"

