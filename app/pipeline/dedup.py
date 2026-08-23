from __future__ import annotations

import datetime
import hashlib
from typing import Optional
from sqlalchemy.orm import Session
from app.models.lead import Lead
from app.pipeline.normalize import canonicalize_url, normalize_unicode


def compute_fingerprint(url: str, title: str, published_at: Optional[datetime.datetime] = None) -> str:
    """
    Generate a deterministic SHA-256 fingerprint for deduplication.
    Format: SHA256(normalized_url + published_date_str + normalized_title)
    """
    clean_url = canonicalize_url(url)
    clean_title = normalize_unicode(title).lower()
    date_str = published_at.strftime("%Y-%m-%d") if published_at else "no_date"

    payload = f"{clean_url}|{date_str}|{clean_title}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_duplicate(db: Session, fingerprint: str) -> bool:
    """Check whether a lead with the given content fingerprint already exists in the database."""
    return db.query(Lead.id).filter(Lead.content_fingerprint == fingerprint).first() is not None


def get_existing_lead(db: Session, fingerprint: str) -> Optional[Lead]:
    """Retrieve existing lead by fingerprint."""
    return db.query(Lead).filter(Lead.content_fingerprint == fingerprint).first()
