from unittest.mock import AsyncMock, patch
import pytest

@pytest.mark.asyncio
@patch("core.tts.asyncio.create_subprocess_exec")
async def test_tts_dummy(mock_exec):
    pass
