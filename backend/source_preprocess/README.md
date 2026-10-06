# source_preprocess 模块说明

`source_preprocess` 负责把外部输入源转换为后端长文本提取流水线可以稳定消费的章节文本。它位于 LLM 提取、RAG、数据库写入之前，是整个 PersonaWeaver 后端链路的输入预处理层。

## 模块职责

当前模块职责包括四部分：

1. 数据源适配：识别输入来源和文件类型，将不同来源转换为原始文本。
2. 文本标准化：处理编码、换行、格式差异，统一为 UTF-8 文本。
3. 文本清洗：去除明显噪声，保留适合长文本提取的正文内容。
4. 章节切分：把清洗后的长文本拆分为章节记录，供逐章提取模块使用。

本模块不负责 LLM 调用、RAG 向量写入、Supabase 持久化、角色卡生成和前端展示。

## 当前目录结构

```text
source_preprocess/
├── pipeline.py          # 预处理主流程，串联输入适配、清洗和章节切分
├── text_cleaner.py      # 文本清洗逻辑
├── chapter_chunker.py   # 章节切分逻辑
└── parsers/             # 输入源适配层
    ├── router.py        # 根据 source_type 选择具体 parser
    ├── txt_parser.py    # txt/md 文本解析与编码标准化
    ├── pdf_parser.py    # PDF 文本提取
    ├── docx_parser.py   # DOCX 段落文本提取
    └── epub_parser.py   # EPUB spine 章节文本提取
```

## parsers 的边界

`parsers` 只负责“输入源适配”，也就是：

```text
文件 / URL / 图片 / 文档格式 → 原始文本
```

`parsers` 不负责文本清洗。清洗工作由 `text_cleaner.py` 统一完成。

这样拆分的原因是：

- 不同成员可以并行开发 pdf、epub、图片 OCR、网页等 parser。
- 所有 parser 输出统一的原始文本，后续清洗和切章逻辑不需要重复实现。
- parser 内部只处理格式差异，不介入业务提取逻辑，降低协作冲突。

## pipeline 的处理流程

`process_source_file` 当前流程为：

```text
1. 接收 source_path 或 file_url
2. 复制或下载原始文件到本地缓存目录
3. 根据 source_type 调用 parsers/router.py
4. parser 输出原始文本
5. text_cleaner.clean_text 清洗文本
6. chapter_chunker.split_into_chapters 切分章节
7. 返回章节记录和本地缓存路径
```

## 当前已支持与待实现类型

当前已支持：

```text
txt
md
pdf
docx
epub
```

当前 router 中已预留但尚未实现：

```text
doc
jpg / jpeg / png / webp / heic / heif
url / html
```

认领 parser 的成员只需要实现对应格式到原始文本的转换，并在 `parsers/router.py` 中接入。

## 新 parser 的开发要求

新增 parser 时建议遵守以下规则：

1. 输入参数使用 `Path` 或明确的 URL 字符串。
2. 输出必须是 `str` 类型原始文本。
3. 不在 parser 中写入数据库。
4. 不在 parser 中调用 LLM。
5. 不在 parser 中做角色、剧情、摘要等业务提取。
6. 不在 parser 中做复杂清洗；格式转换所需的基础归一化可以保留。
7. 无法解析时抛出清晰异常，说明文件类型、失败阶段和可能原因。

## 建议的后续拆分

为了让输入源适配边界更清晰，后续可以在 `source_preprocess` 下新增 `input_adapters/` 目录，并逐步将 `parsers/` 迁移或重命名为输入源适配层：

```text
source_preprocess/
├── input_adapters/
│   ├── router.py
│   ├── txt_adapter.py
│   ├── pdf_adapter.py
│   ├── epub_adapter.py
│   ├── image_ocr_adapter.py
│   └── web_adapter.py
├── text_cleaner.py
├── chapter_chunker.py
└── pipeline.py
```

短期复赛阶段可以先保留 `parsers/` 名称，README 中明确其职责；等接口稳定后再重命名，避免影响现有调用。

## 与其他模块的关系

```text
source_preprocess
  → workflow_runner
  → llm_dispatch / llm_chapter_extraction
  → remote_persistence / RAG
  → Supabase
  → frontend
```

前端不直接依赖本模块。前端通过后端接口发起任务，后端在任务内部调用本模块完成输入预处理。
