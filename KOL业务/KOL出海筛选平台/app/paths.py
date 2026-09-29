import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    database_path: Path
    log_dir: Path

    @classmethod
    def from_environment(cls) -> "AppPaths":
        override = os.environ.get("KOL_PLATFORM_DATA_DIR")
        if override:
            data_dir = Path(override).expanduser()
        else:
            from platformdirs import user_data_path

            data_dir = user_data_path("KOL合作管理平台", "Capgemini")

        return cls(
            data_dir=data_dir,
            database_path=data_dir / "kol_platform.db",
            log_dir=data_dir / "logs",
        )
