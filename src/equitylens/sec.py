"""Cached SEC JSON access with a single paced request stream."""

import hashlib
import json
import re
import time
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

import requests

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_BASE = "https://data.sec.gov/submissions/"
FACTS_BASE = "https://data.sec.gov/api/xbrl/companyfacts/"
RETRYABLE = {429, 500, 502, 503, 504}


class SecError(RuntimeError):
    """An SEC source could not be read or validated."""


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
        temporary.write(content)
    try:
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def retry_after(value: str | None) -> float:
    if not value:
        return 0
    try:
        if value.isdecimal():
            return float(value)
        return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return 0


class SecClient:
    def __init__(
        self, cache: Path, organization: str, email: str, *,
        offline: bool = False, refresh: bool = False, session=None,
        sleep=time.sleep, monotonic=time.monotonic,
    ):
        self.cache = cache
        self.organization = organization.strip()
        self.email = email.strip()
        self.offline = offline
        self.refresh = refresh
        self.session = session if session is not None else requests.Session()
        self.sleep = sleep
        self.monotonic = monotonic
        self.next_request = 0.0
        self.sources = []

    def get(self, url: str, relative_path: str, validate) -> dict:
        path = self.cache / relative_path
        from_cache = path.is_file() and not self.refresh
        if from_cache:
            content = path.read_bytes()
        elif self.offline:
            raise SecError(f"Missing cached source {path}. Save the SEC JSON from {url}.")
        else:
            content = self.download(url)
        try:
            payload = json.loads(content, parse_float=Decimal)
            if not isinstance(payload, dict):
                raise ValueError("expected a JSON object")
            validate(payload)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise SecError(f"Invalid SEC JSON from {url} ({path}): {exc}") from exc
        if not from_cache:
            atomic_write(path, content)
        self.sources.append({
            "url": url,
            "path": relative_path,
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        })
        return payload

    def download(self, url: str, *, accept: str = "application/json") -> bytes:
        email_pattern = r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+"
        identity = f"{self.organization} {self.email}"
        if not self.organization or not re.fullmatch(email_pattern, self.email) \
                or not all(" " <= char <= "~" for char in identity):
            raise SecError(
                "Set SEC_CONTACT_EMAIL privately in .env before live requests, "
                "or use --offline with manually downloaded SEC files."
            )
        headers = {"User-Agent": identity, "Accept": accept}
        for attempt in range(4):
            self.sleep(max(0, self.next_request - self.monotonic()))
            self.next_request = self.monotonic() + 0.6
            delay = 2 ** attempt
            try:
                with self.session.get(
                    url, headers=headers, timeout=(10, 45), allow_redirects=False
                ) as response:
                    if response.status_code == 200:
                        return response.content
                    if response.status_code not in RETRYABLE:
                        raise SecError(
                            f"SEC HTTP {response.status_code} for {url}. "
                            "See docs/sec-download.md for the manual cache procedure."
                        )
                    delay = max(delay, retry_after(response.headers.get("Retry-After")))
                    failure = f"HTTP {response.status_code}"
            except (requests.Timeout, requests.ConnectionError) as exc:
                failure = type(exc).__name__
            except requests.RequestException as exc:
                raise SecError(f"SEC request failed for {url}: {type(exc).__name__}.") from exc
            if attempt == 3 or delay > 60:
                break
            self.sleep(delay)
        raise SecError(f"SEC request failed for {url} ({failure}). See docs/sec-download.md.")
