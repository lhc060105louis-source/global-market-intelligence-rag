from functools import lru_cache
from uuid import UUID, uuid4

from app.paths import AppPaths


@lru_cache(maxsize=1)
def get_device_id() -> str:
    paths = AppPaths.from_environment()
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    device_file = paths.data_dir / "device-id"
    if device_file.exists():
        value = device_file.read_text("utf-8").strip()
        try:
            return str(UUID(value))
        except ValueError:
            pass
    value = str(uuid4())
    device_file.write_text(value, encoding="utf-8")
    return value
