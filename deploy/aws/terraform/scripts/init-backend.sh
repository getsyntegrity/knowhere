#!/bin/bash
# 初始化 Terraform Backend 资源（S3 Bucket 和 DynamoDB Table）
# 使用方法：
#   ./init-backend.sh dev
#   ./init-backend.sh test
#   ./init-backend.sh prod

set -e

ENVIRONMENT=${1:-dev}
PROJECT_NAME="knowhere"
REGION=${2:-us-east-1}

if [[ ! "$ENVIRONMENT" =~ ^(dev|test|prod)$ ]]; then
    echo "错误：环境必须是 dev、test 或 prod"
    exit 1
fi

# 根据环境设置区域
if [ "$ENVIRONMENT" == "dev" ]; then
    REGION="us-west-1"
elif [ "$ENVIRONMENT" == "test" ] || [ "$ENVIRONMENT" == "prod" ]; then
    REGION="us-east-1"
fi

BUCKET_NAME="${PROJECT_NAME}-terraform-state-${ENVIRONMENT}"
DYNAMODB_TABLE="${PROJECT_NAME}-terraform-locks-${ENVIRONMENT}"

echo "=========================================="
echo "初始化 Terraform Backend - ${ENVIRONMENT} 环境"
echo "=========================================="
echo "项目名称: ${PROJECT_NAME}"
echo "环境: ${ENVIRONMENT}"
echo "区域: ${REGION}"
echo "S3 Bucket: ${BUCKET_NAME}"
echo "DynamoDB Table: ${DYNAMODB_TABLE}"
echo ""

# 检查 AWS CLI 是否已配置
if ! aws sts get-caller-identity &>/dev/null; then
    echo "错误：AWS CLI 未配置或凭证无效"
    exit 1
fi

# 创建 S3 Bucket（如果不存在）
echo "检查 S3 Bucket: ${BUCKET_NAME}..."
if aws s3 ls "s3://${BUCKET_NAME}" 2>&1 | grep -q 'NoSuchBucket'; then
    echo "创建 S3 Bucket: ${BUCKET_NAME}..."
    
    # 创建 bucket（如果区域不是 us-east-1，需要指定 LocationConstraint）
    if [ "$REGION" == "us-east-1" ]; then
        aws s3api create-bucket \
            --bucket "${BUCKET_NAME}" \
            --region "${REGION}"
    else
        aws s3api create-bucket \
            --bucket "${BUCKET_NAME}" \
            --region "${REGION}" \
            --create-bucket-configuration LocationConstraint="${REGION}"
    fi
    
    # 启用版本控制
    echo "启用 S3 Bucket 版本控制..."
    aws s3api put-bucket-versioning \
        --bucket "${BUCKET_NAME}" \
        --versioning-configuration Status=Enabled
    
    # 启用加密
    echo "启用 S3 Bucket 加密..."
    aws s3api put-bucket-encryption \
        --bucket "${BUCKET_NAME}" \
        --server-side-encryption-configuration '{
            "Rules": [{
                "ApplyServerSideEncryptionByDefault": {
                    "SSEAlgorithm": "AES256"
                }
            }]
        }'
    
    # 阻止公共访问
    echo "配置 S3 Bucket 公共访问阻止..."
    aws s3api put-public-access-block \
        --bucket "${BUCKET_NAME}" \
        --public-access-block-configuration \
            "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
    
    echo "✅ S3 Bucket 创建成功"
else
    echo "✅ S3 Bucket 已存在"
fi

# 创建 DynamoDB Table（如果不存在）
echo ""
echo "检查 DynamoDB Table: ${DYNAMODB_TABLE}..."
if ! aws dynamodb describe-table --table-name "${DYNAMODB_TABLE}" --region "${REGION}" &>/dev/null; then
    echo "创建 DynamoDB Table: ${DYNAMODB_TABLE}..."
    aws dynamodb create-table \
        --table-name "${DYNAMODB_TABLE}" \
        --attribute-definitions AttributeName=LockID,AttributeType=S \
        --key-schema AttributeName=LockID,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST \
        --region "${REGION}" \
        --tags Key=Name,Value="${DYNAMODB_TABLE}" Key=Environment,Value="${ENVIRONMENT}" Key=Project,Value="${PROJECT_NAME}"
    
    echo "等待 DynamoDB Table 创建完成..."
    aws dynamodb wait table-exists \
        --table-name "${DYNAMODB_TABLE}" \
        --region "${REGION}"
    
    echo "✅ DynamoDB Table 创建成功"
else
    echo "✅ DynamoDB Table 已存在"
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

