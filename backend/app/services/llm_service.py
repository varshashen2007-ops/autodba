"""
Phase 4.1: Real Groq LLM Service

The deterministic AutoDBA engine remains authoritative.
The LLM is strictly an explanation layer.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from groq import Groq

from app.core.logging import logger


class LLMProvider(ABC):
    """Abstract interface for an AutoDBA LLM provider."""

    @abstractmethod
    def explain(
        self,
        *,
        query: str,
        diagnosis: Dict[str, Any],
        recommendation: Optional[Dict[str, Any]],
        similar_cases: List[Dict[str, Any]],
    ) -> str:
        raise NotImplementedError


class GroqLLMProvider(LLMProvider):
    """Real Groq-backed LLM provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY")

        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured."
            )

        self.model = model or os.getenv(
            "GROQ_MODEL",
            "openai/gpt-oss-120b",
        )

        self.client = Groq(api_key=self.api_key)

    def explain(
        self,
        *,
        query: str,
        diagnosis: Dict[str, Any],
        recommendation: Optional[Dict[str, Any]],
        similar_cases: List[Dict[str, Any]],
    ) -> str:
        system_prompt = """
You are AutoDBA, an AI explanation assistant for PostgreSQL
database performance engineering.

The deterministic AutoDBA engine is the ONLY authority for:
- execution-plan analysis
- bottleneck detection
- recommendations
- SQL previews
- HypoPG validation
- safety checks
- human approval
- remediation
- benchmark results

You are NOT allowed to:
- execute SQL
- propose new SQL
- modify or rewrite SQL
- invent indexes or columns
- invent benchmark results
- invent planner costs
- approve remediation
- change recommendation status
- bypass safety checks
- claim an optimization succeeded without supplied benchmark evidence

IMPORTANT:
Do not output CREATE INDEX, DROP INDEX, ALTER, UPDATE, DELETE,
INSERT, or any other executable SQL statement.

If a deterministic recommendation contains sql_preview, refer to it
as "the deterministic SQL preview" rather than reproducing it.

Use ONLY the supplied deterministic diagnosis, recommendation,
and historical cases.

Explain:
1. What the PostgreSQL evidence shows.
2. Why the finding matters.
3. What the deterministic recommendation says.
4. What historical cases indicate.
5. What validation, approval, remediation, or benchmarking remains.

If there are no findings, explicitly state that no performance
bottleneck was identified by the deterministic engine.

Never treat historical cases as proof that the current query
will achieve the same result.
"""

        user_payload = {
            "query": query,
            "deterministic_diagnosis": diagnosis,
            "deterministic_recommendation": recommendation,
            "similar_historical_cases": similar_cases,
        }

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            max_tokens=700,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": str(user_payload),
                },
            ],
        )

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError("Groq returned an empty response.")

        return content.strip()


class LLMService:
    """Application-level service using the real Groq provider."""

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
    ) -> None:
        self.provider = provider or GroqLLMProvider()

    def explain_diagnosis(
        self,
        *,
        query: str,
        diagnosis: Dict[str, Any],
        recommendation: Optional[Dict[str, Any]] = None,
        similar_cases: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        """Generate the advisory explanation.

        The LLM layer is strictly advisory: it must never break the
        deterministic pipeline. Any provider failure (missing credentials,
        rate limits, oversized requests, network errors) is logged and
        degrades to ``None`` so the authoritative deterministic result is
        still returned to the caller.
        """

        try:
            return self.provider.explain(
                query=query,
                diagnosis=diagnosis,
                recommendation=recommendation,
                similar_cases=similar_cases or [],
            )
        except Exception as exc:
            logger.warning(
                "LLM explanation unavailable; deterministic diagnosis unaffected",
                extra={
                    "provider": type(self.provider).__name__,
                    "model": getattr(self.provider, "model", None),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            return None


def get_llm_service() -> LLMService:
    return LLMService()
