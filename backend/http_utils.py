"""HTTP helpers shared by all services: retries, rate limits, timeouts,
atomic cached downloads. No service-specific logic lives here."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

import requests

from backend.errors import AuthenticationError, ServiceError

log = logging.getLogger(__name__)

TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}


def request_with_retry(
    service: str,
    method: str,
    url: str,
    *,
    session: requests.Session | None = None,
    max_attempts: int = 6,
    backoff_s: float = 2.0,
    timeout: tuple[float, float] = (20, 300),
    auth_hint: str | None = None,
    on_auth_failure: Callable[[], None] | None = None,
    **kwargs,
) -> requests.Response:
    """Perform an HTTP request, retrying transient failures.

    - 401/403 -> optional single re-auth via `on_auth_failure`, then AuthenticationError
    - 429     -> honours Retry-After
    - 5xx / timeouts / connection errors -> exponential backoff
    """
    sess = session or requests.Session()
    reauthed = False
    last_err: str = ""
    for attempt in range(1, max_attempts + 1):
        try:
            resp = sess.request(method, url, timeout=timeout, **kwargs)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            wait = backoff_s * 2 ** (attempt - 1)
            log.warning("[%s] %s (attempt %d/%d); retrying in %.0fs",
                        service, last_err, attempt, max_attempts, wait)
            time.sleep(wait)
            continue

        if resp.status_code in (401, 403):
            if on_auth_failure and not reauthed:
                log.info("[%s] HTTP %s; refreshing credentials once", service, resp.status_code)
                on_auth_failure()
                reauthed = True
                # caller-provided headers may need refreshing; re-read from session
                continue
            raise AuthenticationError(
                service,
                f"HTTP {resp.status_code} from {url}: {resp.text[:300]}",
                auth_hint or "Check the credential in .env and its permissions.")

        if resp.status_code in TRANSIENT_STATUS:
            retry_after = resp.headers.get("Retry-After")
            try:
                wait = float(retry_after) if retry_after else backoff_s * 2 ** (attempt - 1)
            except ValueError:
                wait = backoff_s * 2 ** (attempt - 1)
            wait = min(wait, 300)
            last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            log.warning("[%s] %s (attempt %d/%d); retrying in %.0fs",
                        service, last_err, attempt, max_attempts, wait)
            time.sleep(wait)
            continue

        if resp.status_code >= 400:
            raise ServiceError(service, f"HTTP {resp.status_code} from {url}: {resp.text[:500]}")
        return resp

    raise ServiceError(service, f"Giving up after {max_attempts} attempts: {last_err}",
                       "The service may be temporarily unavailable; re-run the pipeline later "
                       "(already-downloaded files are cached and will be reused).")


def atomic_write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(content)
    tmp.replace(path)
    return path


def stream_download(service: str, url: str, dest: Path, *, session: requests.Session,
                    validate: Callable[[Path], None], **kwargs) -> Path:
    """Download to `dest` atomically and validate; reuses a valid cached file."""
    if dest.exists():
        try:
            validate(dest)
            log.debug("[%s] cache hit %s", service, dest.name)
            return dest
        except Exception as exc:  # corrupt cache -> re-download
            log.warning("[%s] cached file %s invalid (%s); re-downloading", service, dest.name, exc)
            dest.unlink(missing_ok=True)

    resp = request_with_retry(service, "GET", url, session=session, stream=True, **kwargs)
    ctype = resp.headers.get("Content-Type", "")
    if "text/html" in ctype:
        raise AuthenticationError(
            service, f"Expected a data file from {url} but received an HTML page "
                     "(usually a login redirect).",
            "Your token may be invalid/expired or lack access to this archive.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with tmp.open("wb") as fh:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            fh.write(chunk)
    try:
        validate(tmp)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise ServiceError(service, f"Downloaded file failed validation ({exc}): {url}")
    tmp.replace(dest)
    return dest
