# 本地运行与维护

## 1. 安装

推荐 Python 3.11 和 Node.js 22。SQLite 使用 Python 标准库，不需要安装或启动独立数据库服务。默认运行路径已不依赖 PostgreSQL、Supabase 和 OSS。

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

前端：

```powershell
cd frontend
npm ci
```

也可以在根目录执行 `conda env create -f environment.yml`，随后 `conda activate personaweaver`。

## 2. 启动

分别在两个终端运行：

```powershell
# 仓库根目录
.\backend\start.cmd
```

```powershell
# 仓库根目录
.\frontend\start.cmd
```

或者直接使用：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

已通过 `.\scripts\start.cmd` 启动服务时，可使用 `.\scripts\restart.cmd` 停止并重新启动前后端。

前端 `http://127.0.0.1:5173`，API 文档 `http://127.0.0.1:8000/docs`，健康检查 `http://127.0.0.1:8000/health`。

默认仅监听本机。Vite 会在端口占用时尝试下一个端口，以终端输出为准；后端端口占用时需要指定其他端口。使用 `frontend/.env.local` 中的 `PERSONAWEAVER_API_TARGET` 调整代理目标。跨源部署可设置 `VITE_API_BASE_URL`，但同源代理是默认方式。

生产构建：

```powershell
cd frontend
npm run build
```

**构建完成后重新启动后端**，后端会提供 `frontend/dist` 中的 SPA 和静态资产。此时可直接访问 `http://127.0.0.1:8000`，不需要前端开发服务器。

本地任务在服务进程内运行，**只启动一个 worker**。不要通过多个后端实例同时打开同一个数据库；启动恢复逻辑会将未完成任务标记为中断。开发时的 `--reload` 也会中断正在运行的任务。

## 3. 首次使用

1. 打开应用即可进入本地工作台，无需登录、注册或设置密码；在“偏好设置 → 个人资料”中修改显示名称、邮箱并上传头像（PNG、JPG、WebP，最大 2 MB）。
2. 在作品库上传文件，最大 20 MB；点击解析章节即可阅读，不需要模型。
3. 在设置中保存模型服务、地址和名称，并测试连接。
4. 在“模型选用”绑定测试通过的提取模型，发起资料提取，可选择全部章节、前 N 章或连续章节区间；不要求配置 Embedding。
5. 查看资料和章节依据，在“人物档案”里直接看到人物的档案描述和身份标签，展开右侧详情查看约 200 字的档案描述、结构化信息、补充档案、事实与关系；描述偏短时可点击“重新生成”，并一键生成角色卡或手动编写角色卡。
6. 从角色卡开始对话，或创建普通创作助手会话。

未保存模型设置的账户会使用根目录 `.env` 中的 `ECNU_API_BASE_URL`、`ECNU_API_KEY`、`ECNU_MODEL_NAME` 作为初始配置，模型服务选择“OpenAI 兼容”。进程环境变量优先于 `.env`，密钥不会返回给前端。已保存的账户设置优先，不会被初始配置覆盖；设置页面空白密钥输入会保留初始密钥，保存后使用账户配置。修改后端代码后需关闭原后端窗口并重新启动，统一启动脚本不会替换已经运行的后端。

若未配置 ECNU 地址或模型名称，则回退到 `Ollama / http://127.0.0.1:11434 / qwen2.5:7b`。需要自己启动 Ollama 并准备该模型，或改为已安装的模型名称。应用不会自动下载模型。

如果更新代码后仍提示连接本地模型失败，先检查 `http://127.0.0.1:8000/health` 是否包含 `"model_config_version":"ecnu-env-v1"`。缺少该字段说明服务未加载新版配置代码；启动脚本会提示旧进程 PID，先在 PowerShell 执行 `Stop-Process -Id <PID>` 再重新启动（会中断运行中的任务）。ECNU 是远程服务，无需启动本机模型；请先在设置中测试连接成功再执行提取。缺少 ECNU 密钥、代理失败和 TLS 错误会分别显示明确提示。

运行 `scripts/diagnose-model.cmd` 可检查后端版本及 `.env` 配置的 ECNU HTTPS 连接。该诊断只发不带密钥的 GET、不调用模型、不写数据库；返回 HTTP 状态只能说明传输可达，不能说明密钥或模型有效。代理、证书、网络错误会显示异常类型和数值错误码，不显示密钥或异常原文。请在本机终端运行：受限沙箱中的连接失败不能代表普通后端进程的网络状态。新版后端也会把模型传输异常的脱敏类型和错误码记入后端日志。

OpenAI 兼容服务的地址填写到 `/v1` 等 API 前缀，或完整 `/chat/completions` 地址；例如 `http://127.0.0.1:1234/v1`。兼容服务可以不要求 API Key；vivo 需要 API Key。这里的“OpenAI 兼容”表示请求协议，不保证任意提供商支持全部参数。

文件上传、章节解析、手动角色卡和历史会话管理可离线使用；**模型提取和生成回复需要可用模型**。远程模型会接收发送的文本和角色设定，使用敏感素材前应确认提供商的数据政策。

## 4. 本地数据

默认目录（仓库根 `db/`，与模型配置 `db/agent/` 并列）：

```text
db/
  agent/                 # 模型配置 models.json / settings.json
  personaweaver.sqlite3  # 用户、作品索引、模型设置、角色卡和会话
  uploads/
  avatars/
  novel/
    <book_id>/
      extraction.sqlite3 # 本作品的章节、提取结果、资料、任务与检查点
      unified.txt
      chapters/
      chapters.json
  backups/
```

主数据库存储用户、令牌哈希、作品索引、模型配置、角色卡、会话和消息。每本作品目录内的 `extraction.sqlite3` 存储该作品的章节、任务、任务日志、提取结果、资料汇总、实体归并、向量缓存和提取检查点。源文件和头像在本地文件目录。章节解析结果同时导出到 `novel/<book_id>/`，包括清洗后的 `unified.txt`、`chapters/0001.txt` 等逐章文本及章节来源信息 `chapters.json`；章节列表接口返回 `text_path`。重解析只替换正文导出文件，不会删除作品数据库。删除书籍时会清理整个作品目录。启动时会初始化主库和作品库 schema，并把旧版本主库中的作品数据迁移到对应作品库。
模型与 Provider 配置由 `db/agent/models.json` 与 `db/agent/settings.json` 持久化（可通过 `PERSONAWEAVER_AGENT_DIR` 覆盖）；设置页保存或激活的模型会写入 `settings.json`，下次启动优先从该文件加载。

可在启动进程前设置环境变量：

```powershell
$env:PERSONAWEAVER_DATA_DIR = "D:\PersonaWeaverData"
$env:PERSONAWEAVER_DB_PATH = "D:\PersonaWeaverData\personaweaver.sqlite3"
.\backend\start.cmd
```

本地模型初始配置只使用根目录 `.env` 的三个 `ECNU_*` 字段，不会将其他旧配置加载到进程环境，也不会因存在云端凭据而连接远程数据库或把文件上传到 OSS。配置路径建议使用绝对路径。不要把 `PERSONAWEAVER_DB_PATH` 指向不属于本应用的 SQLite 文件。

默认使用单一本地工作区。无 Authorization 的请求复用数据库中最早创建的账户及其作品、模型设置和头像；空数据库自动建立没有密码的创作者资料。旧账户不被删除。上传文件使用生成的文件名；删除作品会级联删除其章节、任务、资料与角色卡。相关会话保留，但失去角色卡关联。

前端不使用登录令牌或账户密码。旧认证接口保留兼容用途，显式 bearer 请求仍按原账户检查所有权。本地工作区的访问不依赖该认证机制。模型 API Key 是模型服务凭据，仍可在模型设置中填写。

**模型 API Key 在本地配置文件中明文保存**，接口只返回是否已配置，不回传密钥；空白输入保留原密钥，接口提交空字符串则删除密钥。请限制 `db/agent/`、数据目录和备份的访问权限，不提交到 Git，不将本地开发服务直接暴露到公网。

## 5. 任务和结果

- 同一作品同时只能有一个解析或提取任务。
- 模型请求配置包含超时；错误会写入任务和日志，不会生成模拟结果冒充成功。
- 长章节优先按段落切分，单段最多 6000 个 Unicode 字符、相邻段最多重叠 300 字符，所有分段完整处理。
- 提示词集中放在 `backend/app/ai/prompts/`：`extraction.py` 保存主提取、受控补查、结构修复、Agent 恢复决策、人物综合和旧版兼容提示；`conversation.py` 保存对话默认系统提示与上下文压缩/分支摘要；`protocol.py` 保存协议级 JSON 指令。管道、provider 和领域代码只引用这些常量，不再内嵌提示词。
- 完整成功的章节、累计资料、实体映射和资料版本在一个数据库事务中更新。失败章节保留上一轮结果；补查失败保留待核实问题，人物综合失败保留事实并隐藏未完成综合。至少一个章节完整成功才允许发布；整轮失败或取消不改上一轮已发布结果。
- 增量提取保留范围外已发布章节；默认复用同原文、模型及流程版本的检查点，强制重算仅重新提取选定章节。资料页累计展示所有已发布章节，不提供按章无剧透快照。
- 已有提取结果的作品不能重新解析，以避免章节与已有依据失配；需要上传新版本。
- 四类资料为人物、剧情、物品、世界与地点。同名只作为候选；相同身份且无冲突的人物、同一处原文记录或明确别名依据才能自动归并，其余保留独立条目待确认。关系、身份和物品归属变化按章保留。
- 模型输出使用严格结构校验；每条事实必须带输入片段 ID 与逐字引文，后端生成事实 ID、章节与字符偏移。`summary/description/identity/appearance/personality/time/owner/significance/type` 等标量字段必须是单个字符串，多值字段必须为数组；类型不符不能当作成功，只允许一次修复。若模型接口只返回 `choices/usage` 等响应包或内容为空，不再把响应包当作提取 JSON，而是明确提示输出为空、可能被 `max_tokens` 截断或仅返回推理内容。原文阅读器点击依据定位高亮，旧资料无定位信息时兼容显示章节内容。
- 引文匹配证明该字符串出现在原文中，不证明模型对事实、人物身份或关系的理解正确，也不等同于人工核验。人物综合是模型归纳，逐段绑定已有事实 ID，不能使用未知 ID；仍需人工检查语义支持程度。
- 身份、别名、指代歧义最多补查两轮，每轮最多三个片段、合计 6000 字符；关键词和相邻章节读取严格限制于本次选定范围，不调用向量服务。无法解决的问题保留警告。
- 人物综合按章顺序分批处理，检查点独立保存；仅事实或模型发生变化时更新。人工合并、拆分使用来源记录与资料 revision，并在提取任务执行时禁用；失效综合立即隐藏，下一轮提取再更新。
- 人工决定不能映射到重提取后的来源时转为待确认，不自动套用；可以忽略失效决定，或针对新的来源重新操作。已确认拆分不会仅因为同名再次自动合并。
- 已创建的角色卡是可编辑资产，后续重新提取不会自动覆盖角色卡。
- 人物档案列表展示可直接用作角色卡简介的摘要（优先取综合档案首段，其次简介/身份，最后性格/外貌，截断 220 字）。详情统一在右侧抽屉中查看：人物档案头部（头像、别名、状态、次数、登场章节）、约 200 字档案描述、结构化基本信息、补充档案、人物关系、按类型列出的事实依据（可回原文、可删除）；档案描述可点击“重新生成”调用 `POST /api/v1/books/{book_id}/knowledge/characters/{character_id}/synthesize` 按最新提示重新归纳。右侧抽屉底部可“生成角色卡”，由 `POST /api/v1/cards/from-character` 依据最新档案生成 Markdown 正文与简介；同名角色卡已存在时返回既有卡片（传 `overwrite=true` 才用最新档案覆盖，会覆盖手工编辑）。
- 会话使用最近 40 条消息及当前角色卡正文；不具备无限上下文。
- 模型回复成功后才把本轮用户消息与回复一并落库。请求失败时页面保留输入以便重试。
- 任务详情支持进度、分段明细、恢复决策、复用数量、取消和失败/部分完成续跑。取消在当前模型请求返回或超时后停止；正式发布持有事务锁并再次检查取消标记，已发布完成的任务不能取消。
- `extraction_units` 保存分段、恢复决策、补查和人物综合检查点；`knowledge_entities` 保存实体映射；`entity_resolutions` 保存人工决定。任务仅保存请求范围、模型 Profile 引用与配置/输入指纹，不保存 API Key。
- 服务重启将进行中的任务标为失败，保留成功检查点，用户手动续跑创建关联新任务；原文或模型配置变化时拒绝续跑并要求重新提取。补查缓存还绑定可读范围，不将旧任务范围外资料带入本轮。没有跨进程队列和自动付费恢复。
- 结构或引文校验错误允许一次修复；超时、限流和临时服务错误最多重试两次，鉴权错误直接失败。任务只在配置的模型上运行，不自动更换提供商。

提取使用受限的 `ExtractionAgent` 执行循环，而不是把整本书视为一个不可分割的 workflow。章节分段、受控补查和人物综合都是独立动作，Agent 根据动作失败观察在有限次数内选择 `retry`、`split` 或 `skip`；程序校验工具可用性、恢复深度和输出结构。未知错误、取消和资料版本冲突仍会终止任务，结构错误、空输出和已耗尽底层重试的传输错误可以跳过当前动作并继续其他动作。成功章节才会进入原子发布，失败章节保留上一轮结果。任务可能以 `completed_with_warnings` 完成，详情页展示跳过检查点并允许续跑。

阶段顺序仍由程序约束，模型只决定失败动作的恢复方式，恢复深度最多 2。决策通过普通 JSON 输出，不要求模型支持原生工具调用；只有长于 1000 字符的原文分段提供 `split`。网络不可用时不额外请求模型决策；决策格式错误或选择未授权工具时保留失败并继续，鉴权错误直接终止。续跑创建新任务，复用完整检查点并重新执行未完成动作。

提取 Agent 不负责事实判断或直接写入资料；模型只提供结构化事实和恢复建议，后端负责原文引文校验、检查点、归并、权限和发布事务。本轮不包含对话工具、MCP 或长期记忆。新表与字段按现有版本 1 的增量初始化规则添加；旧提取和角色卡保留，旧资料在下次提取时纳入累计事实视图。

## 6. 备份与恢复

创建数据库一致性快照（包含已提交的 WAL 事务；同时备份主库和每本作品的 `extraction.sqlite3`）：

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.backup_local
```

指定新的主库目标文件：

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.backup_local --output "D:\Backups\personaweaver.sqlite3"
```

脚本拒绝覆盖已有文件；作品库会以 `<主库名>-<book_id>-extraction.sqlite3` 写入同一目录。不能在数据库运行时只复制 `.sqlite3` 主文件作为完整备份。

完整备份应同时包含数据库、`uploads` 和 `avatars`。为了保持数据库与文件的一致性，先停止后端，再创建数据库快照并复制文件目录；不要把带模型密钥的备份公开分享。

恢复时先停止后端，将旧数据目录移至另一个安全位置，再放回数据库快照及对应文件目录。不要混用旧 WAL/SHM 文件和新的数据库快照。如果更换数据目录，当前源文件记录使用绝对路径，还需要更新 books.source_path；优先在原目录恢复。

## 7. 测试

```powershell
# 根目录，禁用机器上与本项目无关的 pytest 插件
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
.\.venv\Scripts\python.exe -m pytest -q
```

```powershell
cd frontend
npm test
npm run build
```

后端测试使用临时 SQLite 和文件目录，覆盖身份验证、权限隔离、上传/解析、任务恢复、原子结果更新、模型配置、角色卡、消息历史、错误回复及备份。模型调用使用替身，不依赖真实服务或产生模型费用。前端测试覆盖免登录资料读取、忽略旧令牌、上传格式、错误处理和工作区重置；本地工作区测试覆盖无密码初始化、头像上传、资料与模型持久化及旧账户复用。

模型规格中的上下文窗口、能力标记及价格是模型说明，按模型 ID 保存在当前浏览器，不会改变后端模型协议；最大输出、Temperature、Top P 和超时通过后端模型配置保存。

浏览器验收脚本为 `frontend/test/ui-smoke.cjs`，需可用的 Playwright、Chrome（或设置 `PW_TEST_BROWSER=msedge`）和 Python 后端依赖。构建后运行 `node test/ui-smoke.cjs`；脚本使用临时数据库及本地端口 18761，验证免登录路由、资料和头像持久化、模型说明以及 320–1440px 布局，截图写入 `.docs/plan/assets/`。可通过 `NODE_PATH` 指定 Playwright 安装位置、`PW_TEST_PYTHON` 指定 Python。

作品提取验收为 `node frontend/test/extraction-smoke.cjs`，先构建前端；使用独立临时数据库、模型替身和端口 18763，覆盖模型/范围选择、失败续跑、Agent 跳过中间章节后继续、部分发布与续跑补齐、原文高亮、实体拆分、角色卡和 320–1440px 响应式布局。支持 `NODE_PATH`、`PW_TEST_PYTHON`、`PW_TEST_EXECUTABLE`；`PW_TEST_OUTPUT` 指定截图目录，默认 `.docs/plan/assets/2026-10-17-extraction/`。2026-10-19 的 Agent 验收截图保存在 `.docs/plan/assets/2026-10-19-extraction-agent/`。替身仅存在于测试模块，不由正式应用导入；不调用真实模型。

真实模型提供商联调需用户授权后单独进行。2026-10-17 已使用默认 `ecnu-max`（ECNU Responses 协议）在隔离临时数据库完成单章短文验收：连接测试、1 章提取和 2 个人物综合成功，覆盖 2 人物、3 物品、2 剧情、3 地点；6 条引文按 Unicode 偏移逐字匹配原文，2 段综合均绑定已有事实 ID，任务无待核实问题，输出未包含 API Key。验证中发现模型偶尔将 `identity/appearance/personality` 等标量返回为数组，严格校验按预期拒绝；提取提示词和修复提示已明确标量必须为单个字符串、禁止数组，复测通过。另对 `GLM-4.5-Air` 做隔离诊断：`max_tokens=2048` 时输出被截断（`total_tokens=3139`、消息内容为空）；提高到 8192 后不再截断，但仍出现 `behavior/speech` 字符串和剧情事件缺少 `name`，说明该模型不适合严格提取，建议使用 `ecnu-max`。真实模型请求仅用于本次小范围验收，未写入正式数据库；结果记录在 `.docs/plan/assets/2026-10-17-extraction/real-model-validation.json`。默认 Conda `pytorch` 若仍为 Python 3.9，请使用 Python >=3.10 的独立环境运行本项目，不应为了运行测试直接升级现有训练环境。

## 8. 接口

所有业务接口前缀 `/api/v1`，除注册、登录、健康检查和公开头像外，需要 `Authorization: Bearer <token>`。

| 领域 | 主要接口 |
| --- | --- |
| 账户 | POST `/auth/register`、`/auth/login`、`/auth/logout`；GET `/auth/me` |
| 资料 | PATCH `/auth/profile`、`/auth/role`；PUT `/auth/password`；POST `/auth/avatar` |
| 模型 | GET/PUT `/settings/model`；POST `/settings/model/test` |
| 作品 | GET/POST `/books`；GET/DELETE `/books/{id}`；GET `/books/{id}/source` |
| 章节 | POST `/books/{id}/parse`；GET `/books/{id}/chapters`、`/books/{id}/chapters/{chapter_id}` |
| 提取 | POST `/extract`；GET `/tasks`、`/tasks/{id}`、`/task-logs` |
| 任务控制 | GET `/tasks/{id}/units`；POST `/tasks/{id}/cancel`、`/tasks/{id}/retry` |
| 结果 | GET `/chapter-extractions?book_id=...`、`/summaries?book_id=...` |
| 实体校正 | POST `/books/{id}/entity-resolutions`；DELETE `/books/{id}/entity-resolutions/{resolution_id}?revision=...`（忽略失效决定）；POST `/books/{id}/rebuild-knowledge?revision=...`（整理已有资料） |
| 角色卡 | GET/POST `/cards`；PATCH/DELETE `/cards/{id}`；GET `/cards/{id}/export` |
| 对话 | GET/POST `/conversations`；GET/PATCH/DELETE `/conversations/{id}` |
| 消息 | POST/DELETE `/conversations/{id}/messages` |

上传接口使用原始文件 body，`Content-Type: application/octet-stream`，文件名通过 `filename` 查询参数传入；不是 multipart。作品另外支持 `title`、`author`、`language` 查询参数。详见自动生成的 `/docs`。

`POST /extract` 接受 `book_id`，以及互斥的 `max_chapters` 或成对的 `chapter_start/chapter_end`；省略范围表示全书。`force` 默认 false；范围越界返回 422，同书活动任务返回 409。未解析作品仍会先自动解析，此时范围在解析后校验。

`GET /summaries` 保留 `summaries`，增加 `revision`、`coverage`（累计章序号）、`pending_count`、`warnings` 和 `pending_resolutions`。四类 content 仍为数组，实体新增 `entity_id/source_ids/evidence/synthesis/synthesis_status`；`evidence.sources` 的 `start/end` 为章节原文 Unicode 字符偏移，右边界不包含终点。

实体校正请求为 `{revision, action: "merge"|"split", source_ids, other_source_ids?}`；拆分选择同一实体的部分来源，剩余来源由服务端计算。`source_ids` 来自资料实体，而不是客户端生成。创建角色卡可额外指定 `source_entity_id`；同名多实体时必须指定该字段，同名卡仍需另取卡名。续跑接口返回新 `task_id`，仅接受失败或取消的提取任务。

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/books?filename=story.txt" `
  -H "Authorization: Bearer <token>" `
  -H "Content-Type: application/octet-stream" `
  --data-binary "@<本地文本文件路径>"
```

## 9. 提取前后端参考设计

提取相关设计参考 [Novel Fan Graph](https://github.com/LucianaiB2004/novel-fan-graph)。2026-10-19 已核对该仓库的 README、`references/extraction-prompt.md`、`references/data-schema.md` 和 `references/acceptance-checklist.md`；以下为设计参考，尚未实现的能力不代表当前功能。

| 参考点 | 本项目对应位置与采用方向 |
| --- | --- |
| 证据优先的原子事实 | `backend/app/ai/prompts/extraction.py` 与 `backend/app/ai/extraction_pipeline.py`；保持逐字引文校验和程序生成 ID，完善短引文、单条事实及禁止推断关系的规则 |
| 人物状态与关系按章演化 | `backend/app/domains/documents/knowledge.py`；保留按章事实和明确的归并依据，后续图谱需建立可追溯的实体引用 |
| 分批提取与跨批归并 | 沿用本项目按章分段、检查点和有限恢复，参考其分离事实提取与归并的思路；批次大小按输入与输出限制决定 |
| 章节导航与事件时间线 | `frontend/src/domains/documents/views/SummaryView.vue`；优先按章组织剧情事实，并复用 `ChapterReader.vue` 回查原文 |
| 人物关系、场景与势力视图 | 后续需先明确数据契约、实体引用和变化章节；地点只表达有依据的层级与连接，不推测坐标 |
| 数据与浏览器共同验收 | 后端校验结构、引文和归并，前端检查章节切换、详情、原文定位及窄屏布局 |

参考项目的“第 N 章防剧透”依赖姓名揭晓、身份、状态和关系阶段等历史数据。当前作品资料是累计视图，仅过滤事实来源章节仍可能显示后续姓名或综合描述；防剧透需另行设计历史投影及测试。

缺失章节占位也需先明确小说原始章号与本地章节顺序索引的对应关系，避免改变既有章节定位。参考项目的固定十章批次和模型分配 ID 不直接套用到当前提取协议。

### 2026-10-19 实体档案与章节时间线

作品资料已采用实体档案与独立剧情时间线。同名资料先规范全角字符、空白和大小写；人物按同名及短的明确身份标签检查，身份栏中的长描述句不当作稳定身份标签；物品/地点按同名及明确类型冲突检查。冲突时，无身份/类型的中间记录不会作为桥梁强行合并；显式别名仍需原文同时出现姓名与别名。不同实体、同名冲突及人工拆分边界保持可确认、可校正。

投影汇总全部描述字段和列表字段，列表去重，标量采用最后一次明确记载值。`field_history` 保存字段值、章节和事实 ID，重复连续值只补充依据；归属返回旧值时仍产生新的阶段。实体同时带 `first_chapter`、`last_chapter`、`chapter_id`、`chapter_no` 和 `projection_version`。详情只显示一份概览，再展示按章变化，原始章节记录折叠为证据，可展开并回查原文。

剧情按来源章节号与原文偏移排序，同名但跨章的事件保持独立；仅同引文、同描述的重复事件可以去重。`time` 保留原文时间表达，不猜测相对日期，也不把倒叙强行转换成故事绝对时间。前端支持来源章节筛选、搜索及原文定位；来源筛选仍为累计资料的筛选，不代表防剧透快照。

新提取对人物、物品和世界/地点生成综合档案；较长实体先分批综合，再生成一份最终档案，避免拼接多份简介。综合缓存包含提示词版本并校验引用事实 ID。旧资料缺少逐字引文时保留原记录，不为其额外生成无法回查的模型档案。

“整理已有资料”调用 `POST /books/{id}/rebuild-knowledge?revision=...`，仅使用已保存的章节事实重建四类资料，保留有效人工拆分/合并与未变化档案的综合结果，不调用模型，也不修改原文章节和用户编辑的角色卡。旧分组发生合并后综合档案会待更新，界面先显示已有描述与按章字段；后续正常提取可生成新的综合档案。提取任务执行中或版本过期返回 409。

### 2026-10-19 提取质量与关系视图

提取版本为 `evidence-v4-normalized-key-facts`。严格类型校验之后清理事实字段的首尾空白、空列表项及重复列表项，保留重要行为、台词和描述；引文原样保留，包含最终被关键性筛选移除的记录也必须先通过逐字引文校验。重复待核实问题在提取与分段组合时去重。版本升级会使旧检查点失效，已有发布资料仍保留；需要新规则结果时重新发起提取。

人物关系以实体 ID 区分节点，按当前人物指向关系目标保留方向，重复关系汇总来源。同名目标有多个候选时显示独立的“同名待确认”节点，不自动连到某一份档案。仅有关系名称但没有对应档案的目标显示为未建档节点。关系来源按所选章节筛选，可直接回查原文；档案、时间线和场景视图统一响应搜索与来源筛选，资料仍是累计视图。

提取弹窗显示选定范围及已覆盖、尚未覆盖数量；覆盖不代表检查点一定可复用，模型、原文和版本指纹仍决定实际复用。任务详情显示动作统计、异常筛选、可读章节与字符范围、事实数量、实际恢复动作及资料入口；`GET /tasks/{id}/units` 额外返回 `chapter_no`、`chapter_title`、`recovery_tool`，不返回模型载荷。
## 6. 知识库 CRUD 与生命周期

知识库数据存储在每本作品的 `extraction.sqlite3` 中。原文证据表
`knowledge_evidence` 不随知识编辑覆盖；人物、人物事实、事件、线索和关系使用当前状态字段、版本字段及软删除字段管理。

当前已提供知识库 API：

- `/api/v1/books/{book_id}/knowledge/characters`
- `/api/v1/books/{book_id}/knowledge/characters/{character_id}/facts`
- `/api/v1/books/{book_id}/knowledge/events`
- `/api/v1/books/{book_id}/knowledge/clues`
- `/api/v1/books/{book_id}/knowledge/changes`

Agent 或用户创建的事实必须尽可能绑定章节证据。事实更新会创建新版本并将旧版本标记为
`superseded`；删除默认只从当前视图移除，变更记录写入 `knowledge_changes`。人物支持软删除和恢复。
默认查询只返回未删除的当前记录，审计查询通过变更日志查看历史。

关系支持创建、读取、修改和软删除；人物支持合并及撤销合并；提取任务发布时会把 Agent
变更写入批次号，可通过 `/api/v1/books/{book_id}/knowledge/batches/{batch_id}/rollback` 回滚该批次。
无法解析关系目标的人物会进入 `knowledge_reviews`，可在知识库页面或审核 API 中处理。
伏笔可通过 `/api/v1/books/{book_id}/knowledge/clues/{clue_id}/verify` 从候选状态转为
`revealed`。前端知识库入口为 `/knowledge`。
