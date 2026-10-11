"""Polite, cached async HTTP for the Polish indexes and the scan host.

Every request goes to a volunteer society's server or to the state archives'
image host, so the client is a careful guest:

* **Four hosts, fixed.** A request hook refuses any request that is not https
  to one of :data:`HOSTS`, whatever built the address, including an address
  taken from a response. Szukaj w Archiwach's own pages
  (``www.szukajwarchiwach.gov.pl``) are not among them: they sit behind a bot
  check and are opened by a person, in a browser.
* **No redirects off a host.** Redirects are followed by hand, only to the
  same host over https; anything else is reported, never followed.
* **Bounded answers.** A page over ``MAX_TEXT_BYTES`` or a scan over
  ``MAX_IMAGE_BYTES`` is refused as it streams in, before it is all read.
* **One request at a time per host, at least ``min_interval`` apart** (four
  seconds by default, never less), and longer where a site asks for it:
  :data:`HOST_FLOORS`. Hosts are independent of one another.
* **Identical concurrent calls share one request.**
* **Answers are cached on disk,** keyed by the request (address and form
  body), for as many days as the caller says: the coverage list for 7,
  searches for 1, the Poznań Project's name groups and archive pages for
  longer. A failure is never cached, and an unreadable entry is fetched again.
* **A 429, a 5xx or a dropped connection gets one retry,** honouring
  ``Retry-After`` up to 30 seconds. A timeout is not retried: a server that
  took that long is struggling already.
* **An honest User-Agent** naming the package, its version and its home.
"""

from __future__ import annotations

import asyncio
import email.utils
import hashlib
import json
import logging
import os
import random
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

import httpx

from . import __version__

logger = logging.getLogger("polish_archives_mcp.client")

#: Where the project lives; named in the User-Agent so a site can see who calls.
PROJECT_URL = "https://github.com/ianderso/polish-archives-mcp"

#: The only hosts a request may reach.
GENETEKA = "geneteka.genealodzy.pl"
POZNAN = "poznan-project.psnc.pl"
BASIA = "www.basia.famula.pl"
PHOTOS = "photos.szukajwarchiwach.gov.pl"
HOSTS = frozenset({GENETEKA, POZNAN, BASIA, PHOTOS})

#: Szukaj w Archiwach's own site: unit and fonds pages, behind Imperva. Never
#: fetched; named so a refusal can say why.
SWA_SITE = "www.szukajwarchiwach.gov.pl"

#: Least seconds between two requests to a host, where a site asks for more
#: than the server's own interval. BaSIA's robots.txt gives a crawl delay of
#: 10 seconds and says each search is a costly database query; one search is
#: one request, so honouring it costs a caller almost nothing.
HOST_FLOORS: Mapping[str, float] = {BASIA: 10.0}

#: Longest wait honoured from a ``Retry-After`` header, in seconds.
RETRY_AFTER_CAP = 30.0

#: Redirect hops followed within one host.
MAX_REDIRECTS = 3

#: A page larger than this is refused. Geneteka's coverage list, the largest
#: answer read, was 2.5 MB on 2026-10-11.
MAX_TEXT_BYTES = 10_000_000

#: A scan larger than this is not written. Full-size scans (3500 px, JPEG)
#: were 0.6 to 5 MB.
MAX_IMAGE_BYTES = 60_000_000

#: Read timeout for a scan download.
DOWNLOAD_TIMEOUT = 180.0

_DAY = 86_400.0

#: Text that marks a page as an Imperva (Incapsula) bot check.
_IMPERVA_MARKERS = ("_Incapsula_Resource", "Incapsula incident ID")


class SiteError(RuntimeError):
    """A request a site refused, or one that could not be completed.

    ``code`` says what kind of failure it was: ``no_response`` and
    ``timeout`` (``status`` 0), ``http_error``, ``rate_limited``,
    ``redirected`` (``location`` set), ``challenge`` (a bot check),
    ``too_large``, ``not_an_image``, ``scan_unavailable``, or
    ``unexpected_answer`` when a site's page no longer has the shape the
    server reads.
    """

    def __init__(
        self, code: str, detail: str, *, status: int = 0, url: str = "", location: str = ""
    ):
        """Record what failed and where."""
        self.code = code
        self.detail = detail
        self.status = status
        self.url = url
        self.location = location
        super().__init__(f"{url} -> {code} {status or ''}: {detail}".strip())


class HostNotAllowed(RuntimeError):
    """Raised when a request is aimed at a host outside :data:`HOSTS`."""


def user_agent(contact: str = "") -> str:
    """The User-Agent sent with every request, naming this project."""
    extra = f"; {contact}" if contact else ""
    return f"polish-archives-mcp/{__version__} (+{PROJECT_URL}{extra})"


def is_jpeg(head: bytes) -> bool:
    """True if the bytes begin as a JPEG does. Trusted over the Content-Type."""
    return head.startswith(b"\xff\xd8\xff")


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """A JPEG's (width, height) from its frame header, or None if none is found."""
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = int.from_bytes(data[i + 2 : i + 4], "big")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height = int.from_bytes(data[i + 5 : i + 7], "big")
            width = int.from_bytes(data[i + 7 : i + 9], "big")
            return width, height
        if length < 2:
            return None
        i += 2 + length
    return None


class ArchivesHttp:
    """Cached, paced async HTTP for the four hosts in :data:`HOSTS`.

    Parameters
    ----------
    cache_dir : Path
        Directory for cached responses. Created on first write.
    timeout : float, optional
        Per-request timeout in seconds.
    min_interval : float, optional
        Least time between the start of one request to a host and the next.
    contact : str, optional
        Appended to the User-Agent.
    retries : int, optional
        Further attempts after a 429, a 5xx or a dropped connection.
    backoff : float, optional
        Base of the wait between attempts when no ``Retry-After`` is given.
    host_floors : mapping, optional
        Longer intervals for particular hosts. Tests pass ``{}``.
    max_text_bytes : int, optional
        Largest page read.
    transport : httpx.AsyncBaseTransport, optional
        For tests.
    """

    def __init__(
        self,
        cache_dir: Path,
        *,
        timeout: float = 60.0,
        min_interval: float = 4.0,
        contact: str = "",
        retries: int = 1,
        backoff: float = 1.0,
        host_floors: Mapping[str, float] = HOST_FLOORS,
        max_text_bytes: int = MAX_TEXT_BYTES,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._cache_dir = cache_dir
        self._timeout = timeout
        self._min_interval = min_interval
        self._host_floors = dict(host_floors)
        self._retries = retries
        self._backoff = backoff
        self._clock = clock
        self._sleep = sleep
        self._max_text_bytes = max_text_bytes
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": user_agent(contact)},
            event_hooks={"request": [self._only_known_hosts]},
            follow_redirects=False,
            transport=transport,
        )
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._host_last: dict[str, float] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self._live_calls = 0
        self._cache_hits = 0
        self._shared_waits = 0
        self._hosts_called: dict[str, int] = {}
        self._last_error: dict | None = None

    # ------------------------------------------------------------------ #
    # Counters
    # ------------------------------------------------------------------ #
    @property
    def live_calls(self) -> int:
        """int: Requests sent this session, retries and downloads included."""
        return self._live_calls

    @property
    def cache_hits(self) -> int:
        """int: Answers served from the disk cache this session."""
        return self._cache_hits

    @property
    def shared_waits(self) -> int:
        """int: Calls answered by joining an identical request already in flight."""
        return self._shared_waits

    @property
    def hosts_called(self) -> dict[str, int]:
        """dict: Live requests this session, by host."""
        return dict(self._hosts_called)

    @property
    def last_error(self) -> dict | None:
        """dict or None: The most recent failure this session."""
        return self._last_error

    @property
    def cache_dir(self) -> Path:
        """Path: Where answers are cached."""
        return self._cache_dir

    def interval_for(self, host: str) -> float:
        """Least seconds between two requests to ``host``."""
        return max(self._min_interval, self._host_floors.get(host, 0.0))

    # ------------------------------------------------------------------ #
    # Lifecycle and the host allowlist
    # ------------------------------------------------------------------ #
    async def aclose(self) -> None:
        """Close the HTTP transport."""
        await self._http.aclose()

    async def __aenter__(self) -> ArchivesHttp:
        """Return the client."""
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Close the transport."""
        await self.aclose()

    async def _only_known_hosts(self, request: httpx.Request) -> None:
        """Refuse any request that is not https to one of the four hosts."""
        host = request.url.host.lower()
        if request.url.scheme != "https" or host not in HOSTS:
            if host == SWA_SITE:
                raise HostNotAllowed(
                    "refusing a request to www.szukajwarchiwach.gov.pl: its unit and fonds "
                    "pages sit behind a bot check and are opened by a person in a browser"
                )
            raise HostNotAllowed(
                f"refusing a request to {host!r}: this server reaches only "
                f"{', '.join(sorted(HOSTS))}"
            )

    # ------------------------------------------------------------------ #
    # Requests
    # ------------------------------------------------------------------ #
    async def get_text(
        self,
        url: str,
        *,
        ttl_days: float,
        refresh: bool = False,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        """Fetch one page as text (a POST when ``data`` is given); cached and shared.

        Parameters
        ----------
        url : str
            The address, on one of :data:`HOSTS`.
        ttl_days : float
            How long a cached answer is served.
        refresh : bool, optional
            Skip the cached copy and ask again; the answer replaces it.
        data : mapping, optional
            A form body. The request is a POST, and the body is part of the
            cache key.
        headers : mapping, optional
            Extra request headers (a Referer, say). Not part of the cache key.

        Raises
        ------
        SiteError
            For any failure. Nothing is cached.
        HostNotAllowed
            If the address is not https on one of the four hosts.
        """
        key = _key(url, data)
        if not refresh:
            cached = self._cache_get(key, ttl_days * _DAY)
            if cached is not None:
                self._cache_hits += 1
                return cached
        text = await self._shared(key, lambda: self._fetch_text(url, data, headers))
        self._cache_put(key, text)
        return text

    def cached_at(self, url: str, data: Mapping[str, str] | None = None) -> float | None:
        """When the cached answer for this request was stored (epoch seconds), or None."""
        try:
            entry = json.loads(self._cache_path(_key(url, data)).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            return None
        stored = entry.get("stored") if isinstance(entry, dict) else None
        return float(stored) if isinstance(stored, int | float) else None

    async def _fetch_text(
        self, url: str, data: Mapping[str, str] | None, headers: Mapping[str, str] | None
    ) -> str:
        response = await self._send(url, limit=self._max_text_bytes, data=data, headers=headers)
        text = response.text
        if any(marker in text[:20_000] for marker in _IMPERVA_MARKERS):
            error = SiteError(
                "challenge",
                "the site answered with a bot check (Imperva); it must be opened in a browser",
                status=response.status_code,
                url=url,
            )
            self._note(error)
            raise error
        return text

    async def _send(
        self,
        url: str,
        *,
        limit: int,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> httpx.Response:
        """One request, paced, retried and redirected by hand; the final response.

        Raises
        ------
        SiteError
            On a status of 400 or more, no response, a bot challenge, a
            redirect to another host, or a body over ``limit`` bytes.
        HostNotAllowed
            If a host is not one of the four. Never retried.
        """
        attempt = 0
        while True:
            try:
                response = await self._follow(
                    url, limit=limit, data=data, headers=headers, timeout=timeout
                )
            except SiteError as exc:
                error = exc
                response = None
            else:
                if response.status_code < 400:
                    return response
                error = _http_error(response, url)
            retryable = error.code in ("no_response", "rate_limited") or error.status >= 500
            if not retryable or attempt >= self._retries:
                self._note(error)
                raise error
            attempt += 1
            wait = _retry_after(response)
            if wait is None:
                wait = self._backoff * 2 ** (attempt - 1) + random.uniform(0, self._backoff / 2)
            wait = min(wait, RETRY_AFTER_CAP)
            logger.info("%s -> %s; retry %d in %.1fs", url, error.code, attempt, wait)
            await self._sleep(wait)

    async def _follow(self, url: str, *, limit: int, **kwargs: Any) -> httpx.Response:
        """Send, following redirects only within the same host over https."""
        host = (urlsplit(url).hostname or "").lower()
        for _ in range(MAX_REDIRECTS + 1):
            response = await self._paced(url, limit=limit, **kwargs)
            if response.status_code not in (301, 302, 303, 307, 308):
                return response
            location = urljoin(url, response.headers.get("location", ""))
            target = urlsplit(location)
            if target.scheme != "https" or (target.hostname or "").lower() != host:
                raise SiteError(
                    "redirected",
                    f"the site redirects this request to {location}",
                    status=response.status_code,
                    url=url,
                    location=location,
                )
            if response.status_code == 303:
                kwargs["data"] = None
            url = location
        raise SiteError("redirected", "too many redirects", url=url)

    async def _paced(
        self,
        url: str,
        *,
        limit: int,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> httpx.Response:
        """Send one request once this host's turn and interval have come.

        The body is streamed and refused as soon as it passes ``limit``
        bytes, so neither a declared nor an undeclared size can make the
        server read more.
        """
        host = (urlsplit(url).hostname or "").lower()
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        options: dict[str, Any] = {}
        if headers:
            options["headers"] = dict(headers)
        if timeout is not None:
            options["timeout"] = timeout
        method = "GET"
        if data is not None:
            method = "POST"
            options["data"] = dict(data)
        async with lock:
            last = self._host_last.get(host)
            if last is not None:
                wait = self.interval_for(host) - (self._clock() - last)
                if wait > 0:
                    await self._sleep(wait)
            self._host_last[host] = self._clock()
            self._live_calls += 1
            self._hosts_called[host] = self._hosts_called.get(host, 0) + 1
            try:
                async with self._http.stream(method, url, **options) as response:
                    body = await _read_capped(response, limit, url)
                return _with_body(response, body)
            except httpx.TimeoutException as exc:
                raise SiteError("timeout", _transport_text(exc), url=url) from None
            except httpx.TransportError as exc:
                raise SiteError("no_response", _transport_text(exc), url=url) from None

    async def fetch_image(self, url: str, *, max_bytes: int = MAX_IMAGE_BYTES) -> bytes:
        """Fetch an image's bytes, uncached. Raises SiteError if it is not a JPEG."""
        response = await self._send(
            url, limit=max_bytes, timeout=httpx.Timeout(self._timeout, read=DOWNLOAD_TIMEOUT)
        )
        body = response.content
        if not is_jpeg(body[:4]):
            text = body[:20_000].decode("utf-8", "replace")
            if any(marker in text for marker in _IMPERVA_MARKERS):
                error = SiteError(
                    "challenge",
                    "the photo host answered with a bot check (Imperva); open the unit page "
                    "in a browser instead",
                    status=response.status_code,
                    url=url,
                )
            else:
                error = SiteError(
                    "not_an_image",
                    "the photo host answered with something that is not a JPEG "
                    f"({response.headers.get('content-type', 'no content type')}); "
                    "nothing was saved",
                    status=response.status_code,
                    url=url,
                )
            self._note(error)
            raise error
        return body

    # ------------------------------------------------------------------ #
    # Shared machinery
    # ------------------------------------------------------------------ #
    async def _shared(self, key: str, make: Callable[[], Awaitable[Any]]) -> Any:
        """Run ``make`` once for concurrent callers asking the same thing."""
        if (pending := self._inflight.get(key)) is not None:
            self._shared_waits += 1
            return await asyncio.shield(pending)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            data = await make()
        except asyncio.CancelledError:
            future.cancel()
            raise
        except Exception as exc:
            future.set_exception(exc)
            # Mark it retrieved: a failure nobody else was waiting on must
            # not be logged as "exception was never retrieved".
            future.exception()
            raise
        else:
            future.set_result(data)
            return data
        finally:
            self._inflight.pop(key, None)

    def _note(self, error: SiteError) -> None:
        self._last_error = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "error": error.code,
            "status": error.status or None,
            "detail": error.detail[:300],
            "request": error.url[:300],
        }

    def note_error(self, error: SiteError) -> None:
        """Record a failure found after the answer arrived (an unreadable page, say)."""
        self._note(error)

    # ------------------------------------------------------------------ #
    # Cache
    # ------------------------------------------------------------------ #
    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    def _cache_get(self, key: str, ttl: float) -> Any:
        """Return a cached answer, or None if absent, expired or unreadable."""
        path = self._cache_path(key)
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError, ValueError):
            # A truncated or hand-edited entry is a re-fetch, not a crash.
            logger.warning("discarding unreadable cache entry %s", path.name)
            return None
        if not isinstance(entry, dict) or "data" not in entry:
            return None
        stored = entry.get("stored")
        if not isinstance(stored, int | float) or time.time() - stored > ttl:
            return None
        return entry["data"]

    def _cache_put(self, key: str, data: Any) -> None:
        try:
            _write_atomically(
                self._cache_path(key), json.dumps({"stored": time.time(), "data": data})
            )
        except OSError:
            # A cache that cannot be written costs speed, not correctness.
            logger.warning("could not write the response cache in %s", self._cache_dir)

    def forget(self, url: str, data: Mapping[str, str] | None = None) -> None:
        """Drop one cached answer, so a page found unreadable is asked for again."""
        self._cache_path(_key(url, data)).unlink(missing_ok=True)


async def _read_capped(response: httpx.Response, limit: int, url: str) -> bytes:
    """Read a streamed body, refusing it once it passes ``limit`` bytes."""
    too_large = SiteError(
        "too_large",
        f"the answer is over {limit / 1_000_000:g} MB, more than this server reads",
        status=response.status_code,
        url=url,
    )
    declared = response.headers.get("content-length", "").strip()
    if declared.isdigit() and int(declared) > limit:
        raise too_large
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > limit:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)


def _with_body(response: httpx.Response, body: bytes) -> httpx.Response:
    """A complete response carrying ``body``, already decoded, in place of the stream."""
    spent = {"content-encoding", "content-length", "transfer-encoding"}
    return httpx.Response(
        response.status_code,
        headers=[(k, v) for k, v in response.headers.multi_items() if k.lower() not in spent],
        content=body,
        request=response.request,
        extensions=response.extensions,
    )


def _http_error(response: httpx.Response, url: str) -> SiteError:
    """Classify a 4xx or 5xx answer."""
    status = response.status_code
    text = response.text
    if response.headers.get("cf-mitigated", "").lower() == "challenge":
        return SiteError(
            "challenge",
            "the site answered with a bot check (Cloudflare); it must be opened in a browser",
            status=status,
            url=url,
        )
    if any(marker in text[:20_000] for marker in _IMPERVA_MARKERS):
        return SiteError(
            "challenge",
            "the site answered with a bot check (Imperva); it must be opened in a browser",
            status=status,
            url=url,
        )
    if status == 429:
        return SiteError(
            "rate_limited", "the site asked for fewer requests", status=status, url=url
        )
    stripped = text.strip()
    if stripped[:1] == "<":
        detail = response.reason_phrase or "an HTML error page"
    else:
        detail = " ".join(stripped.split())[:300] or response.reason_phrase
    return SiteError("http_error", detail, status=status, url=url)


def _transport_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}".rstrip(": ")


def _retry_after(response: httpx.Response | None) -> float | None:
    """Seconds a ``Retry-After`` header asks for, or None if absent or unreadable."""
    if response is None:
        return None
    raw = (response.headers.get("retry-after") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def _key(url: str, data: Mapping[str, str] | None = None) -> str:
    body = "" if data is None else "\n" + urlencode(sorted(data.items()))
    return hashlib.sha256((url + body).encode()).hexdigest()[:24]


def _write_atomically(path: Path, text: str) -> None:
    """Write a file so a reader never sees it half-written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
