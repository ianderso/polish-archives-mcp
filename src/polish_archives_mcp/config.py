"""Configuration from environment variables.

==================================  ============================================
``POLISH_ARCHIVES_CACHE_DIR``       Directory for the on-disk response cache.
``POLISH_ARCHIVES_TIMEOUT``         HTTP timeout in seconds for one request.
``POLISH_ARCHIVES_MIN_INTERVAL``    Least seconds between two requests to one
                                    host. Never below 4.
``POLISH_ARCHIVES_CONTACT``         An email address or URL appended to the
                                    User-Agent, so a site can reach whoever
                                    runs this server.
``POLISH_ARCHIVES_DOWNLOAD_DIR``    When set, the folder every ``swa_scan``
                                    destination must lie inside.
==================================  ============================================

None is required: the three indexes and the photo host need no key and no
account. A ``.env`` file in the working directory supplies any of these that
the environment does not. The download folder is the operator's to set, never
a model's: it narrows where the server writes.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

#: Least seconds between requests to one host, unless configured otherwise.
#: The script this server grew from paused four seconds between pages.
DEFAULT_MIN_INTERVAL = 4.0

#: The floor on POLISH_ARCHIVES_MIN_INTERVAL. Each site is a volunteer
#: society's or an archive's server; nothing here should hit one faster.
MIN_INTERVAL_FLOOR = 4.0


class ConfigError(RuntimeError):
    """Raised when a setting is present but unusable."""


@dataclass
class Config:
    """Resolved server configuration.

    Attributes
    ----------
    cache_dir : Path
        Directory holding cached responses.
    timeout : float
        HTTP timeout in seconds for one request. Scan downloads get longer.
    min_interval : float
        Least seconds between the start of one request to a host and the next.
    contact : str
        Appended to the User-Agent when set. Empty by default.
    download_dir : Path or None
        When set, ``swa_scan`` writes only inside this folder.
    """

    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "polish-archives-mcp")
    timeout: float = 60.0
    min_interval: float = DEFAULT_MIN_INTERVAL
    contact: str = ""
    download_dir: Path | None = None


def load_config() -> Config:
    """Load configuration from the environment.

    A ``.env`` file in the working directory is read if present; real
    environment variables win. Only the working directory is consulted.
    ``load_dotenv()`` with no path searches upward from the *calling
    module's* location instead, which for an installed package is
    ``site-packages``.

    Raises
    ------
    ConfigError
        If a number is unusable or a contact string could break the header.
        The server loads its configuration on the first tool call, so this
        surfaces there as a ``not_configured`` result rather than as a crash.
    """
    load_dotenv(Path.cwd() / ".env")

    cfg = Config()
    if raw := os.environ.get("POLISH_ARCHIVES_CACHE_DIR"):
        cfg.cache_dir = Path(raw).expanduser()
    if raw := os.environ.get("POLISH_ARCHIVES_TIMEOUT"):
        cfg.timeout = _positive("POLISH_ARCHIVES_TIMEOUT", raw)
    if raw := os.environ.get("POLISH_ARCHIVES_MIN_INTERVAL"):
        value = _positive("POLISH_ARCHIVES_MIN_INTERVAL", raw)
        if value < MIN_INTERVAL_FLOOR:
            raise ConfigError(
                f"POLISH_ARCHIVES_MIN_INTERVAL must be at least {MIN_INTERVAL_FLOOR:g}; "
                f"got {raw!r}."
            )
        cfg.min_interval = value
    if raw := os.environ.get("POLISH_ARCHIVES_CONTACT"):
        cfg.contact = _contact(raw)
    if raw := os.environ.get("POLISH_ARCHIVES_DOWNLOAD_DIR"):
        cfg.download_dir = _download_dir(raw)
    return cfg


def _positive(name: str, raw: str) -> float:
    """Parse one numeric setting, naming the variable if it is unusable."""
    try:
        value = float(raw.strip())
    except ValueError:
        raise ConfigError(f"{name} must be a number; got {raw!r}.") from None
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"{name} must be greater than zero; got {raw!r}.")
    return value


def _contact(raw: str) -> str:
    """Keep a contact string safe to place inside a User-Agent header.

    A newline would let the value inject a second header, and parentheses
    would close the comment it sits in.
    """
    text = raw.strip()
    if any(ch in text for ch in "\r\n()") or not text.isprintable():
        raise ConfigError(
            "POLISH_ARCHIVES_CONTACT must be one line with no parentheses, such as an "
            f"email address or a URL; got {raw!r}."
        )
    return text


def _download_dir(raw: str) -> Path:
    """The folder ``swa_scan`` is confined to: absolute, and already there.

    A folder that does not exist yet is refused rather than created, so a
    typing slip cannot confine downloads to somewhere unintended.
    """
    path = Path(raw.strip()).expanduser()
    if not path.is_absolute():
        raise ConfigError(f"POLISH_ARCHIVES_DOWNLOAD_DIR must be an absolute path; got {raw!r}.")
    if not path.is_dir():
        raise ConfigError(
            f"POLISH_ARCHIVES_DOWNLOAD_DIR must be a folder that exists; got {raw!r}."
        )
    return path
