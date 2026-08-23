from app.pipeline.normalize import (
    normalize_unicode,
    clean_html,
    parse_vietnamese_currency,
    parse_datetime,
    extract_location,
    extract_contact_info,
    canonicalize_url,
)
from app.pipeline.dedup import (
    compute_fingerprint,
    is_duplicate,
    get_existing_lead,
)
from app.pipeline.extract import (
    AIExtractor,
    ai_extractor,
    prefilter_keywords,
)
from app.pipeline.scoring import (
    AIScoringEngine,
    scoring_engine,
)

# Alias for backwards compatibility
ScoringEngine = AIScoringEngine

__all__ = [
    "normalize_unicode",
    "clean_html",
    "parse_vietnamese_currency",
    "parse_datetime",
    "extract_location",
    "extract_contact_info",
    "canonicalize_url",
    "compute_fingerprint",
    "is_duplicate",
    "get_existing_lead",
    "AIExtractor",
    "ai_extractor",
    "prefilter_keywords",
    "AIScoringEngine",
    "ScoringEngine",
    "scoring_engine",
]
