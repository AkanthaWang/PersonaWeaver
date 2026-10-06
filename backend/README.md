# Backend Workflow (L0 -> L2)

本目录实现你当前阶段需要的工作流：

输入 -> 多源文件解析 -> 文本清洗 -> 章节/逻辑分块 -> LLM逐章结构化提取

## 目录结构

- `main.py`: FastAPI 入口，保持保留
- `config.json`: 本地缓存路径 + LLM 配置 + 逐章提取 prompt
- `source_preprocess/`: 源文件预处理
  - `parsers/`: 多源文件解析入口（当前先实现 txt/md）
  - `text_cleaner.py`: 文本清洗
  - `chapter_chunker.py`: 章节/逻辑分块
  - `pipeline.py`: 统一预处理流水线（并写入本地缓存）
- `llm_chapter_extraction/`: L1 -> L2 逐章结构化提取
  - `extractor_client.py`: 通过统一 LLM client 调用当前 provider，并解析 JSON
  - `chapter_structured_extractor.py`: 按维度逐章提取并合并结果
- `workflow_runner.py`: 串联输入解析/清洗/分块/逐章提取的一体化脚本
- `test/`: 测试代码与测试说明（当前先写不执行）

## 本地缓存说明

本地缓存目录在项目根目录：
- `local_cache/<book_title>_<book_id>/source_input/`: 从 `source_files.file_url` 拉取后的本地源文件
- `local_cache/<book_title>_<book_id>/unified_format/`: 统一格式文本
- `local_cache/<book_title>_<book_id>/chapter_content_text/`: 章节文本文件
- `local_cache/<book_title>_<book_id>/extraction_json/`: L2 逐章结构化结果 JSON

说明：
- 缓存目录按书名和书籍ID自动分隔，命名格式为 `书名_book_id`。
- 当提供 `file_url` 时，流程会先下载到 `source_input`，再从本地缓存继续解析/清洗/分块。
- `txt/md` 输入在落入 `source_input` 后会自动归一化为 UTF-8，避免后续统一文本和章节文本继续乱码。
- 章节切分阶段会自动去掉重复标题行，并对过短章节做丢弃/合并处理，减少只有标题的伪章节。

数据库仅存 URL/路径：
- L0: `source_files.unified_format_url`
- L1: `chapters.content_text_url`
- L2: `chapter_extractions.book_extraction_json_local_url` + `chapter_extractions.book_extraction_json_oss_url`
- Summary: `summary.content_local_url` + `summary.content_oss_url`

注意：当前实现里，L2 会按 `extractor_type`（`character/plot/item/location/full`）合并整书 JSON，再上传到 OSS；`summary` 会按维度分流输出，其中 `characters`、`items` 落盘为 JSON，`storyline_events`、`world_locations` 落盘为 Markdown，并且数据库里的 `summary.content_local_url` / `summary.content_oss_url` 都精确保存到具体文件，而不是目录。角色卡生成时会优先读取 `summary.characters` 中选中的角色条目，再结合章节证据补充，且卡片本身现在只输出 Markdown 文件，数据库中的 `card.content_local_url` / `card.content_oss_url` 也会直接对应到该文件。

## 使用示例

### 0) 一次性准备

先确保依赖和本地环境变量可用。当前推荐把校园 API、数据库、OSS 等私密配置放在项目根目录 `.env`，后端会自动读取：

```powershell
pip install -r requirements.txt
copy .env.example .env
```

当前主模型路径默认走校园远程 API，请至少在 `.env` 中配置：

```env
ECNU_API_BASE_URL=https://chat.ecnu.edu.cn/open/api/v1/chat/completions
ECNU_API_KEY=<你的校园API密钥>
ECNU_MODEL_NAME=ecnu-max
```

如果要走远程入库，请确认 `.env` 中至少存在 `SUPABASE_DB_URL`，或者可用的 `DATABASE_URL` / `SUPABASE_POOLER_DB_URL`。

### 0.1) 启动后端接口（可选）

如果你还需要 FastAPI 入口，可以单独启动：

```powershell
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

这不是 L0 -> L2 主流程本身，只是保留给旧接口和前端使用。

### 1) 源文件预处理（txt）

```python
from backend.source_preprocess import process_source_file

result = process_source_file(
    source_path="data/神游.txt",
    source_type="txt",
    source_file_id="sf_demo_001",
  file_name="神游.txt",
    filter_noise=True,
)
print(result["unified_format_url"])
print(len(result["chapters"]))
```

对应的单独函数是 `backend.source_preprocess.process_source_file(...)`。

命令行单独运行这一段：

```powershell
python -c "from backend.source_preprocess import process_source_file; result = process_source_file(source_path='data/神游.txt', source_type='txt', source_file_id='sf_demo_001', file_name='神游.txt', filter_noise=True); print(result['unified_format_url']); print(len(result['chapters']))"
```

也可以直接按 `source_files` 记录处理：

```python
result = process_source_file(
  file_url="https://example.com/source/shenyou.txt",
  file_name="神游.txt",
  source_type="txt",
  source_file_id="sf_demo_001",
)
```

### 2) 逐章结构化提取

```python
from backend.llm_chapter_extraction import extract_chapter_structured

chapter_result = extract_chapter_structured(
    chapter_title="第一回",
    chapter_text="章节正文...",
)
print(chapter_result)
```

对应的单独函数是 `backend.llm_chapter_extraction.extract_chapter_structured(...)`。

命令行单独运行这一段：

```powershell
python -c "from backend.llm_chapter_extraction import extract_chapter_structured; print(extract_chapter_structured(chapter_title='第一回', chapter_text='章节正文...'))"
```

### 3) 一体化运行（L0 -> L2）

```python
from backend.workflow_runner import run_l0_to_l2_pipeline

result = run_l0_to_l2_pipeline(
  source_path="data/神游.txt",
  source_type="txt",
  source_file_id="sf_demo_001",
)
print(result["source_file_row"])
```

对应的总入口函数是 `backend.workflow_runner.run_l0_to_l2_pipeline(...)`。

命令行一键运行这一段：

```powershell
python -c "from backend.workflow_runner import run_l0_to_l2_pipeline; import json; result = run_l0_to_l2_pipeline(source_path='data/神游.txt', source_type='txt', source_file_id='sf_demo_001', file_name='神游.txt', filter_noise=True); print(json.dumps(result['source_file_row'], ensure_ascii=False, indent=2))"
```

如果要同时上传到远程 Supabase：

```powershell
python -c "from backend.workflow_runner import run_l0_to_l2_pipeline; import json; result = run_l0_to_l2_pipeline(source_path='data/神游.txt', source_type='txt', source_file_id='sf_demo_001', file_name='神游.txt', filter_noise=True, upload_chapters_to_remote=True, user_id='u_demo_001', username='demo_user', book_id='b_demo_001', book_title='神游'); print(json.dumps(result['remote_persist'], ensure_ascii=False, indent=2))"
```

开启章节远程入库（会把 `users/books/source_files/chapters/chapter_extractions` 一并 upsert，并上传 L2 聚合 JSON 到 OSS）：

```python
from backend.workflow_runner import run_l0_to_l2_pipeline

result = run_l0_to_l2_pipeline(
  source_path="data/神游.txt",
  source_type="txt",
  source_file_id="sf_demo_001",
  upload_chapters_to_remote=True,
  user_id="u_demo_001",
  username="demo_user",
  book_id="b_demo_001",
  book_title="神游",
)
print(result["remote_persist"])
```

说明：
- 连接串读取顺序：函数参数 `remote_db_url` > `SUPABASE_DB_URL` > `DATABASE_URL`。
- 如果以上变量都不存在，会抛出配置错误。
- 若 `db.<project-ref>.supabase.co` 在当前网络无法解析，程序会自动尝试 Supabase pooler。
- 可选覆盖：`SUPABASE_POOLER_DB_URL`（完整连接串）或 `SUPABASE_POOLER_HOST` + `SUPABASE_POOLER_PORT`。
- `source_files.parse_status` 会按 `pending/running/parsed/failed` 流转（点击开始提取后为 `running`，整链路成功后为 `parsed`）。
- `extraction_tasks` 会记录 `chapter_extraction` 与 `summary` 两类任务进度。
- `word_count` 当前统计的是章节文本字符数。
- 远程上传依赖 OSS 环境变量：`OSS_ENDPOINT/OSS_BUCKET/OSS_ACCESS_KEY_ID/OSS_ACCESS_KEY_SECRET`（兼容 `VITE_` 前缀变量）。

### 4) 这些版块是否都封装成了可单独调用的函数

是的，当前已经封装好了：

- [backend/source_preprocess/pipeline.py](backend/source_preprocess/pipeline.py) 里的 `process_source_file(...)`
- [backend/llm_chapter_extraction/chapter_structured_extractor.py](backend/llm_chapter_extraction/chapter_structured_extractor.py) 里的 `extract_chapter_structured(...)`
- [backend/workflow_runner.py](backend/workflow_runner.py) 里的 `run_l0_to_l2_pipeline(...)`

它们也都被包级导出，外部可以直接这样 import：

- [backend/source_preprocess/__init__.py](backend/source_preprocess/__init__.py)
- [backend/llm_chapter_extraction/__init__.py](backend/llm_chapter_extraction/__init__.py)

## 测试工具脚本

- [backend/test/run_full_pipeline_smoke.py](backend/test/run_full_pipeline_smoke.py)：一键跑完整链路
- [backend/test/pull_remote_extractions.py](backend/test/pull_remote_extractions.py)：从远程数据库拉取 L2 JSON 到本地缓存

## 老流程说明

旧流程为：文本读取 -> 章节切分 -> Prompt + Few-shot 提取 -> JSONL。
当前已迁移为模块化结构，且保留旧接口文件 `long.py`、`langextract.py` 作为兼容层，避免 `main.py` 立即失效。
