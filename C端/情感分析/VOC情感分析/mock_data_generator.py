"""Generate synthetic seed cases for the P0 dynamic few-shot case store."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from llm_client import chat_json
from rag_service import DEFAULT_CASE_STORE, RagCase
from sentiment_analyzer import DEFAULT_TEXT_MODEL
import voc_rules


DEFAULT_TOPICS = [
    "winter_range_drop",
    "range_lower_than_claimed",
    "safety_warning",
    "charging_failure",
    "ota_bug_after_update",
    "service_no_response",
    "repair_delay",
    "price_cut_complaint",
    "delivery_delay",
    "screen_lag",
]


EXAMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "examples": {
            "type": "array",
            "items": {"type": "string"},
        }
    },
    "required": ["examples"],
}


def generate_topic_examples(topic_id: str, count: int, model: str) -> list[str]:
    definition = voc_rules.TOPIC_DEFINITIONS[topic_id]
    forbidden = list(definition.get("keywords", ()))
    messages = [
        {
            "role": "system",
            "content": (
                "You are an automotive customer review data generator. Output ONLY JSON. "
                "Generate realistic, conversational, and distinct English comments as they would appear on "
                "Hacker News, Reddit, or Twitter. Use natural internet slang, frustration, or technical jargon "
                "typical of EV owners. Do not be overly poetic. Each comment must clearly map to the specified issue."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "topic_id": topic_id,
                    "topic_name": definition["name"],
                    "count": count,
                    "forbidden_literal_phrases": forbidden,
                    "instruction": "Do not directly use the forbidden literal phrases. Do not output labels or explanations. Generate raw user comments only.",
                },
                ensure_ascii=False,
            ),
        },
    ]
    result = chat_json(messages, EXAMPLE_SCHEMA, model=model)
    examples = result.get("examples", []) if isinstance(result, dict) else []
    unique: list[str] = []
    for value in examples:
        text = str(value).strip()
        if text and text not in unique:
            unique.append(text)
    return unique[:count]


def build_cases(topic_id: str, examples: list[str]) -> list[RagCase]:
    definition = voc_rules.TOPIC_DEFINITIONS[topic_id]
    parent = str(definition["parent_category"])
    return [
        RagCase.from_dict(
            {
                "text": text,
                "language": "en",
                "parent_topic": parent,
                "topic_id": topic_id,
                "sentiment_label": "负面情感",
                "sentiment_spec": "抱怨",
                "source_type": "synthetic_seed",
                "quality_score": 0.75,
            }
        )
        for text in examples
    ]


def write_cases(path: Path, cases: list[RagCase]) -> int:
    existing: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("case_id"):
                existing[str(value["case_id"])] = value
    for case in cases:
        existing[case.case_id] = asdict(case)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n" for value in existing.values()),
        encoding="utf-8",
    )
    return len(cases)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate synthetic VOC RAG seed cases.")
    parser.add_argument("--output", type=Path, default=DEFAULT_CASE_STORE)
    parser.add_argument("--count", type=int, default=5, help="Examples per topic.")
    parser.add_argument("--topic", action="append", choices=sorted(voc_rules.TOPIC_DEFINITIONS))
    parser.add_argument("--model", default=DEFAULT_TEXT_MODEL)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    topics = args.topic or DEFAULT_TOPICS
    generated: list[RagCase] = []
    for topic_id in topics:
        examples = generate_topic_examples(topic_id, max(1, args.count), args.model)
        generated.extend(build_cases(topic_id, examples))
        print(f"Generated {len(examples)} case(s) for {topic_id}.", flush=True)
    added = write_cases(args.output, generated)
    print(f"Wrote {added} synthetic seed case(s) to {args.output}.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
