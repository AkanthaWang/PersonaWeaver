# PersonaWeaver 前端

Vue 3 本地故事创作工作台，提供创作概览、作品库、故事资料、角色库、角色对话和偏好设置。打开即可使用，无需登录、注册或设置密码；在个人资料中可上传头像和修改显示名称。

页面路由：`/dashboard`、`/upload`、`/summary`、`/characters`、`/chat`、`/settings`；其余路径统一回落到 `/dashboard`。

技术栈：Vue 3、Vite、Vue Router、Pinia、Element Plus、Axios。通过 `/api/v1` 调用本地后端 REST API。

运行、构建、测试与浏览器验收说明见 [项目详细文档](../docs/DETAILS.md)。
