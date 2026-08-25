import pytest
from backend.models import Database


@pytest.mark.asyncio
async def test_roundtrip(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.init()
    assert await db.get_waveform_cache("123") is None
    await db.set_waveform_cache("123", {"low": [0.1], "mid": [0.2], "high": [0.3]}, 210.5)
    got = await db.get_waveform_cache("123")
    assert got == {"bands": {"low": [0.1], "mid": [0.2], "high": [0.3]}, "duration": 210.5}
    await db.close()
