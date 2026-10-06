# PersonaWeaver（灵织）

------

## 📖 项目简介

**PersonaWeaver（灵织）\**是一个面向\**长篇小说、剧本杀文本与角色素材**的长文本角色资产提取与内容生产系统。

PersonaWeaver 将长文本中分散的：

- 角色
- 性格
- 人物关系
- 剧情事件
- 物品
- 地点
- 世界观
- 原文证据

转化为**结构化、可检索、可追溯、可复用的角色资产**，并在此基础上提供：

- 角色卡生成
- 全书摘要
- RAG 检索
- 证据增强问答
- Agent 化任务编排基础

项目的核心理念是：

> **先资产化，再生成。**

系统不直接将整本长文本交给大模型生成最终内容，而是先完成**文本解析 → 章节切分 → 结构化抽取 → 资产汇总 → 证据保存**，再通过 RAG 和 Agent Workflow 调用相关资产，为后续问答、角色分析、剧情组织和内容生产提供可靠的数据基础。

------

# ✨ 核心能力

```text
                     PersonaWeaver
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
      长文本处理        角色资产层        Agent / RAG
          │                │                │
      文件解析          Character        Planning
      章节切分          Plot             Tool Calling
      Chunk             Item             Retrieval
                        Location          Evidence
                        World             Validation
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                    内容生产与问答
```

### 📚 1. 长文本处理

支持长篇文本进入统一处理流程：

- TXT / Markdown 等文本输入
- 文本清洗
- 编码归一
- 章节切分
- 逻辑分块
- Chunk 构建

------

### 👤 2. 角色资产提取

围绕角色建立结构化资产：

- 角色基本信息
- 性格特征
- 行为特征
- 人物关系
- 关键事件
- 角色相关证据

------

### 🧩 3. 剧情与世界观抽取

从章节内容中抽取：

- 剧情事件
- 物品
- 地点
- 世界观信息

并进一步汇总形成作品级资料。

------

### 🪪 4. 角色卡生成

根据角色条目与章节证据生成 Markdown 角色卡，包括：

```text
角色基本信息
性格特征
人物关系
关键事件
原文证据
```

------

### 🔎 5. RAG 证据检索

将章节、段落和证据片段构建为：

```text
Chunk
   ↓
Embedding
   ↓
Vector Store
   ↓
Retriever
   ↓
Top-K Evidence
```

用户提问时检索相关原文，再将问题、Prompt 和证据共同交给模型生成回答。

------

### 🤖 6. Agentic Workflow

PersonaWeaver 不仅把 LLM 作为一次性调用接口，而是将现有的：

```text
文本解析
章节抽取
角色检索
证据检索
角色卡生成
RAG 问答
```

组织为可进一步 Agent 化的任务节点。

Agent 层负责：

- Task Planning
- Tool Calling
- Multi-Step Workflow
- Retrieval
- Evidence Grounding
- Result Validation

底层工具则负责确定性的文本处理、结构化抽取、数据库访问和向量检索。

------

# 🧠 为什么需要 PersonaWeaver？

长篇小说和剧本杀文本中的角色信息通常并不是集中存在的。

一个角色的完整画像可能分散在：

```text
对白
 ↓
动作
 ↓
旁白
 ↓
剧情事件
 ↓
其他角色评价
 ↓
不同章节
```

因此，传统人工整理通常需要经历：

```text
反复阅读
    ↓
手工摘录
    ↓
信息合并
    ↓
关系整理
    ↓
设定校对
    ↓
二次改写
```

PersonaWeaver 将这一过程转化为结构化的数据处理链路。

项目材料将问题概括为三个方面：

### 01 信息分散

角色设定、行为动机和关系变化跨章节出现，需要反复阅读才能拼出完整画像。

### 02 证据断裂

传统摘要或模型回答难以直接回到原文，容易出现设定漂移。

### 03 复用困难

一次整理结果难以直接服务于后续问答、剧情改写、分镜设计和其他内容生产。

因此，PersonaWeaver 的目标不是单纯生成一个摘要，而是：

> **把长文本中的信息转化为可以检索、引用和继续创作的角色资产。**

------

# 🏗️ 系统架构

PersonaWeaver 将整个系统划分为四个核心层次。

```text
┌──────────────────────────────────────────────┐
│                Raw Long-form Text            │
│        小说 / 剧本杀 / 角色素材              │
└───────────────────────┬──────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────┐
│                 Text Layer                   │
│                                              │
│ 文件解析 → 清洗 → 章节切分 → Chunk          │
└───────────────────────┬──────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────┐
│              Structured Information          │
│                                              │
│ Character / Plot / Item / Location / World  │
└───────────────────────┬──────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────┐
│                 Asset Layer                  │
│                                              │
│ 章节汇总 → 角色画像 → 角色卡 → 作品资料      │
└───────────────────────┬──────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────┐
│               Retrieval Layer                │
│                                              │
│ Embedding → Vector Store → Retriever        │
└───────────────────────┬──────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────┐
│              Agentic Layer                   │
│                                              │
│ Planning → Tool Calling → Retrieval         │
│ → Evidence Check → Generation               │
└───────────────────────┬──────────────────────┘
                        │
                        ▼
                 Content Production
```

其中，**Agent 层建立在已有的结构化资产和 RAG 基础设施之上**，负责复杂任务的规划与工具编排，而不是替代底层的数据处理模块。

------

# 🔄 核心工作流

```text
                用户输入
                   │
                   ▼
          ┌─────────────────┐
          │   Task Planning │
          │    任务理解/拆解 │
          └────────┬────────┘
                   │
                   ▼
          ┌─────────────────┐
          │   Tool Calling  │
          └────────┬────────┘
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
   Text Tool   Asset Tool   RAG Tool
       │           │           │
       ▼           ▼           ▼
   章节处理      角色资产      证据检索
       │           │           │
       └───────────┼───────────┘
                   ▼
          ┌─────────────────┐
          │ Evidence Check  │
          │   证据校验      │
          └────────┬────────┘
                   │
                   ▼
          ┌─────────────────┐
          │ Asset / Content │
          │    Generation   │
          └────────┬────────┘
                   │
                   ▼
              最终结果
```

传统流程更接近：

```text
Text → LLM → Answer
```

PersonaWeaver 进一步演化为：

```text
Goal
 ↓
Plan
 ↓
Tools
 ↓
Retrieval
 ↓
Evidence
 ↓
Validation
 ↓
Generation
```

------

# 🤖 Agent Architecture

PersonaWeaver 的 Agent 层定位为：

> **Long-form Character Intelligence Agent**

即以结构化角色资产作为长期状态，以 RAG 作为证据层，以 LLM 作为任务规划与推理核心。

```text
                         User Goal
                            │
                            ▼
                 ┌────────────────────┐
                 │  Persona Agent     │
                 │                    │
                 │ Task Understanding │
                 │ Task Planning      │
                 └─────────┬──────────┘
                           │
             ┌─────────────┼─────────────┐
             │             │             │
             ▼             ▼             ▼
        Text Tools     Asset Tools   Retrieval Tools
             │             │             │
             ▼             ▼             ▼
        Document       Character      Vector Search
        Parsing        Search         Evidence
        Chunking       Plot Search    Retrieval
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                 ┌────────────────────┐
                 │ Evidence Validator │
                 └─────────┬──────────┘
                           │
                           ▼
                 ┌────────────────────┐
                 │ Generation Agent   │
                 └─────────┬──────────┘
                           │
                           ▼
                     Final Result
```

------

## 1. Task Planning

Agent 首先理解用户目标，而不是直接生成答案。

例如：

```text
用户：

“分析某角色在前 80 回中的性格变化，
并找出 5 个关键事件作为证据。”
```

Agent 可以将任务拆解为：

```text
① 定位目标角色
② 获取角色资产
③ 检索相关章节
④ 找出关键事件
⑤ 建立时间线
⑥ 分析性格变化
⑦ 检索原文证据
⑧ 验证结论
⑨ 生成最终报告
```

------

## 2. Tool Calling

Agent 可以调用 PersonaWeaver 的底层工具。

典型工具包括：

```text
parse_document()
split_chapters()

extract_chapter_structured()

search_character()
search_plot()

retrieve_evidence()

generate_character_card()

rag_query()
```

Agent 负责：

```text
决定调用什么工具
        ↓
决定调用顺序
        ↓
读取工具结果
        ↓
决定下一步
```

而工具负责：

```text
执行具体任务
        ↓
返回结构化结果
```

从而形成：

> **LLM 决策 + Deterministic Tools 执行**

的 Agent 架构。

------

## 3. Multi-Step Workflow

复杂角色任务不再依赖一次 LLM Call：

```text
Understand
    ↓
Plan
    ↓
Retrieve
    ↓
Analyze
    ↓
Verify
    ↓
Generate
```

每一步都可以产生中间状态，并成为下一步的输入。

------

## 4. Evidence-Grounded Agent

PersonaWeaver Agent 的重要特点是：

> **关键结论必须尽可能建立在原始文本证据之上。**

例如：

```text
Agent
 │
 ├── Character Search
 │
 ├── Plot Search
 │
 └── Evidence Retrieval
           │
           ▼
      Original Text
           │
           ▼
     Evidence Check
           │
           ▼
      Final Answer
```

角色分析不只是生成：

```text
“这个角色比较孤独。”
```

而是尽可能进一步提供：

```text
Chapter 23
Paragraph 17

Evidence:
“……”

Conclusion:
角色在该阶段表现出……
```

从而降低角色设定漂移。

------

# 🔎 RAG：Agent 的证据层

PersonaWeaver 中的 RAG 不只是为了提高召回率，而是承担 Agent 的**Evidence Layer**。

```text
Chapter
   │
   ▼
Paragraph
   │
   ▼
Chunk
   │
   ▼
Embedding
   │
   ▼
Vector Store
   │
   ▼
Retriever
   │
   ▼
Top-K Evidence
   │
   ▼
Agent Context
```

系统尽可能保存：

```json
{
  "chapter_index": 12,
  "paragraph_index": 38,
  "evidence_text": "..."
}
```

这样 Agent 在生成角色分析、关系判断和剧情总结时，可以进一步回溯原始文本。

项目设计明确强调保留 `chapter_index`、`paragraph_index` 和 `evidence_text`，以建立完整的证据链。

------

# 🧠 Structured Asset as Agent Memory

PersonaWeaver 不依赖把整本小说永久塞入模型上下文。

系统将作品组织为结构化资产：

```text
Book
│
├── Chapters
│
├── Characters
│   ├── Character A
│   ├── Character B
│   └── Character C
│
├── Relationships
│
├── Plot Events
│
├── Items
│
├── Locations
│
└── Evidence Chunks
```

Agent 根据任务动态检索所需信息。

因此：

```text
Long Context
     ↓
Structured Memory
     ↓
Retrieval
     ↓
Agent Reasoning
```

这也是 PersonaWeaver 区别于单纯 Chatbot 的重要设计。

------

# 🧩 LLM Task Pipeline

PersonaWeaver 当前已经将大模型应用拆分为多个任务节点：

### Task 01 — Chapter Extraction

```text
Chapter
   ↓
LLM
   ↓
Structured JSON
```

提取：

```text
Character
Plot
Item
Location
World
```

函数：

```text
extract_chapter_structured
```

------

### Task 02 — Book-level Summary

```text
Chapter JSON
      ↓
Aggregation
      ↓
Character Index
Plot Lines
World Information
```

函数：

```text
dispatch_summary_prompts
```

------

### Task 03 — Character Card

```text
Character Asset
       +
Chapter Evidence
       ↓
Character Card
```

函数：

```text
generate_character_card
```

------

### Task 04 — RAG Query

```text
Question
   ↓
Retriever
   ↓
Top-K Chunks
   ↓
LLM
   ↓
Answer + Evidence
```

函数：

```text
rag_query
```

这些任务节点已经构成 PersonaWeaver 当前 Agent Workflow 的底层能力基础。

------

# 📐 设计原则

## 1. 先资产化，再生成

```text
Raw Text
   ↓
Structured Facts
   ↓
Evidence
   ↓
Character Assets
   ↓
Content Generation
```

------

## 2. 细粒度存储，粗粒度调用

存储层保留：

```text
Chapter
Paragraph
Chunk
Evidence
```

模型调用阶段根据上下文需求合并章节，以降低重复 Prompt 和固定请求成本。

当前设计建议模型调用阶段按约 **5～10 章**组织。

------

## 3. 数据与 Agent 解耦

```text
Agent
  ↓
Tool
  ↓
Structured Data
```

而不是：

```text
Agent
  ↓
Everything inside Prompt
```

这样可以让 Agent 更容易：

- 调试
- 替换模型
- 扩展工具
- 进行结果验证
- 接入新的内容生产流程

------

## 4. 证据优先

模型输出尽可能对应：

```text
chapter_index
paragraph_index
evidence_text
```

让结果能够回到原始文本。

------

## 5. AI 辅助整理，人负责创作

PersonaWeaver 的目标不是完全替代创作者。

系统负责：

```text
重复
分散
结构化
检索
证据整理
```

用户负责：

```text
判断
修改
创意
创作
最终决策
```

即：

> **让 AI 负责整理，让人负责创造。**

------

# ⚙️ 模型服务

PersonaWeaver 使用统一 LLM Client 屏蔽不同模型服务之间的接口差异。

当前推荐：

```text
                PersonaWeaver
                       │
                Unified LLM Client
                       │
            ┌──────────┴──────────┐
            │                     │
            ▼                     ▼
      vivo AIGC API          校园 API
        Primary              Fallback
            │                     │
            ▼                     ▼
 Volc-DeepSeek-V3.2          ecnu-max
```

当前：

- vivo AIGC：默认模型调用路径
- 校园 API：Fallback
- Unified LLM Client：统一模型调用接口

vivo API 出现额度、权限或限流问题时，可以切换到校园 API。

------

# 🚀 Quick Start

## 1. Clone

```bash
git clone <your-repository-url>
cd PersonaWeaver
```

------

## 2. Configure Environment

创建：

```text
.env
```

推荐从：

```text
.env.example
```

复制。

```bash
copy .env.example .env
```

Linux / macOS：

```bash
cp .env.example .env
```

配置：

```env
LLM_PROVIDER=vivo
LLM_FALLBACK_PROVIDERS=remote_api

VIVO_AIGC_APP_ID=<your-vivo-app-id>
VIVO_AIGC_BASE_URL=https://api-ai.vivo.com.cn/v1/chat/completions
VIVO_AIGC_API_KEY=<your-vivo-api-key>
VIVO_AIGC_MODEL=Volc-DeepSeek-V3.2

ECNU_API_BASE_URL=https://chat.ecnu.edu.cn/open/api/v1/chat/completions
ECNU_API_KEY=<your-ecnu-api-key>
ECNU_MODEL_NAME=ecnu-max
```

**不要将真实 API Key 写入 README、代码或 `backend/config.json`。**

------

# 🐍 3. Create Environment

项目提供：

```text
environment.yml
```

执行：

```bash
conda env create -f environment.yml
conda activate charpick
```

如果环境已经存在：

```bash
conda activate charpick
```

也可以：

```bash
pip install -r requirements.txt
```

> 如果后续将 Conda 环境正式重命名为 `personaweaver`，请同步修改上述命令。

------

# 🗄️ 4. Database

PersonaWeaver 支持：

- PostgreSQL
- Supabase PostgreSQL

配置：

```env
SUPABASE_DB_URL=postgresql://postgres.<project-ref>:<db-password>@<host>:6543/postgres?sslmode=require

DATABASE_URL=postgresql://postgres.<project-ref>:<db-password>@<host>:5432/postgres?sslmode=require
```

RAG 数据库连接按照：

```text
REMOTE_DB_URL
      ↓
SUPABASE_DB_URL
      ↓
DATABASE_URL
```

依次读取。

如果只进行：

```text
LLM API Smoke Test
```

可以暂时不配置数据库。

------

# 🔎 5. Embedding

默认可以使用 hash embedding 验证 RAG 链路：

```env
RAG_EMBEDDING_PROVIDER=hash
RAG_EMBEDDING_MODEL=hash-embedding-256
RAG_EMBEDDING_DIM=256
RAG_TOP_K=10
```

如果后续使用 OpenAI-compatible Embedding：

```env
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_MODEL=<embedding-model-name>
EMBEDDING_DIM=<embedding-dim>
EMBEDDING_BASE_URL=<embedding-endpoint>
EMBEDDING_API_KEY=<embedding-api-key>
```

------

# ▶️ 6. Start Backend

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

启动后：

```text
http://127.0.0.1:8000
```

------

# 🔌 API

主要接口：

```text
GET  /health

POST /chat

POST /api/v1/extract

GET  /api/v1/tasks/{task_id}

POST /api/v1/rag/chunks/preview

POST /api/v1/rag/index-text

POST /api/v1/rag/query
```

------

# 🧪 API Smoke Test

## vivo AIGC

```bash
curl -s -X POST "http://127.0.0.1:8000/chat" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"请简短自我介绍\",\"provider\":\"vivo\",\"model\":\"Volc-DeepSeek-V3.2\"}"
```

## 校园 API

```bash
curl -s -X POST "http://127.0.0.1:8000/chat" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"请简短自我介绍\",\"provider\":\"remote_api\",\"model\":\"ecnu-max\"}"
```

如果返回：

```json
{
  "response": "..."
}
```

说明模型服务已经成功连接。

------

# 📁 Project Structure

```text
PersonaWeaver/
│
├── backend/
│   │
│   ├── main.py
│   │   └── FastAPI 统一接口入口
│   │
│   ├── config.json
│   │   └── 后端配置，不保存真实密钥
│   │
│   ├── agents/
│   │   ├── persona_agent.py
│   │   │   └── Agent 主编排
│   │   │
│   │   ├── planner.py
│   │   │   └── Task Planning
│   │   │
│   │   ├── tools/
│   │   │   ├── text_tools.py
│   │   │   ├── extraction_tools.py
│   │   │   ├── character_tools.py
│   │   │   ├── retrieval_tools.py
│   │   │   └── generation_tools.py
│   │   │
│   │   └── workflows/
│   │       ├── character_analysis.py
│   │       ├── character_card.py
│   │       └── evidence_qa.py
│   │
│   ├── llm_dispatcher.py
│   │   └── LLM Provider 调度
│   │
│   ├── llm_dispatch/
│   │   └── llm_client.py
│   │       └── 统一模型调用
│   │
│   ├── llm_chapter_extraction/
│   │   └── 章节级结构化抽取
│   │
│   ├── rag/
│   │   ├── chunk/
│   │   ├── embedding/
│   │   ├── vector_store/
│   │   └── retriever/
│   │
│   ├── source_preprocess/
│   │   └── 文本解析、清洗、章节切分
│   │
│   ├── remote_persistence.py
│   │   └── Supabase / OSS 持久化
│   │
│   └── test/
│       └── 后端测试与 Smoke Test
│
├── docs/
│   └── 项目文档
│
├── docs_local/
│   └── 本地笔记，不提交 GitHub
│
├── examples/
│   └── 示例输入与请求体
│
├── .env.example
├── .env
├── environment.yml
├── requirements.txt
└── README.md
```

> `agents/` 目录代表 Agent Orchestration Layer。如果当前代码仓库尚未实际加入该目录，应在实现后再启用对应结构，避免 README 与代码状态不一致。

------

# 📊 Current Capabilities

| 能力                      | 状态 |
| ------------------------- | ---- |
| 长文本解析                | ✅    |
| TXT / Markdown            | ✅    |
| 章节切分                  | ✅    |
| Chunk 构建                | ✅    |
| 角色抽取                  | ✅    |
| 剧情抽取                  | ✅    |
| 物品抽取                  | ✅    |
| 地点 / 世界观抽取         | ✅    |
| 全书信息汇总              | ✅    |
| 角色卡生成                | ✅    |
| RAG                       | ✅    |
| Embedding                 | ✅    |
| Vector Store              | ✅    |
| Evidence Retrieval        | ✅    |
| vivo AIGC                 | ✅    |
| 校园 API Fallback         | ✅    |
| Structured Output         | ✅    |
| Agent Workflow 基础       | 🔧    |
| Task Planning             | 🔧    |
| Tool Calling              | 🔧    |
| Evidence Validation Agent | 🔧    |
| Multi-Agent Collaboration | 🔭    |
| 自动剧情 / 分镜生成       | 🔭    |
| 自动视频生产              | 🔭    |

**说明：**

- ✅ 当前项目已有能力
- 🔧 基于当前系统可以实现 / 正在 Agent 化的能力
- 🔭 后续规划，不代表当前版本已经完成

------

# 🧪 推荐 Agent Demo

为了展示 PersonaWeaver 的 Agent 能力，可以使用：

## Character Research Agent

输入：

```text
分析某角色在前 80 回中的性格变化，
找出 5 个关键事件，并给出原文证据。
```

Agent Workflow：

```text
User Goal
    ↓
Character Research Agent
    ↓
Identify Character
    ↓
Search Character Asset
    ↓
Retrieve Relevant Chapters
    ↓
Retrieve Evidence
    ↓
Build Timeline
    ↓
Analyze Character Change
    ↓
Evidence Validation
    ↓
Generate Report
```

最终输出：

```text
角色概览
      +
性格变化时间线
      +
关键事件
      +
章节 / 段落证据
      +
分析结论
```

这个场景能够同时体现：

```text
LLM
+
Agent Planning
+
Tool Calling
+
Structured Data
+
RAG
+
Evidence Grounding
+
Long-form Text Processing
```

------

# 🔭 Roadmap

PersonaWeaver 当前聚焦：

> **文本资产层**

未来可以进一步扩展为：

```text
                 PersonaWeaver
                       │
                       ▼
              ┌─────────────────┐
              │  Character Asset│
              │      Layer      │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  Story Planning │
              │      Layer      │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  Video Creation │
              │      Layer      │
              └─────────────────┘
```

## Phase 1 — Character Asset Layer

继续强化：

- 长文本解析
- 角色资产
- 角色卡
- 证据回溯
- RAG
- Character Agent

## Phase 2 — Story Organization Layer

将：

```text
角色资产
+
剧情摘要
+
事件线
```

组织成：

```text
脚本
分镜
剧情大纲
```

## Phase 3 — Video Production Layer

探索与：

- OpenMontage
- ViMax
- OmniShow

等方向的工具或模型连接，形成：

```text
Novel
 ↓
Character Assets
 ↓
Story
 ↓
Script
 ↓
Storyboard
 ↓
Video
```

需要强调的是，这些视频生产方向属于**后续扩展与调研方向**，并非当前 PersonaWeaver 已完成的核心能力。项目材料也明确将这些内容与当前已实现系统进行了区分。

------

# 🔐 Security

请勿提交：

```text
.env
API Keys
Database Passwords
OSS Secrets
Supabase Credentials
```

`.env.example` 只保存：

```text
配置字段
+
占位符
```

真实密钥只保存于：

```text
.env
```

如果密钥曾经误提交到 Git 历史，应立即：

1. 在对应平台重置密钥
2. 清理 Git 历史
3. 更新本地 `.env`

------

# 🎯 Project Positioning

PersonaWeaver 不是单纯的：

```text
❌ Text Summarizer
❌ Chatbot
❌ RAG Demo
```

而是一个：

```text
                 Long-form Text
                       │
                       ▼
              Structured Extraction
                       │
                       ▼
                Character Assets
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
       RAG Evidence          Agent Layer
            │                     │
            └──────────┬──────────┘
                       ▼
                Content Production
```

的**长文本角色智能基础设施**。

其核心技术路线可以概括为：

> **Structured Assets + RAG + Agentic Workflow**

即：

> **以结构化角色资产作为长期状态，以 RAG 作为证据层，以 Agent 作为任务编排层，以 LLM 作为理解、规划与生成核心。**

------

# 🌱 Vision

长篇作品的价值不仅存在于正文中。

角色、关系、事件和世界观本身，就是可以被持续调用的内容资产。

PersonaWeaver 希望建立从：

```text
Long-form Text
      ↓
Character Intelligence
      ↓
Structured Assets
      ↓
Agentic Reasoning
      ↓
Content Production
```

的完整链路。

最终让角色资产能够服务于：

- 智能问答
- 角色扮演
- 剧情创作
- 脚本生成
- 分镜生成
- 数字人
- 多角色内容生产
- 多 Agent 内容生产

项目材料也将角色资产进一步复用于数字人、具身智能和多角色内容生产作为长期方向。

------

# 👥 Team

**团队名称：哈基米难卖绿豆**

**学校：华东师范大学**

团队围绕“长文本角色资产提取”进行协作，包括：

- 产品与场景
- 后端与算法
- 前端与原型
- 数据库与 RAG
- 大模型应用
- 项目材料与展示

项目核心工作围绕文本理解、系统开发、RAG 与产品表达形成完整协作链路。

------

# 📚 References

- Lewis et al. *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. NeurIPS 2020.
- Beltagy, Peters & Cohan. *Longformer: The Long-Document Transformer*.
- Gao et al. *Retrieval-Augmented Generation for Large Language Models: A Survey*.
- Wu et al. *AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation*.
- Polyak et al. *Movie Gen: A Cast of Media Foundation Models*.
- Blattmann et al. *Align your Latents: High-Resolution Video Synthesis with Latent Diffusion Models*.
- Shao et al. *MetaPal: A New Paradigm for Human-Computer Interaction — From Command Response to Emotional Empathy*.

------

# 🔗 Related Research

PersonaWeaver 后续扩展方向参考：

```text
OpenMontage
ViMax
OmniShow
```

这些项目用于研究自动化内容生产、多 Agent 剧情视频生成以及多模态视频生成方向，并不作为 PersonaWeaver 当前已完成能力进行描述。

------

## PersonaWeaver · 灵织

From Long Text to Character Intelligence

从长文本到可追溯、可复用、可持续生产的角色智能资产



做角色智能生态的基石与引擎
