from __future__ import annotations

import datetime
import html
import re
import unicodedata
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# Common Vietnamese locations
PROVINCES_VIETNAM = [
    "Hà Nội", "Hồ Chí Minh", "TP.HCM", "TP. Hồ Chí Minh", "Đà Nẵng", "Hải Phòng", "Cần Thơ",
    "An Giang", "Bà Rịa - Vũng Tàu", "Bắc Giang", "Bắc Kạn", "Bạc Liêu", "Bắc Ninh",
    "Bến Tre", "Bình Định", "Bình Dương", "Bình Phước", "Bình Thuận", "Cà Mau",
    "Cao Bằng", "Đắk Lắk", "Đắk Nông", "Điện Biên", "Đồng Nai", "Đồng Tháp",
    "Gia Lai", "Hà Giang", "Hà Nam", "Hà Tĩnh", "Hải Dương", "Hậu Giang",
    "Hòa Bình", "Hưng Yên", "Khánh Hòa", "Kiên Giang", "Kon Tum", "Lai Châu",
    "Lâm Đồng", "Lạng Sơn", "Lào Cai", "Long An", "Nam Định", "Nghệ An",
    "Ninh Bình", "Ninh Thuận", "Phú Thọ", "Phú Yên", "Quảng Bình", "Quảng Nam",
    "Quảng Ngãi", "Quảng Ninh", "Quảng Trị", "Sóc Trăng", "Sơn La", "Tây Ninh",
    "Thái Bình", "Thái Nguyên", "Thanh Hóa", "Thừa Thiên Huế", "Tiền Giang",
    "Trà Vinh", "Tuyên Quang", "Vĩnh Long", "Vĩnh Phúc", "Yên Bái"
]


def normalize_unicode(text: Optional[str]) -> str:
    """Normalize Unicode to NFKC and clean whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_html(raw_html: Optional[str]) -> str:
    """Strip HTML tags, remove navigation/footer boilerplate, and unescape entities safely."""
    if not raw_html:
        return ""
    # Remove script, style, header, footer, nav, aside, noscript, svg, form tags completely
    cleaned = re.sub(r"<(script|style|header|footer|nav|aside|noscript|svg|form).*?>.*?</\1>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
    # Strip html tags
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # Unescape HTML entities
    cleaned = html.unescape(cleaned)
    return normalize_unicode(cleaned)


def canonicalize_url(url: str) -> str:
    """Strip tracking queries (utm_*, ref, fbclid) and normalize url."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        # Filter out common tracking query params
        tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid", "gclid"}
        query_dict = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in tracking_params]
        normalized_query = urlencode(query_dict)
        
        # Remove trailing slash from path if path != '/'
        path = parsed.path.rstrip("/") if len(parsed.path) > 1 else parsed.path
        
        clean_url = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.params,
            normalized_query,
            ""  # drop fragment
        ))
        return clean_url
    except Exception:
        return url.strip()


def parse_vietnamese_currency(text: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    """
    Extract budget value from Vietnamese currency text.
    Returns (normalized_vnd_value, original_budget_text).
    Example:
      '4,5 tỷ VNĐ' -> (4500000000.0, '4,5 tỷ VNĐ')
      '300 triệu đồng' -> (300000000.0, '300 triệu đồng')
      '12.500.000.000 đ' -> (12500000000.0, '12.500.000.000 đ')
    """
    if not text:
        return None, None

    text = normalize_unicode(text)
    
    # 1. Pattern: X tỷ Y triệu (e.g. 4 tỷ 500 triệu)
    combo_pattern = r"(\d+(?:[.,]\d+)?)\s*t[ỷi]\s*(\d+(?:[.,]\d+)?)\s*tri[ệe]u"
    combo_match = re.search(combo_pattern, text, re.IGNORECASE)
    if combo_match:
        ty_part = float(combo_match.group(1).replace(",", "."))
        trieu_part = float(combo_match.group(2).replace(",", "."))
        total = (ty_part * 1_000_000_000) + (trieu_part * 1_000_000)
        return total, combo_match.group(0)

    # 2. Pattern: X tỷ (e.g. 4.5 tỷ, 4,5 tỷ đồng, 4 tỷ VND)
    ty_pattern = r"(\d+(?:[.,]\d+)?)\s*t[ỷi](?:\s*(?:đồng|vnđ|vnd|đ))?"
    ty_match = re.search(ty_pattern, text, re.IGNORECASE)
    if ty_match:
        val_str = ty_match.group(1).replace(",", ".")
        try:
            val = float(val_str) * 1_000_000_000
            return val, ty_match.group(0)
        except ValueError:
            pass

    # 3. Pattern: X triệu (e.g. 800 triệu, 800tr)
    trieu_pattern = r"(\d+(?:[.,]\d+)?)\s*(?:tri[ệe]u|tr)(?:\s*(?:đồng|vnđ|vnd|đ))?"
    trieu_match = re.search(trieu_pattern, text, re.IGNORECASE)
    if trieu_match:
        val_str = trieu_match.group(1).replace(",", ".")
        try:
            val = float(val_str) * 1_000_000
            return val, trieu_match.group(0)
        except ValueError:
            pass

    # 4. Pattern: Exact numbers with dots (e.g. 4.500.000.000 VNĐ or 4,500,000,000 đ)
    exact_pattern = r"(\d{1,3}(?:[.,]\d{3}){2,})(?:\s*(?:đồng|vnđ|vnd|đ))?"
    exact_match = re.search(exact_pattern, text, re.IGNORECASE)
    if exact_match:
        raw_num = exact_match.group(1)
        cleaned_num = re.sub(r"[.,]", "", raw_num)
        try:
            val = float(cleaned_num)
            return val, exact_match.group(0)
        except ValueError:
            pass

    return None, None


def utc_now() -> datetime.datetime:
    """Return timezone-naive UTC datetime compatible with SQLite and Python 3.13+."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def parse_datetime(date_str: Optional[str]) -> Optional[datetime.datetime]:
    """Parse various Vietnamese date formats to UTC datetime object."""
    if not date_str:
        return None

    date_str = normalize_unicode(date_str).lower()

    # ISO-8601 metadata is the most reliable format used by article:published_time
    # and schema.org datePublished. Keep Vietnam wall-clock time when stripping the
    # timezone because the application stores naive local datetimes.
    iso_candidate = date_str.strip()
    try:
        if "t" in iso_candidate:
            iso_value = iso_candidate.replace("z", "+00:00")
            parsed_iso = datetime.datetime.fromisoformat(iso_value)
            return parsed_iso.replace(tzinfo=None)
    except ValueError:
        pass

    # Relative times
    now = utc_now()
    if "vừa xong" in date_str or "vừa đăng" in date_str:
        return now
    
    hours_match = re.search(r"(\d+)\s*giờ\s*trước", date_str)
    if hours_match:
        return now - datetime.timedelta(hours=int(hours_match.group(1)))
        
    days_match = re.search(r"(\d+)\s*ngày\s*trước", date_str)
    if days_match:
        return now - datetime.timedelta(days=int(days_match.group(1)))

    if "hôm qua" in date_str:
        return now - datetime.timedelta(days=1)

    # Date formats
    formats = [
        "%H:%M:%S %d/%m/%Y",
        "%H:%M %d/%m/%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d.%m.%Y",
    ]

    # Clean date string from text prefix like "Ngày đăng: 24/08/2026 09:30"
    cleaned_date = re.sub(r"^(?:ngày|ngày đăng|thời điểm đăng|cập nhật|hạn đóng thầu|đăng lúc)\s*:\s*", "", date_str, flags=re.IGNORECASE)
    cleaned_date = cleaned_date.strip()

    for fmt in formats:
        try:
            return datetime.datetime.strptime(cleaned_date, fmt)
        except ValueError:
            continue

    # Try matching regex DD/MM/YYYY in text
    date_regex = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?:\s+(\d{1,2}):(\d{1,2}))?", cleaned_date)
    if date_regex:
        day, month, year = int(date_regex.group(1)), int(date_regex.group(2)), int(date_regex.group(3))
        hour = int(date_regex.group(4)) if date_regex.group(4) else 0
        minute = int(date_regex.group(5)) if date_regex.group(5) else 0
        try:
            return datetime.datetime(year, month, day, hour, minute)
        except ValueError:
            pass

    return None


def extract_location(text: Optional[str]) -> Optional[str]:
    """Identify Vietnamese province or city in text."""
    if not text:
        return None
    for province in PROVINCES_VIETNAM:
        # Check boundary or direct substring
        if re.search(rf"\b{re.escape(province)}\b", text, re.IGNORECASE):
            # Normalize TP.HCM to Hà Nội / TP.HCM
            if province in ["Hồ Chí Minh", "TP. Hồ Chí Minh"]:
                return "TP.HCM"
            return province
    return None



def normalize_phone_numbers(value: object) -> Optional[str]:
    """Normalize Vietnamese phone numbers to text-safe domestic 0-prefixed form."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    else:
        text = str(value).strip()
    if not text or text.upper() in {"#ERROR!", "ERROR", "N/A", "NULL", "NONE"}:
        return None

    normalized: list[str] = []
    for part in re.split(r"[,;/\n]+|\s+hoặc\s+", text, flags=re.IGNORECASE):
        extension_match = re.search(r"(?:ext\.?|máy\s*lẻ)\s*[:.]?\s*(\d+)", part, re.IGNORECASE)
        extension = extension_match.group(1) if extension_match else None
        if extension_match:
            part = part[:extension_match.start()]
        digits = re.sub(r"\D", "", part)
        if digits.startswith("0084"):
            digits = "0" + digits[4:]
        elif digits.startswith("84"):
            digits = "0" + digits[2:]
        elif not digits.startswith("0"):
            if len(digits) == 9 and digits[0] in "35789":
                digits = "0" + digits
            elif len(digits) == 10 and digits.startswith("2"):
                digits = "0" + digits

        valid_mobile = len(digits) == 10 and re.fullmatch(r"0[35789]\d{8}", digits)
        valid_landline = len(digits) == 11 and re.fullmatch(r"02\d{9}", digits)
        if not (valid_mobile or valid_landline):
            continue
        result = digits + (f" máy lẻ {extension}" if extension else "")
        if result not in normalized:
            normalized.append(result)
    return "; ".join(normalized) or None

def extract_contact_info(text: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract contact name, email, and phone number from text."""
    if not text:
        return None, None, None

    # Email extraction
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    email = email_match.group(0) if email_match else None

    # Phone extraction (Vietnamese mobile & landline patterns)
    phone_match = re.search(r"(?:\+84|0)(?:[35789]\d{8}|2\d{9})", re.sub(r"[\s.-]", "", text))
    phone = normalize_phone_numbers(phone_match.group(0)) if phone_match else None

    # Contact Name heuristic
    name = None
    contact_prefix = re.search(
        r"(?:liên hệ|người liên hệ|đại diện|cán bộ phụ trách)\s*(?:[:\s]\s*(?:ông|bà)?)?\s*([A-ZĐÀ-Ỹa-zđà-ỹ\s]{3,35})(?=[,.\n]|\s+email|\s+sđt|\s+điện thoại|$)",
        text,
        re.IGNORECASE,
    )
    if contact_prefix:
        name = normalize_unicode(contact_prefix.group(1)).strip()
        if len(name) < 3 or len(name) > 40:
            name = None

    return name, email, phone
