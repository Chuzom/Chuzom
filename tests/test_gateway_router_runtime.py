import asyncio


def test_budget_lock_is_event_loop_local():
    from chuzom import router

    async def lock_id() -> int:
        async with router._budget_lock():
            return id(router._budget_lock())

    first = asyncio.run(lock_id())
    second = asyncio.run(lock_id())

    assert first != second


def test_disabled_subprocess_backends_from_env(monkeypatch):
    from chuzom import router

    monkeypatch.setenv("CHUZOM_DISABLE_SUBPROCESS_BACKENDS", "codex, gemini_cli")

    assert router._disabled_subprocess_backends() == {"codex", "gemini_cli"}
