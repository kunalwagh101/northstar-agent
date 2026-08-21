import zoneinfo
from datetime import datetime, timedelta


def test_bundled_tzdata_works_without_a_system_timezone_database() -> None:
    """Exercise the same fallback path used on Windows."""
    original_tzpath = zoneinfo.TZPATH
    zoneinfo.reset_tzpath(())
    zoneinfo.ZoneInfo.clear_cache()

    try:
        timezone = zoneinfo.ZoneInfo("Asia/Kolkata")
        sample = datetime(2026, 8, 21, 12, tzinfo=timezone)

        assert timezone.key == "Asia/Kolkata"
        assert sample.utcoffset() == timedelta(hours=5, minutes=30)
    finally:
        zoneinfo.reset_tzpath(original_tzpath)
        zoneinfo.ZoneInfo.clear_cache()
