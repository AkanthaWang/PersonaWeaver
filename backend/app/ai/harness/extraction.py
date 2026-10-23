"""Extraction stages reuse evidence checks, recovery tools and unit checkpoints."""

import sqlite3
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver


class ExtractionState(TypedDict, total=False):
    chapters: list[dict]
    selected: list[dict]
    scope_hash: str
    by_chapter: dict
    staged: dict
    results: list
    summaries: dict
    invalid: list
    published: bool


def run_extraction(worker, chapters):
    graph = StateGraph(ExtractionState)
    graph.add_node("prepare", lambda s: worker.prepare_graph(s["chapters"]))
    for name in ("extract", "lookup", "merge", "synthesis", "publish"):
        graph.add_node(name, getattr(worker, name + "_graph"))
    phases = ["prepare", "extract", "lookup", "merge", "synthesis", "publish"]
    graph.add_edge(START, phases[0])
    for previous, following in zip(phases, phases[1:]):
        graph.add_edge(previous, following)
    graph.add_edge(phases[-1], END)
    with sqlite3.connect(str(worker.db.path), check_same_thread=False, timeout=30) as conn:
        saver = SqliteSaver(conn)
        return graph.compile(checkpointer=saver).invoke(
            {"chapters": chapters}, {"configurable": {"thread_id": "extraction:" + worker.task_id}},
            durability="sync")
