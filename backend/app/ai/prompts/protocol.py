"""Protocol-level prompt fragments shared by provider transports."""

ANTHROPIC_JSON_SUFFIX = "请仅输出合法 JSON 对象，不要包含 Markdown 代码块。"

__all__ = ["ANTHROPIC_JSON_SUFFIX"]
