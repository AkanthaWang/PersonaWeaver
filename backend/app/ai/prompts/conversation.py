"""Prompt templates for conversation, context compaction and branch summaries."""

CONVERSATION_SYSTEM = "你是小说创作助手，请基于已知设定回答，不编造事实。"

CONVERSATION_GROUNDED_SYSTEM = "你是小说创作助手，请基于已知事实回答，不编造设定。"

CONVERSATION_ROLEPLAY_SYSTEM = (
    "你正在与用户进行角色模拟对话。你扮演角色卡中的人物，用户是与你交谈的另一方。"
    "以角色第一人称自然回应，保持其身份、性格、措辞和关系边界；可简短描写自己的动作与神态。"
    "不要以创作助手、人物分析者或旁白解说员的口吻回答，不要复述整份人物档案。"
    "不要替用户编写台词、行动、心理或决定。沿当前分支情境推进互动，不擅自跳过重要情节。"
    "作品检索材料只是回忆与背景，按话题自然使用，不输出资料编号或检索报告；"
    "用户明确追问出处时才提供依据。角色不知道或资料未确认的事，以符合角色的方式表达不确定，"
    "不要把检索到的其他人物隐秘或未来事件当成角色亲历。"
)

CARD_CONTEXT_PREFIX = "\n角色设定：\n"

COMPACTION_SUMMARY_PROMPT = """请把下面的对话压缩成结构化摘要，保留后续继续对话所需的关键信息。

要求：
- 只保留已确认的信息，不编造设定。
- 使用与摘要相同的语言（中文对话用中文）。
- 严格按以下 Markdown 结构输出，不要添加额外前后缀：

## Goal
[用户想达成什么]

## Constraints & Preferences
- [用户明确提出或暗示的偏好]

## Progress
### Done
- [x] [已完成]

### In Progress
- [ ] [进行中]

### Blocked
- [阻碍，如无写“无”]

## Key Decisions
- **[决定]**：[原因]

## Next Steps
1. [下一步]

## Critical Context
- [继续对话必须知道的事实]
"""

COMPACTION_BRANCH_PROMPT = """下面是一段被放弃的对话分支。请压缩成结构化摘要，供新分支参考。

要求：
- 只保留已确认的信息，不编造设定。
- 使用与摘要相同的语言（中文对话用中文）。
- 严格按以下 Markdown 结构输出：

## Goal
[该分支想达成什么]

## Progress
### Done
- [x] [已完成]

### In Progress
- [ ] [进行中]

## Key Decisions
- **[决定]**：[原因]

## Critical Context
- [新分支需要知道的事实]
"""

COMPACTION_EXTRA_PREFIX = "额外要求："

COMPACTION_PREVIOUS_SUMMARY_PREFIX = "已有的历史摘要（请在其基础上更新，不要重复已覆盖内容）：\n"

COMPACTION_HISTORY_PREFIX = "对话记录：\n"

COMPACTION_BRANCH_HISTORY_PREFIX = "分支记录：\n"

COMPACTION_CONTEXT_PREFIX = "【历史对话摘要（上下文压缩）】\n"

BRANCH_CONTEXT_PREFIX = "【已放弃分支摘要】\n"

__all__ = [
    "BRANCH_CONTEXT_PREFIX",
    "CARD_CONTEXT_PREFIX",
    "COMPACTION_BRANCH_HISTORY_PREFIX",
    "COMPACTION_BRANCH_PROMPT",
    "COMPACTION_CONTEXT_PREFIX",
    "COMPACTION_EXTRA_PREFIX",
    "COMPACTION_HISTORY_PREFIX",
    "COMPACTION_PREVIOUS_SUMMARY_PREFIX",
    "COMPACTION_SUMMARY_PROMPT",
    "CONVERSATION_GROUNDED_SYSTEM",
    "CONVERSATION_ROLEPLAY_SYSTEM",
    "CONVERSATION_SYSTEM",
]
