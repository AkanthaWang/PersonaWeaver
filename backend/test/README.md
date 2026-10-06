# 测试说明（暂不执行）

本目录用于存放预处理与逐章提取流程的测试代码。
当前阶段先写测试骨架，不强制执行。

## 建议测试顺序

1. `source_preprocess.parsers`：txt/md 输入解析
2. `source_preprocess.text_cleaner`：文本清洗稳定性
3. `source_preprocess.chapter_chunker`：章节切分正确性
4. `llm_chapter_extraction.chapter_structured_extractor`：逐章结构化输出格式

新增专门测试文件：

- `backend/test/test_llm_chapter_structured_extractor.py`

## 运行方式（后续）

```bash
pytest backend/test -q
```

如果环境中暂未安装 pytest，可先安装：

```bash
pip install pytest
```

## 一键脚本

### 1) 一键跑完整链路

文件：`backend/test/run_full_pipeline_smoke.py`

运行：

```bash
python backend/test/run_full_pipeline_smoke.py
```

默认会使用本地 `data/神游.txt`，执行：

输入 -> 多源文件解析 -> 文本清洗 -> 章节 / 逻辑分块 -> LLM 逐章结构化提取

它会把 L2 JSON 落到本地缓存 `local_cache/<书名>/extraction_json/`，不会默认上传 OSS 或远程数据库。

### 2) 从远程数据库拉取 L2 JSON 到本地

文件：`backend/test/pull_remote_extractions.py`

运行：

```bash
python backend/test/pull_remote_extractions.py --book-id b_demo_001 --source-file-id sf_remote_demo_001
```

默认会把远程数据库里 `chapter_extractions.extraction_json_url` 指向的内容，落到：

```text
local_cache/pulled_extractions/<source_file_id>/
```

如果 `extraction_json_url` 是本地路径，脚本会直接读取；如果是 HTTP/HTTPS 地址，也会自动下载。
