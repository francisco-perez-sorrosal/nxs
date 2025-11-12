"""Summarization service for generating concise conversation summaries."""

from __future__ import annotations

from typing import Sequence

from anthropic.types import MessageParam
from pydantic import BaseModel, ConfigDict, model_validator

from nxs.application.claude import Claude
from nxs.application.reasoning.utils import load_prompt, format_prompt
from nxs.logger import get_logger

logger = get_logger("summarization_service")


class SummaryResult(BaseModel):
    """Result returned by the summarization service."""

    summary: str = ""
    total_messages: int = 0
    messages_summarized: int = 0
    skipped: bool = False
    error: str | None = None

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _validate_counts(self) -> "SummaryResult":
        if self.messages_summarized > self.total_messages:
            raise ValueError("messages_summarized cannot exceed total_messages")
        return self


class SummarizationService:
    """Agentic summarization helper that can summarise message collections."""

    def __init__(
        self,
        llm: Claude,
        *,
        chunk_size: int = 20,
        max_tokens: int = 500,
        min_messages: int = 4,
        initial_prompt_path: str = "summarization/initial_summary.txt",
        update_prompt_path: str = "summarization/update_summary.txt",
    ) -> None:
        self.llm = llm
        self.chunk_size = max(1, chunk_size)
        self.max_tokens = max(32, max_tokens)
        self.min_messages = max(0, min_messages)
        self._initial_prompt_template = load_prompt(initial_prompt_path)
        self._update_prompt_template = load_prompt(update_prompt_path)

    async def summarize(
        self,
        messages_or_text: Sequence[MessageParam] | str,
        *,
        existing_summary: str = "",
        start_index: int = 0,
        force: bool = False,
    ) -> SummaryResult:
        """Summarise a collection of messages or a single text."""
        if isinstance(messages_or_text, str):
            summary_text, error = await self._summarize_text(
                messages_or_text,
                existing_summary=existing_summary,
            )
            summary_text = summary_text.strip()
            return SummaryResult(
                summary=summary_text,
                total_messages=0,
                messages_summarized=0,
                skipped=not bool(summary_text),
                error=error,
            )

        messages = self._normalize_messages(messages_or_text)
        total_messages = len(messages)

        if total_messages == 0:
            return SummaryResult(
                summary="",
                total_messages=0,
                messages_summarized=0,
                skipped=True,
            )

        if not force and start_index >= total_messages:
            return SummaryResult(
                summary=existing_summary,
                total_messages=total_messages,
                messages_summarized=total_messages,
                skipped=True,
            )

        if (
            total_messages < self.min_messages
            and not force
            and not existing_summary.strip()
        ):
            return SummaryResult(
                summary="",
                total_messages=total_messages,
                messages_summarized=total_messages,
                skipped=True,
            )

        per_chunk_summaries: list[str] = []
        messages_processed = start_index
        captured_error: str | None = None

        for index in range(start_index, total_messages, self.chunk_size):
            chunk_messages = messages[index : index + self.chunk_size]
            chunk_text = self._format_messages(chunk_messages)
            logger.debug(
                "Summarization chunk %s: messages=%s, preview=%r",
                index // self.chunk_size + 1,
                len(chunk_messages),
                chunk_text[:200],
            )

            chunk_summary, error = await self._summarize_text(
                chunk_text,
                existing_summary="",
            )

            summary_text = chunk_summary.strip()
            logger.debug(
                "Summarization chunk %s result: %r",
                index // self.chunk_size + 1,
                summary_text[:200],
            )

            if error and not summary_text:
                return SummaryResult(
                    summary=existing_summary.strip(),
                    total_messages=total_messages,
                    messages_summarized=messages_processed,
                    error=error,
                )

            if summary_text:
                per_chunk_summaries.append(summary_text)

            messages_processed = min(total_messages, index + len(chunk_messages))

            if error:
                captured_error = error

        aggregated_sections = [
            f"Segment {idx + 1} Summary:\n{summary}"
            for idx, summary in enumerate(per_chunk_summaries)
        ]
        concatenated_summary_text = "\n\n".join(aggregated_sections).strip()

        if not concatenated_summary_text and start_index < total_messages:
            concatenated_summary_text = self._format_messages(messages[start_index:]).strip()

        final_summary_text, error = await self._summarize_text(
            concatenated_summary_text,
            existing_summary=existing_summary,
        )

        if error and not final_summary_text.strip():
            return SummaryResult(
                summary=existing_summary.strip(),
                total_messages=total_messages,
                messages_summarized=messages_processed,
                error=error,
            )

        final_text = final_summary_text.strip()
        if not final_text and existing_summary.strip():
            final_text = existing_summary.strip()

        summary_present = bool(final_text)

        logger.debug(
            "Summarization final result: summary_present=%s, length=%s, error=%s",
            summary_present,
            len(final_text),
            error or captured_error,
        )

        return SummaryResult(
            summary=final_text,
            total_messages=total_messages,
            messages_summarized=messages_processed if summary_present else start_index,
            skipped=not summary_present,
            error=error or captured_error,
        )

    async def _summarize_text(
        self,
        text: str,
        *,
        existing_summary: str,
    ) -> tuple[str, str | None]:
        """Summarise a single string of text."""
        if not text.strip():
            return existing_summary, None

        prompt = self._build_prompt_from_text(text, existing_summary)

        try:
            response = await self.llm.create_message(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
            )
            summary_text = self._extract_summary_text(response).strip()
            if not summary_text:
                warning_message = "Summary unavailable: model returned an empty response."
                logger.warning(warning_message)
                return warning_message, "empty-summary"
            combined = self._combine_summaries(existing_summary, summary_text)
            return combined, None
        except Exception as exc:  # pragma: no cover - network/SDK failure
            warning_message = "Summary unavailable: summarization service encountered an error."
            logger.warning("%s %s", warning_message, exc)
            return warning_message, str(exc)

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _normalize_messages(
        self,
        messages_or_text: Sequence[MessageParam] | str,
    ) -> list[MessageParam]:
        if isinstance(messages_or_text, str):
            return [{"role": "user", "content": messages_or_text}]
        return list(messages_or_text)

    def _build_prompt_from_text(self, text: str, existing_summary: str) -> str:
        """Create a prompt for initial or incremental summarisation from raw text."""
        if existing_summary.strip():
            return format_prompt(
                self._update_prompt_template,
                summary=existing_summary.strip(),
                new_messages=text,
            )
        return format_prompt(self._initial_prompt_template, conversation=text)

    @staticmethod
    def _combine_summaries(existing_summary: str, new_summary: str) -> str:
        existing = existing_summary.strip()
        new = new_summary.strip()
        if not existing:
            return new
        if not new:
            return existing
        return f"{existing}\n\n{new}"

    def _format_messages(self, messages: Sequence[MessageParam]) -> str:
        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            text = self._extract_text_from_content(content, max_length=200)
            if not text:
                continue
            if role == "user":
                lines.append(f"User: {text}")
            elif role == "assistant":
                lines.append(f"Assistant: {text}")
        return "\n".join(lines)

    @staticmethod
    def _extract_summary_text(response) -> str:
        if not response or not getattr(response, "content", None):
            return ""
        block = response.content[0]
        if hasattr(block, "text"):
            return str(block.text)
        if isinstance(block, dict):
            return str(block.get("text", ""))
        return str(block)

    @staticmethod
    def _extract_text_from_content(content, max_length: int = 60) -> str:
        if isinstance(content, str):
            return content[:max_length]

        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")[:max_length]
                text_attr = getattr(block, "text", None)
                if text_attr is not None:
                    return str(text_attr)[:max_length]
            return ""

        return str(content)[:max_length]

