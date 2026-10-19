# CLAUDE.md

本文件为 Claude Code 在本仓库中工作时提供指引。

## 项目结构

- `frontend/` —— 前端代码
- `backend/` —— 后端代码
- `docs/` —— 项目详细文档（`DETAILS.md`）
- `.docs/plan/` —— 每次任务的计划与记录

## 工作记录规范

每次执行任务时，需在 `.docs/plan/` 下新建一个 Markdown 文件记录计划与结果：

- 命名格式：`年-月-日-时间-事件.md`，时间为 24 小时制 `HHmm`
- 示例：`2026-01-15-1430-重构README.md`
- 内容建议包含：目标、方案、改动文件、结果/遗留问题

## 常用命令

<!-- 待补充：前端/后端的安装、启动、测试、构建命令 -->

## 约定

- README 只保留项目整体介绍与技术栈，具体细节写入 `docs/DETAILS.md`
- 前端改动限定在 `frontend/`，后端改动限定在 `backend/`
- 每完成一个功能后，执行 `git add .` 并提交：
  ```bash
  git add .
  git commit -m "相关功能"
  ```