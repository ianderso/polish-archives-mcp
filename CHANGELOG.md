# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/). The tool surface is the public
interface: renaming or removing a tool or a parameter is a major release, and
adding one is a minor release. Before 1.0, a minor release may do either.
A change to how a site's page is read, with the tools unchanged, is a patch
release.

## [Unreleased]

## [0.1.0] — 2026-10-11

First release.

### Added

- Seven tools: `regions`, `geneteka_coverage`, `geneteka_search`,
  `poznan_search`, `basia_search`, `swa_scan` (writes one new file, never
  overwrites) and `cache_status`.
- `geneteka_coverage` reads Geneteka's list of registers indexed, parish by
  parish, with the years exactly as Geneteka writes them and each register's
  `rid`; with `year`, whether each register covers it. Cached for a week.
- `geneteka_search` reads one page of fifty rows per call, by region or by
  register, with the custodian, the indexer's notes and any scan link on
  each row. A search by `rid` checks the register's record type and names
  the years in the span Geneteka has not indexed.
- `poznan_search` matches given names to the Poznań Project's name groups
  and returns the groups when a name fits none; reports "too many results"
  as its own answer, never as a zero; and says who holds each original
  register, from the project's archive pages.
- `basia_search` returns BaSIA's call number and scan, the unit's address on
  www.szukajwarchiwach.gov.pl, and on every row a warning that BaSIA's
  series number can differ from the archive's. Rows linked to the retired
  szukajwarchiwach.pl domain say so and carry the reference from the link.
- `swa_scan` downloads a full-size scan from Szukaj w Archiwach's open photo
  host by the scan's 64-character name, refuses the host's "file
  unavailable" picture, and saves only under the destination rules of
  contentdm-mcp (absolute path, new `.jpg`, no hidden component, nothing
  under `~/Library` unless `POLISH_ARCHIVES_DOWNLOAD_DIR` says so).
- A polite client: four hosts, fixed; no redirects off a host; one request
  at a time per host, at least four seconds apart and ten for BaSIA; one
  retry on 429, 5xx or a dropped connection, honouring `Retry-After`; pages
  capped at 10 MB and scans at 60 MB; answers cached on disk, failures
  never.
- Server instructions that keep the evidence model: an index row is a
  finding aid; a zero from a parish or year outside Geneteka's coverage is
  not a negative; Latin, Polish and German name equivalents; scans cited by
  the archive's call number from the unit page.
