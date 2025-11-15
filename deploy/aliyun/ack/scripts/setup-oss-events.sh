#!/bin/bash

# 配置OSS事件通知的脚本

set -e

# 配置变量
REGION=${REGION:-cn-guangzhou}
BUCKET_NAME=${OSS_BUCKET_NAME}
CALLBACK_URL=${API_WEBHOOK_ENDPOINT}
ENVIRONMENT=${ENVIRONMENT:-dev}

# 颜色输出
GREEN='\033[0;32m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

# 检查必要的环境变量
if [ -z "$BUCKET_NAME" ]; then
    echo "ERROR: OSS_BUCKET_NAME 环境变量未设置"
    exit 1
fi

if [ -z "$CALLBACK_URL" ]; then
    echo "ERROR: API_WEBHOOK_ENDPOINT 环境变量未设置"
    exit 1
fi

# 使用阿里云CLI配置OSS事件通知
log "配置OSS事件通知..."
log "存储桶: $BUCKET_NAME"
log "回调URL: $CALLBACK_URL"

# 配置 OSS 事件通知
log "配置 OSS 事件通知..."
log "存储桶: $BUCKET_NAME"
log "回调URL: $CALLBACK_URL"
log "区域: $REGION"
echo ""

# 注意：OSS 事件通知需要通过控制台或 API 配置
# 这里提供详细的配置步骤
log "请通过以下方式配置 OSS 事件通知："
echo ""
echo "方式一：通过控制台配置（推荐）"
echo "1. 访问：https://oss.console.aliyun.com/bucket/detail?bucket=${BUCKET_NAME}"
echo "2. 选择：基础设置 → 事件通知"
echo "3. 点击：创建规则"
echo "4. 配置："
echo "   - 规则名称: upload-notification"
echo "   - 事件类型:"
echo "     * oss:ObjectCreated:PutObject"
echo "     * oss:ObjectCreated:PostObject"
echo "     * oss:ObjectCreated:CompleteMultipartUpload"
echo "   - 前缀过滤: uploads/"
echo "   - 回调URL: ${CALLBACK_URL}"
echo "5. 点击：确定"
echo ""
echo "方式二：通过阿里云 CLI 配置"
if command -v aliyun &> /dev/null; then
    log "检测到阿里云 CLI，可以使用以下命令："
    echo ""
    echo "aliyun oss put-bucket-notification-config \\"
    echo "  oss://${BUCKET_NAME} \\"
    echo "  --notification-config '{\"TopicConfiguration\":{\"Id\":\"upload-notification\",\"Topic\":\"arn:acs:mns:${REGION}:${ACCOUNT_ID}:topics/oss-events\",\"Events\":[\"oss:ObjectCreated:PutObject\",\"oss:ObjectCreated:PostObject\",\"oss:ObjectCreated:CompleteMultipartUpload\"],\"Filter\":{\"Key\":{\"FilterRules\":[{\"Name\":\"prefix\",\"Value\":\"uploads/\"}]}}}}'"
    echo ""
    warn "注意：需要先创建 MNS Topic 或使用其他回调方式"
else
    warn "未检测到阿里云 CLI，建议通过控制台配置"
fi
echo ""
log "配置信息总结："
    log "  存储桶: $BUCKET_NAME"
    log "  事件类型: oss:ObjectCreated:PutObject, oss:ObjectCreated:PostObject, oss:ObjectCreated:CompleteMultipartUpload"
    log "  前缀过滤: uploads/"
    log "  回调URL: $CALLBACK_URL"

log "OSS事件通知配置完成"

