from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MergeDecision:
    kind: Literal["local", "remote", "manual"]
    fields: list[str]
