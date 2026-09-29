#!/usr/bin/env python
"""Batch C-end VOC analysis for CSV/XLSX comment files."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import html
import inspect
import json
import os
import re
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree

import voc_rules
from llm_client import is_ollama_provider
from rag_service import RagDecision, RagService
from sentiment_analyzer import (
    CPU_FALLBACK_HOST,
    DEFAULT_HOST,
    DEFAULT_TEXT_MODEL,
    analyze,
    installed_models,
    is_cuda_backend_error,
    normalize_topic,
    start_cpu_ollama,
    wait_for_ollama,
)


VOC_ALLOWED_SUFFIXES = {".csv", ".xlsx"}
CATEGORY_LABELS = voc_rules.CATEGORY_LABELS
TOPIC_DEFINITIONS = voc_rules.TOPIC_DEFINITIONS
RECALL_KEYWORDS = voc_rules.RECALL_KEYWORDS
RIGHTS_KEYWORDS = voc_rules.RIGHTS_KEYWORDS
STANDARD_METADATA_COLUMNS = {"source_id", "channel", "published_at", "language"}
STANDARD_CONTENT_COLUMNS = {"text", "image_url", "image_path"}
STANDARD_REQUIRED_COLUMNS = STANDARD_METADATA_COLUMNS | {"text"}
STANDARD_OPTIONAL_COLUMNS = {
    "region",
    "brand",
    "model",
    "model_ycode",
    "source_url",
    "image_url",
    "image_path",
    "media_type",
    "ocr_text",
    "review_status",
    "anonym_user_id",
}
INPUT_FIELD_ALIASES = {
    "publish_at": "published_at",
    "specname": "model_ycode",
    "piclist_json": "source_url",
    "image": "image_url",
    "image_urls": "image_url",
    "images": "image_url",
    "img": "image_url",
    "picture": "image_url",
    "picture_url": "image_url",
    "pic_url": "image_url",
    "photo": "image_url",
    "photo_url": "image_url",
}
SENTIMENT_SPECS = {
    "joy",
    "happiness",
    "satisfaction",
    "excitement",
    "moved",
    "affection",
    "trust",
    "anticipation",
    "surprise",
    "curiosity",
    "calm",
    "indifference",
    "anxiety",
    "worry",
    "nervousness",
    "fear",
    "sadness",
    "disappointment",
    "frustration",
    "anger",
    "disgust",
    "complaint",
    "shame",
    "guilt",
    "jealousy",
    "envy",
    "contempt",
    "confusion",
}
DEFAULT_SENTIMENT_SPEC_BY_LABEL = {
    "positive": "satisfaction",
    "neutral": "calm",
    "negative": "complaint",
    "mixed": "satisfaction",
    "unknown": "indifference",
}
CHANNELS = {"forum", "tiktok", "customer_service", "test_drive", "app_order", "survey", "other"}
CHANNEL_ALIASES = {
    "youtube": "forum",
    "bilibili": "forum",
    "reddit": "forum",
    "app": "app_order",
    "service": "customer_service",
}
JOURNEY_STAGES = {
    "pre_sales_awareness",
    "pre_sales_lead",
    "sales_experience",
    "after_sales_service",
    "after_sales_community",
    "full_journey",
}
MODEL_CARD_VERSION = "sentiment-model-v1.0"
OCR_ENGINE = None
OCR_ENGINE_LOCK = threading.Lock()


def remote_worker_count(default: int = 4) -> int:
    try:
        workers = int(os.getenv("VOC_MAX_WORKERS", str(default)))
    except ValueError:
        workers = default
    return max(1, min(16, workers))


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", "_", str(value or "").strip().lower())


def clean_cell(value: object) -> str:
    return str(value or "").strip()


def normalize_input_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {normalize_header(key): clean_cell(value) for key, value in row.items()}
    for source, target in INPUT_FIELD_ALIASES.items():
        if clean_cell(normalized.get(source)) and not clean_cell(normalized.get(target)):
            normalized[target] = normalized[source]
    if clean_cell(normalized.get("piclist_json")) and not clean_cell(normalized.get("image_url")):
        normalized["image_url"] = normalized["piclist_json"]
    return normalized


def has_image_reference(row: dict[str, str]) -> bool:
    return bool(clean_cell(row.get("image_url")) or clean_cell(row.get("image_path")))


def has_required_values(row: dict[str, str]) -> bool:
    has_metadata = all(clean_cell(row.get(column)) for column in STANDARD_METADATA_COLUMNS)
    has_content = bool(clean_cell(row.get("text")) or has_image_reference(row))
    return has_metadata and has_content


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            with path.open("r", encoding=encoding, newline="") as stream:
                reader = csv.DictReader(stream)
                if not reader.fieldnames:
                    return []
                return [
                    normalize_input_row(row)
                    for row in reader
                ]
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV encoding is not supported. Please save it as UTF-8 or GB18030.")


def column_name_to_index(name: str) -> int:
    index = 0
    for char in name:
        index = index * 26 + (ord(char.upper()) - ord("A") + 1)
    return index - 1


def read_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values: list[str] = []
    for item in root.findall("x:si", namespace):
        pieces = [node.text or "" for node in item.findall(".//x:t", namespace)]
        values.append("".join(pieces))
    return values


def first_worksheet_path(archive: zipfile.ZipFile) -> str:
    names = archive.namelist()
    for candidate in ("xl/worksheets/sheet1.xml", "xl/worksheets/sheet.xml"):
        if candidate in names:
            return candidate
    sheets = sorted(name for name in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name))
    if not sheets:
        raise ValueError("No worksheet was found in the Excel file.")
    return sheets[0]


def read_xlsx_rows(path: Path) -> list[dict[str, str]]:
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        shared_strings = read_xlsx_shared_strings(archive)
        root = ElementTree.fromstring(archive.read(first_worksheet_path(archive)))

    table: list[list[str]] = []
    for row_node in root.findall(".//x:sheetData/x:row", namespace):
        cells: dict[int, str] = {}
        for cell in row_node.findall("x:c", namespace):
            ref = cell.attrib.get("r", "")
            match = re.match(r"([A-Z]+)", ref)
            if not match:
                continue
            value_node = cell.find("x:v", namespace)
            inline_node = cell.find("x:is/x:t", namespace)
            raw_value = value_node.text if value_node is not None else inline_node.text if inline_node is not None else ""
            if cell.attrib.get("t") == "s" and raw_value != "":
                raw_value = shared_strings[int(raw_value)]
            cells[column_name_to_index(match.group(1))] = html.unescape(str(raw_value or ""))
        if cells:
            max_index = max(cells)
            table.append([cells.get(index, "") for index in range(max_index + 1)])

    if not table:
        return []
    headers = [normalize_header(value) for value in table[0]]
    rows: list[dict[str, str]] = []
    for raw_row in table[1:]:
        rows.append(normalize_input_row({
            headers[index]: clean_cell(value)
            for index, value in enumerate(raw_row)
            if index < len(headers) and headers[index]
        }))
    return rows


def read_voc_rows(path: Path) -> list[dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        rows = read_csv_rows(path)
    elif suffix == ".xlsx":
        rows = read_xlsx_rows(path)
    else:
        raise ValueError("Only CSV and XLSX files are supported for C-end VOC analysis.")
    source_dir = str(path.resolve().parent)
    valid_rows = [row for row in rows if has_required_values(row)]
    for row in valid_rows:
        row["__source_dir"] = source_dir
    return valid_rows


def validate_voc_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    columns = set(rows[0].keys()) if rows else set()
    visible_columns = {column for column in columns if not column.startswith("__")}
    missing_metadata = sorted(STANDARD_METADATA_COLUMNS - visible_columns)
    missing_content = not (visible_columns & STANDARD_CONTENT_COLUMNS)
    missing = missing_metadata + (["text_or_image"] if missing_content else [])
    return {
        "row_count": len(rows),
        "columns": sorted(visible_columns),
        "missing_columns": missing,
        "optional_columns": sorted(STANDARD_OPTIONAL_COLUMNS & visible_columns),
        "can_analyze": bool(rows) and not missing,
        "input_schema": "standard_signal_multimodal",
        "accepted_schemas": {
            "standard_signal": sorted(STANDARD_REQUIRED_COLUMNS),
            "standard_signal_multimodal": sorted(STANDARD_METADATA_COLUMNS) + ["at least one of text, image_url, or image_path"],
        },
    }


def split_media_refs(value: Any) -> list[str]:
    text = clean_cell(value)
    if not text:
        return []
    refs: list[str] = []
    if text.startswith("[") or text.startswith("{"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, str):
                    refs.append(item)
                elif isinstance(item, dict):
                    refs.extend(
                        clean_cell(item.get(key))
                        for key in ("url", "image_url", "path", "image_path")
                        if clean_cell(item.get(key))
                    )
        elif isinstance(parsed, dict):
            refs.extend(
                clean_cell(parsed.get(key))
                for key in ("url", "image_url", "path", "image_path")
                if clean_cell(parsed.get(key))
            )
    if not refs:
        refs = [part.strip() for part in re.split(r"[|,;\n]+", text) if part.strip()]
    seen: set[str] = set()
    unique_refs: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            unique_refs.append(ref)
    return unique_refs


def media_type_for(row: dict[str, str]) -> str:
    explicit = clean_cell(row.get("media_type")).lower()
    if explicit in {"text", "image", "text_image"}:
        return explicit
    has_text = bool(clean_cell(row.get("text")))
    has_image = has_image_reference(row)
    if has_text and has_image:
        return "text_image"
    if has_image:
        return "image"
    return "text"


def local_image_path(ref: str, source_dir: str = "") -> Path | None:
    if re.match(r"^https?://", ref, flags=re.I):
        return None
    path = Path(ref)
    if not path.is_absolute() and source_dir:
        path = Path(source_dir) / path
    return path


def ocr_engine() -> Any:
    global OCR_ENGINE
    if OCR_ENGINE is None:
        with OCR_ENGINE_LOCK:
            if OCR_ENGINE is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR  # type: ignore
                except ImportError as exc:
                    raise RuntimeError("rapidocr_onnxruntime is not installed; install requirements.txt to enable image OCR.") from exc
                OCR_ENGINE = RapidOCR()
    return OCR_ENGINE


def ocr_image_ref(ref: str, source_dir: str = "") -> str:
    path = local_image_path(ref, source_dir)
    cleanup_path: Path | None = None
    if path is None:
        suffix = Path(urllib.parse.urlparse(ref).path).suffix or ".jpg"
        with urllib.request.urlopen(ref, timeout=20) as response:
            data = response.read()
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            handle.write(data)
            cleanup_path = Path(handle.name)
            path = cleanup_path
        finally:
            handle.close()
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")
    try:
        result, _ = ocr_engine()(str(path))
    finally:
        if cleanup_path:
            cleanup_path.unlink(missing_ok=True)
    lines: list[str] = []
    for item in result or []:
        if len(item) >= 2:
            text = item[1][0] if isinstance(item[1], (list, tuple)) else item[1]
            if clean_cell(text):
                lines.append(clean_cell(text))
    return "\n".join(lines)


def extract_ocr_text(row: dict[str, str], max_images: int = 2) -> str:
    existing = clean_cell(row.get("ocr_text"))
    if existing:
        return existing
    refs = split_media_refs(row.get("image_path")) + split_media_refs(row.get("image_url"))
    if not refs:
        return ""
    source_dir = clean_cell(row.get("__source_dir"))
    texts: list[str] = []
    errors: list[str] = []
    for ref in refs[:max_images]:
        try:
            text = ocr_image_ref(ref, source_dir)
        except Exception as exc:
            errors.append(f"{ref}: {exc}")
            continue
        if clean_cell(text):
            texts.append(text)
    if errors:
        row["ocr_errors"] = " | ".join(errors)
    return "\n".join(texts)


def build_analysis_text(row: dict[str, str]) -> str:
    raw_text = clean_cell(row.get("text"))
    ocr_text = extract_ocr_text(row)
    row["ocr_text"] = ocr_text
    row["source_media_type"] = media_type_for(row)
    if raw_text and ocr_text:
        return f"User text: {raw_text}\nImage OCR text: {ocr_text}"
    if ocr_text:
        return ocr_text
    return raw_text


def build_context(row: dict[str, str]) -> str:
    fields = [
        ("channel", row.get("channel")),
        ("region", row.get("region")),
        ("brand", row.get("brand")),
        ("model", row.get("model")),
        ("model_ycode", row.get("model_ycode")),
        ("published_at", row.get("published_at")),
        ("language", row.get("language")),
        ("source_url", row.get("source_url")),
        ("media_type", row.get("source_media_type") or media_type_for(row)),
        ("image_url", row.get("image_url")),
        ("image_path", row.get("image_path")),
    ]
    return "; ".join(f"{key}: {value}" for key, value in fields if clean_cell(value))


def clamp_number(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    return int(round(clamp_number(value, minimum, maximum, default)))


def normalize_channel(value: Any) -> str:
    text = clean_cell(value).lower()
    text = CHANNEL_ALIASES.get(text, text)
    return text if text in CHANNELS else "other"


def normalize_language(value: Any) -> str:
    text = clean_cell(value)
    upper_text = text.upper()
    aliases = {
        "CN": "Chinese",
        "ZH": "Chinese",
        "ZH-CN": "Chinese",
        "CHINESE": "Chinese",
        "Chinese": "Chinese",
        "Chinese": "Chinese",
    }
    if upper_text in {"DE", "EN", "FR", "IT", "ES", "UNKNOWN"}:
        return upper_text
    return aliases.get(upper_text) or aliases.get(text) or "UNKNOWN"


def normalize_region(value: Any) -> str:
    text = clean_cell(value).upper()
    return text or "not specified"


def normalize_model_name(value: Any) -> str:
    text = clean_cell(value)
    return text or "not specified"


def normalize_review_status(value: Any) -> str:
    text = clean_cell(value) or "review_pass"
    return text if text in {"pending_review", "review_pass", "review_reject"} else "pending_review"


def excel_datetime_from(value: Any) -> datetime | None:
    text = clean_cell(value)
    if not text or not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return None
    try:
        serial = float(text)
    except ValueError:
        return None
    if serial < 1:
        return None
    return datetime(1899, 12, 30) + timedelta(days=serial)


def parsed_datetime_from(value: Any) -> datetime | None:
    text = clean_cell(value)
    if not text:
        return None
    excel_datetime = excel_datetime_from(text)
    if excel_datetime:
        return excel_datetime
    normalized = text.replace("T", " ").rstrip("Z")
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(normalized[: len(datetime.now().strftime(fmt))], fmt)
        except ValueError:
            continue
    match = re.search(r"\d{4}-\d{1,2}-\d{1,2}", text)
    if match:
        for fmt in ("%Y-%m-%d", "%Y-%m-%d"):
            try:
                return datetime.strptime(match.group(0), fmt)
            except ValueError:
                continue
    return None


def published_date_from(value: Any) -> str:
    parsed = parsed_datetime_from(value)
    if parsed:
        return parsed.strftime("%Y-%m-%d")
    return "UNKNOWN_DATE"


def published_time_from(value: Any) -> str:
    text = clean_cell(value)
    parsed = parsed_datetime_from(text)
    if not parsed:
        return "unknown"
    if excel_datetime_from(text) and float(text) % 1 == 0:
        return "unknown"
    if re.search(r"\d{1,2}:\d{2}", text) or (excel_datetime_from(text) and float(text) % 1 != 0):
        return parsed.strftime("%H:%M:%S")
    return "unknown"


def normalize_standard_stage(value: Any) -> str:
    text = clean_cell(value)
    return text if text in JOURNEY_STAGES else "full_journey"


def sentiment_score_for(label: str, confidence: Any = None) -> float:
    return voc_rules.standard_sentiment_score(label)


def sentiment_strength_for(label: str, topic: str = "other") -> int:
    return voc_rules.standard_sentiment_strength(label, topic)


def normalize_sentiment_spec(value: Any, label: str = "neutral") -> str:
    text = clean_cell(value)
    if text in SENTIMENT_SPECS:
        return text
    return DEFAULT_SENTIMENT_SPEC_BY_LABEL.get(label, "indifference")


def normalize_sentiment_label(label: Any) -> str:
    aliases = {
        "positive": "positive",
        "neutral": "neutral",
        "negative": "negative",
        "mixed": "mixed",
        "unknown": "neutral",
    }
    text = clean_cell(label)
    text = aliases.get(text, text)
    return text if text in voc_rules.SENTIMENT_LABELS else "neutral"


def sentiment_label_from_specs(specs: list[str], fallback: Any = "neutral") -> str:
    has_positive = any(spec in voc_rules.POSITIVE_EMOTIONS for spec in specs)
    has_negative = any(spec in voc_rules.NEGATIVE_EMOTIONS for spec in specs)
    if has_positive and has_negative:
        return "mixed"
    if has_positive:
        return "positive"
    if any(spec in voc_rules.NEGATIVE_EMOTIONS for spec in specs):
        return "negative"
    if any(spec in voc_rules.NEUTRAL_EMOTIONS for spec in specs):
        return "neutral"
    return normalize_sentiment_label(fallback)


def emotion_specs_from_result(result: dict[str, Any]) -> list[str]:
    specs = [
        spec for spec in voc_rules.raw_sentiment_specs(result.get("sentiment_spec"))
        if spec in SENTIMENT_SPECS
    ]
    raw_emotions = result.get("emotions")
    if isinstance(raw_emotions, list):
        for item in raw_emotions:
            name = item.get("name") if isinstance(item, dict) else item
            text = clean_cell(name)
            if text in SENTIMENT_SPECS and text not in specs:
                specs.append(text)
    return specs


def sentiment_spec_from_result(result: dict[str, Any], label: str) -> str | list[str]:
    direct_specs = emotion_specs_from_result(result)
    if direct_specs:
        return voc_rules.standard_sentiment_spec(label, direct_specs if label == "mixed" else direct_specs[0])
    return voc_rules.standard_sentiment_spec(label, normalize_sentiment_spec("", label))


def keyword_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    lower_text = text.lower()
    return [keyword for keyword in keywords if keyword.lower() in lower_text]


def effective_text(row: dict[str, str]) -> str:
    return clean_cell(row.get("analysis_text")) or clean_cell(row.get("text")) or clean_cell(row.get("ocr_text"))


def category_from_result(result: dict[str, Any]) -> dict[str, Any]:
    result_topic = normalize_topic(result.get("topic"))
    label = normalize_sentiment_label(result.get("label", "neutral"))
    standard_strength = sentiment_strength_for(label, result_topic)
    raw_categories = result.get("sentiment_categories")
    if isinstance(raw_categories, list):
        for item in raw_categories:
            if isinstance(item, dict):
                code = normalize_topic(item.get("code"))
                if code == "other" and result_topic != "other":
                    code = result_topic
                return {
                    "code": code,
                    "label": CATEGORY_LABELS.get(code, CATEGORY_LABELS["other"]),
                    "strength": standard_strength,
                }
    code = result_topic
    return {
        "code": code,
        "label": CATEGORY_LABELS.get(code, CATEGORY_LABELS["other"]),
        "strength": standard_strength,
    }


def entity_match_key(value: str) -> str:
    return re.sub(r"[\W_]+", "", clean_cell(value).lower())


def entity_normalized_name(value: str) -> str:
    return re.sub(r"[\W]+", "_", clean_cell(value).lower()).strip("_")


def canonical_entity(
    entity_type: str,
    name: str,
    normalized_name: str,
    row: dict[str, str],
) -> tuple[str, str, str]:
    combined_key = entity_match_key(f"{name} {normalized_name}")
    brand = clean_cell(row.get("brand"))
    brand_key = entity_match_key(brand)
    if brand and brand_key and brand_key in combined_key:
        return "brand", brand, entity_normalized_name(brand)

    model = clean_cell(row.get("model"))
    model_key = entity_match_key(model)
    if model and model_key and model_key in combined_key:
        return "vehicle_model", model, entity_normalized_name(model)

    symptom_aliases = (
        ("ghost_brake", "phantom braking", ("phantom braking", "unintended braking", "unexpected road hazard", "phantom brake", "phantom braking", "ghost brake")),
        ("sudden_brake", "hard braking", ("hard braking", "sudden braking", "sudden brake", "hard brake")),
    )
    lower_text = f"{name} {normalized_name}".lower()
    for canonical_name, display_name, aliases in symptom_aliases:
        if any(alias.lower() in lower_text for alias in aliases):
            return "symptom", display_name, canonical_name

    taxonomy_match = voc_rules.normalize_entity_with_taxonomy(entity_type, name)
    if taxonomy_match:
        canonical_name = taxonomy_match["name"]
        return entity_type, canonical_name, entity_normalized_name(canonical_name)

    if not normalized_name:
        normalized_name = name
    return entity_type, name, entity_normalized_name(normalized_name)


def normalize_entities(raw_entities: Any, row: dict[str, str], result: dict[str, Any]) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    result_topic = normalize_topic(result.get("topic"))
    row_score = sentiment_score_for(str(result.get("label", "neutral")))

    def add_entity(entity_type: str, name: str, normalized_name: str, sentiment_score: Any) -> None:
        if not name:
            return
        entity_type, name, normalized_name = canonical_entity(entity_type, name, normalized_name, row)
        dedupe_key = (entity_type, entity_match_key(normalized_name))
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        entities.append(
            {
                "type": entity_type,
                "name": name,
                "normalized_name": normalized_name,
                "sentiment_score": clamp_number(
                    sentiment_score,
                    -1.0,
                    1.0,
                    row_score,
                ),
            }
        )

    if isinstance(raw_entities, list):
        for item in raw_entities:
            if not isinstance(item, dict):
                continue
            entity_type = clean_cell(item.get("type"))
            if entity_type not in {"vehicle_model", "part", "symptom", "brand", "other"}:
                entity_type = "other"
            name = clean_cell(item.get("name"))
            if not name:
                continue
            normalized_name = clean_cell(item.get("normalized_name")) or name
            add_entity(entity_type, name, normalized_name, item.get("sentiment_score"))
    brand = clean_cell(row.get("brand"))
    if brand:
        add_entity("brand", brand, brand.lower().replace(" ", "_"), row_score)
    model = clean_cell(row.get("model"))
    if model:
        add_entity("vehicle_model", model, model.lower().replace(" ", "_"), row_score)
    text = effective_text(row).lower()
    symptom_keywords = {
        "ghost_brake": ("phantom braking", "unintended braking", "unexpected road hazard", "phantom brake", "phantom braking", "ghost brake"),
        "sudden_brake": ("hard braking", "sudden braking", "sudden brake", "hard brake"),
    }
    if any(keyword in text for keyword in symptom_keywords["ghost_brake"]):
        add_entity("symptom", "phantom braking", "ghost_brake", -1.0)
    if any(keyword in text for keyword in symptom_keywords["sudden_brake"]):
        add_entity("symptom", "hard braking", "sudden_brake", -1.0)
    voc_rules.enrich_entities_from_text(entities, text, row_score)
    return entities


def topic_from_text(text: str, fallback_topic: str) -> dict[str, str]:
    lower_text = text.lower()
    code = normalize_topic(fallback_topic)
    for topic_id, definition in TOPIC_DEFINITIONS.items():
        if definition.get("parent_category") == code and any(keyword.lower() in lower_text for keyword in definition["keywords"]):
            return {"topic_id": topic_id, "name": definition["name"]}
    for topic_id, definition in TOPIC_DEFINITIONS.items():
        if definition.get("parent_category") == code:
            return {"topic_id": topic_id, "name": definition["name"]}
    return {"topic_id": "other_unclassified", "name": TOPIC_DEFINITIONS["other_unclassified"]["name"]}


def normalize_topics(raw_topics: Any, text: str, fallback_topic: str) -> list[dict[str, str]]:
    parent_category = normalize_topic(fallback_topic)
    if isinstance(raw_topics, list):
        topics: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in raw_topics:
            if not isinstance(item, dict):
                continue
            topic_id = clean_cell(item.get("topic_id"))
            if topic_id not in TOPIC_DEFINITIONS:
                continue
            if TOPIC_DEFINITIONS[topic_id].get("parent_category") != parent_category:
                continue
            if topic_id in seen:
                continue
            seen.add(topic_id)
            name = clean_cell(item.get("name")) or TOPIC_DEFINITIONS[topic_id]["name"]
            topics.append({"topic_id": topic_id, "name": name})
        if topics:
            return topics
    return [topic_from_text(text, fallback_topic)]


def build_standardized_event(row: dict[str, str], result: dict[str, Any], row_number: int) -> dict[str, Any]:
    raw_label = result.get("sentiment_label") or result.get("label") or "neutral"
    label = sentiment_label_from_specs(emotion_specs_from_result(result), raw_label)
    text = effective_text(row)
    recall_hits = keyword_hits(text, RECALL_KEYWORDS)
    rights_hits = keyword_hits(text, RIGHTS_KEYWORDS)
    result_for_category = {**result, "label": label}
    category = category_from_result(result_for_category)
    standard_score = sentiment_score_for(label)
    standard_strength = sentiment_strength_for(label, category["code"])
    event = {
        "source_id": clean_cell(row.get("source_id")) or f"row-{row_number}",
        "channel": normalize_channel(row.get("channel")),
        "published_at": published_time_from(row.get("published_at")),
        "published_date": published_date_from(row.get("published_at")),
        "language": normalize_language(row.get("language")),
        "region": normalize_region(row.get("region")),
        "brand": clean_cell(row.get("brand")),
        "model": normalize_model_name(row.get("model")),
        "model_ycode": clean_cell(row.get("model_ycode")),
        "journey_stage": normalize_standard_stage(result.get("journey_stage") or row.get("journey_stage")),
        "sentiment_label": label,
        "sentiment_score": standard_score,
        "sentiment_spec": sentiment_spec_from_result(result, label),
        "sentiment_strength": standard_strength,
        "sentiment_categories": [category],
        "entities": normalize_entities(result.get("entities"), row, {**result, "label": label}),
        "topics": normalize_topics(result.get("topics"), text, category["code"]),
        "recall_keyword_hit": bool(recall_hits),
        "rights_keyword_hit": bool(rights_hits),
        "risk_keywords": sorted(set(recall_hits + rights_hits)),
        "model_card_version": clean_cell(row.get("model_card_version") or result.get("model_card_version")) or MODEL_CARD_VERSION,
    }
    if media_type_for(row) != "text":
        event.update(
            {
                "source_media_type": row.get("source_media_type") or media_type_for(row),
                "raw_text": clean_cell(row.get("text")),
                "ocr_text": clean_cell(row.get("ocr_text")),
                "ocr_errors": clean_cell(row.get("ocr_errors")),
                "analysis_text": text,
                "image_url": clean_cell(row.get("image_url")),
                "image_path": clean_cell(row.get("image_path")),
            }
        )
    return event


def write_jsonl_events(path: Path, events: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n" for event in events),
        encoding="utf-8",
    )


def analyze_voc_rows(
    rows: list[dict[str, str]],
    analyze_func: Callable[[str, str, str, str], dict[str, Any]] | None = None,
    host: str = DEFAULT_HOST,
    model: str = DEFAULT_TEXT_MODEL,
    limit: int | None = None,
    progress: Callable[[int, int], None] | None = None,
    max_workers: int | None = None,
    rag: RagService | None = None,
) -> dict[str, Any]:
    if not rows:
        raise ValueError("No valid comments were found in the uploaded file.")

    if analyze_func is None:
        active_host = host
        if is_ollama_provider():
            if active_host == DEFAULT_HOST and wait_for_ollama(CPU_FALLBACK_HOST, attempts=1):
                active_host = CPU_FALLBACK_HOST
            models = installed_models(active_host)
            if model not in models:
                raise RuntimeError(f"Local Ollama model {model!r} is not installed.")

        def analyze_func(
            active_host: str,
            model: str,
            text: str,
            context: str,
            retrieved_examples: list[dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
            try:
                return analyze(
                    active_host,
                    model,
                    text,
                    context,
                    retrieved_examples=retrieved_examples,
                )
            except RuntimeError as exc:
                if not is_ollama_provider() or active_host != DEFAULT_HOST or not is_cuda_backend_error(exc):
                    raise
                start_cpu_ollama()
                if not wait_for_ollama(CPU_FALLBACK_HOST):
                    raise
                return analyze(
                    CPU_FALLBACK_HOST,
                    model,
                    text,
                    context,
                    retrieved_examples=retrieved_examples,
                )

        host = active_host

    valid_rows = [row for row in rows if has_required_values(row)]
    if not valid_rows:
        raise ValueError("No rows contain all required standard signal values.")
    selected_rows = valid_rows[:limit] if limit else valid_rows
    active_rag = rag or RagService.from_env()
    analyzed: list[dict[str, Any]] = []
    standardized_events: list[dict[str, Any]] = []
    seen_source_ids: set[str] = set()
    total = len(selected_rows)

    try:
        analyzer_parameters = inspect.signature(analyze_func).parameters
    except (TypeError, ValueError):
        analyzer_parameters = {}
    supports_examples = "retrieved_examples" in analyzer_parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in analyzer_parameters.values()
    )

    def analyze_one(
        index_and_row: tuple[int, dict[str, str]],
    ) -> tuple[int, dict[str, str], dict[str, Any], RagDecision]:
        index, row = index_and_row
        analysis_text = build_analysis_text(row)
        if not analysis_text:
            raise ValueError(f"Row {index} has no text and no readable OCR text.")
        row["analysis_text"] = analysis_text
        decision = active_rag.route(analysis_text)
        if decision.route == "direct":
            result = active_rag.direct_result(decision)
        elif decision.route == "dynamic_few_shot" and supports_examples:
            result = analyze_func(
                host,
                model,
                analysis_text,
                build_context(row),
                retrieved_examples=decision.examples,
            )
        else:
            result = analyze_func(host, model, analysis_text, build_context(row))
        return index, row, result, decision

    indexed_rows = list(enumerate(selected_rows, start=1))
    worker_count = max_workers if max_workers is not None else (1 if is_ollama_provider() else remote_worker_count())
    completed = 0
    if worker_count <= 1 or total <= 1:
        analyzed_results = []
        for item in indexed_rows:
            analyzed_results.append(analyze_one(item))
            completed += 1
            if progress:
                progress(completed, total)
    else:
        analyzed_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_index = {
                executor.submit(analyze_one, item): item[0]
                for item in indexed_rows
            }
            for future in concurrent.futures.as_completed(future_to_index):
                analyzed_results.append(future.result())
                completed += 1
                if progress:
                    progress(completed, total)
        analyzed_results.sort(key=lambda item: item[0])

    rag_routes: Counter[str] = Counter()
    pseudo_candidates = 0
    for index, row, result, decision in analyzed_results:
        rag_routes[decision.route] += 1
        if active_rag.consider_pseudo_real(
            row["analysis_text"],
            result,
            decision.matches,
            language=clean_cell(row.get("language")) or "unknown",
        ):
            pseudo_candidates += 1
        label = sentiment_label_from_specs(
            emotion_specs_from_result(result),
            result.get("sentiment_label") or result.get("label", "unknown"),
        )
        item = {
            **{key: value for key, value in row.items() if not key.startswith("__")},
            "row_number": index,
            "label": label,
            "topic": normalize_topic(result.get("topic")),
            "journey_stage": normalize_standard_stage(result.get("journey_stage")),
        }
        analyzed.append(item)
        event = build_standardized_event(row, result, index)
        source_id = str(event["source_id"])
        status = normalize_review_status(row.get("review_status") or result.get("review_status"))
        if source_id in seen_source_ids:
            pass
        elif status != "review_pass":
            pass
        else:
            seen_source_ids.add(source_id)
            standardized_events.append(event)

    pseudo_added = active_rag.flush_pending()

    report = build_voc_report(analyzed, source_total=len(rows))
    report["standardized_events"] = standardized_events
    report["standardized_events_json"] = standardized_events
    report["standardized_events_full"] = standardized_events
    report["standardized_summary"] = {
        "output_events": len(standardized_events),
        "processed_rows": len(selected_rows),
        "skipped_rows": len(selected_rows) - len(standardized_events),
        "output_format": "jsonl",
    }
    report["rag_summary"] = {
        "enabled": active_rag.enabled,
        "case_store": str(active_rag.case_store),
        "case_count": len(active_rag.cases),
        "routes": dict(rag_routes),
        "pseudo_candidates": pseudo_candidates,
        "pseudo_cases_added": pseudo_added,
    }
    return report


def count_field(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(Counter(clean_cell(row.get(field)) or "unknown" for row in rows))


def top_items(counter: Counter, limit: int = 8) -> list[dict[str, Any]]:
    return [{"name": key, "count": value} for key, value in counter.most_common(limit)]


def build_voc_report(rows: list[dict[str, Any]], source_total: int | None = None) -> dict[str, Any]:
    total = len(rows)
    label_counts = count_field(rows, "label")
    topic_counts = count_field(rows, "topic")
    stage_counts = count_field(rows, "journey_stage")
    negative_count = (
        label_counts.get("negative", 0)
        + label_counts.get("mixed", 0)
    )
    actionable = [
        row
        for row in rows
        if row.get("label") in {"negative", "mixed"}
    ]

    topic_counter = Counter(clean_cell(row.get("topic")) or "unknown" for row in actionable)
    stage_counter = Counter(clean_cell(row.get("journey_stage")) or "unknown" for row in actionable)
    primary_topic = topic_counter.most_common(1)[0][0] if topic_counter else "unknown"
    primary_stage = stage_counter.most_common(1)[0][0] if stage_counter else "unknown"
    headline = (
        f"{negative_count} comments need follow-up; the main issue is {primary_topic}, "
        f"concentrated in {primary_stage}."
        if total
        else "No VOC comments were analyzed."
    )

    follow_up_rows = actionable[:20]

    return {
        "report_type": "c_end_voc",
        "headline": headline,
        "summary": {
            "total_comments": total,
            "source_total_comments": source_total if source_total is not None else total,
            "negative_or_mixed_count": negative_count,
            "primary_topic": primary_topic,
            "primary_stage": primary_stage,
            "label_counts": label_counts,
            "topic_counts": topic_counts,
            "stage_counts": stage_counts,
        },
        "sentiment_distribution": label_counts,
        "topic_distribution": topic_counts,
        "stage_distribution": stage_counts,
        "follow_up_comments": follow_up_rows,
        "top_topics": top_items(topic_counter),
        "comments": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze customer signals and export standardized emotion events.")
    parser.add_argument("input", nargs="?", help="CSV/XLSX file with standard signal rows.")
    parser.add_argument("--output", help="Optional report JSON output path.")
    parser.add_argument("--standardized-output", help="JSONL output path for downstream standardized events.")
    parser.add_argument("--full-output", help="JSON output path for the same minimal standardized events.")
    parser.add_argument("--limit", type=int, help="Analyze only the first N rows.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="LLM host.")
    parser.add_argument("--model", default=DEFAULT_TEXT_MODEL, help="LLM model.")
    parser.add_argument(
        "--max-workers",
        type=int,
        help="Parallel LLM calls. Defaults to 4 for remote APIs and 1 for Ollama. Can also use VOC_MAX_WORKERS.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.input:
        parser.print_help()
        return 1
    input_path = Path(args.input)
    rows = read_voc_rows(input_path)
    validation = validate_voc_rows(rows)
    if not validation["can_analyze"]:
        raise ValueError(f"Missing required columns: {', '.join(validation['missing_columns'])}")

    total_rows = min(len(rows), args.limit) if args.limit else len(rows)
    print(f"Analyzing {total_rows} valid row(s)...", flush=True)

    def print_progress(done: int, total_count: int) -> None:
        print(f"Analyzed {done}/{total_count}", flush=True)

    started_at = time.perf_counter()
    report = analyze_voc_rows(
        rows,
        host=args.host,
        model=args.model,
        limit=args.limit,
        progress=print_progress,
        max_workers=args.max_workers,
    )
    elapsed_seconds = time.perf_counter() - started_at
    print(f"Analysis finished in {elapsed_seconds:.2f} seconds.", flush=True)
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.standardized_output:
        write_jsonl_events(Path(args.standardized_output), report.get("standardized_events", []))
    if args.full_output:
        Path(args.full_output).write_text(json.dumps(report.get("standardized_events_json", []), ensure_ascii=False, indent=2), encoding="utf-8")
    if not any([args.output, args.standardized_output, args.full_output]):
        print(json.dumps(report.get("standardized_events", []), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
