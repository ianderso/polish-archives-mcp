"""The HTTP client: the host allowlist, pacing, retries, the cache and the size caps."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from polish_archives_mcp import __version__
from polish_archives_mcp.client import (
    BASIA,
    GENETEKA,
    HOST_FLOORS,
    PHOTOS,
    POZNAN,
    HostNotAllowed,
    SiteError,
    user_agent,
)

from .conftest import make_http

G = f"https://{GENETEKA}/rejestry.php?lang=pol"


class FakeClock:
    """A clock that only moves when the client sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(round(seconds, 3))
        self.now += seconds


def test_the_user_agent_names_the_project_and_the_contact():
    assert user_agent() == (
        f"polish-archives-mcp/{__version__} (+https://github.com/ianderso/polish-archives-mcp)"
    )
    assert user_agent("me@example.org").endswith("; me@example.org)")


@pytest.mark.parametrize(
    "url",
    [
        "https://www.szukajwarchiwach.gov.pl/jednostka/-/jednostka/11962370",
        "https://szukajwarchiwach.pl/11/730/0/1/25",
        "https://attacker.example/collect",
        f"http://{GENETEKA}/rejestry.php",
        "https://geneteka.genealodzy.pl.attacker.example/",
    ],
)
async def test_only_the_four_hosts_over_https_are_reached(http, url):
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        route = router.route().mock(return_value=httpx.Response(200, text="x"))
        with pytest.raises(HostNotAllowed):
            await http.get_text(url, ttl_days=1)
        assert route.call_count == 0


async def test_the_refusal_of_szukaj_w_archiwach_says_why(http):
    with respx.mock(assert_all_mocked=True, assert_all_called=False):
        with pytest.raises(HostNotAllowed, match="bot check"):
            await http.get_text(
                "https://www.szukajwarchiwach.gov.pl/jednostka/-/jednostka/1", ttl_days=1
            )


async def test_a_redirect_to_another_host_is_not_followed(http):
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.get(G).mock(
            return_value=httpx.Response(302, headers={"location": "https://attacker.example/"})
        )
        elsewhere = router.route(host="attacker.example").mock(return_value=httpx.Response(200))
        with pytest.raises(SiteError) as caught:
            await http.get_text(G, ttl_days=1)
    assert caught.value.code == "redirected" and elsewhere.call_count == 0


async def test_a_redirect_within_the_host_is_followed(http):
    moved = f"https://{GENETEKA}/rejestry2.php"
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.get(G).mock(return_value=httpx.Response(301, headers={"location": moved}))
        router.get(moved).mock(return_value=httpx.Response(200, text="moved here"))
        assert await http.get_text(G, ttl_days=1) == "moved here"


async def test_requests_to_one_host_are_spaced(tmp_path):
    clock = FakeClock()
    http = make_http(tmp_path, min_interval=4.0, clock=clock, sleep=clock.sleep)
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.route(host=GENETEKA).mock(return_value=httpx.Response(200, text="ok"))
        for i in range(3):
            await http.get_text(f"{G}&n={i}", ttl_days=1)
    assert clock.slept == [4.0, 4.0]


async def test_basia_gets_its_own_longer_interval(tmp_path):
    clock = FakeClock()
    http = make_http(
        tmp_path, min_interval=4.0, host_floors=HOST_FLOORS, clock=clock, sleep=clock.sleep
    )
    assert http.interval_for(BASIA) == 10.0 and http.interval_for(POZNAN) == 4.0
    assert http.interval_for(GENETEKA) == 10.0
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.route(host=BASIA).mock(return_value=httpx.Response(200, text="ok"))
        await http.get_text(f"https://{BASIA}/en/", ttl_days=1, data={"lname0": "A"})
        await http.get_text(f"https://{BASIA}/en/", ttl_days=1, data={"lname0": "B"})
    assert clock.slept == [10.0]


async def test_different_hosts_do_not_wait_for_each_other(tmp_path):
    clock = FakeClock()
    http = make_http(tmp_path, min_interval=4.0, clock=clock, sleep=clock.sleep)
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        for host in (GENETEKA, POZNAN):
            router.route(host=host).mock(return_value=httpx.Response(200, text="ok"))
        await http.get_text(G, ttl_days=1)
        await http.get_text(f"https://{POZNAN}/", ttl_days=1)
    assert clock.slept == []


async def test_a_503_is_retried_once_honouring_retry_after(tmp_path):
    clock = FakeClock()
    http = make_http(tmp_path, clock=clock, sleep=clock.sleep)
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        route = router.get(G).mock(
            side_effect=[
                httpx.Response(503, headers={"retry-after": "7"}),
                httpx.Response(200, text="ok"),
            ]
        )
        assert await http.get_text(G, ttl_days=1) == "ok"
    assert route.call_count == 2 and 7.0 in clock.slept


async def test_a_long_retry_after_is_capped(tmp_path):
    clock = FakeClock()
    http = make_http(tmp_path, clock=clock, sleep=clock.sleep)
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.get(G).mock(
            side_effect=[
                httpx.Response(429, headers={"retry-after": "3600"}),
                httpx.Response(200, text="ok"),
            ]
        )
        await http.get_text(G, ttl_days=1)
    assert max(clock.slept) == 30.0


async def test_a_second_failure_is_reported_and_a_404_is_not_retried(http):
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        route = router.get(G).mock(return_value=httpx.Response(500, text="boom"))
        with pytest.raises(SiteError) as caught:
            await http.get_text(G, ttl_days=1)
        assert route.call_count == 2 and caught.value.status == 500
        missing = router.get(f"https://{POZNAN}/x").mock(return_value=httpx.Response(404))
        with pytest.raises(SiteError):
            await http.get_text(f"https://{POZNAN}/x", ttl_days=1)
        assert missing.call_count == 1
    assert http.last_error["status"] == 404


async def test_a_dropped_connection_is_retried(http):
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        route = router.get(G).mock(
            side_effect=[httpx.ConnectError("reset"), httpx.Response(200, text="ok")]
        )
        assert await http.get_text(G, ttl_days=1) == "ok"
    assert route.call_count == 2


async def test_a_timeout_is_not_retried(http):
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        route = router.get(G).mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(SiteError) as caught:
            await http.get_text(G, ttl_days=1)
    assert caught.value.code == "timeout" and route.call_count == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403, headers={"cf-mitigated": "challenge"}, text="<html>"),
        httpx.Response(403, text='<script src="/_Incapsula_Resource?x=1"></script>'),
        httpx.Response(200, text='<html><script src="/_Incapsula_Resource?x=1"></script>'),
    ],
    ids=["cloudflare", "imperva-403", "imperva-200"],
)
async def test_a_bot_check_is_reported_as_a_challenge(http, response):
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.get(G).mock(return_value=response)
        with pytest.raises(SiteError) as caught:
            await http.get_text(G, ttl_days=1)
    assert caught.value.code == "challenge"


async def test_answers_are_cached_and_failures_are_not(http):
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        route = router.get(G).mock(
            side_effect=[httpx.Response(500), httpx.Response(500), httpx.Response(200, text="ok")]
        )
        with pytest.raises(SiteError):
            await http.get_text(G, ttl_days=1)
        assert await http.get_text(G, ttl_days=1) == "ok"
        assert await http.get_text(G, ttl_days=1) == "ok"
    assert route.call_count == 3 and http.cache_hits == 1
    assert http.cached_at(G) is not None


async def test_a_form_body_is_part_of_the_cache_key(http):
    url = f"https://{POZNAN}/getresults.php"
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        route = router.post(url).mock(
            side_effect=lambda request: httpx.Response(200, text=request.content.decode())
        )
        a = await http.get_text(url, ttl_days=1, data={"groom_lastname": "A"})
        b = await http.get_text(url, ttl_days=1, data={"groom_lastname": "B"})
        again = await http.get_text(url, ttl_days=1, data={"groom_lastname": "A"})
    assert a != b and again == a and route.call_count == 2


async def test_refresh_asks_again(http):
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        route = router.get(G).mock(return_value=httpx.Response(200, text="ok"))
        await http.get_text(G, ttl_days=1)
        await http.get_text(G, ttl_days=1, refresh=True)
    assert route.call_count == 2


async def test_an_unreadable_cache_entry_is_fetched_again(http):
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        route = router.get(G).mock(return_value=httpx.Response(200, text="ok"))
        await http.get_text(G, ttl_days=1)
        for entry in http.cache_dir.glob("*.json"):
            entry.write_text("{not json", encoding="utf-8")
        assert await http.get_text(G, ttl_days=1) == "ok"
    assert route.call_count == 2


async def test_identical_calls_in_flight_share_one_request(http):
    gate = asyncio.Event()

    async def slow(request):
        await gate.wait()
        return httpx.Response(200, text="ok")

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        route = router.get(G).mock(side_effect=slow)
        tasks = [asyncio.create_task(http.get_text(G, ttl_days=1)) for _ in range(3)]
        await asyncio.sleep(0)
        gate.set()
        assert await asyncio.gather(*tasks) == ["ok"] * 3
    assert route.call_count == 1 and http.shared_waits == 2


@pytest.mark.parametrize("declared", [True, False])
async def test_an_answer_over_the_cap_is_refused(tmp_path, declared):
    http = make_http(tmp_path, max_text_bytes=1_000)
    body = b"x" * 5_000
    headers = {"content-length": str(len(body))} if declared else {}
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.get(G).mock(return_value=httpx.Response(200, content=body, headers=headers))
        with pytest.raises(SiteError) as caught:
            await http.get_text(G, ttl_days=1)
    assert caught.value.code == "too_large"
    assert list(http.cache_dir.glob("*.json")) == []


async def test_an_image_that_is_not_a_jpeg_is_refused(http):
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.route(host=PHOTOS).mock(return_value=httpx.Response(200, content=b"<html>"))
        with pytest.raises(SiteError) as caught:
            await http.fetch_image(f"https://{PHOTOS}/{'a' * 64}_max")
    assert caught.value.code == "not_an_image"


async def test_every_request_carries_the_user_agent(http):
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        route = router.get(G).mock(return_value=httpx.Response(200, text="ok"))
        await http.get_text(G, ttl_days=1)
    assert route.calls[0].request.headers["User-Agent"].startswith("polish-archives-mcp/")
