from __future__ import annotations

import hashlib
from typing import Optional
from sqlalchemy.orm import Session
from app.models.lead import Lead
from app.pipeline.normalize import canonicalize_url


def compute_fingerprint(
    url: str,
    title: str = "",
    published_at: Optional[object] = None,
) -> str:
    """
    Generate a deterministic URL-only fingerprint.

    ``title`` and ``published_at`` remain optional for backwards compatibility
    with old callers and stored data migrations. They are intentionally ignored:
    one source URL represents one lead regardless of title/date variations.
    """
    clean_url = canonicalize_url(url)
    return hashlib.sha256(clean_url.encode("utf-8")).hexdigest()


def is_duplicate(db: Session, url: str) -> bool:
    """Check for an existing lead using only its canonical source URL."""
    clean_url = canonicalize_url(url)
    return db.query(Lead.id).filter(Lead.source_url == clean_url).first() is not None


def get_existing_lead(db: Session, url: str) -> Optional[Lead]:
    """Retrieve an existing lead using only its canonical source URL."""
    clean_url = canonicalize_url(url)
    return db.query(Lead).filter(Lead.source_url == clean_url).first()
