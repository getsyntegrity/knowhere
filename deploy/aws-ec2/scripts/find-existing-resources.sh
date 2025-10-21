#!/bin/bash
# 查找现有AWS资源ID的脚本
# 用于配置terraform.tfvars文件中的现有资源参数

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
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

highlight() {
    echo -e "${CYAN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

# 检查AWS CLI是否配置
check_aws_cli() {
    if ! command -v aws &> /dev/null; then
        error "AWS CLI 未安装。请先安装 AWS CLI。"
        exit 1
    fi

    if ! aws sts get-caller-identity &> /dev/null; then
        error "AWS CLI 未配置或凭证无效。请运行 'aws configure' 配置凭证。"
        exit 1
    fi

    local caller_identity=$(aws sts get-caller-identity)
    local account_id=$(echo "$caller_identity" | jq -r '.Account')
    local user_arn=$(echo "$caller_identity" | jq -r '.Arn')
    
    log "AWS CLI 配置正确"
    info "账户ID: $account_id"
    info "用户ARN: $user_arn"
    echo ""
}

# 获取当前区域
get_current_region() {
    local region=$(aws configure get region)
    if [ -z "$region" ]; then
        region="us-east-1"
        warn "未设置默认区域，使用 us-east-1"
    fi
    echo "$region"
}

# 查找VPC
find_vpcs() {
    local region=$1
    highlight "=== 查找现有VPC ==="
    
    local vpcs=$(aws ec2 describe-vpcs --region "$region" --query 'Vpcs[*].[VpcId,Tags[?Key==`Name`].Value|[0],CidrBlock,State]' --output table 2>/dev/null || echo "")
    
    if [ -z "$vpcs" ] || [ "$vpcs" = "None" ]; then
        warn "未找到VPC或无法访问"
        return
    fi
    
    echo "$vpcs"
    echo ""
    
    # 提供选择建议
    local vpc_count=$(echo "$vpcs" | grep -c "vpc-" || echo "0")
    if [ "$vpc_count" -gt 0 ]; then
        info "建议选择默认VPC（通常名为 'default'）或包含 'main' 的VPC"
    fi
    echo ""
}

# 查找安全组
find_security_groups() {
    local region=$1
    local vpc_id=$2
    highlight "=== 查找现有安全组 ==="
    
    local query="SecurityGroups[*].[GroupId,GroupName,Description,VpcId]"
    local filter=""
    
    if [ -n "$vpc_id" ]; then
        filter="--filters Name=vpc-id,Values=$vpc_id"
        info "在VPC $vpc_id 中查找安全组..."
    else
        info "查找所有安全组..."
    fi
    
    local security_groups=$(aws ec2 describe-security-groups --region "$region" $filter --query "$query" --output table 2>/dev/null || echo "")
    
    if [ -z "$security_groups" ] || [ "$security_groups" = "None" ]; then
        warn "未找到安全组或无法访问"
        return
    fi
    
    echo "$security_groups"
    echo ""
    
    # 提供选择建议
    info "建议选择包含以下关键词的安全组："
    info "- 'default' (默认安全组)"
    info "- 'web' 或 'app' (应用服务器安全组)"
    info "- 'allow-http-https' (允许HTTP/HTTPS的安全组)"
    echo ""
}

# 查找RDS实例
find_rds_instances() {
    local region=$1
    highlight "=== 查找现有RDS实例 ==="
    
    local rds_instances=$(aws rds describe-db-instances --region "$region" --query 'DBInstances[*].[DBInstanceIdentifier,Engine,EngineVersion,DBInstanceClass,DBInstanceStatus,Endpoint.Address]' --output table 2>/dev/null || echo "")
    
    if [ -z "$rds_instances" ] || [ "$rds_instances" = "None" ]; then
        warn "未找到RDS实例或无法访问"
        return
    fi
    
    echo "$rds_instances"
    echo ""
    
    # 提供选择建议
    info "建议选择："
    info "- PostgreSQL 实例（Engine = postgres）"
    info "- 状态为 'available' 的实例"
    info "- 版本 15.x 或更高"
    echo ""
}

# 查找Redis集群
find_redis_clusters() {
    local region=$1
    highlight "=== 查找现有Redis集群 ==="
    
    local redis_clusters=$(aws elasticache describe-replication-groups --region "$region" --query 'ReplicationGroups[*].[ReplicationGroupId,Description,Status,NodeType,Engine,EngineVersion]' --output table 2>/dev/null || echo "")
    
    if [ -z "$redis_clusters" ] || [ "$redis_clusters" = "None" ]; then
        warn "未找到Redis集群或无法访问"
        return
    fi
    
    echo "$redis_clusters"
    echo ""
    
    # 提供选择建议
    info "建议选择："
    info "- 状态为 'available' 的集群"
    info "- Engine = redis"
    info "- 版本 7.x 或更高"
    echo ""
}

# 查找S3存储桶
find_s3_buckets() {
    local region=$1
    highlight "=== 查找现有S3存储桶 ==="
    
    local buckets=$(aws s3api list-buckets --region "$region" --query 'Buckets[*].[Name,CreationDate]' --output table 2>/dev/null || echo "")
    
    if [ -z "$buckets" ] || [ "$buckets" = "None" ]; then
        warn "未找到S3存储桶或无法访问"
        return
    fi
    
    echo "$buckets"
    echo ""
    
    # 提供选择建议
    info "建议选择："
    info "- 名称包含项目相关关键词的存储桶"
    info "- 创建时间较新的存储桶"
    info "- 确保存储桶名称全局唯一"
    echo ""
}

# 生成terraform.tfvars配置
generate_terraform_config() {
    local vpc_id=$1
    local security_group_id=$2
    local rds_identifier=$3
    local redis_identifier=$4
    local s3_bucket_name=$5
    
    highlight "=== 生成 terraform.tfvars 配置 ==="
    
    echo "# 网络配置（使用现有资源）"
    if [ -n "$vpc_id" ]; then
        echo "use_existing_vpc              = true"
        echo "existing_vpc_id               = \"$vpc_id\""
    else
        echo "use_existing_vpc              = false"
        echo "existing_vpc_id               = \"\""
    fi
    
    if [ -n "$security_group_id" ]; then
        echo "use_existing_security_group   = true"
        echo "existing_security_group_id    = \"$security_group_id\""
    else
        echo "use_existing_security_group   = false"
        echo "existing_security_group_id    = \"\""
    fi
    
    echo ""
    echo "# 数据库配置（使用现有资源）"
    if [ -n "$rds_identifier" ]; then
        echo "use_existing_rds              = true"
        echo "existing_rds_identifier       = \"$rds_identifier\""
    else
        echo "use_existing_rds              = false"
        echo "existing_rds_identifier       = \"\""
    fi
    
    if [ -n "$redis_identifier" ]; then
        echo "use_existing_redis            = true"
        echo "existing_redis_identifier     = \"$redis_identifier\""
    else
        echo "use_existing_redis            = false"
        echo "existing_redis_identifier     = \"\""
    fi
    
    echo ""
    echo "# S3配置（使用现有资源）"
    if [ -n "$s3_bucket_name" ]; then
        echo "use_existing_s3               = true"
        echo "existing_s3_bucket_name       = \"$s3_bucket_name\""
    else
        echo "use_existing_s3               = false"
        echo "existing_s3_bucket_name       = \"\""
    fi
    
    echo ""
    info "请将上述配置复制到 terraform.tfvars 文件中"
}

# 交互式选择资源
interactive_selection() {
    local region=$1
    
    highlight "=== 交互式资源选择 ==="
    echo ""
    
    # VPC选择
    read -p "是否要使用现有VPC？(y/n): " use_vpc
    local vpc_id=""
    if [[ $use_vpc =~ ^[Yy]$ ]]; then
        find_vpcs "$region"
        read -p "请输入VPC ID (例如: vpc-12345678): " vpc_id
    fi
    
    # 安全组选择
    read -p "是否要使用现有安全组？(y/n): " use_sg
    local security_group_id=""
    if [[ $use_sg =~ ^[Yy]$ ]]; then
        find_security_groups "$region" "$vpc_id"
        read -p "请输入安全组ID (例如: sg-12345678): " security_group_id
    fi
    
    # RDS选择
    read -p "是否要使用现有RDS实例？(y/n): " use_rds
    local rds_identifier=""
    if [[ $use_rds =~ ^[Yy]$ ]]; then
        find_rds_instances "$region"
        read -p "请输入RDS实例标识符: " rds_identifier
    fi
    
    # Redis选择
    read -p "是否要使用现有Redis集群？(y/n): " use_redis
    local redis_identifier=""
    if [[ $use_redis =~ ^[Yy]$ ]]; then
        find_redis_clusters "$region"
        read -p "请输入Redis集群标识符: " redis_identifier
    fi
    
    # S3选择
    read -p "是否要使用现有S3存储桶？(y/n): " use_s3
    local s3_bucket_name=""
    if [[ $use_s3 =~ ^[Yy]$ ]]; then
        find_s3_buckets "$region"
        read -p "请输入S3存储桶名称: " s3_bucket_name
    fi
    
    echo ""
    generate_terraform_config "$vpc_id" "$security_group_id" "$rds_identifier" "$redis_identifier" "$s3_bucket_name"
}

# 显示帮助信息
show_help() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help              显示此帮助信息"
    echo "  -r, --region REGION    指定AWS区域 (默认: 从配置读取)"
    echo "  -i, --interactive      交互式选择资源"
    echo "  -a, --all              显示所有资源（不交互）"
    echo "  --vpc-only             只显示VPC"
    echo "  --sg-only              只显示安全组"
    echo "  --rds-only             只显示RDS实例"
    echo "  --redis-only           只显示Redis集群"
    echo "  --s3-only              只显示S3存储桶"
    echo ""
    echo "示例:"
    echo "  $0 --interactive        # 交互式选择资源"
    echo "  $0 --all                # 显示所有资源"
    echo "  $0 --region us-west-2   # 在特定区域查找"
    echo "  $0 --vpc-only           # 只显示VPC"
}

# 主函数
main() {
    local region=""
    local interactive=false
    local show_all=false
    local vpc_only=false
    local sg_only=false
    local rds_only=false
    local redis_only=false
    local s3_only=false
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -r|--region)
                region="$2"
                shift 2
                ;;
            -i|--interactive)
                interactive=true
                shift
                ;;
            -a|--all)
                show_all=true
                shift
                ;;
            --vpc-only)
                vpc_only=true
                shift
                ;;
            --sg-only)
                sg_only=true
                shift
                ;;
            --rds-only)
                rds_only=true
                shift
                ;;
            --redis-only)
                redis_only=true
                shift
                ;;
            --s3-only)
                s3_only=true
                shift
                ;;
            *)
                error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 检查AWS CLI
    check_aws_cli
    
    # 获取区域
    if [ -z "$region" ]; then
        region=$(get_current_region)
    fi
    
    log "使用AWS区域: $region"
    echo ""
    
    # 根据参数执行相应操作
    if [ "$interactive" = true ]; then
        interactive_selection "$region"
    elif [ "$show_all" = true ]; then
        find_vpcs "$region"
        find_security_groups "$region"
        find_rds_instances "$region"
        find_redis_clusters "$region"
        find_s3_buckets "$region"
    elif [ "$vpc_only" = true ]; then
        find_vpcs "$region"
    elif [ "$sg_only" = true ]; then
        find_security_groups "$region"
    elif [ "$rds_only" = true ]; then
        find_rds_instances "$region"
    elif [ "$redis_only" = true ]; then
        find_redis_clusters "$region"
    elif [ "$s3_only" = true ]; then
        find_s3_buckets "$region"
    else
        # 默认显示所有资源
        find_vpcs "$region"
        find_security_groups "$region"
        find_rds_instances "$region"
        find_redis_clusters "$region"
        find_s3_buckets "$region"
        
        echo ""
        info "使用 --interactive 选项进行交互式选择"
        info "使用 --help 查看所有选项"
    fi
}

# 运行主函数
main "$@"
