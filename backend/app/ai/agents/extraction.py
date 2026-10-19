"""Bounded extraction agent with model-selected recovery tools."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Callable

from pydantic import Field

from backend.app.ai.extraction_pipeline import StrictModel, digest, request_json
from backend.app.ai.prompts.extraction import EXTRACTION_AGENT_SYSTEM_PROMPT
from backend.app.domains.workflow import failures


@dataclass
class AgentState:
    phase: str = "idle"
    cursor: int = 0
    completed: int = 0
    skipped: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class AgentAction:
    kind: str
    key: str
    fingerprint: str
    label: str
    execute: Callable[[], Any]
    chapter_id: str | None = None
    force: bool = False
    percent: int = 0
    split: Callable[[], list[AgentAction]] | None = None
    input_size: int = 0


class RecoveryDecision(StrictModel):
    tool: str = Field(pattern="^(retry|split|skip)$")


class ExtractionAgent:
    """Observe failures and let the model choose a bounded recovery tool."""

    max_recovery_depth = 2

    def __init__(self, worker):
        self.worker = worker
        self.state = AgentState()

    def run(self, actions: list[AgentAction], phase: str) -> list[Any]:
        self.state.phase = phase
        results = []
        for cursor, action in enumerate(actions):
            self.state.cursor = cursor
            self.worker.step(action.kind, action.label, action.percent)
            try:
                result = self._perform(action, 0)
            except self.worker.cancelled_error:
                raise
            except Exception as exc:
                if not failures.is_recoverable(exc):
                    raise
                self.state.skipped += 1
                self.worker.record_failure(action.kind, action.key, action.label, exc)
                self.state.failures.append(self.worker.failures[-1])
                result = None
            else:
                self.state.completed += 1
            results.append(result)
        return results

    def _perform(self, action: AgentAction, depth: int):
        return self.worker.unit(
            action.kind, action.key, action.fingerprint,
            lambda: self._execute(action, depth), action.chapter_id, action.force,
        )

    def _execute(self, action: AgentAction, depth: int):
        try:
            return action.execute()
        except self.worker.cancelled_error:
            raise
        except Exception as exc:
            if not failures.is_recoverable(exc):
                raise
            # Transport retries already ran in request_json. Do not ask an
            # unavailable model to diagnose its own network failure.
            if failures.classify(exc) == failures.TRANSPORT or depth >= self.max_recovery_depth:
                raise
            tools = ["retry", "skip"]
            if action.split:
                tools.append("split")
            observation = {
                "action": action.kind, "error_type": failures.classify(exc),
                "input_size": action.input_size, "recovery_depth": depth,
                "available_tools": tools,
            }

            def validate(value):
                parsed = RecoveryDecision.model_validate(value).model_dump()
                if parsed["tool"] not in tools:
                    raise ValueError("Agent 选择了当前不可用的工具")
                return parsed

            try:
                decision = self.worker.unit(
                    "agent", f"{action.kind}:{action.key}:decision",
                    digest([self.worker.config_hash, action.fingerprint, observation]),
                    lambda: request_json(self.worker.settings, [
                        {"role": "system", "content": EXTRACTION_AGENT_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(observation)},
                    ], validate, self.worker.check),
                    action.chapter_id, action.force,
                )
            except self.worker.cancelled_error:
                raise
            except Exception as planning_error:
                if not failures.is_recoverable(planning_error):
                    raise
                self.worker.mark_skipped("agent", f"{action.kind}:{action.key}:decision")
                self.worker.log("warning", f"{action.label}：Agent 决策不可用，保留失败检查点")
                raise exc
            self.worker.log("info", f"Agent：{action.label} → {decision['tool']}")
            self.worker.check()
            if decision["tool"] == "skip":
                raise
            if decision["tool"] == "split":
                from backend.app.ai.extraction_pipeline import combine

                return combine([self._perform(child, depth + 1) for child in action.split()])
            retry = AgentAction(
                kind=action.kind, key=f"{action.key}:retry", fingerprint=action.fingerprint,
                label=action.label, execute=action.execute, chapter_id=action.chapter_id,
                force=action.force, percent=action.percent, split=action.split, input_size=action.input_size,
            )
            return self._perform(retry, depth + 1)
