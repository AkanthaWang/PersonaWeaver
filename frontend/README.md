# NovelWeaver Frontend

小说角色与剧情工作台前端，聚焦文件上传、角色提取和创作协作流程。

## 📖 目录

- [🧐 简介](#-简介)
- [✨ 功能特性](#-功能特性)
- [📸 演示截图](#-演示截图)
- [🚀 快速开始](#-快速开始)
- [📂 项目结构](#-项目结构)
- [🛠️ 技术栈](#️-技术栈)
- [❓ 常见问题](#-常见问题)
- [🤝 贡献指南](#-贡献指南)
- [📄 许可证](#-许可证)

## 🧐 简介

NovelWeaver Frontend 是 NovelWeaver 的可视化前端系统，面向小说创作过程中的数据沉淀与角色管理。

- 背景：创作过程里角色设定、章节内容和提取结果往往分散，难以统一管理。
- 目标：把上传、解析、提取、浏览和交互串成一条可追踪的工作流。
- 适用人群：网文作者、编辑、内容运营、AI 应用开发者。

## ✨ 功能特性

- 登录与注册：支持用户名密码登录、会话校验和账号信息维护。
- 上传处理：上传 epub/txt/pdf/image 到 OSS，并创建解析任务。
- 一致性保障：OSS 上传失败不入库；入库失败自动回滚 OSS 对象。
- 任务视图：分区展示待解析、解析中、已完成任务并支持进度追踪。
- 角色提取：从书籍角色列表发起手动提取任务。
- 创作配套：数据看板、角色库、聊天和全局设置一体化。

## 📸 演示截图

可在本节放置登录页、上传页、看板页截图或 GIF。

示例文件建议：

- docs/images/login.png
- docs/images/upload.png
- docs/images/dashboard.png

## 🚀 快速开始

### 前置要求

请确保本地环境满足：

- Node.js 18+
- npm 9+

### 安装步骤

1. 克隆仓库

```bash
git clone https://github.com/your-org/NovelWeaver.git
cd NovelWeaver/frontend_vue
```

2. 安装依赖

```bash
npm install
```

3. 配置环境变量

```bash
# macOS/Linux
cp .env.example .env.local

# Windows PowerShell
Copy-Item .env.example .env.local
```

在 `.env.local` 中至少填写以下配置：

```env
# Supabase
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key

# OSS
VITE_OSS_ENDPOINT=oss-cn-shanghai.aliyuncs.com
VITE_OSS_BUCKET=your_bucket
VITE_OSS_BUCKET_HOST=your_bucket.oss-cn-shanghai.aliyuncs.com
VITE_OSS_ACCESS_KEY_ID=your_access_key_id
VITE_OSS_ACCESS_KEY_SECRET=your_access_key_secret
```

4. 启动项目

```bash
npm run dev
```

### 构建与预览

```bash
npm run build
npm run preview
```

## 📂 项目结构

```text
frontend_vue/
├── src/
│   ├── api/                              # API 层 - 业务逻辑与数据交互
│   │   ├── client.js                     # API 入口，整合所有模块导出
│   │   ├── core.js                       # 核心工具函数（ID生成、加密、查询构建等）
│   │   ├── modules/                      # 模块化 API 接口
│   │   │   ├── authApi.js                # 认证相关（注册、登录、用户信息、头像等）
│   │   │   ├── bookApi.js                # 书籍相关（上传、查询、任务状态等）
│   │   │   ├── cardApi.js                # 卡片相关（获取卡片列表等）
│   │   │   ├── chatApi.js                # 对话相关 API
│   │   │   ├── summaryApi.js             # 摘要相关（角色、地点、剧情等）
│   │   │   └── taskApi.js                # 任务相关 API
│   │   └── oss/                          # OSS 存储操作
│   │       ├── ossAvatar.js              # 用户头像上传
│   │       ├── ossBook.js                # 书籍文件上传
│   │       ├── ossCommon.js              # 通用 OSS 操作（put、delete 等）
│   │       └── uploadRepository.js       # 数据库与 OSS 操作编排
│   ├── components/                       # Vue 组件
│   │   └── AppLayout.vue                 # 全局布局组件
│   ├── lib/                              # 三方库集成与配置
│   │   ├── oss.js                        # 阿里云 OSS 客户端初始化
│   │   └── supabase.js                   # Supabase 客户端初始化
│   ├── pages/                            # 页面组件
│   │   ├── LoginPage.vue                 # 登录/注册页
│   │   ├── DashboardPage.vue             # 数据看板页
│   │   ├── UploadPage.vue                # 文件上传处理页
│   │   ├── ChatPage.vue                  # 对话/聊天页
│   │   ├── CharactersPage.vue            # 角色管理页
│   │   └── SettingsPage.vue              # 全局设置页
│   ├── stores/                           # Pinia 状态管理
│   │   ├── auth.js                       # 认证状态（token、用户信息）
│   │   ├── appState.js                   # 应用全局状态（当前任务、书籍等）
│   │   └── settings.js                   # 配置状态（API 密钥、OSS 配置等）
│   ├── App.vue                           # 根组件
│   ├── main.js                           # 应用入口
│   ├── router.js                         # 路由配置
│   └── styles.css                        # 全局样式
├── test_modules/                         # 测试脚本
│   ├── test-oss-connection.js            # OSS 连接测试
│   └── test-supabase-connection.js       # Supabase 连接测试
├── package.json                          # NPM 依赖配置
├── vite.config.js                        # Vite 构建配置
├── index.html                            # HTML 入口
└── README.md                             # 项目文档
```

### 核心架构说明

- **API 层**：采用模块化设计，按业务域分离（auth、book、task 等），共享 core.js 工具函数
- **OSS 层**：统一管理文件上传与删除，支持自动回滚机制
- **状态管理**：Pinia store 管理登录状态、应用全局状态和配置
- **页面路由**：基于 Vue Router 的 SPA 导航，支持权限校验
- **工具库**：lib/ 目录集中管理三方库初始化（Supabase、OSS）

## 🛠️ 技术栈

- 核心框架：Vue 3、Vite 6、Vue Router 4
- 状态管理：Pinia
- UI 组件：Element Plus
- 网络请求：Axios
- 后端能力：Supabase（Auth + PostgREST）
- 存储：阿里云 OSS

## ❓ 常见问题

### 问题 1：UploadPage 提示上传失败，但 OSS 测试脚本通过

可能原因是浏览器 CORS 配置不完整。请检查 OSS Bucket CORS：

- AllowedOrigin 包含当前前端域名（例如 `http://localhost:5173`）
- AllowedMethod 包含 `PUT, GET, OPTIONS`
- AllowedHeader 至少包含 `Content-Type`（建议 `*`）



## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request。

建议流程：

1. Fork 仓库并新建分支
2. 提交最小可复现改动
3. 附上变更说明与测试步骤
4. 提交 PR 并等待 Review

## 📄 许可证

本项目当前按仓库根目录许可证文件执行。

## 👤 作者

NovelWeaver 团队

感谢所有为项目提出建议和提交代码的贡献者。

## 💡 编写小贴士

- README 需随版本迭代同步更新，尤其是环境变量和接口说明。
- 命令与代码块请始终使用带语言标识的 fenced code block。
- 发布前请确认未提交真实密钥（尤其是 `.env.local`）。
