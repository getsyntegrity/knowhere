#!/bin/bash

# ECS Fargate部署脚本

set -e

# 配置变量
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID}
PROJECT_NAME=${PROJECT_NAME:-knowhere}
TERRAFORM_DIR="deploy/aws/terraform"

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

# 检查必要的环境变量
check_requirements() {
    log "检查环境变量..."
    
    if [ -z "$AWS_ACCOUNT_ID" ]; then
        error "AWS_ACCOUNT_ID 环境变量未设置"
    fi
    
    if ! command -v aws &> /dev/null; then
        error "AWS CLI 未安装"
    fi
    
    if ! command -v terraform &> /dev/null; then
        error "Terraform 未安装"
    fi
    
    log "环境检查通过"
}

# 初始化Terraform
init_terraform() {
    log "初始化Terraform..."
    cd $TERRAFORM_DIR
    terraform init
    cd - > /dev/null
}

# 规划Terraform
plan_terraform() {
    log "规划Terraform变更..."
    cd $TERRAFORM_DIR
    terraform plan -out=tfplan
    cd - > /dev/null
}

# 应用Terraform
apply_terraform() {
    log "应用Terraform配置..."
    cd $TERRAFORM_DIR
    terraform apply tfplan
    cd - > /dev/null
}

# 创建ECS任务定义
create_task_definitions() {
    log "创建ECS任务定义..."
    
    # 获取Terraform输出
    cd $TERRAFORM_DIR
    ECR_BACKEND_URL=$(terraform output -raw ecr_backend_repository_url)
    ECR_FRONTEND_URL=$(terraform output -raw ecr_frontend_repository_url)
    VPC_ID=$(terraform output -raw vpc_id)
    PUBLIC_SUBNETS=$(terraform output -json public_subnet_ids | jq -r '.[]' | tr '\n' ',' | sed 's/,$//')
    PRIVATE_SUBNETS=$(terraform output -json private_subnet_ids | jq -r '.[]' | tr '\n' ',' | sed 's/,$//')
    BACKEND_TG_ARN=$(terraform output -raw backend_target_group_arn)
    FRONTEND_TG_ARN=$(terraform output -raw frontend_target_group_arn)
    ECS_CLUSTER_ARN=$(terraform output -raw ecs_cluster_arn)
    cd - > /dev/null
    
    # 更新任务定义中的镜像URL
    sed "s|YOUR_ACCOUNT_ID.dkr.ecr.YOUR_REGION.amazonaws.com/knowhere-backend:latest|$ECR_BACKEND_URL:latest|g" \
        deploy/aws/ecs-task-definition-backend.json > /tmp/backend-task-def.json
    
    sed "s|YOUR_ACCOUNT_ID.dkr.ecr.YOUR_REGION.amazonaws.com/knowhere-frontend:latest|$ECR_FRONTEND_URL:latest|g" \
        deploy/aws/ecs-task-definition-frontend.json > /tmp/frontend-task-def.json
    
    # 注册任务定义
    aws ecs register-task-definition \
        --cli-input-json file:///tmp/backend-task-def.json \
        --region $AWS_REGION
    
    aws ecs register-task-definition \
        --cli-input-json file:///tmp/frontend-task-def.json \
        --region $AWS_REGION
    
    log "任务定义创建完成"
}

# 创建ECS服务
create_ecs_services() {
    log "创建ECS服务..."
    
    # 获取安全组ID
    BACKEND_SG=$(aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=${PROJECT_NAME}-ecs-tasks-*" \
        --query 'SecurityGroups[0].GroupId' \
        --output text \
        --region $AWS_REGION)
    
    # 更新服务配置
    sed "s/subnet-xxxxxxxxx,subnet-yyyyyyyyy/$PUBLIC_SUBNETS/g" \
        deploy/aws/ecs-service-backend.json > /tmp/backend-service.json
    sed -i "s/sg-xxxxxxxxx/$BACKEND_SG/g" /tmp/backend-service.json
    sed -i "s/arn:aws:elasticloadbalancing:YOUR_REGION:YOUR_ACCOUNT_ID:targetgroup\/knowhere-backend-tg\/xxxxxxxxx/$BACKEND_TG_ARN/g" /tmp/backend-service.json
    
    sed "s/subnet-xxxxxxxxx,subnet-yyyyyyyyy/$PUBLIC_SUBNETS/g" \
        deploy/aws/ecs-service-frontend.json > /tmp/frontend-service.json
    sed -i "s/sg-yyyyyyyyy/$BACKEND_SG/g" /tmp/frontend-service.json
    sed -i "s/arn:aws:elasticloadbalancing:YOUR_REGION:YOUR_ACCOUNT_ID:targetgroup\/knowhere-frontend-tg\/yyyyyyyyy/$FRONTEND_TG_ARN/g" /tmp/frontend-service.json
    
    # 更新Worker服务配置
    sed "s/subnet-xxxxxxxxx,subnet-yyyyyyyyy/$PUBLIC_SUBNETS/g" \
        deploy/aws/ecs-service-worker.json > /tmp/worker-service.json
    sed -i "s/sg-xxxxxxxxx/$BACKEND_SG/g" /tmp/worker-service.json
    
    # 创建服务
    aws ecs create-service \
        --cli-input-json file:///tmp/backend-service.json \
        --region $AWS_REGION || warn "后端服务可能已存在"
    
    aws ecs create-service \
        --cli-input-json file:///tmp/frontend-service.json \
        --region $AWS_REGION || warn "前端服务可能已存在"
    
    # 创建Worker服务
    aws ecs create-service \
        --cli-input-json file:///tmp/worker-service.json \
        --region $AWS_REGION || warn "Worker服务可能已存在"
    
    log "ECS服务创建完成"
}

# 等待服务稳定
wait_for_services() {
    log "等待服务稳定..."
    
    aws ecs wait services-stable \
        --cluster $PROJECT_NAME-cluster \
        --services $PROJECT_NAME-backend-service \
        --region $AWS_REGION
    
    aws ecs wait services-stable \
        --cluster $PROJECT_NAME-cluster \
        --services $PROJECT_NAME-frontend-service \
        --region $AWS_REGION
    
    aws ecs wait services-stable \
        --cluster $PROJECT_NAME-cluster \
        --services $PROJECT_NAME-worker-service \
        --region $AWS_REGION
    
    log "服务已稳定"
}

# 显示部署信息
show_deployment_info() {
    log "部署完成！"
    
    cd $TERRAFORM_DIR
    ALB_DNS=$(terraform output -raw alb_dns_name)
    DOMAIN_NAME=$(terraform output -raw domain_name)
    API_DOMAIN=$(terraform output -raw api_domain_name)
    cd - > /dev/null
    
    info "负载均衡器DNS: $ALB_DNS"
    info "主域名: $DOMAIN_NAME"
    info "API域名: $API_DOMAIN"
    info "ECS集群: $PROJECT_NAME-cluster"
    
    log "请等待DNS传播完成，然后访问: https://$DOMAIN_NAME"
}

# 主函数
main() {
    case "${1:-all}" in
        "infrastructure")
            log "仅部署基础设施..."
            check_requirements
            init_terraform
            plan_terraform
            apply_terraform
            ;;
        "services")
            log "仅部署ECS服务..."
            check_requirements
            create_task_definitions
            create_ecs_services
            wait_for_services
            ;;
        "all")
            log "完整部署..."
            check_requirements
            init_terraform
            plan_terraform
            apply_terraform
            create_task_definitions
            create_ecs_services
            wait_for_services
            show_deployment_info
            ;;
        *)
            error "未知选项: $1. 使用: infrastructure, services, 或 all"
            ;;
    esac
}

# 运行主函数
main "$@"
