#!/bin/bash
# 验证部署方案完整性脚本

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
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

# 检查函数
check_file() {
    local file_path="$1"
    local description="$2"
    
    if [ -f "$file_path" ]; then
        log "✅ $description: $file_path"
        return 0
    else
        error "❌ 缺少文件: $description ($file_path)"
        return 1
    fi
}

check_executable() {
    local file_path="$1"
    local description="$2"
    
    if [ -f "$file_path" ] && [ -x "$file_path" ]; then
        log "✅ $description: $file_path (可执行)"
        return 0
    elif [ -f "$file_path" ]; then
        warn "⚠️  $description: $file_path (存在但不可执行)"
        return 1
    else
        error "❌ 缺少文件: $description ($file_path)"
        return 1
    fi
}

# 主验证函数
main() {
    local exit_code=0
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local deploy_dir="$(dirname "$script_dir")"
    
    log "开始验证Knowhere EC2部署方案完整性..."
    log "部署目录: $deploy_dir"
    log ""
    
    # 检查目录结构
    log "检查目录结构..."
    local dirs=(
        "$deploy_dir/terraform"
        "$deploy_dir/scripts"
        "$deploy_dir/systemd"
        "$deploy_dir/nginx"
        "$deploy_dir/config"
        "$deploy_dir/user-data"
        "$deploy_dir/docs"
    )
    
    for dir in "${dirs[@]}"; do
        if [ -d "$dir" ]; then
            log "✅ 目录存在: $dir"
        else
            error "❌ 缺少目录: $dir"
            ((exit_code++))
        fi
    done
    log ""
    
    # 检查Terraform文件
    log "检查Terraform配置文件..."
    local terraform_files=(
        "$deploy_dir/terraform/main.tf"
        "$deploy_dir/terraform/variables.tf"
        "$deploy_dir/terraform/outputs.tf"
        "$deploy_dir/terraform/ec2-instances.tf"
        "$deploy_dir/terraform/iam.tf"
        "$deploy_dir/terraform/security-groups.tf"
        "$deploy_dir/terraform/vpc.tf"
        "$deploy_dir/terraform/alb.tf"
        "$deploy_dir/terraform/database.tf"
        "$deploy_dir/terraform/s3.tf"
        "$deploy_dir/terraform/cloudwatch.tf"
        "$deploy_dir/terraform/terraform.tfvars.example"
    )
    
    for file in "${terraform_files[@]}"; do
        check_file "$file" "Terraform配置" || ((exit_code++))
    done
    log ""
    
    # 检查脚本文件
    log "检查部署脚本..."
    local script_files=(
        "$deploy_dir/scripts/provision-instance.sh"
        "$deploy_dir/scripts/deploy.sh"
        "$deploy_dir/scripts/deploy-app.sh"
        "$deploy_dir/scripts/health-check.sh"
    )
    
    for file in "${script_files[@]}"; do
        check_executable "$file" "部署脚本" || ((exit_code++))
    done
    log ""
    
    # 检查systemd服务文件
    log "检查systemd服务配置..."
    local systemd_files=(
        "$deploy_dir/systemd/knowhere-api.service"
        "$deploy_dir/systemd/knowhere-web.service"
        "$deploy_dir/systemd/knowhere-worker.service"
        "$deploy_dir/systemd/knowhere-scheduler.service"
    )
    
    for file in "${systemd_files[@]}"; do
        check_file "$file" "systemd服务配置" || ((exit_code++))
    done
    log ""
    
    # 检查Nginx配置
    log "检查Nginx配置..."
    local nginx_files=(
        "$deploy_dir/nginx/knowhere.conf"
        "$deploy_dir/nginx/nginx.conf"
        "$deploy_dir/nginx/ssl-params.conf"
    )
    
    for file in "${nginx_files[@]}"; do
        check_file "$file" "Nginx配置" || ((exit_code++))
    done
    log ""
    
    # 检查配置文件
    log "检查配置文件..."
    local config_files=(
        "$deploy_dir/config/env.template"
    )
    
    for file in "${config_files[@]}"; do
        check_file "$file" "配置模板" || ((exit_code++))
    done
    log ""
    
    # 检查用户数据脚本
    log "检查用户数据脚本..."
    check_executable "$deploy_dir/user-data/ecs-instance-init.sh" "EC2用户数据脚本" || ((exit_code++))
    log ""
    
    # 检查文档
    log "检查文档..."
    local doc_files=(
        "$deploy_dir/README.md"
        "$deploy_dir/docs/DEPLOYMENT_GUIDE.md"
        "$deploy_dir/SUMMARY.md"
    )
    
    for file in "${doc_files[@]}"; do
        check_file "$file" "文档" || ((exit_code++))
    done
    log ""
    
    # 检查脚本语法
    log "检查脚本语法..."
    local scripts=(
        "$deploy_dir/scripts/provision-instance.sh"
        "$deploy_dir/scripts/deploy.sh"
        "$deploy_dir/scripts/deploy-app.sh"
        "$deploy_dir/scripts/health-check.sh"
        "$deploy_dir/user-data/ecs-instance-init.sh"
    )
    
    for script in "${scripts[@]}"; do
        if [ -f "$script" ]; then
            if bash -n "$script" 2>/dev/null; then
                log "✅ 语法正确: $(basename "$script")"
            else
                error "❌ 语法错误: $(basename "$script")"
                ((exit_code++))
            fi
        fi
    done
    log ""
    
    # 检查Terraform语法（如果已初始化）
    log "检查Terraform语法..."
    cd "$deploy_dir/terraform"
    if [ -d ".terraform" ]; then
        if terraform validate >/dev/null 2>&1; then
            log "✅ Terraform配置语法正确"
        else
            warn "⚠️  Terraform配置有语法错误（可能需要先运行 terraform init）"
        fi
    else
        info "ℹ️  Terraform未初始化，跳过语法检查"
    fi
    log ""
    
    # 总结
    log "=================="
    if [ $exit_code -eq 0 ]; then
        log "🎉 验证完成！所有文件都已正确创建，可以开始部署。"
        log ""
        log "下一步操作："
        log "1. 配置AWS凭证: aws configure"
        log "2. 编辑Terraform变量: cp terraform.tfvars.example terraform.tfvars"
        log "3. 开始部署: ./scripts/deploy.sh"
    else
        error "❌ 发现 $exit_code 个问题，请修复后再试。"
    fi
    
    exit $exit_code
}

# 运行主函数
main "$@"
