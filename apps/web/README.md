# Knowhere 前端应用

基于 Next.js 14 + TypeScript + Tailwind CSS + Shadcn UI 构建的现代化前端应用。

## 功能特性

- 🔐 **完整认证系统** - JWT登录/注册 + OAuth第三方登录（Google、Apple、GitHub）
- 🎨 **主题切换** - 支持深色/浅色/系统主题
- 🔑 **API Key管理** - 创建、管理、撤销API Keys
- 💳 **计费管理** - Credits余额、使用统计、交易记录
- ⚙️ **用户设置** - 个人资料、安全设置、偏好配置
- 📱 **响应式设计** - 完美适配桌面端和移动端
- 🎯 **OpenAI风格UI** - 参考OpenAI的现代化界面设计

## 技术栈

- **框架**: Next.js 14 (App Router)
- **语言**: TypeScript
- **样式**: Tailwind CSS
- **组件**: Shadcn UI + Radix UI
- **状态管理**: React Context + Hooks
- **表单**: React Hook Form + Zod
- **主题**: next-themes
- **通知**: Sonner
- **图标**: Lucide React

## 快速开始

### 1. 安装依赖

```bash
pnpm install
```

### 2. 环境配置

创建 `.env.local` 文件：

```env
# API配置
NEXT_PUBLIC_API_URL=http://localhost:5006/api

# OAuth配置（可选）
NEXT_PUBLIC_GOOGLE_CLIENT_ID=your_google_client_id
NEXT_PUBLIC_GITHUB_CLIENT_ID=your_github_client_id
NEXT_PUBLIC_APPLE_CLIENT_ID=your_apple_client_id

# 版权和备案信息配置（可选，运行时动态配置）
# 注意：这些配置在部署时通过环境变量设置，不带 NEXT_PUBLIC_ 前缀
# 国内部署示例（在部署配置中设置）：
# COMPANY_NAME=深圳市渊维科技有限公司
# SIMPLE_COMPANY_NAME=渊维科技
# ICP_NUMBER=粤ICP备2025384995号-3
# ICP_URL=https://beian.miit.gov.cn/
# 海外部署示例：
# COMPANY_NAME=Your Company Name
# SIMPLE_COMPANY_NAME=Your Company
# （不设置 ICP 相关变量即可隐藏备案信息）
```

### 3. 启动开发服务器

```bash
pnpm dev
```

访问 [http://localhost:3000](http://localhost:3000) 查看应用。

## 项目结构

```
apps/web/
├── app/                          # Next.js App Router
│   ├── (auth)/                   # 认证相关页面
│   │   ├── login/               # 登录页面
│   │   ├── register/            # 注册页面
│   │   └── callback/            # OAuth回调页面
│   ├── (dashboard)/             # 仪表板页面
│   │   ├── page.tsx            # 概览首页
│   │   ├── api-keys/           # API Key管理
│   │   ├── billing/            # 计费管理
│   │   └── settings/           # 用户设置
│   ├── layout.tsx              # 根布局
│   └── page.tsx                # 首页重定向
├── components/                   # 组件库
│   ├── ui/                     # Shadcn UI组件
│   ├── auth/                   # 认证相关组件
│   ├── dashboard/              # 仪表板组件
│   ├── common/                 # 通用组件
│   ├── theme-provider.tsx      # 主题提供者
│   └── theme-toggle.tsx        # 主题切换
├── contexts/                    # React Context
│   └── AuthContext.tsx         # 认证上下文
├── hooks/                       # 自定义Hooks
│   ├── useAuth.ts              # 认证Hook
│   └── useToast.ts             # 通知Hook
├── lib/                        # 工具库
│   ├── api.ts                  # API客户端
│   ├── format.ts               # 格式化工具
│   ├── oauth.ts                # OAuth工具
│   └── utils.ts                # 通用工具
└── middleware.ts               # Next.js中间件
```

## 主要功能

### 认证系统
- JWT登录/注册
- OAuth第三方登录（Google、Apple、GitHub）
- 自动token刷新
- 路由保护

### API Key管理
- 创建、查看、管理API Keys
- 启用/禁用API Keys
- 重新生成和撤销
- 使用统计和监控

### 计费管理
- Credits余额显示
- 使用统计图表
- 交易记录
- 购买Credits（集成Stripe）

### 用户设置
- 个人资料管理
- 密码修改
- 通知偏好
- 界面设置

## 开发指南

### 添加新页面
1. 在 `app/(dashboard)/` 下创建新目录
2. 添加 `page.tsx` 文件
3. 在侧边栏导航中添加链接

### 添加新组件
1. 在 `components/` 下创建组件文件
2. 使用 TypeScript 和 Tailwind CSS
3. 遵循 Shadcn UI 设计规范

### API集成
1. 在 `lib/api.ts` 中添加新的API方法
2. 在组件中使用 `useAuth` Hook获取认证状态
3. 使用 `useToast` Hook显示通知

## 部署

### Vercel部署
1. 连接GitHub仓库到Vercel
2. 配置环境变量
3. 自动部署

### 其他平台
1. 构建应用：`pnpm build`
2. 启动生产服务器：`pnpm start`
3. 配置反向代理到API服务器

## 环境变量

| 变量名 | 描述 | 必需 | 默认值 |
|--------|------|------|--------|
| `NEXT_PUBLIC_API_URL` | API服务器地址 | 是 | - |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Google OAuth客户端ID | 否 | - |
| `NEXT_PUBLIC_GITHUB_CLIENT_ID` | GitHub OAuth客户端ID | 否 | - |
| `NEXT_PUBLIC_APPLE_CLIENT_ID` | Apple OAuth客户端ID | 否 | - |
| `COMPANY_NAME` | 公司名称（显示在页脚，运行时配置） | 否 | Knowhere AI |
| `SIMPLE_COMPANY_NAME` | 公司简称（运行时配置） | 否 | - |
| `ICP_NUMBER` | ICP备案号（国内部署时使用，运行时配置） | 否 | - |
| `ICP_URL` | ICP备案链接（运行时配置） | 否 | https://beian.miit.gov.cn/ |

**注意**：
- 这些配置在部署时通过环境变量设置，不带 `NEXT_PUBLIC_` 前缀
- 服务端组件在 SSR 时读取环境变量，通过 React Context 传递给客户端组件
- 如果设置了 `ICP_NUMBER`，页脚会自动显示备案信息
- 海外部署时，只需设置 `COMPANY_NAME`，不设置 ICP 相关变量即可隐藏备案信息
- 支持运行时动态配置，无需重新构建镜像

## 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 创建Pull Request

## 许可证

MIT License
