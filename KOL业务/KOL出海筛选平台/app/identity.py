from urllib.parse import urlsplit

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Kol


def normalized_handle(value: str | None) -> str | None:
    text = (value or "").strip().casefold()
    return text or None


def canonical_channel_url(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlsplit(text)
    host = (parsed.hostname or "").casefold()
    if host in {"www.youtube.com", "m.youtube.com", "youtube.com"}:
        host = "youtube.com"
    path = "/" + "/".join(part for part in parsed.path.split("/") if part)
    return f"https://{host}{path}".casefold() if host else None


def find_existing_kol(session: Session, *, platform: str, platform_account_id: str | None,
                      profile_url: str | None, handle: str | None, exclude_id: int | None = None) -> Kol | None:
    base = [func.lower(Kol.platform) == platform.strip().lower()]
    if exclude_id is not None:
        base.append(Kol.id != exclude_id)
    account_id = (platform_account_id or "").strip()
    if account_id:
        found = session.scalar(select(Kol).where(*base, Kol.platform_account_id == account_id))
        if found:
            return found
    canonical = canonical_channel_url(profile_url)
    if canonical:
        candidates = session.scalars(select(Kol).where(*base, Kol.profile_url.is_not(None)))
        for candidate in candidates:
            if canonical_channel_url(candidate.profile_url) == canonical:
                return candidate
    handle_key = normalized_handle(handle)
    if handle_key:
        return session.scalar(select(Kol).where(*base, func.lower(func.trim(Kol.handle)) == handle_key))
    return None
