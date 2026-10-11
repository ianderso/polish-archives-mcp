# Contributing

Issues and pull requests are welcome. This file says how the project is put
together and what a change is expected to carry.

## Setting up

```bash
git clone https://github.com/ianderso/polish-archives-mcp
cd polish-archives-mcp
uv sync --extra dev
```

Before sending a change, run what CI runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

The suite is mocked with [respx](https://lundberg.github.io/respx/) against
recorded responses. It must never touch a live site: each one is a volunteer
society's or an archive's server, and CI should not depend on any of them
being up.

## Where things live

| Path | What it holds |
| --- | --- |
| `src/polish_archives_mcp/server.py` | The tools. Their docstrings and `Field` descriptions *are* the published tool descriptions and schema. Also the destination rules for `swa_scan`. |
| `src/polish_archives_mcp/client.py` | The cached, paced HTTP client, the four-host allowlist, the redirect rule and the size caps. |
| `src/polish_archives_mcp/geneteka.py` | Geneteka: the coverage list, its shortened years, and the search rows. |
| `src/polish_archives_mcp/poznan.py` | The Poznań Project: name groups, result blocks, and who holds each register. |
| `src/polish_archives_mcp/basia.py` | BaSIA: the search form, the result boxes, and the unit addresses. |
| `src/polish_archives_mcp/text.py` | Small text helpers shared by the parsers. |
| `src/polish_archives_mcp/config.py` | Settings from the environment and `.env`. |
| `docs/API-NOTES.md` | What each site was observed to do, and when. |
| `docs/DESIGN.md` | Why the server is shaped the way it is, and what is out of scope by decision. |
| `tests/fixtures/` | Recorded responses and the tool-schema snapshot. |
| `tests/test_tool_contract.py` | Tests over the tool surface as a client sees it. |
| `tests/test_swa_scan.py` | The scan host, and every refusal of a destination. |
| `tests/live_check.py` | The one script that talks to live sites, run by hand. Not collected. |

## What a change carries

**A test that fails without it.** Bug fixes especially: reproduce the bug as a
test first.

**Descriptions written for the model.** A tool's docstring is what a model
reads when choosing and calling it. The combined descriptions have a ceiling
(`DESCRIPTION_BUDGET` in `tests/test_tool_contract.py`), because they are sent
on every session. Raise it deliberately, in a pull request of its own. They
are dedented at import, so the budget measures the same text on every Python.

**The evidence distinction, kept.** An index row is a finding aid to the
register, never the record. Search answers say so; a contract test enforces
it.

**A zero that is only a zero.** An outage, a bot check, a page the parser no
longer understands, or a "too many results" message must each come back as
its own `error`, never as an empty list. A parser that finds no entries and
no "nothing found" message raises `unexpected_answer`.

**A structured result, never an exception.** Every tool catches its failures
and returns an `error` envelope. A sweep test calls every tool with every site
failing and fails if one raises.

**Nothing that writes to a site, fetches Szukaj w Archiwach's unit pages, or
works around a bot check.** See [docs/DESIGN.md](docs/DESIGN.md#out-of-scope-by-decision).

**Nothing that widens what an argument can reach.** Treat every argument as
written by someone else's text. The hosts are fixed in `client.HOSTS`; a new
source adds a host there, with a reason in `docs/DESIGN.md`. A new place to
write goes through `server._destination`, with a test in
`tests/test_swa_scan.py` showing that the refusals still come before the harm.

**A new fixture recorded, not invented,** when a change depends on how a site
answers, with what was observed and when added to `docs/API-NOTES.md`. Keep
fixtures to ordinary public examples: a common surname in a large parish,
never your own family.

**The snapshot, when the surface changes.** Renaming or adding a tool or a
parameter fails the snapshot test on purpose. Regenerate it with
`uv run python -m tests.regen_tool_snapshot`, update the README tables, and add
a `CHANGELOG.md` entry.

## When a site changes its page

The three indexes are read from their own web pages, which can change
without notice. When `uv run python -m tests.live_check` fails:

1. Fetch the page by hand, once, with the project's User-Agent, at the same
   pace the server keeps.
2. Record the new answer as a fixture, trimmed to a few entries.
3. Change the parser, and add what changed and when to `docs/API-NOTES.md`.

## Releasing

A maintainer bumps `__version__` in `src/polish_archives_mcp/__init__.py` and
both versions in `server.json`, moves the changelog's Unreleased entries under
the new version, and publishes a GitHub release tagged `v<version>`. The
release workflow builds the tag, publishes to PyPI by Trusted Publishing, and
lists the version in the MCP Registry.
