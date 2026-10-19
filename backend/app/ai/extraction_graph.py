"""A small LangGraph pipeline for chapter fact extraction."""

from __future__ import annotations

from typing import Any, TypedDict

from .extraction_pipeline import combine, extract_inputs, segments


class ExtractionState(TypedDict, total=False):
    settings: dict[str, Any]
    chapter_title: str
    chapter_text: str
    chapter: dict
    payload: dict[str, Any]


def _extract(state: ExtractionState) -> ExtractionState:
    chapter = state.get("chapter") or {
        "id": "chapter_inline", "book_id": "inline", "chapter_no": 1,
        "title": state["chapter_title"], "content": state["chapter_text"],
    }
    return {**state, "payload": combine([
        extract_inputs(state["settings"], [part]) for part in segments(chapter)
    ])}


def build_extraction_graph():
    """Compile the graph lazily; importing this module does not require LangGraph."""

    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(ExtractionState)
    graph.add_node("extract", _extract)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", END)
    return graph.compile()


def extract_chapter(settings: dict[str, Any], chapter_title: str, chapter_text: str, chapter=None) -> dict:
    state = {
        "settings": settings,
        "chapter_title": chapter_title,
        "chapter_text": chapter_text,
        "chapter": chapter,
    }
    try:
        graph = build_extraction_graph()
    except ImportError:
        return _extract(state)["payload"]
    result = graph.invoke(state)
    return result["payload"]
