#!/bin/bash
# 初始化阿里云 Terraform Backend 资源（OSS Bucket）
# 使用方法：
#   ./init-backend.sh dev
#   ./init-backend.sh test
#   ./init-backend.sh prod

set -e

ENVIRONMENT=${1:-dev}
PROJECT_NAME="knowhere"
REGION=${2:-cn-guangzhou}

if [[ ! "$ENVIRONMENT" =~ ^(dev|test|prod)$ ]]; then
    echo "错误：环境必须是 dev、test 或 prod"
    exit 1
fi

BUCKET_NAME="${PROJECT_NAME}-terraform-state-${ENVIRONMENT}"

echo "=========================================="
echo "初始化阿里云 Terraform Backend - ${ENVIRONMENT} 环境"
echo "=========================================="
echo "项目名称: ${PROJECT_NAME}"
echo "环境: ${ENVIRONMENT}"
echo "区域: ${REGION}"
echo "OSS Bucket: ${BUCKET_NAME}"
echo ""

# 检查阿里云 CLI 是否已配置
if ! command -v aliyun &> /dev/null; then
    echo "错误：阿里云 CLI 未安装"
    echo "请先安装阿里云 CLI: https://help.aliyun.com/document_detail/121258.html"
    exit 1
fi

# 检查是否已配置凭证
if ! aliyun configure get &> /dev/null; then
    echo "错误：阿里云 CLI 未配置或凭证无效"
    echo "请先运行: aliyun configure"
    exit 1
fi

# 创建 OSS Bucket（如果不存在）
echo "检查 OSS Bucket: ${BUCKET_NAME}..."
if ! aliyun oss ls | grep -q "${BUCKET_NAME}"; then
    echo "创建 OSS Bucket: ${BUCKET_NAME}..."
    
    # 创建 bucket
    aliyun oss mb "oss://${BUCKET_NAME}" --region "${REGION}"
    
    # 启用版本控制
    echo "启用 OSS Bucket 版本控制..."
    aliyun oss bucket-versioning --method put "oss://${BUCKET_NAME}" --status Enabled
    
    # 启用加密
    echo "启用 OSS Bucket 加密..."
    aliyun oss bucket-encryption --method put "oss://${BUCKET_NAME}" --sse-algorithm AES256
    
    # 阻止公共访问（使用OSS ACL设置）
    echo "配置 OSS Bucket 公共访问阻止..."
    # OSS通过ACL控制访问，设置为private即可阻止公共访问
    aliyun oss bucket-acl --method put "oss://${BUCKET_NAME}" --acl private
    
    echo "✅ OSS Bucket 创建成功"
else
    echo "✅ OSS Bucket 已存在"
fi

echo ""
echo "=========================================="
echo "✅ Backend 初始化完成！"
echo "=========================================="
echo ""
echo "下一步："
echo "1. 复制 backend-config.${ENVIRONMENT}.example 为 backend-config.${ENVIRONMENT}"
echo "2. 运行: terraform init -backend-config=backend-config.${ENVIRONMENT}"
echo "3. 运行: terraform plan -var-file=terraform.tfvars.${ENVIRONMENT}"
echo ""

