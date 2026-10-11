"""swa_scan: the photo host, the placeholder it serves, and where a scan may be written.

The destination rules are contentdm-mcp's, test for test: a model steered by
text it read must not be able to make the server write somewhere that runs
later.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import httpx
import pytest

from polish_archives_mcp import server
from polish_archives_mcp.client import is_jpeg, jpeg_size

from .conftest import SCAN_HASH, call_tool, fixture, jpeg, photos_site

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PLIST = b'<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict/></plist>\n'
IMPERVA = (
    b'<html><head><META NAME="robots" CONTENT="noindex,nofollow"><script '
    b'src="/_Incapsula_Resource?SWJIYLWA=5074a744e2e3d891814e9a2dace20bd4"></script></head>'
)


def link(path: Path, target: Path) -> None:
    """Make a symbolic link to a folder, or skip where the system will not let a test."""
    try:
        path.symlink_to(target, target_is_directory=True)
    except OSError as exc:  # Windows without the privilege
        pytest.skip(f"cannot make a symbolic link here: {exc}")


def configure(monkeypatch, **changes) -> None:
    """Change the running server's settings, as the operator's environment would."""
    monkeypatch.setattr(
        server.runtime, "config", dataclasses.replace(server.runtime.config, **changes)
    )


# --------------------------------------------------------------------------- #
# The image itself
# --------------------------------------------------------------------------- #
async def test_a_scan_is_written_with_its_size_and_a_citation_note(served, sites, tmp_path):
    route = photos_site(sites)
    target = tmp_path / "scan-1.jpg"
    out = await call_tool("swa_scan", hash=SCAN_HASH, destination=str(target))
    assert out["path"] == str(target.resolve()) and target.read_bytes() == jpeg()
    assert (out["width"], out["height"]) == (3500, 2393)
    assert out["source_url"] == f"https://photos.szukajwarchiwach.gov.pl/{SCAN_HASH}_max"
    assert "Sygnatura" in out["cite_note"]
    assert str(route.calls[0].request.url) == out["source_url"]


@pytest.mark.parametrize(
    "given",
    [
        SCAN_HASH.upper(),
        f"{SCAN_HASH}_max",
        f"https://photos.szukajwarchiwach.gov.pl/{SCAN_HASH}_max",
        f"https://photos.szukajwarchiwach.gov.pl/{SCAN_HASH}",
    ],
)
async def test_a_hash_may_come_with_its_suffix_or_address(served, sites, tmp_path, given):
    photos_site(sites)
    out = await call_tool("swa_scan", hash=given, destination=str(tmp_path / "s.jpg"))
    assert out["source_url"].endswith(f"/{SCAN_HASH}_max")


@pytest.mark.parametrize(
    "given",
    [
        "abc",
        SCAN_HASH[:-1],
        SCAN_HASH + "0",
        "../../etc/passwd",
        f"https://www.szukajwarchiwach.gov.pl/{SCAN_HASH}_max",
        f"https://attacker.example/{SCAN_HASH}_max",
    ],
)
async def test_anything_but_a_scan_name_is_refused_before_any_request(
    served, sites, tmp_path, given
):
    route = photos_site(sites)
    out = await call_tool("swa_scan", hash=given, destination=str(tmp_path / "s.jpg"))
    assert out["error"] == "invalid_hash" and route.call_count == 0


async def test_the_file_unavailable_picture_is_not_saved_as_a_scan(served, sites, tmp_path):
    photos_site(sites, fixture("swa_placeholder_plik_niedostepny.jpg"))
    target = tmp_path / "scan.jpg"
    out = await call_tool("swa_scan", hash=SCAN_HASH, destination=str(target))
    assert out["error"] == "scan_unavailable" and not target.exists()


async def test_a_small_image_is_not_a_full_scan(served, sites, tmp_path):
    photos_site(sites, jpeg(400, 300))
    target = tmp_path / "scan.jpg"
    out = await call_tool("swa_scan", hash=SCAN_HASH, destination=str(target))
    assert out["error"] == "scan_unavailable" and not target.exists()


@pytest.mark.parametrize(
    ("body", "error"),
    [(PNG, "not_an_image"), (PLIST, "not_an_image"), (b"#!/bin/sh\n", "not_an_image"),
     (IMPERVA, "blocked")],
    ids=["png", "plist", "script", "imperva"],
)  # fmt: skip
async def test_bytes_that_are_not_a_jpeg_leave_no_file(served, sites, tmp_path, body, error):
    photos_site(sites, httpx.Response(200, content=body))
    target = tmp_path / "scan.jpg"
    out = await call_tool("swa_scan", hash=SCAN_HASH, destination=str(target))
    assert out["error"] == error and not target.exists()


async def test_the_photo_host_failing_is_an_outage(served, sites, tmp_path):
    photos_site(sites, httpx.Response(502, text="bad gateway"))
    out = await call_tool("swa_scan", hash=SCAN_HASH, destination=str(tmp_path / "s.jpg"))
    assert out["error"] == "upstream_error"


def test_the_jpeg_helpers_read_a_frame_header():
    assert is_jpeg(jpeg()) and not is_jpeg(PNG)
    assert jpeg_size(jpeg(3500, 2393)) == (3500, 2393)
    assert jpeg_size(fixture("swa_placeholder_plik_niedostepny.jpg")) == (379, 273)
    assert jpeg_size(b"\xff\xd8garbage") is None


# --------------------------------------------------------------------------- #
# Where it may be written
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name", ["agent.plist", "scan.png", "run.sh", "scan", "scan.jpg.command", ".jpg"]
)
async def test_a_destination_without_a_jpeg_suffix_is_refused_before_any_request(
    served, sites, tmp_path, name
):
    route = photos_site(sites)
    out = await call_tool("swa_scan", hash=SCAN_HASH, destination=str(tmp_path / name))
    assert out["error"] == "bad_extension" and route.call_count == 0
    assert not (tmp_path / name).exists()


async def test_an_upper_case_suffix_is_still_a_jpeg(served, sites, tmp_path):
    photos_site(sites)
    out = await call_tool("swa_scan", hash=SCAN_HASH, destination=str(tmp_path / "SCAN.JPEG"))
    assert out["format"] == "jpeg"


async def test_a_relative_destination_is_refused(served, sites):
    out = await call_tool("swa_scan", hash=SCAN_HASH, destination="scan.jpg")
    assert out["error"] == "relative_destination"


async def test_an_existing_file_is_never_overwritten(served, sites, tmp_path):
    route = photos_site(sites)
    target = tmp_path / "scan.jpg"
    target.write_bytes(b"mine")
    out = await call_tool("swa_scan", hash=SCAN_HASH, destination=str(target))
    assert out["error"] == "destination_exists" and target.read_bytes() == b"mine"
    assert route.call_count == 0


async def test_a_missing_folder_is_refused(served, sites, tmp_path):
    out = await call_tool(
        "swa_scan", hash=SCAN_HASH, destination=str(tmp_path / "nowhere" / "s.jpg")
    )
    assert out["error"] == "no_such_directory"


@pytest.mark.parametrize(
    "where",
    [".hidden/scan.jpg", ".scan.jpg", "visible/.git/hooks/scan.jpg", "link-to-hidden/scan.jpg"],
)
async def test_a_hidden_destination_is_refused_before_any_request(served, sites, tmp_path, where):
    route = photos_site(sites)
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible/.git/hooks").mkdir(parents=True)
    link(tmp_path / "link-to-hidden", tmp_path / ".hidden")
    out = await call_tool("swa_scan", hash=SCAN_HASH, destination=str(tmp_path / where))
    assert out["error"] == "hidden_path" and route.call_count == 0
    assert list((tmp_path / ".hidden").iterdir()) == []


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """A home folder with a Library, standing in for the user's."""
    fake = tmp_path / "home"
    (fake / "Library/LaunchAgents").mkdir(parents=True)
    (fake / "Library/Mobile Documents/Genealogy").mkdir(parents=True)
    (fake / "Pictures").mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake))
    return fake


@pytest.mark.parametrize(
    "where", ["Library/LaunchAgents/agent.jpg", "Library/Mobile Documents/Genealogy/scan.jpg"]
)
async def test_nothing_is_written_under_library(served, sites, home, where):
    route = photos_site(sites)
    out = await call_tool("swa_scan", hash=SCAN_HASH, destination=str(home / where))
    assert out["error"] == "protected_location" and route.call_count == 0
    assert "POLISH_ARCHIVES_DOWNLOAD_DIR" in out["message"]


async def test_library_is_recognised_however_it_is_spelt(served, sites, home):
    if not (home / "library").exists():
        pytest.skip("this file system tells upper and lower case apart")
    route = photos_site(sites)
    out = await call_tool(
        "swa_scan", hash=SCAN_HASH, destination=str(home / "library/LaunchAgents/a.jpg")
    )
    assert out["error"] == "protected_location" and route.call_count == 0


async def test_a_link_into_library_is_followed_and_refused(served, sites, home):
    photos_site(sites)
    link(home / "Pictures/agents", home / "Library/LaunchAgents")
    out = await call_tool(
        "swa_scan", hash=SCAN_HASH, destination=str(home / "Pictures/agents/a.jpg")
    )
    assert out["error"] == "protected_location"
    assert list((home / "Library/LaunchAgents").iterdir()) == []


async def test_a_dangling_link_is_never_written_through(served, sites, tmp_path):
    photos_site(sites)
    dangling = tmp_path / "scan.jpg"
    try:
        dangling.symlink_to(tmp_path / "elsewhere.jpg")
    except OSError as exc:
        pytest.skip(f"cannot make a symbolic link here: {exc}")
    out = await call_tool("swa_scan", hash=SCAN_HASH, destination=str(dangling))
    assert out["error"] == "destination_exists" and not (tmp_path / "elsewhere.jpg").exists()


async def test_with_a_download_folder_every_file_lands_inside_it(
    served, sites, tmp_path, monkeypatch
):
    folder = tmp_path / "downloads"
    folder.mkdir()
    configure(monkeypatch, download_dir=folder)
    photos_site(sites)
    out = await call_tool("swa_scan", hash=SCAN_HASH, destination=str(folder / "scan.jpg"))
    assert out["path"] == str((folder / "scan.jpg").resolve())


@pytest.mark.parametrize(
    "where", ["scan.jpg", "downloads/../scan.jpg", "downloads/escape/scan.jpg", "downloadsX/a.jpg"]
)
async def test_with_a_download_folder_nothing_lands_outside_it(
    served, sites, tmp_path, monkeypatch, where
):
    folder = tmp_path / "downloads"
    folder.mkdir()
    (tmp_path / "downloadsX").mkdir()
    link(folder / "escape", tmp_path)
    configure(monkeypatch, download_dir=folder)
    route = photos_site(sites)
    out = await call_tool("swa_scan", hash=SCAN_HASH, destination=str(tmp_path / where))
    assert out["error"] == "outside_download_dir" and route.call_count == 0
    assert str(folder) in out["message"]
    assert not (tmp_path / "scan.jpg").exists()


async def test_a_download_folder_may_itself_be_hidden_or_under_library(
    served, sites, home, monkeypatch
):
    """The operator chose the folder; the rules apply to what a model adds below it."""
    photos_site(sites)
    for folder in (home / ".archive", home / "Library/Mobile Documents/Genealogy"):
        folder.mkdir(exist_ok=True)
        configure(monkeypatch, download_dir=folder)
        out = await call_tool("swa_scan", hash=SCAN_HASH, destination=str(folder / "scan.jpg"))
        assert out["format"] == "jpeg", out
        (folder / ".cache").mkdir()
        out = await call_tool(
            "swa_scan", hash=SCAN_HASH, destination=str(folder / ".cache/scan.jpg")
        )
        assert out["error"] == "hidden_path"


async def test_a_download_folder_does_not_unlock_library_beneath_it(
    served, sites, home, monkeypatch
):
    configure(monkeypatch, download_dir=home)
    route = photos_site(sites)
    out = await call_tool(
        "swa_scan", hash=SCAN_HASH, destination=str(home / "Library/LaunchAgents/a.jpg")
    )
    assert out["error"] == "protected_location" and route.call_count == 0
