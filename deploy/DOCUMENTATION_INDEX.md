# 部署文档索引

本文档提供所有部署相关文档的索引和说明。

## 主要文档

### 📘 [README.md](README.md)
**主部署指南** - 包含完整的部署流程、架构说明和快速开始指南

### 🚀 [DEPLOYMENT_AWS.md](DEPLOYMENT_AWS.md)
**AWS 部署详细指南** - AWS 平台完整部署指南，包括镜像构建、基础设施部署、应用部署等

### 🚀 [DEPLOYMENT_ALIYUN.md](DEPLOYMENT_ALIYUN.md)
**阿里云部署详细指南** - 阿里云平台完整部署指南，重点说明 ACR 构建服务自动构建镜像

### 🌐 [DOMAIN_CONFIG.md](DOMAIN_CONFIG.md)
**域名配置说明** - 详细的域名与分支映射、路由配置、SSL证书配置

### 🏗️ [aws/terraform/PLAN_RESOURCES.md](aws/terraform/PLAN_RESOURCES.md)
**资源详细说明** - Terraform plan 中所有资源的详细说明和作用

---

## AWS 部署文档

### 📁 [DEPLOYMENT_AWS.md](DEPLOYMENT_AWS.md)
**AWS 部署详细指南** - AWS 平台完整部署指南（推荐阅读）

### 📁 [aws/terraform/README.md](aws/terraform/README.md)
**Terraform 多环境配置指南** - 详细的多环境配置说明、Backend配置、变量说明

### 📁 [aws/terraform/ENVIRONMENT_SETUP.md](aws/terraform/ENVIRONMENT_SETUP.md)
**多环境配置说明** - 环境隔离机制、部署流程、配置状态

### 📁 [aws/WORKER_DEPLOYMENT_GUIDE.md](aws/WORKER_DEPLOYMENT_GUIDE.md)
Worker 服务部署指南

---

## 阿里云部署文档

### 📁 [DEPLOYMENT_ALIYUN.md](DEPLOYMENT_ALIYUN.md)
**阿里云部署详细指南** - 阿里云平台完整部署指南，重点说明 ACR 构建服务（推荐阅读）

### 📁 [aliyun/ack/terraform/README.md](aliyun/ack/terraform/README.md)
**阿里云 Terraform 配置指南** - Terraform 多环境配置说明、Backend配置、变量说明

### 📁 [aliyun/ack/ACR_BUILD_SERVICE_CONFIG.md](aliyun/ack/ACR_BUILD_SERVICE_CONFIG.md)
**ACR 构建服务配置指南** - 详细的 ACR 构建规则配置说明，包括 Gitee 连接、构建规则创建等

### 📁 [aliyun/ack/kubernetes/README.md](aliyun/ack/kubernetes/README.md)
**Kubernetes 部署指南** - Kubernetes 资源部署说明

### 📁 [aliyun/ack/scripts/ACR_BUILD_SCRIPTS_README.md](aliyun/ack/scripts/ACR_BUILD_SCRIPTS_README.md)
**ACR 构建脚本使用说明** - 触发和查看 ACR 构建的脚本使用说明

---

## 本地开发文档

### 📁 [local-dev/README.md](local-dev/README.md)
本地开发环境配置

### 📁 [local-dev/S3_EVENT_SETUP.md](local-dev/S3_EVENT_SETUP.md)
S3 事件设置说明

### 📁 [docker/QUICK_START.md](docker/QUICK_START.md)
Docker 快速开始指南

---

## 文档结构说明

```
deploy/
├── README.md                    # 主部署指南（必读）
├── DEPLOYMENT_AWS.md           # AWS 部署详细指南（推荐）
├── DEPLOYMENT_ALIYUN.md        # 阿里云部署详细指南（推荐）
├── DOMAIN_CONFIG.md            # 域名配置说明
├── DOCUMENTATION_INDEX.md      # 本文档（文档索引）
│
├── aws/                        # AWS部署
│   ├── terraform/
│   │   ├── README.md          # Terraform配置指南
│   │   ├── ENVIRONMENT_SETUP.md  # 多环境配置
│   │   └── PLAN_RESOURCES.md  # 资源详细说明
│   └── WORKER_DEPLOYMENT_GUIDE.md
│
├── aliyun/                     # 阿里云部署
│   └── ack/
│       ├── ACR_BUILD_SERVICE_CONFIG.md  # ACR构建服务配置
│       ├── terraform/
│       │   └── README.md      # 阿里云Terraform配置
│       ├── kubernetes/
│       │   └── README.md      # Kubernetes部署指南
│       └── scripts/
│           └── ACR_BUILD_SCRIPTS_README.md  # ACR构建脚本说明
│
└── local-dev/                  # 本地开发
    ├── README.md
    └── S3_EVENT_SETUP.md
```

---

## 快速导航

### 首次部署
1. 阅读 [README.md](README.md) 了解整体架构
2. 查看 [DOMAIN_CONFIG.md](DOMAIN_CONFIG.md) 了解域名配置
3. 根据平台选择：
   - **AWS**: 阅读 [DEPLOYMENT_AWS.md](DEPLOYMENT_AWS.md) 完整部署指南
   - **阿里云**: 阅读 [DEPLOYMENT_ALIYUN.md](DEPLOYMENT_ALIYUN.md) 完整部署指南（重点了解 ACR 构建服务）

### 多环境配置
- [aws/terraform/ENVIRONMENT_SETUP.md](aws/terraform/ENVIRONMENT_SETUP.md) - 环境隔离机制
- [DOMAIN_CONFIG.md](DOMAIN_CONFIG.md) - 域名配置

### 资源说明
- [aws/terraform/PLAN_RESOURCES.md](aws/terraform/PLAN_RESOURCES.md) - 所有资源的详细说明

### 故障排查
- 各平台的 README.md 中包含故障排查章节

---

## 文档更新说明

- ✅ 已删除重复的域名配置文档
- ✅ 已合并域名配置到统一的 DOMAIN_CONFIG.md
- ✅ 已更新所有文档中的域名引用
- ✅ 已添加文档索引便于查找
- ✅ 已创建标准主 README 文档，提供部署概览和快速导航
- ✅ 已创建 AWS 部署详细指南（DEPLOYMENT_AWS.md）
- ✅ 已创建阿里云部署详细指南（DEPLOYMENT_ALIYUN.md），重点说明 ACR 构建服务
- ✅ 已删除非必要文档：
  - `aws/README.md`（已被 DEPLOYMENT_AWS.md 替代）
  - `aliyun/NEXT_STEPS.md`（临时性文档）
  - `aliyun/IMPORT_STATUS.md`（临时性资源导入状态报告）
  - `aliyun/DEPLOYMENT_ISSUES.md`（部署问题已整合到主文档）
  - `aws/terraform/DNS_MANUAL_CONFIG.md`（域名配置已统一到 DOMAIN_CONFIG.md）
  - `aws/terraform/MANUAL_DNS_SETUP.md`（域名配置已统一到 DOMAIN_CONFIG.md）
  - `aliyun/CONFIG_CHECKLIST.md`（临时性配置检查清单）
  - `aliyun/ack/terraform/RESOURCE_IDS.md`（临时性资源ID记录）

