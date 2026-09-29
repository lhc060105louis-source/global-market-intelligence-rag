from dataclasses import dataclass, field
import os


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_key: str
    adapter: str
    fake_mode: str
    demo_mode: str = "off"
    actor_api_keys: dict[str, str] = field(default_factory=dict)
    auto_sync_on_ingest: bool = True
    maxkb_base_url: str = "http://127.0.0.1:8080"
    maxkb_api_token: str = ""
    maxkb_admin_username: str = ""
    maxkb_admin_password: str = ""
    maxkb_workspace_id: str = ""
    maxkb_knowledge_bases: dict[str, str] | None = None
    maxkb_applications: dict[str, str] | None = None
    maxkb_application_access_tokens: dict[str, str] | None = None
    maxkb_timeout_seconds: float = 45.0
    maxkb_sync_workers: int = 4
    maxkb_sync_batch_size: int = 50
    maxkb_sync_poll_interval_seconds: float = 5.0
    maxkb_sync_max_attempts: int = 3
    maxkb_query_top_k: int = 5
    maxkb_query_similarity: float = 0.6
    maxkb_query_max_context_chars: int = 5000
    rag_query_planner_mode: str = "shadow"
    rag_query_max_retries: int = 1
    rag_query_fallback_top_k: int = 15
    rag_query_fallback_similarity: float = 0.35
    rag_query_deadline_seconds: float = 60.0
    rag_semantic_draft_mode: str = "shadow"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_text_model: str = "qwen2.5:7b"


def get_settings() -> Settings:
    kb = {key: os.getenv(key, "") for key in ("c_current", "c_history", "b_business", "kol")}
    apps = {key: os.getenv(f"MAXKB_APP_{key.upper()}", "") for key in ("c_current", "c_history", "b_business", "kol")}
    apps["cross_domain"] = os.getenv("MAXKB_APP_CROSS_DOMAIN", "")
    app_tokens = {key: os.getenv(f"MAXKB_APP_ACCESS_TOKEN_{key.upper()}", "") for key in ("c_current", "c_history", "b_business", "kol", "cross_domain")}
    actor_api_keys = {
        os.getenv("RAG_HUB_ACTOR_KEY_OPERATOR", ""): "operator",
        os.getenv("RAG_HUB_ACTOR_KEY_SYSTEM", ""): "system",
        os.getenv("RAG_HUB_ACTOR_KEY_DOMAIN_SERVICE", ""): "domain_service",
        os.getenv("RAG_HUB_ACTOR_KEY_SCENARIO_ENGINE", ""): "scenario_engine",
        os.getenv("RAG_HUB_ACTOR_KEY_DEMO_DRIVER", ""): "demo_driver",
    }
    actor_api_keys = {key: value for key, value in actor_api_keys.items() if key}
    primary_key = os.getenv("RAG_HUB_API_KEY", "replace-me")
    actor_api_keys.setdefault(primary_key, "operator")
    return Settings(
        database_url=os.getenv("RAG_HUB_DATABASE_URL", "sqlite:///./data/rag_hub.db"),
        api_key=os.getenv("RAG_HUB_API_KEY", "replace-me"),
        adapter=os.getenv("RAG_HUB_ADAPTER", "fake"),
        fake_mode=os.getenv("RAG_HUB_FAKE_MODE", "success"),
        demo_mode=(os.getenv("RAG_DEMO_MODE", "off") or "off").strip().lower(),
        actor_api_keys=actor_api_keys,
        auto_sync_on_ingest=os.getenv("RAG_HUB_AUTO_SYNC_ON_INGEST", "true").lower() in {"1", "true", "yes", "on"},
        maxkb_base_url=os.getenv("MAXKB_BASE_URL", "http://127.0.0.1:8080").rstrip("/"),
        maxkb_api_token=os.getenv("MAXKB_API_TOKEN", ""),
        maxkb_admin_username=os.getenv("MAXKB_ADMIN_USERNAME", os.getenv("MAXKB_USERNAME", "")),
        maxkb_admin_password=os.getenv("MAXKB_ADMIN_PASSWORD", os.getenv("MAXKB_PASSWORD", "")),
        maxkb_workspace_id=os.getenv("MAXKB_WORKSPACE_ID", ""),
        maxkb_knowledge_bases={k: os.getenv(f"MAXKB_KB_{k.upper()}", "") for k in kb},
        maxkb_applications=apps,
        maxkb_application_access_tokens=app_tokens,
        # This is the timeout for one MaxKB HTTP request.  The total background
        # indexing wait is controlled independently by the poll interval and
        # max-attempts settings below.
        maxkb_timeout_seconds=float(os.getenv("MAXKB_REQUEST_TIMEOUT_SECONDS", "45")),
        maxkb_sync_workers=int(os.getenv("MAXKB_SYNC_WORKERS", "4")),
        maxkb_sync_batch_size=int(os.getenv("MAXKB_SYNC_BATCH_SIZE", "50")),
        maxkb_sync_poll_interval_seconds=float(os.getenv("MAXKB_SYNC_POLL_INTERVAL_SECONDS", "5")),
        maxkb_sync_max_attempts=int(os.getenv("MAXKB_SYNC_MAX_ATTEMPTS", "3")),
        maxkb_query_top_k=int(os.getenv("MAXKB_QUERY_TOP_K", "5")),
        maxkb_query_similarity=float(os.getenv("MAXKB_QUERY_SIMILARITY", "0.6")),
        maxkb_query_max_context_chars=int(os.getenv("MAXKB_QUERY_MAX_CONTEXT_CHARS", "5000")),
        rag_query_planner_mode=(os.getenv("RAG_QUERY_PLANNER_MODE", "shadow") or "shadow").strip().lower(),
        rag_query_max_retries=int(os.getenv("RAG_QUERY_MAX_RETRIES", "1")),
        rag_query_fallback_top_k=int(os.getenv("RAG_QUERY_FALLBACK_TOP_K", "15")),
        rag_query_fallback_similarity=float(os.getenv("RAG_QUERY_FALLBACK_SIMILARITY", "0.35")),
        rag_query_deadline_seconds=float(os.getenv("RAG_QUERY_DEADLINE_SECONDS", "60")),
        rag_semantic_draft_mode=(os.getenv("RAG_SEMANTIC_DRAFT_MODE", "shadow") or "shadow").strip().lower(),
        ollama_base_url=(os.getenv("RAG_HUB_OLLAMA_BASE_URL") or "http://127.0.0.1:11434").strip().rstrip("/"),
        ollama_text_model=(os.getenv("RAG_HUB_OLLAMA_TEXT_MODEL") or "qwen2.5:7b").strip(),
    )
