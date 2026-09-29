"""Lightweight case retrieval and conservative pseudo-label growth for VOC RAG."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import threading
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

import voc_rules


DEFAULT_CASE_STORE = Path(__file__).with_name("rag_cases.jsonl")
VALID_SOURCE_TYPES = {"synthetic_seed", "pseudo_real"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RagCase:
    case_id: str
    text: str
    language: str
    parent_topic: str
    topic_id: str
    sentiment_label: str
    sentiment_spec: str | list[str]
    source_type: str
    quality_score: float = 0.8

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RagCase":
        source_type = str(value.get("source_type") or "synthetic_seed")
        if source_type not in VALID_SOURCE_TYPES:
            source_type = "synthetic_seed"
        return cls(
            case_id=str(value.get("case_id") or _case_id(str(value.get("text") or ""))),
            text=str(value.get("text") or "").strip(),
            language=str(value.get("language") or "unknown").strip(),
            parent_topic=str(value.get("parent_topic") or "other").strip(),
            topic_id=str(value.get("topic_id") or "other_unclassified").strip(),
            sentiment_label=str(value.get("sentiment_label") or "中性情感").strip(),
            sentiment_spec=value.get("sentiment_spec") or "无感",
            source_type=source_type,
            quality_score=max(0.0, min(1.0, float(value.get("quality_score", 0.8)))),
        )


@dataclass(frozen=True)
class RetrievalMatch:
    case: RagCase
    score: float


@dataclass(frozen=True)
class RagDecision:
    route: str
    matches: tuple[RetrievalMatch, ...] = ()
    reason: str = ""

    @property
    def examples(self) -> list[dict[str, Any]]:
        return [
            {
                "text": match.case.text,
                "parent_topic": match.case.parent_topic,
                "topic_id": match.case.topic_id,
                "sentiment_label": match.case.sentiment_label,
                "sentiment_spec": match.case.sentiment_spec,
                "similarity": round(match.score, 4),
                "source_type": match.case.source_type,
            }
            for match in self.matches
        ]


class Embedder(Protocol):
    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Dependency-free character n-gram vectors used as the P0 fallback."""

    def __init__(self, dimensions: int = 1024) -> None:
        self.dimensions = dimensions

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._encode_one(text) for text in texts]

    def _encode_one(self, text: str) -> list[float]:
        compact = "".join(str(text).lower().split())
        vector = [0.0] * self.dimensions
        tokens = [compact[index : index + size] for size in (1, 2, 3) for index in range(max(0, len(compact) - size + 1))]
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            raw = int.from_bytes(digest, "big")
            index = raw % self.dimensions
            vector[index] += -1.0 if raw & 1 else 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class SentenceTransformerEmbedder:
    """Local semantic embedder for English VOC text."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "RAG_EMBEDDING_PROVIDER=sentence_transformers requires sentence-transformers."
            ) from exc
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self.model.encode(list(texts), normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]


def _case_id(text: str) -> str:
    return "case-" + hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def expected_parent_topic(topic_id: str) -> str:
    definition = voc_rules.TOPIC_DEFINITIONS.get(topic_id, {})
    return str(definition.get("parent_category") or "other")


def hierarchy_is_valid(parent_topic: str, topic_id: str) -> bool:
    return topic_id in voc_rules.TOPIC_DEFINITIONS and expected_parent_topic(topic_id) == parent_topic


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return float(sum(a * b for a, b in zip(left, right)))


def _topic_id(result: dict[str, Any]) -> str:
    topics = result.get("topics")
    if isinstance(topics, list):
        for item in topics:
            if isinstance(item, dict) and item.get("topic_id") in voc_rules.TOPIC_DEFINITIONS:
                return str(item["topic_id"])
    return "other_unclassified"


def _majority_topic(matches: Sequence[RetrievalMatch]) -> tuple[str, int]:
    counts = Counter(match.case.topic_id for match in matches)
    return counts.most_common(1)[0] if counts else ("other_unclassified", 0)


class RagService:
    def __init__(
        self,
        case_store: Path = DEFAULT_CASE_STORE,
        *,
        enabled: bool = True,
        embedder: Embedder | None = None,
        high_threshold: float = 0.75,
        medium_threshold: float = 0.55,
        direct_real_cases: int = 3,
        max_cases_per_topic: int = 100,
    ) -> None:
        self.case_store = Path(case_store)
        self.enabled = enabled
        self.embedder = embedder or HashingEmbedder()
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self.direct_real_cases = direct_real_cases
        self.max_cases_per_topic = max_cases_per_topic
        self._lock = threading.Lock()
        self._pending: list[RagCase] = []
        self.cases = self._load_cases()
        self._vectors = self.embedder.encode([case.text for case in self.cases]) if self.cases else []

    @classmethod
    def from_env(cls) -> "RagService":
        enabled = _enabled(os.getenv("VOC_RAG_ENABLED"))
        provider = os.getenv("RAG_EMBEDDING_PROVIDER", "sentence_transformers").strip().lower()
        embedder: Embedder
        if not enabled:
            embedder = HashingEmbedder(_env_int("RAG_HASH_DIMENSIONS", 1024))
        elif provider == "sentence_transformers":
            embedder = SentenceTransformerEmbedder(
                os.getenv(
                    "RAG_EMBEDDING_MODEL",
                    "sentence-transformers/all-MiniLM-L6-v2",
                )
            )
        elif provider == "hashing":
            embedder = HashingEmbedder(_env_int("RAG_HASH_DIMENSIONS", 1024))
        else:
            raise ValueError(f"Unsupported RAG_EMBEDDING_PROVIDER: {provider}")
        return cls(
            Path(os.getenv("RAG_CASE_STORE", str(DEFAULT_CASE_STORE))),
            enabled=enabled,
            embedder=embedder,
            high_threshold=_env_float("RAG_HIGH_THRESHOLD", 0.75),
            medium_threshold=_env_float("RAG_MEDIUM_THRESHOLD", 0.55),
            direct_real_cases=_env_int("RAG_DIRECT_REAL_CASES", 3),
            max_cases_per_topic=_env_int("RAG_MAX_CASES_PER_TOPIC", 100),
        )

    def _load_cases(self) -> list[RagCase]:
        if not self.case_store.exists():
            return []
        cases: list[RagCase] = []
        for line in self.case_store.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                case = RagCase.from_dict(json.loads(line))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if case.text and hierarchy_is_valid(case.parent_topic, case.topic_id):
                cases.append(case)
        return cases

    def retrieve(self, text: str, top_k: int = 3) -> tuple[RetrievalMatch, ...]:
        if not self.enabled or not self.cases or not text.strip():
            return ()
        query = self.embedder.encode([text])[0]
        ranked = sorted(
            (RetrievalMatch(case, _dot(query, vector)) for case, vector in zip(self.cases, self._vectors)),
            key=lambda match: match.score,
            reverse=True,
        )
        return tuple(ranked[:top_k])

    def route(self, text: str) -> RagDecision:
        matches = self.retrieve(text)
        if not matches:
            return RagDecision("standard", reason="no_cases")
        top_score = matches[0].score
        majority, agreement = _majority_topic(matches)
        inferred_parent = voc_rules.infer_business_context(text)[1]
        parent_consistent = inferred_parent == "other" or inferred_parent == matches[0].case.parent_topic
        real_count = sum(
            case.source_type == "pseudo_real" and case.topic_id == majority for case in self.cases
        )
        if (
            top_score >= self.high_threshold
            and agreement >= 2
            and parent_consistent
            and majority != "other_unclassified"
            and real_count >= self.direct_real_cases
        ):
            return RagDecision("direct", matches, "high_similarity_and_real_consensus")
        if top_score >= self.medium_threshold:
            return RagDecision("dynamic_few_shot", matches, "retrieval_examples_available")
        return RagDecision("standard", matches, "low_similarity")

    def direct_result(self, decision: RagDecision) -> dict[str, Any]:
        if decision.route != "direct" or not decision.matches:
            raise ValueError("direct_result requires a direct RAG decision")
        topic_id, _ = _majority_topic(decision.matches)
        selected = next(match.case for match in decision.matches if match.case.topic_id == topic_id)
        return {
            "label": selected.sentiment_label,
            "topic": selected.parent_topic,
            "journey_stage": "full_journey",
            "sentiment_spec": selected.sentiment_spec,
            "sentiment_score": voc_rules.standard_sentiment_score(selected.sentiment_label),
            "sentiment_strength": voc_rules.standard_sentiment_strength(selected.sentiment_label, selected.parent_topic),
            "sentiment_categories": [{"code": selected.parent_topic, "strength": 3}],
            "entities": [],
            "topics": [{"topic_id": selected.topic_id, "name": voc_rules.TOPIC_DEFINITIONS[selected.topic_id]["name"]}],
        }

    def consider_pseudo_real(
        self,
        text: str,
        result: dict[str, Any],
        matches: Sequence[RetrievalMatch],
        *,
        language: str = "unknown",
    ) -> bool:
        if not self.enabled or len("".join(text.split())) < 6:
            return False
        topic_id = _topic_id(result)
        parent = str(result.get("topic") or "other")
        if (
            topic_id == "other_unclassified"
            or parent == "other"
            or not hierarchy_is_valid(parent, topic_id)
        ):
            return False
        majority, agreement = _majority_topic(matches)
        inferred_parent = voc_rules.infer_business_context(text)[1]
        top_score = matches[0].score if matches else 0.0
        unanimous_retrieval = len(matches) >= 3 and agreement == len(matches) and majority == topic_id
        rules_conflict = inferred_parent != "other" and inferred_parent != parent
        majority_sentiment = Counter(
            match.case.sentiment_label
            for match in matches
            if match.case.topic_id == majority
        ).most_common(1)
        result_sentiment = str(result.get("label") or result.get("sentiment_label") or "")
        sentiment_agrees = bool(majority_sentiment and majority_sentiment[0][0] == result_sentiment)
        if (
            not unanimous_retrieval
            or top_score < self.high_threshold
            or rules_conflict
            or not sentiment_agrees
        ):
            return False
        case = RagCase(
            case_id=_case_id(text),
            text=text.strip(),
            language=language or "unknown",
            parent_topic=parent,
            topic_id=topic_id,
            sentiment_label=str(result.get("label") or result.get("sentiment_label") or "中性情感"),
            sentiment_spec=result.get("sentiment_spec") or "无感",
            source_type="pseudo_real",
            quality_score=max(0.0, min(1.0, matches[0].score if matches else 0.7)),
        )
        with self._lock:
            known_ids = {item.case_id for item in self.cases} | {item.case_id for item in self._pending}
            topic_count = sum(item.topic_id == topic_id for item in self.cases) + sum(
                item.topic_id == topic_id for item in self._pending
            )
            if case.case_id in known_ids or topic_count >= self.max_cases_per_topic:
                return False
            self._pending.append(case)
        return True

    def flush_pending(self) -> int:
        with self._lock:
            if not self._pending:
                return 0
            added = list(self._pending)
            self._pending.clear()
            combined = self.cases + added
            self.case_store.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", delete=False, dir=self.case_store.parent, suffix=".tmp"
            ) as handle:
                for case in combined:
                    handle.write(json.dumps(asdict(case), ensure_ascii=False, separators=(",", ":")) + "\n")
                temporary = Path(handle.name)
            temporary.replace(self.case_store)
            self.cases = combined
            self._vectors = self.embedder.encode([case.text for case in self.cases])
            return len(added)
