# PersonaWeaver 后端

本地 FastAPI 服务通过 SQLite 和本地文件保存工作区数据。主要入口与模块说明见 [项目详细文档](../docs/DETAILS.md) 和 [架构说明](../docs/ARCHITECTURE.md)。

在仓库根目录启动：

```powershell
.\backend\start.cmd
```

或直接运行：

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

备份和模型连接检查分别位于 `backend/scripts/backup_local.py` 与 `backend/scripts/check_model_connection.py`。
