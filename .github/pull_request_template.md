<!-- What this changes and why. Link the issue it closes, if there is one. -->

## Checklist

What each item means is in [CONTRIBUTING.md](https://github.com/ianderso/polish-archives-mcp/blob/main/CONTRIBUTING.md#what-a-change-carries).

- [ ] A test that fails without this change.
- [ ] `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest` pass.
- [ ] Tool descriptions are written for the model and fit under `DESCRIPTION_BUDGET`. Raising it takes a pull request of its own, saying why.
- [ ] Anything returning index rows says they are finding aids, not the record.
- [ ] Failures come back as an `error` result, not an exception, and an outage is never reported as a zero.
- [ ] If a tool or parameter changed: `tests/fixtures/tool_schema.json` is regenerated and the README tables are updated.
- [ ] If this relies on how a site answers: a recorded fixture, and what was observed and when in `docs/API-NOTES.md`.
- [ ] Fixtures use ordinary public examples, not anyone's own family.
- [ ] A `CHANGELOG.md` entry, if users will notice the change.
- [ ] Nothing here writes to a site, fetches Szukaj w Archiwach's unit pages, or works around a bot check.
