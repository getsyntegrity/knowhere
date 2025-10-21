# Knowhere EC2 部署详细指南

## 概述

本指南将详细说明如何在AWS EC2上部署Knowhere知识库管理系统，包括基础设施配置、应用部署、监控设置等。

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        Internet                             │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                Squarespace DNS                              │
│  apitest.knowhereto.ai  →  test.knowhereto.ai              │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                EC2实例 (t3.large)                           │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    Nginx (80/443)                      ││
│  │  ┌─────────────────┐  ┌─────────────────────────────┐  ││
│  │  │   API反向代理    │  │      Web反向代理            │  ││
│  │  │  (5005端口)     │  │     (3000端口)              │  ││
│  │  └─────────────────┘  └─────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────┐│
│  │                应用服务层                               ││
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐  ││
│  │  │ Backend API │ │ Web Frontend│ │ Celery Worker   │  ││
│  │  │ (FastAPI)   │ │ (Next.js)   │ │ (后台任务)      │  ││
│  │  └─────────────┘ └─────────────┘ └─────────────────┘  ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                数据存储层                                    │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐      │
│  │ PostgreSQL  │ │    Redis    │ │      S3         │      │
│  │   (RDS)     │ │(ElastiCache)│ │   (文件存储)    │      │
│  └─────────────┘ └─────────────┘ └─────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## 部署步骤

### 阶段1: 环境准备

#### 1.1 安装必要工具

**在本地机器上安装：**

```bash
# 安装AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# 安装Terraform
wget https://releases.hashicorp.com/terraform/1.5.0/terraform_1.5.0_linux_amd64.zip
unzip terraform_1.5.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/

# 安装Git（如果未安装）
sudo apt update
sudo apt install git
```

#### 1.2 配置AWS凭证

```bash
# 配置AWS凭证
aws configure

# 输入以下信息：
# AWS Access Key ID: [你的访问密钥]
# AWS Secret Access Key: [你的秘密密钥]
# Default region name: us-east-1
# Default output format: json

# 验证配置
aws sts get-caller-identity
```

#### 1.3 创建SSH密钥对

```bash
# 生成SSH密钥对
ssh-keygen -t rsa -b 4096 -C "knowhere-ec2" -f ~/.ssh/knowhere-ec2

# 将公钥添加到AWS
aws ec2 import-key-pair --key-name "knowhere-ec2" --public-key-material fileb://~/.ssh/knowhere-ec2.pub
```

### 阶段2: 代码准备

#### 2.1 克隆代码仓库

```bash
# 克隆仓库
git clone https://github.com/your-org/knowhere.git
cd knowhere

# 检查分支
git branch -a
git checkout main
```

#### 2.2 配置Terraform变量

```bash
# 进入Terraform目录
cd deploy/aws-ec2/terraform

# 复制配置文件
cp terraform.tfvars.example terraform.tfvars

# 编辑配置文件
nano terraform.tfvars
```

**terraform.tfvars 配置示例：**

```hcl
# AWS配置
aws_region = "us-east-1"

# 项目配置
project_name = "knowhere"
environment  = "test"
domain_name  = "knowhereto.ai"

# 子域名配置
api_subdomain = "apitest"
web_subdomain = "test"

# 实例配置
instance_type        = "t3.large"
root_volume_size     = 50
root_volume_type     = "gp3"
root_volume_iops     = 3000

# 网络配置
use_existing_vpc              = false
use_existing_security_group   = false

# 数据库配置
use_existing_rds              = false
use_existing_redis            = false

# S3配置
use_existing_s3               = false

# 密钥配置
create_key_pair = true
key_pair_name   = "knowhere-ec2"

# 监控配置
enable_detailed_monitoring     = false
cloudwatch_log_retention_days = 7
notification_email            = "your-email@example.com"

# SSL配置
enable_ssl            = true
ssl_certificate_arn   = ""

# 标签
common_tags = {
  Project     = "knowhere"
  Environment = "test"
  ManagedBy   = "terraform"
  Owner       = "your-team"
}
```

### 阶段3: 基础设施部署

#### 3.1 初始化Terraform

```bash
# 进入Terraform目录
cd deploy/aws-ec2/terraform

# 初始化Terraform
terraform init

# 验证配置
terraform validate
```

#### 3.2 规划部署

```bash
# 查看将要创建的资源
terraform plan

# 保存计划到文件
terraform plan -out=tfplan
```

#### 3.3 应用配置

```bash
# 应用Terraform配置
terraform apply tfplan

# 或者直接应用
terraform apply
```

**部署完成后，记录以下输出信息：**

```bash
# 获取重要信息
terraform output instance_public_ip
terraform output api_url
terraform output web_url
terraform output ssh_command
```

### 阶段4: 应用配置

#### 4.1 SSH到实例

```bash
# 使用Terraform输出的SSH命令
ssh -i ~/.ssh/knowhere-ec2.pem ubuntu@<instance-ip>

# 或者手动连接
ssh -i ~/.ssh/knowhere-ec2.pem ubuntu@<instance-ip>
```

#### 4.2 克隆代码到实例

```bash
# 在实例上克隆代码
sudo mkdir -p /opt/knowhere
sudo chown ubuntu:ubuntu /opt/knowhere
cd /opt/knowhere
git clone https://github.com/your-org/knowhere.git .

# 复制部署脚本
sudo cp -r deploy/aws-ec2/scripts /opt/knowhere/deploy/aws-ec2/
sudo chmod +x /opt/knowhere/deploy/aws-ec2/scripts/*.sh
```

#### 4.3 运行配置脚本

```bash
# 运行首次配置脚本
sudo /opt/knowhere/deploy/aws-ec2/scripts/provision-instance.sh
```

#### 4.4 配置环境变量

```bash
# 编辑环境变量文件
sudo nano /opt/knowhere/.env
```

**环境变量配置示例：**

```bash
# 基础配置
ENVIRONMENT=test
DEBUG=false
LOG_LEVEL=INFO

# 数据库配置（使用Terraform输出）
DATABASE_URL=postgresql://postgres:password@your-rds-endpoint:5432/knowhere

# Redis配置
REDIS_HOST=your-redis-endpoint
REDIS_PORT=6379
REDIS_PASSWORD=

# S3配置
S3_BUCKET_NAME=knowhere-test-storage-xxxxx
S3_ACCESS_KEY_ID=your-access-key
S3_SECRET_ACCESS_KEY=your-secret-key
S3_REGION=us-east-1

# API配置
SECRET_KEY=your-secret-key-here
API_HOST=0.0.0.0
API_PORT=5005

# Web配置
NEXT_PUBLIC_API_URL=https://apitest.knowhereto.ai
NEXT_PUBLIC_POSTHOG_KEY=your-posthog-key
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=your-stripe-key

# Celery配置
CELERY_BROKER_URL=redis://your-redis-endpoint:6379/0
CELERY_RESULT_BACKEND=redis://your-redis-endpoint:6379/0
```

#### 4.5 启动服务

```bash
# 启动所有服务
sudo systemctl start knowhere-api
sudo systemctl start knowhere-web
sudo systemctl start knowhere-worker
sudo systemctl start nginx

# 检查服务状态
sudo systemctl status knowhere-api
sudo systemctl status knowhere-web
sudo systemctl status knowhere-worker
sudo systemctl status nginx
```

### 阶段5: DNS配置

#### 5.1 在Squarespace中配置DNS

1. 登录Squarespace管理面板
2. 进入域名设置
3. 添加以下A记录：
   - `apitest.knowhereto.ai` → `<EC2实例IP>`
   - `test.knowhereto.ai` → `<EC2实例IP>`

#### 5.2 等待DNS传播

```bash
# 检查DNS解析
nslookup apitest.knowhereto.ai
nslookup test.knowhereto.ai

# 等待几分钟后测试
curl -I http://apitest.knowhereto.ai/health
curl -I http://test.knowhereto.ai
```

### 阶段6: SSL配置（可选）

#### 6.1 安装Certbot

```bash
# 在EC2实例上安装Certbot
sudo apt update
sudo apt install certbot python3-certbot-nginx
```

#### 6.2 获取SSL证书

```bash
# 获取SSL证书
sudo certbot --nginx -d apitest.knowhereto.ai -d test.knowhereto.ai

# 测试自动续期
sudo certbot renew --dry-run
```

### 阶段7: 验证部署

#### 7.1 健康检查

```bash
# 运行健康检查脚本
/usr/local/bin/knowhere-health-check.sh

# 手动检查服务
curl -f http://localhost:5005/health
curl -f http://localhost:3000
```

#### 7.2 功能测试

```bash
# 测试API端点
curl -X GET https://apitest.knowhereto.ai/health
curl -X GET https://apitest.knowhereto.ai/docs

# 测试Web前端
curl -I https://test.knowhereto.ai
```

#### 7.3 监控检查

```bash
# 查看CloudWatch日志
aws logs describe-log-groups
aws logs get-log-events --log-group-name /aws/ec2/knowhere-test

# 查看系统资源
htop
df -h
free -h
```

## 运维操作

### 日常维护

#### 服务管理

```bash
# 查看所有服务状态
sudo systemctl status knowhere-*

# 重启特定服务
sudo systemctl restart knowhere-api
sudo systemctl restart knowhere-web
sudo systemctl restart knowhere-worker

# 查看服务日志
sudo journalctl -u knowhere-api -f
sudo journalctl -u knowhere-web -f
sudo journalctl -u knowhere-worker -f
```

#### 应用部署

```bash
# 部署新版本
sudo /opt/knowhere/deploy/aws-ec2/scripts/deploy-app.sh

# 回滚到前一版本
sudo /opt/knowhere/deploy/aws-ec2/scripts/rollback.sh
```

#### 日志管理

```bash
# 查看应用日志
knowhere-logs.sh api
knowhere-logs.sh web
knowhere-logs.sh worker

# 查看Nginx日志
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# 查看系统日志
sudo journalctl -f
```

### 监控和维护

#### 系统监控

```bash
# 查看系统资源使用
htop
iotop
nethogs

# 查看磁盘使用
df -h
du -sh /opt/knowhere/*

# 查看网络连接
ss -tulpn
netstat -tlnp
```

#### 应用监控

```bash
# 查看进程状态
ps aux | grep knowhere
ps aux | grep nginx

# 查看端口监听
sudo lsof -i :5005
sudo lsof -i :3000
sudo lsof -i :80
sudo lsof -i :443
```

#### CloudWatch监控

```bash
# 查看CloudWatch指标
aws cloudwatch get-metric-statistics \
  --namespace "AWS/EC2" \
  --metric-name "CPUUtilization" \
  --dimensions Name=InstanceId,Value=i-xxxxx \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-01T23:59:59Z \
  --period 300 \
  --statistics Average
```

### 故障排除

#### 常见问题

1. **服务无法启动**
   ```bash
   # 查看详细错误信息
   sudo journalctl -u knowhere-api -l --no-pager
   
   # 检查配置文件
   sudo nginx -t
   
   # 检查端口占用
   sudo lsof -i :5005
   ```

2. **数据库连接失败**
   ```bash
   # 测试数据库连接
   psql $DATABASE_URL
   
   # 检查网络连接
   telnet your-rds-endpoint 5432
   
   # 检查安全组
   aws ec2 describe-security-groups --group-ids sg-xxxxx
   ```

3. **Nginx配置错误**
   ```bash
   # 测试Nginx配置
   sudo nginx -t
   
   # 查看Nginx错误日志
   sudo tail -f /var/log/nginx/error.log
   
   # 重新加载配置
   sudo systemctl reload nginx
   ```

4. **权限问题**
   ```bash
   # 检查文件权限
   ls -la /opt/knowhere/
   
   # 修复权限
   sudo chown -R appuser:appuser /opt/knowhere/
   sudo chmod -R 755 /opt/knowhere/
   ```

#### 日志分析

```bash
# 查看错误日志
sudo grep -i error /var/log/nginx/error.log
sudo journalctl -u knowhere-api | grep -i error

# 查看访问日志
sudo tail -f /var/log/nginx/access.log | grep -v "200"

# 分析性能
sudo tail -f /var/log/nginx/access.log | awk '{print $NF}' | sort -n
```

## 扩展和维护

### 垂直扩展

#### 升级实例类型

```bash
# 停止实例
aws ec2 stop-instances --instance-ids i-xxxxx

# 修改实例类型
aws ec2 modify-instance-attribute \
  --instance-id i-xxxxx \
  --instance-type t3.xlarge

# 启动实例
aws ec2 start-instances --instance-ids i-xxxxx
```

#### 增加存储空间

```bash
# 扩展EBS卷
aws ec2 modify-volume --volume-id vol-xxxxx --size 100

# 在实例上扩展文件系统
sudo growpart /dev/xvda1 1
sudo resize2fs /dev/xvda1
```

### 水平扩展

#### 创建多个实例

1. 使用Terraform创建多个实例
2. 配置应用负载均衡器
3. 使用共享存储（EFS）

#### 负载均衡配置

```bash
# 创建目标组
aws elbv2 create-target-group \
  --name knowhere-api-tg \
  --protocol HTTP \
  --port 5005 \
  --vpc-id vpc-xxxxx

# 注册目标
aws elbv2 register-targets \
  --target-group-arn arn:aws:elasticloadbalancing:region:account:targetgroup/knowhere-api-tg/xxxxx \
  --targets Id=i-xxxxx,Port=5005
```

### 备份策略

#### 代码备份

```bash
# 代码已存储在Git仓库中
git push origin main
```

#### 数据库备份

```bash
# RDS自动备份已启用
# 手动创建快照
aws rds create-db-snapshot \
  --db-instance-identifier knowhere-test-db \
  --db-snapshot-identifier knowhere-test-backup-$(date +%Y%m%d)
```

#### 文件备份

```bash
# S3版本控制已启用
# 手动备份重要文件
aws s3 sync /opt/knowhere/uploads s3://knowhere-test-storage/uploads/
```

#### 实例备份

```bash
# 创建AMI快照
aws ec2 create-image \
  --instance-id i-xxxxx \
  --name "knowhere-backup-$(date +%Y%m%d)" \
  --description "Knowhere backup $(date)"
```

## 安全加固

### 系统安全

#### 更新系统包

```bash
# 定期更新系统包
sudo apt update
sudo apt upgrade -y

# 自动安全更新
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

#### 配置防火墙

```bash
# 配置UFW防火墙
sudo ufw enable
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

#### 配置fail2ban

```bash
# 配置fail2ban防止暴力破解
sudo nano /etc/fail2ban/jail.local

# 重启fail2ban
sudo systemctl restart fail2ban
```

### 应用安全

#### SSL/TLS配置

```bash
# 检查SSL配置
openssl s_client -connect apitest.knowhereto.ai:443 -servername apitest.knowhereto.ai

# 测试SSL等级
curl -I https://apitest.knowhereto.ai
```

#### 安全头配置

```bash
# 检查安全头
curl -I https://apitest.knowhereto.ai | grep -i "x-frame-options\|x-content-type-options\|x-xss-protection"
```

### 数据安全

#### 加密配置

```bash
# 检查数据库加密
aws rds describe-db-instances --db-instance-identifier knowhere-test-db

# 检查S3加密
aws s3api get-bucket-encryption --bucket knowhere-test-storage
```

#### 访问控制

```bash
# 检查IAM角色
aws iam get-role --role-name knowhere-test-app-server-role

# 检查安全组
aws ec2 describe-security-groups --group-ids sg-xxxxx
```

## 性能优化

### 系统优化

#### 内核参数优化

```bash
# 编辑sysctl配置
sudo nano /etc/sysctl.conf

# 应用配置
sudo sysctl -p
```

#### 文件描述符限制

```bash
# 检查当前限制
ulimit -n

# 永久设置限制
echo "* soft nofile 65536" | sudo tee -a /etc/security/limits.conf
echo "* hard nofile 65536" | sudo tee -a /etc/security/limits.conf
```

### 应用优化

#### Nginx优化

```bash
# 优化Nginx配置
sudo nano /etc/nginx/nginx.conf

# 启用gzip压缩
# 配置缓存
# 优化连接数
```

#### Python应用优化

```bash
# 优化Uvicorn配置
# 调整worker数量
# 配置连接池
```

### 数据库优化

#### PostgreSQL优化

```bash
# 连接数据库
psql $DATABASE_URL

# 检查配置
SHOW shared_buffers;
SHOW effective_cache_size;
SHOW work_mem;
```

#### Redis优化

```bash
# 连接Redis
redis-cli -h your-redis-endpoint

# 检查配置
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
```

## 监控和告警

### CloudWatch监控

#### 自定义指标

```bash
# 发送自定义指标
aws cloudwatch put-metric-data \
  --namespace "Knowhere/API" \
  --metric-data MetricName=HealthCheck,Value=1,Unit=Count
```

#### 告警配置

```bash
# 创建CPU告警
aws cloudwatch put-metric-alarm \
  --alarm-name "knowhere-cpu-high" \
  --alarm-description "CPU utilization is high" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2
```

### 日志分析

#### 日志聚合

```bash
# 使用ELK Stack
# 或使用CloudWatch Logs Insights
```

#### 错误监控

```bash
# 监控错误日志
sudo tail -f /var/log/nginx/error.log | grep -i error

# 设置错误告警
aws cloudwatch put-metric-alarm \
  --alarm-name "knowhere-nginx-errors" \
  --alarm-description "Nginx error rate is high" \
  --metric-name ErrorCount \
  --namespace "Knowhere/Nginx" \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold
```

## 故障恢复

### 实例故障

#### 自动恢复

```bash
# 配置CloudWatch告警自动恢复
aws cloudwatch put-metric-alarm \
  --alarm-name "knowhere-instance-health" \
  --alarm-description "Instance health check failed" \
  --metric-name StatusCheckFailed \
  --namespace AWS/EC2 \
  --statistic Maximum \
  --period 60 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --alarm-actions arn:aws:automate:region:ec2:recover
```

#### 手动恢复

```bash
# 从AMI恢复实例
aws ec2 run-instances \
  --image-id ami-xxxxx \
  --instance-type t3.large \
  --key-name knowhere-ec2 \
  --security-group-ids sg-xxxxx \
  --subnet-id subnet-xxxxx
```

### 数据恢复

#### 数据库恢复

```bash
# 从RDS快照恢复
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier knowhere-test-db-restored \
  --db-snapshot-identifier knowhere-test-backup-20240101
```

#### 文件恢复

```bash
# 从S3恢复文件
aws s3 sync s3://knowhere-test-storage/uploads/ /opt/knowhere/uploads/
```

## 成本优化

### 资源优化

#### 实例优化

```bash
# 使用Spot实例（开发环境）
# 调整实例类型
# 启用自动停止/启动
```

#### 存储优化

```bash
# 使用S3 Intelligent-Tiering
aws s3api put-bucket-intelligent-tiering-configuration \
  --bucket knowhere-test-storage \
  --id entire-bucket \
  --tiering-configuration Id=archived,Status=Enabled,Transitions=Days=30,StorageClass=STANDARD_IA
```

### 监控成本

#### 成本分析

```bash
# 查看成本和使用情况
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost
```

#### 预算告警

```bash
# 创建预算告警
aws budgets create-budget \
  --account-id 123456789012 \
  --budget '{
    "BudgetName": "knowhere-monthly-budget",
    "BudgetLimit": {"Amount": "100", "Unit": "USD"},
    "TimeUnit": "MONTHLY",
    "BudgetType": "COST"
  }'
```

## 总结

本指南详细说明了Knowhere在AWS EC2上的完整部署流程，包括：

1. **环境准备**: 安装工具、配置凭证
2. **基础设施部署**: 使用Terraform创建AWS资源
3. **应用配置**: 在EC2实例上配置和启动应用
4. **DNS配置**: 在Squarespace中配置域名解析
5. **SSL配置**: 使用Let's Encrypt配置HTTPS
6. **验证部署**: 健康检查和功能测试
7. **运维操作**: 日常维护和监控
8. **故障排除**: 常见问题解决方案
9. **扩展维护**: 垂直和水平扩展
10. **安全加固**: 系统、应用和数据安全
11. **性能优化**: 系统和应用性能调优
12. **监控告警**: CloudWatch监控和告警配置
13. **故障恢复**: 自动和手动恢复流程
14. **成本优化**: 资源优化和成本控制

通过遵循本指南，您可以成功部署一个生产就绪的Knowhere知识库管理系统。
