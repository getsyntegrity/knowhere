# Knowhere AWS EC2 部署方案

## 概述

这是Knowhere知识库管理系统的AWS EC2直接部署方案，使用传统的服务器部署方式，直接在EC2实例上运行应用，无需Docker容器化。

## 架构

```
Internet
    ↓
Squarespace DNS
    ↓
EC2实例 (t3.large)
├── Nginx (80/443) → 反向代理
│   ├── apitest.knowhereto.ai → Backend API (5005)
│   └── test.knowhereto.ai → Web Frontend (3000)
├── Backend API (5005) → FastAPI + Uvicorn
├── Web Frontend (3000) → Next.js
├── Worker (后台) → Celery
├── PostgreSQL (RDS)
├── Redis (ElastiCache)
└── 文件存储 (S3)
```

## 特性

- **无Docker**: 直接在EC2上运行，避免Docker打包问题
- **快速迭代**: 直接git pull更新代码，重启服务即可
- **易于调试**: 直接访问文件系统，查看日志，修改配置
- **资源效率**: 无Docker层开销，资源利用率更高
- **简单直接**: 传统部署方式，团队更熟悉

## 目录结构

```
deploy/aws-ec2/
├── terraform/          # Terraform基础设施配置
├── scripts/            # 部署和管理脚本
├── systemd/            # systemd服务配置
├── nginx/              # Nginx配置
├── config/             # 应用配置模板
├── user-data/          # EC2启动脚本
└── docs/               # 文档
```

## 快速开始

### 1. 前置要求

- AWS CLI v2
- Terraform >= 1.0
- Git
- SSH密钥对

### 2. 配置AWS凭证

```bash
aws configure
```

### 3. 配置Terraform变量

```bash
cd deploy/aws-ec2/terraform
cp terraform.tfvars.example terraform.tfvars
# 编辑 terraform.tfvars 填入实际配置
```

### 4. 部署基础设施

```bash
cd deploy/aws-ec2
./scripts/deploy.sh
```

### 5. 配置DNS

在Squarespace中配置以下DNS记录：
- A记录: `apitest.knowhereto.ai` → EC2实例IP
- A记录: `test.knowhereto.ai` → EC2实例IP

### 6. 访问应用

- API: https://apitest.knowhereto.ai
- Web: https://test.knowhereto.ai

## 详细部署步骤

### 步骤1: 准备环境

1. **安装必要工具**
   ```bash
   # 安装AWS CLI
   curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
   unzip awscliv2.zip
   sudo ./aws/install
   
   # 安装Terraform
   wget https://releases.hashicorp.com/terraform/1.5.0/terraform_1.5.0_linux_amd64.zip
   unzip terraform_1.5.0_linux_amd64.zip
   sudo mv terraform /usr/local/bin/
   ```

2. **配置AWS凭证**
   ```bash
   aws configure
   # 输入Access Key ID和Secret Access Key
   ```

3. **克隆代码仓库**
   ```bash
   git clone https://github.com/your-org/knowhere.git
   cd knowhere
   ```

### 步骤2: 配置Terraform

1. **复制配置文件**
   ```bash
   cd deploy/aws-ec2/terraform
   cp terraform.tfvars.example terraform.tfvars
   ```

2. **编辑terraform.tfvars**
   ```bash
   # 填入你的实际配置
   aws_region = "us-east-1"
   project_name = "knowhere"
   environment = "test"
   domain_name = "knowhereto.ai"
   api_subdomain = "apitest"
   web_subdomain = "test"
   ```

### 步骤3: 部署基础设施

1. **初始化Terraform**
   ```bash
   terraform init
   ```

2. **规划部署**
   ```bash
   terraform plan
   ```

3. **应用配置**
   ```bash
   terraform apply
   ```

### 步骤4: 配置应用

1. **SSH到实例**
   ```bash
   ssh -i ~/.ssh/your-key.pem ubuntu@<instance-ip>
   ```

2. **运行配置脚本**
   ```bash
   sudo /opt/knowhere/deploy/aws-ec2/scripts/provision-instance.sh
   ```

3. **配置环境变量**
   ```bash
   sudo nano /opt/knowhere/.env
   # 填入数据库、Redis、S3等配置
   ```

4. **启动服务**
   ```bash
   sudo systemctl start knowhere-api knowhere-web knowhere-worker
   sudo systemctl start nginx
   ```

### 步骤5: 配置SSL（可选）

1. **安装Certbot**
   ```bash
   sudo apt install certbot python3-certbot-nginx
   ```

2. **获取SSL证书**
   ```bash
   sudo certbot --nginx -d apitest.knowhereto.ai -d test.knowhereto.ai
   ```

## 运维操作

### 服务管理

```bash
# 查看服务状态
sudo systemctl status knowhere-api
sudo systemctl status knowhere-web
sudo systemctl status knowhere-worker

# 启动/停止/重启服务
sudo systemctl start|stop|restart knowhere-api
sudo systemctl start|stop|restart knowhere-web
sudo systemctl start|stop|restart knowhere-worker

# 查看服务日志
sudo journalctl -u knowhere-api -f
sudo journalctl -u knowhere-web -f
sudo journalctl -u knowhere-worker -f
```

### 应用部署

```bash
# 部署新版本
sudo /opt/knowhere/deploy/aws-ec2/scripts/deploy-app.sh

# 健康检查
/usr/local/bin/knowhere-health-check.sh

# 查看日志
knowhere-logs.sh api
knowhere-logs.sh web
knowhere-logs.sh worker
```

### 监控和日志

```bash
# 查看系统资源
htop
df -h
free -h

# 查看Nginx日志
sudo tail -f /var/log/nginx/*.log

# 查看应用日志
sudo tail -f /opt/knowhere/logs/*.log

# 查看CloudWatch日志
aws logs describe-log-groups
aws logs get-log-events --log-group-name /aws/ec2/knowhere-test
```

## 配置说明

### 环境变量

主要环境变量配置在 `/opt/knowhere/.env`：

- `DATABASE_URL`: PostgreSQL数据库连接
- `REDIS_HOST`: Redis连接
- `S3_BUCKET_NAME`: S3存储桶名称
- `SECRET_KEY`: 应用密钥
- `NEXT_PUBLIC_API_URL`: API URL（前端使用）

### Nginx配置

Nginx配置文件位于 `/etc/nginx/sites-available/knowhere.conf`：

- 反向代理到后端API和前端
- SSL终止
- 静态文件缓存
- 安全头设置

### Systemd服务

服务配置文件位于 `/etc/systemd/system/`：

- `knowhere-api.service`: FastAPI后端服务
- `knowhere-web.service`: Next.js前端服务
- `knowhere-worker.service`: Celery Worker服务
- `knowhere-scheduler.service`: Celery Beat调度服务

## 故障排除

### 常见问题

1. **服务无法启动**
   ```bash
   # 查看服务状态
   sudo systemctl status knowhere-api
   
   # 查看详细日志
   sudo journalctl -u knowhere-api -l
   
   # 检查配置文件
   sudo nginx -t
   ```

2. **数据库连接失败**
   ```bash
   # 检查数据库连接
   psql $DATABASE_URL
   
   # 检查网络连接
   telnet your-rds-endpoint 5432
   ```

3. **端口被占用**
   ```bash
   # 查看端口使用情况
   sudo netstat -tlnp | grep :5005
   sudo lsof -i :5005
   ```

4. **权限问题**
   ```bash
   # 检查文件权限
   ls -la /opt/knowhere/
   
   # 修复权限
   sudo chown -R appuser:appuser /opt/knowhere/
   ```

### 日志位置

- 应用日志: `/opt/knowhere/logs/`
- Nginx日志: `/var/log/nginx/`
- 系统日志: `journalctl -u service-name`
- CloudWatch日志: AWS控制台

## 扩展和维护

### 垂直扩展

升级实例类型：
```bash
# 停止实例
aws ec2 stop-instances --instance-ids i-xxxxx

# 修改实例类型
aws ec2 modify-instance-attribute --instance-id i-xxxxx --instance-type t3.xlarge

# 启动实例
aws ec2 start-instances --instance-ids i-xxxxx
```

### 水平扩展

1. 创建多个实例
2. 配置负载均衡器
3. 使用共享存储（EFS）

### 备份策略

1. **代码备份**: Git仓库
2. **数据库备份**: RDS自动备份
3. **文件备份**: S3版本控制
4. **实例备份**: AMI快照

## 成本估算

### 测试环境（月成本）

- EC2 t3.large: ~$60
- RDS db.t3.micro: ~$15
- ElastiCache cache.t3.micro: ~$15
- S3存储: ~$5
- 数据传输: ~$5
- **总计**: ~$100/月

### 生产环境（月成本）

- EC2 t3.xlarge: ~$120
- RDS db.t3.small: ~$30
- ElastiCache cache.t3.small: ~$30
- S3存储: ~$10
- 数据传输: ~$10
- **总计**: ~$200/月

## 安全考虑

1. **网络安全**
   - 安全组最小权限
   - VPC私有子网
   - WAF保护

2. **应用安全**
   - HTTPS加密
   - 安全头设置
   - 输入验证

3. **数据安全**
   - 数据库加密
   - S3加密
   - 密钥管理

4. **访问控制**
   - IAM角色
   - SSH密钥认证
   - 多因素认证

## 支持

如果遇到问题，请：

1. 查看日志文件
2. 检查服务状态
3. 参考故障排除指南
4. 联系技术支持

---

**注意**: 这是一个生产级别的部署配置，请根据实际需求调整资源大小和配置参数。
