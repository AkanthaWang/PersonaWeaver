# PersonaWeaver 架构

## 运行入口

- 前端入口为 `frontend/src/main.js`，根组件为 `frontend/src/App.vue`，路由位于 `frontend/src/router.js`。
- 后端入口为 `backend/main.py`，应用由 `backend/app/main.py` 装配。
- 当前工作区使用 SQLite 和本地文件，不需要远程数据库、对象存储或独立数据库服务。

## 前端模块

- `frontend/src/domains/`：按业务领域组织页面和领域能力。
- `frontend/src/components/`：跨领域复用组件。
- `frontend/src/api/client.js`：本地后端 API 客户端。
- `frontend/src/stores/`：个人资料与作品工作区状态。
- `frontend/src/styles/`：设计 tokens、基础样式和页面样式。

## 后端模块

- `backend/app/`：API 装配、领域服务、数据库访问边界及模型运行时。
- `backend/local_app/`：当前 SQLite 应用使用的配置、数据库、安全、请求模型、模型调用和后台任务实现。
- `backend/source_preprocess/`：TXT、Markdown、EPUB、PDF、DOCX 解析，文本清洗和章节切分。
- `backend/llm_dispatch/`：Ollama、OpenAI 兼容服务与模型协议调用。
- `backend/scripts/`：本地数据备份与模型连接诊断工具。

业务请求从路由进入领域服务，再访问 SQLite 和本地文件。模型调用通过统一客户端执行；离线解析不要求配置模型。

## 当前边界

作品上传、解析、资料查看、角色卡、对话、个人设置和模型配置属于当前功能。远程 PostgreSQL、Supabase、OSS、语义检索及多模态能力不属于当前本地运行链路。
