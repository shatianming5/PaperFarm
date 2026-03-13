"""Tests for the TUIPlugin lifecycle."""
import pytest

pytestmark = pytest.mark.asyncio


async def test_tui_plugin_lifecycle():
    from open_researcher.kernel import Kernel
    from open_researcher.plugins.storage import StoragePlugin
    from open_researcher.plugins.tui import TUIPlugin

    storage = StoragePlugin(db_path=":memory:")
    tui = TUIPlugin()

    k = Kernel(db_path=":memory:")
    await k.boot([storage, tui])

    assert tui.kernel is k

    await k.shutdown()


async def test_tui_plugin_not_started():
    from open_researcher.plugins.tui import TUIPlugin

    plugin = TUIPlugin()
    with pytest.raises(RuntimeError, match="not started"):
        _ = plugin.kernel
