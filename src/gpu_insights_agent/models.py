from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QueryRecord:
    id: str
    title: str
    promql: str


@dataclass(frozen=True)
class Observation:
    title: str
    description: str
    rows: list[dict[str, Any]]
    query: QueryRecord
    unit: str = ""
    empty_message: str = "No matching series were found."
    suggestions: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentResponse:
    question: str
    intent: str
    answer: str
    observations: list[Observation]
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "intent": self.intent,
            "answer": self.answer,
            "observations": [
                {
                    "title": observation.title,
                    "description": observation.description,
                    "unit": observation.unit,
                    "rows": observation.rows,
                    "query": {
                        "id": observation.query.id,
                        "title": observation.query.title,
                        "promql": observation.query.promql,
                    },
                }
                for observation in self.observations
            ],
            "suggestions": self.suggestions,
        }
