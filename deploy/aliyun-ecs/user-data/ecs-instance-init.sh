#!/bin/bash
# ECS实例初始化脚本
# 在实例启动时执行

set -e

# 日志函数
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a /var/log/user-data.log
}

error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1" | tee -a /var/log/user-data.log
    exit 1
}

log "开始ECS实例初始化..."

# 更新系统包（使用阿里云镜像源以加快速度）
log "更新系统包..."
# 如果在中国，可以使用阿里云的Ubuntu镜像源
# sed -i 's|http://archive.ubuntu.com|https://mirrors.aliyun.com|g' /etc/apt/sources.list
# sed -i 's|http://security.ubuntu.com|https://mirrors.aliyun.com|g' /etc/apt/sources.list

apt-get update -y
apt-get upgrade -y

# 安装基础工具
log "安装基础工具..."
apt-get install -y \
    curl \
    wget \
    git \
    unzip \
    htop \
    vim \
    ufw \
    fail2ban \
    logrotate \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release

# 安装Python 3.12
log "安装Python 3.12..."
add-apt-repository ppa:deadsnakes/ppa -y
apt-get update -y
apt-get install -y python3.12 python3.12-venv python3.12-dev python3-pip

# 设置Python3.12为默认python3
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1

# 安装Node.js 18
log "安装Node.js 18..."
curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt-get install -y nodejs

# 安装Nginx
log "安装Nginx..."
apt-get install -y nginx

# 安装PostgreSQL客户端
log "安装PostgreSQL客户端..."
apt-get install -y postgresql-client

# 安装Redis客户端
log "安装Redis客户端..."
apt-get install -y redis-tools

# 安装阿里云CLI（可选）
log "安装阿里云CLI..."
# wget https://aliyuncli.alicdn.com/aliyun-cli-linux-latest-amd64.tgz
# tar -xzf aliyun-cli-linux-latest-amd64.tgz
# sudo mv aliyun /usr/local/bin/
# 或者使用包管理器安装
# 注意：阿里云CLI可能需要单独安装

# 创建应用用户
log "创建应用用户..."
useradd -m -s /bin/bash appuser || true
usermod -aG sudo appuser

# 创建应用目录
log "创建应用目录..."
mkdir -p /opt/knowhere/{apps,logs,releases}
chown -R appuser:appuser /opt/knowhere

# 配置SSH（禁用root登录，启用密钥认证）
log "配置SSH..."
sed -i 's/#PermitRootLogin yes/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh

# 配置防火墙
log "配置防火墙..."
ufw --force enable
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp

# 配置fail2ban
log "配置fail2ban..."
cat > /etc/fail2ban/jail.local << EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true
port = ssh
logpath = /var/log/auth.log
maxretry = 3
EOF

systemctl enable fail2ban
systemctl start fail2ban

# 配置日志轮转
log "配置日志轮转..."
cat > /etc/logrotate.d/knowhere << EOF
/opt/knowhere/logs/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 appuser appuser
    postrotate
        systemctl reload knowhere-api knowhere-web knowhere-worker
    endscript
}
EOF

# 配置时区
log "配置时区..."
timedatectl set-timezone Asia/Shanghai  # 或者 UTC

# 优化系统参数
log "优化系统参数..."
cat >> /etc/sysctl.conf << EOF
# 网络优化
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_keepalive_intvl = 60
net.ipv4.tcp_keepalive_probes = 10
net.ipv4.tcp_fin_timeout = 30
net.ipv4.tcp_tw_reuse = 1

# 文件描述符限制
fs.file-max = 2097152
EOF

sysctl -p

# 设置文件描述符限制
cat >> /etc/security/limits.conf << EOF
* soft nofile 65536
* hard nofile 65536
* soft nproc 65536
* hard nproc 65536
EOF

# 创建环境变量文件模板
log "创建环境变量文件模板..."
cat > /opt/knowhere/.env.template << EOF
# 环境配置
ENVIRONMENT=test
DEBUG=false
LOG_LEVEL=INFO

# 数据库配置
DATABASE_URL=postgresql://postgres:password@localhost:5432/knowhere

# Redis配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# OSS配置（替代S3）
OSS_BUCKET_NAME=knowhere-test-storage
OSS_ACCESS_KEY_ID=
OSS_SECRET_ACCESS_KEY=
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_REGION=cn-hangzhou

# API配置
SECRET_KEY=your-secret-key-here
API_HOST=0.0.0.0
API_PORT=5005

# Web配置
NEXT_PUBLIC_API_URL=https://apitest.knowhereto.ai
NEXT_PUBLIC_POSTHOG_KEY=
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=

# 其他配置
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
EOF

# 设置权限
chown appuser:appuser /opt/knowhere/.env.template

# 创建部署脚本目录
mkdir -p /opt/knowhere/deploy/aliyun-ecs/scripts
chown -R appuser:appuser /opt/knowhere/deploy

# 复制SSH密钥到实例
log "复制SSH密钥..."
if [ -f "/tmp/repo-git" ]; then
    cp /tmp/repo-git /opt/knowhere/deploy/aliyun-ecs/scripts/
    chmod 600 /opt/knowhere/deploy/aliyun-ecs/scripts/repo-git
    chown appuser:appuser /opt/knowhere/deploy/aliyun-ecs/scripts/repo-git
    log "SSH密钥已复制"
else
    log "SSH密钥文件不存在，将使用HTTPS克隆"
fi

# 克隆代码仓库（如果提供了Git URL）
if [ -n "${GIT_REPOSITORY_URL}" ]; then
    log "克隆代码仓库..."
    cd /opt/knowhere
    
    # 如果是私有仓库且有SSH密钥
    if [ -n "${GIT_SSH_KEY_PATH}" ] && [ -f "${GIT_SSH_KEY_PATH}" ]; then
        # 配置SSH密钥
        sudo -u appuser mkdir -p /home/appuser/.ssh
        sudo -u appuser cp "${GIT_SSH_KEY_PATH}" /home/appuser/.ssh/id_rsa
        sudo -u appuser chmod 600 /home/appuser/.ssh/id_rsa
        sudo -u appuser ssh-keyscan github.com >> /home/appuser/.ssh/known_hosts
        sudo -u appuser chown -R appuser:appuser /home/appuser/.ssh
        
        # 使用SSH克隆
        sudo -u appuser git clone "${GIT_REPOSITORY_URL}" .
    else
        # 使用HTTPS克隆
        sudo -u appuser git clone "${GIT_REPOSITORY_URL}" .
    fi
    
    # 切换到指定分支
    if [ -n "${GIT_BRANCH}" ]; then
        sudo -u appuser git checkout "${GIT_BRANCH}"
    fi
    
    log "代码仓库克隆完成"
else
    log "未提供Git仓库URL，请手动克隆代码"
fi

log "ECS实例初始化完成！"
log "请运行以下命令完成应用部署："
log "1. cd /opt/knowhere/deploy/aliyun-ecs/scripts"
log "2. sudo ./provision-instance.sh"
log "3. sudo ./deploy-app.sh"

