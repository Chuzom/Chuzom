"""Tests for session context management."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from chuzom.context import (
    SessionBuffer,
    _strip_injected_context,
    auto_summarize_session,
    build_context_messages,
    format_session_summaries,
    get_recent_session_summaries,
    get_session_buffer,
    save_session_summary,
)
from chuzom.types import LLMResponse


class TestSessionBuffer:
    def test_record_and_get_recent(self):
        buf = SessionBuffer(max_messages=5)
        buf.record("user", "Hello", task_type="query")
        buf.record("assistant", "Hi there", task_type="query")

        msgs = buf.get_recent(5)
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[0].content == "Hello"
        assert msgs[1].role == "assistant"

    def test_ring_buffer_eviction(self):
        buf = SessionBuffer(max_messages=3)
        for i in range(5):
            buf.record("user", f"msg-{i}")

        msgs = buf.get_recent(5)
        assert len(msgs) == 3
        assert msgs[0].content == "msg-2"
        assert msgs[2].content == "msg-4"

    def test_get_recent_limits(self):
        buf = SessionBuffer(max_messages=10)
        for i in range(10):
            buf.record("user", f"msg-{i}")

        msgs = buf.get_recent(3)
        assert len(msgs) == 3
        assert msgs[0].content == "msg-7"

    def test_truncates_long_content_on_record(self):
        buf = SessionBuffer()
        long_content = "x" * 5000
        buf.record("user", long_content)

        msgs = buf.get_recent(1)
        assert len(msgs[0].content) == 2000

    def test_clear(self):
        buf = SessionBuffer()
        buf.record("user", "hello")
        buf.clear()
        assert buf.message_count == 0

    def test_format_for_injection_empty(self):
        buf = SessionBuffer()
        assert buf.format_for_injection() == ""

    def test_format_for_injection(self):
        buf = SessionBuffer()
        buf.record("user", "What is Python?", task_type="query")
        buf.record("assistant", "Python is a programming language.", task_type="query")

        result = buf.format_for_injection()
        assert "[Recent conversation context]" in result
        assert "User (query): What is Python?" in result
        assert "Assistant (query): Python is a programming language." in result

    def test_format_truncates_long_messages(self):
        buf = SessionBuffer()
        buf.record("user", "x" * 2000)

        result = buf.format_for_injection()
        # Content in injection is capped at 500 chars + "..."
        assert "..." in result


class TestSessionBufferSingleton:
    def test_returns_same_instance(self):
        buf1 = get_session_buffer()
        buf2 = get_session_buffer()
        assert buf1 is buf2


class TestFormatSessionSummaries:
    def test_empty(self):
        assert format_session_summaries([]) == ""

    def test_formats_summaries(self):
        summaries = [
            {
                "summary": "Worked on auth module",
                "session_start": "2026-03-29T10:00:00",
                "session_end": "2026-03-29T11:00:00",
                "message_count": 5,
                "task_types": ["code", "analyze"],
            },
            {
                "summary": "Research on caching strategies",
                "session_start": "2026-03-30T09:00:00",
                "session_end": "2026-03-30T10:00:00",
                "message_count": 3,
                "task_types": ["research"],
            },
        ]

        result = format_session_summaries(summaries)
        assert "[Previous session context]" in result
        # Input is newest-first (as returned by DB), reversed() makes oldest first
        # So "Research" (index 1, older after reverse) appears before "auth" (index 0, newer after reverse)
        # Actually: reversed([auth, research]) = [research, auth]
        assert result.index("Research on caching") < result.index("auth module")


class TestPersistentSummaries:
    @pytest.fixture
    def db_path(self, tmp_path):
        path = tmp_path / "test.db"
        with patch("chuzom.context._get_db_path", return_value=path):
            yield path

    @pytest.mark.asyncio
    async def test_save_and_retrieve(self, db_path):
        with patch("chuzom.context._get_db_path", return_value=db_path):
            await save_session_summary(
                summary="Built context injection feature",
                message_count=8,
                task_types=["code", "query"],
            )

            summaries = await get_recent_session_summaries(limit=5)
            assert len(summaries) == 1
            assert summaries[0]["summary"] == "Built context injection feature"
            assert summaries[0]["message_count"] == 8
            assert summaries[0]["task_types"] == ["code", "query"]

    @pytest.mark.asyncio
    async def test_respects_limit(self, db_path):
        with patch("chuzom.context._get_db_path", return_value=db_path):
            for i in range(5):
                await save_session_summary(f"Session {i}", i, ["query"])

            summaries = await get_recent_session_summaries(limit=2)
            assert len(summaries) == 2
            # Newest first
            assert summaries[0]["summary"] == "Session 4"

    @pytest.mark.asyncio
    async def test_no_db_returns_empty(self, tmp_path):
        missing = tmp_path / "nonexistent" / "db.sqlite"
        with patch("chuzom.context._get_db_path", return_value=missing):
            summaries = await get_recent_session_summaries()
            assert summaries == []


class TestBuildContextMessages:
    @pytest.fixture
    def reset_session_buffer(self):
        """Reset the global session buffer before each test."""
        import chuzom.context as context_module
        context_module._session_buffer = None
        yield
        context_module._session_buffer = None

    @pytest.mark.asyncio
    async def test_no_context_returns_empty(self, tmp_path, reset_session_buffer):
        db_path = tmp_path / "empty.db"
        with patch("chuzom.context._get_db_path", return_value=db_path):
            msgs = await build_context_messages()
            assert msgs == []

    @pytest.mark.asyncio
    async def test_with_session_buffer_only(self, tmp_path, reset_session_buffer):
        db_path = tmp_path / "empty.db"
        with patch("chuzom.context._get_db_path", return_value=db_path):
            buf = get_session_buffer()
            buf.record("user", "What is FastAPI?", task_type="query")
            buf.record("assistant", "FastAPI is a web framework.", task_type="query")

            msgs = await build_context_messages()
            assert len(msgs) == 1
            assert msgs[0]["role"] == "system"
            assert "FastAPI" in msgs[0]["content"]

    @pytest.mark.asyncio
    async def test_with_caller_context(self, tmp_path):
        db_path = tmp_path / "empty.db"
        with patch("chuzom.context._get_db_path", return_value=db_path):
            msgs = await build_context_messages(
                caller_context="Working on the chuzom project, adding context injection",
            )
            assert len(msgs) == 1
            assert "chuzom" in msgs[0]["content"]
            assert "[Additional context]" in msgs[0]["content"]

    @pytest.mark.asyncio
    async def test_combined_context_order(self, tmp_path):
        db_path = tmp_path / "test.db"
        with patch("chuzom.context._get_db_path", return_value=db_path):
            # Save a previous session summary
            await save_session_summary("Worked on auth", 3, ["code"])

            # Add current session messages
            buf = get_session_buffer()
            buf.record("user", "Now working on context", task_type="code")

            # Build context
            msgs = await build_context_messages(caller_context="Extra info")
            assert len(msgs) == 1
            content = msgs[0]["content"]

            # Previous sessions should come before current session
            prev_idx = content.index("Previous session")
            curr_idx = content.index("Recent conversation")
            extra_idx = content.index("Additional context")

            assert prev_idx < curr_idx < extra_idx

    @pytest.mark.asyncio
    async def test_respects_token_budget(self, tmp_path):
        db_path = tmp_path / "empty.db"
        with patch("chuzom.context._get_db_path", return_value=db_path):
            # Fill buffer with lots of content
            buf = get_session_buffer()
            for i in range(10):
                buf.record("user", f"Message {i}: {'x' * 500}", task_type="query")

            msgs = await build_context_messages(max_context_tokens=100)
            assert len(msgs) == 1
            # Should be truncated to roughly 100*4=400 chars
            assert len(msgs[0]["content"]) <= 500


class TestAutoSummarize:
    @pytest.fixture
    def db_path(self, tmp_path):
        path = tmp_path / "test.db"
        with patch("chuzom.context._get_db_path", return_value=path):
            yield path

    @pytest.fixture
    def reset_session_buffer(self):
        """Reset the global session buffer before each test."""
        import chuzom.context as context_module
        context_module._session_buffer = None
        yield
        context_module._session_buffer = None

    @pytest.mark.asyncio
    async def test_skips_short_sessions(self, db_path, reset_session_buffer):
        with patch("chuzom.context._get_db_path", return_value=db_path):
            buf = get_session_buffer()
            buf.record("user", "hello")
            result = await auto_summarize_session(min_messages=3)
            assert result is None

    @pytest.mark.asyncio
    async def test_summarizes_via_llm(self, db_path, reset_session_buffer):
        mock_response = LLMResponse(
            content="User asked about FastAPI and received an explanation of the framework.",
            model="gemini/gemini-2.5-flash",
            input_tokens=50,
            output_tokens=20,
            cost_usd=0.0001,
            latency_ms=200.0,
            provider="gemini",
        )

        with patch("chuzom.context._get_db_path", return_value=db_path):
            buf = get_session_buffer()
            buf.record("user", "What is FastAPI?", task_type="query")
            buf.record("assistant", "FastAPI is a modern web framework.", task_type="query")
            buf.record("user", "How do I install it?", task_type="query")
            buf.record("assistant", "Run pip install fastapi.", task_type="query")

            with patch("chuzom.router.route_and_call", new_callable=AsyncMock, return_value=mock_response):
                summary = await auto_summarize_session(min_messages=3)

            assert summary is not None
            assert "FastAPI" in summary

            # Verify it was persisted
            summaries = await get_recent_session_summaries()
            assert len(summaries) == 1
            assert summaries[0]["summary"] == summary
            assert summaries[0]["task_types"] == ["query"]

    @pytest.mark.asyncio
    async def test_falls_back_on_llm_failure(self, db_path):
        with patch("chuzom.context._get_db_path", return_value=db_path):
            buf = get_session_buffer()
            buf.record("user", "Build a REST API", task_type="code")
            buf.record("assistant", "Here's the code...", task_type="code")
            buf.record("user", "Add auth", task_type="code")

            with patch("chuzom.router.route_and_call", new_callable=AsyncMock, side_effect=RuntimeError("No models")):
                summary = await auto_summarize_session(min_messages=3)

            assert summary is not None
            assert "Topics:" in summary
            assert "Build a REST API" in summary

    @pytest.mark.asyncio
    async def test_collects_task_types(self, db_path, reset_session_buffer):
        mock_response = LLMResponse(
            content="Mixed session with research and code tasks.",
            model="gemini/gemini-2.5-flash",
            input_tokens=50, output_tokens=20,
            cost_usd=0.0001, latency_ms=200.0, provider="gemini",
        )

        with patch("chuzom.context._get_db_path", return_value=db_path):
            buf = get_session_buffer()
            buf.record("user", "Research caching", task_type="research")
            buf.record("assistant", "Redis is popular", task_type="research")
            buf.record("user", "Write cache code", task_type="code")
            buf.record("assistant", "Here's the code", task_type="code")

            with patch("chuzom.router.route_and_call", new_callable=AsyncMock, return_value=mock_response):
                await auto_summarize_session(min_messages=3)

            summaries = await get_recent_session_summaries()
            assert set(summaries[0]["task_types"]) == {"code", "research"}


class TestInjectedContextStripping:
    """Regression tests for the self-poisoning bug: SessionBuffer (always-on, NOT
    gated by CHUZOM_OKF) recorded every routed prompt/response verbatim, including
    OKF-injected <knowledge_context> blocks — which then kept replaying into
    unrelated future prompts indefinitely, even after OKF was disabled, because
    the buffer no longer knows where the content originally came from.
    """

    def test_strips_okf_knowledge_context_block(self):
        poisoned = (
            "<knowledge_context>\n"
            "## [SourceFile] setup.py\n"
            "fake fabricated content about a nonexistent API\n"
            "</knowledge_context>\n\n"
            "What is the real task API?"
        )
        clean = _strip_injected_context(poisoned)
        assert "knowledge_context" not in clean
        assert "fabricated" not in clean
        assert clean == "What is the real task API?"

    def test_strips_own_previously_injected_blocks(self):
        # a message that itself already carries THIS module's own injected
        # markers (e.g. captured before this fix existed) must not compound
        poisoned = (
            "[Recent conversation context]\n"
            "User (analyze): some old exchange\n"
            "Assistant (analyze): some old reply\n\n"
            "New unrelated question"
        )
        clean = _strip_injected_context(poisoned)
        assert "Recent conversation context" not in clean
        assert clean == "New unrelated question"

    def test_leaves_clean_text_untouched(self):
        assert _strip_injected_context("just a normal prompt") == "just a normal prompt"

    def test_session_buffer_record_strips_before_storing(self):
        """The exact bug, reproduced: recording an OKF-poisoned prompt must not
        let the poisoned block survive in the buffer to be replayed later."""
        buf = SessionBuffer(max_messages=5)
        poisoned_prompt = (
            "<knowledge_context>\n"
            "## [ModelCapability] codex-cli.md\n"
            "The Codex CLI provides access to GPT-3 and GPT-4 models\n"
            "</knowledge_context>\n\n"
            "Say the word \"test\" and nothing else."
        )
        buf.record("user", poisoned_prompt, task_type="query")
        stored = buf.get_recent(1)[0].content
        assert "knowledge_context" not in stored
        assert "codex-cli.md" not in stored
        assert stored == 'Say the word "test" and nothing else.'

        # and it must not appear when replayed into a future prompt either
        injected = buf.format_for_injection(n=1)
        assert "knowledge_context" not in injected
        assert "codex-cli.md" not in injected

    @pytest.mark.asyncio
    async def test_auto_summarize_never_sees_injected_content(self):
        """Defense in depth: even if a poisoned message somehow reached the
        buffer (e.g. from a process still running an older build), the
        summarizer LLM must never be handed the raw injected block."""
        import time as _time

        import chuzom.context as context_module
        from chuzom.context import SessionMessage
        context_module._session_buffer = None

        buf = get_session_buffer()
        # append directly via the dataclass, bypassing record()'s own guard,
        # to simulate content buffered by an older build before this fix
        buf._buffer.append(SessionMessage(
            role="user",
            content="<knowledge_context>\n## [SourceFile] fake.py\nbogus\n"
                   "</knowledge_context>\n\nreal question",
            timestamp=_time.time(),
            task_type="query",
        ))
        buf.record("assistant", "real answer", task_type="query")
        buf.record("user", "another real question", task_type="query")

        captured_prompt = {}

        async def _capture(*args, **kwargs):
            captured_prompt["prompt"] = args[1] if len(args) > 1 else kwargs.get("prompt")
            return LLMResponse(
                content="summary", model="m", input_tokens=1, output_tokens=1,
                cost_usd=0.0, latency_ms=1.0, provider="p",
            )

        with patch("chuzom.context._get_db_path",
                   return_value=None) as _dbp:
            import tempfile
            from pathlib import Path
            with tempfile.TemporaryDirectory() as td:
                _dbp.return_value = Path(td) / "t.db"
                with patch("chuzom.router.route_and_call", side_effect=_capture):
                    await auto_summarize_session(min_messages=3)

        assert "knowledge_context" not in captured_prompt.get("prompt", "")
        assert "fake.py" not in captured_prompt.get("prompt", "")

    @pytest.mark.asyncio
    async def test_retroactive_strip_on_read_of_already_poisoned_db_row(self):
        """A row written before this fix existed (by any older process) must
        still come out clean — this protects users whose SQLite already has
        poisoned summaries, without needing a data migration."""
        import sqlite3
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "t.db"
            with patch("chuzom.context._get_db_path", return_value=db_path):
                # write a poisoned row directly, bypassing save_session_summary,
                # to simulate data persisted before this fix landed
                from chuzom.context import _ensure_session_table
                _ensure_session_table(db_path)
                poisoned_summary = (
                    "<knowledge_context>\n## [SourceFile] x.py\nbogus\n"
                    "</knowledge_context>\n\nWorked on real feature X."
                )
                conn = sqlite3.connect(str(db_path))
                conn.execute(
                    """INSERT INTO session_summaries
                       (session_start, session_end, summary, message_count, task_types)
                       VALUES (?, ?, ?, ?, ?)""",
                    ("2026-01-01", "2026-01-01", poisoned_summary, 4, '["code"]'),
                )
                conn.commit()
                conn.close()

                summaries = await get_recent_session_summaries()
                assert len(summaries) == 1
                assert "knowledge_context" not in summaries[0]["summary"]
                assert "bogus" not in summaries[0]["summary"]
                assert "Worked on real feature X." in summaries[0]["summary"]
