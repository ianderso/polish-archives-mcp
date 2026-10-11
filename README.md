# polish-archives-mcp

[![CI](https://github.com/ianderso/polish-archives-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ianderso/polish-archives-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/polish-archives-mcp)](https://pypi.org/project/polish-archives-mcp/)

<!-- mcp-name: io.github.ianderso/polish-archives-mcp -->

An [MCP](https://modelcontextprotocol.io) server for the **Polish volunteer
indexes of vital records**, and for the archive scans they point to:

- **[Geneteka](https://geneteka.genealodzy.pl/)**, the Polskie Towarzystwo
  Genealogiczne's index of parish and civil registers: tens of millions of
  baptisms, marriages and burials from thousands of parishes across Poland,
  and some beyond. Its coverage list says, parish by parish, which registers
  and years have been indexed.
- **[The Poznań Project](https://poznan-project.psnc.pl/)**: marriages of
  1800-1899 in Wielkopolska and Kujawy, the former Prussian Provinz Posen and
  its neighbours, with ages and parents.
- **[BaSIA](https://www.basia.famula.pl/)**, the Wielkopolskie Towarzystwo
  Genealogiczne "Gniazdo"'s archival index, whose entries name the archive,
  the call number and the scan.
- **[Szukaj w Archiwach](https://www.szukajwarchiwach.gov.pl/)**, the Polish
  state archives' portal: this server downloads a full-size scan from its
  open photo host, given the scan's name.

It works the way a careful genealogist does. **An index row is a finding
aid**, typed by a volunteer from the register: it says which register and
entry to read, and the scan is the evidence. **A zero covers only what was
indexed**, so Geneteka's coverage list comes first. And a scan is cited by
the archive's own call number, the *Sygnatura* on the Szukaj w Archiwach unit
page, never by an index's rendering of it.

Nothing here writes anywhere, and nothing here keeps a family tree. It grew
from a script used in one family-history project, and sits well beside
[familysearch-mcp](https://github.com/ianderso/familysearch-mcp), whose
catalogue holds the filmed copies of many of the same registers.

This is an independent project. It is not affiliated with, endorsed by, or
supported by the Polskie Towarzystwo Genealogiczne, the Poznań Project, the
Wielkopolskie Towarzystwo Genealogiczne "Gniazdo", the Naczelna Dyrekcja
Archiwów Państwowych, or any archive.

## Tools

The server publishes seven tools. All but `swa_scan` are read-only;
`swa_scan` writes one new file and never overwrites one.

**Before searching**

| Tool | Purpose |
| --- | --- |
| `regions` | Geneteka's region codes and names (`15wp` is Wielkopolska). Makes no request. |
| `geneteka_coverage` | The registers Geneteka has indexed for a parish: births, marriages or deaths, the years exactly as Geneteka lists them (gaps included), and each register's `rid`. With `year`, whether each register covers it. The list is cached for a week. |

**Searching the indexes**

| Tool | Purpose |
| --- | --- |
| `geneteka_search` | Births, marriages or deaths in one region, or in one register by `rid`. Rows carry the custodian holding the book, the indexer's notes (often a date or a village) and any scan link. Fifty rows a page. |
| `poznan_search` | Marriages 1800-1899 by groom's and bride's surnames, or either spouse's. Given names are matched to the project's name groups; a name in no group returns the groups. Each row says who holds the original register. |
| `basia_search` | BaSIA entries by surname, with more people in the same entry, a place and radius, years, office and record type. Every row carries BaSIA's call number and scan, the unit's address on szukajwarchiwach.gov.pl, and a warning about BaSIA's series numbers. |

**Reading the scan**

| Tool | Purpose |
| --- | --- |
| `swa_scan` | Download one full-size scan (about 3500 px) from Szukaj w Archiwach's photo host, given its 64-character name. Saves a new `.jpg`, never a hidden file or one under `~/Library`. |
| `cache_status` | This session's requests, by site, the cache, and the pacing. Makes no request. |

### The workflow they serve

1. `geneteka_coverage` for the parish: which registers and years exist in
   the index. A year not listed was never searched.
2. `geneteka_search`, `poznan_search` and `basia_search`. Records are in
   Latin, Polish or German: search Wojciech as Adalbertus and Adalbert too,
   Jan as Joannes and Johann, Marianna as Maria; -ski and -ska, and genitive
   forms ("z Kowalskich"), are one surname.
3. Open the unit page (a BaSIA row's `unit_url`, or a Geneteka row's scan
   link) **in a browser**. Szukaj w Archiwach's pages sit behind a bot check
   and this server never fetches them. Read the *Sygnatura* there, and each
   scan's name from its image address (`photos.szukajwarchiwach.gov.pl/<name>`).
4. `swa_scan` with that name. Read the scan before saying anything about it.
5. Cite the archive, the Sygnatura and the scan number, with the unit page's
   address. Keep the index's id (Geneteka, Poznań Project or BaSIA) as the
   finder.

## Setup

You need Python 3.11 or later and [uv](https://docs.astral.sh/uv/). There is
no key to request and no account to make.

**Without cloning.** `uvx` fetches it from PyPI and runs it in one step:

```bash
uvx polish-archives-mcp
```

**From a clone**, which is what you want if you will change it:

```bash
git clone https://github.com/ianderso/polish-archives-mcp
cd polish-archives-mcp
uv sync
uv run polish-archives-mcp   # stdio server, usually launched by the client
```

Either way the server speaks MCP over stdio, so you will normally let an MCP
client start it rather than run it by hand.

### Claude Desktop

```json
{
  "mcpServers": {
    "polish-archives": {
      "command": "uvx",
      "args": ["polish-archives-mcp"]
    }
  }
}
```

A desktop app does not always inherit your shell's `PATH`. If the server fails
to start because `uvx` cannot be found, give the full path that `which uvx`
prints as the `command`.

### Claude Code

```bash
claude mcp add polish-archives -- uvx polish-archives-mcp
```

## Configuration

Nothing is required. A `.env` file in the directory the server starts in
supplies anything the environment does not; only that directory is read.

| Variable | Meaning |
| --- | --- |
| `POLISH_ARCHIVES_CACHE_DIR` | Response cache directory. Default `~/.cache/polish-archives-mcp`. |
| `POLISH_ARCHIVES_TIMEOUT` | HTTP timeout in seconds for one request. Default 60. Scan downloads get 180 to read. |
| `POLISH_ARCHIVES_MIN_INTERVAL` | Least seconds between two requests to one site. Default 4, and never below 4. BaSIA always gets at least 10. |
| `POLISH_ARCHIVES_CONTACT` | An email address or URL added to the User-Agent, so a site can reach you if your use causes trouble. Optional, and courteous. |
| `POLISH_ARCHIVES_DOWNLOAD_DIR` | An existing folder. When set, `swa_scan` saves only inside it. Set it to save into an iCloud Drive folder, which lives under `~/Library`. |

An unusable value is reported on the first tool call as a `not_configured`
result naming the variable.

## Being a good guest

Each site is a volunteer society's server or an archive's. The client sends
one request at a time to each site, at least four seconds apart, and ten to
BaSIA and Geneteka; different sites do not wait for one another. A Geneteka search fetches
one page of fifty rows per call, never the whole result in a burst. Two
identical calls in flight share one request. The coverage list is cached for
a week, searches for a day, the Poznań Project's name groups for a month; a
failure is never cached. A 429, a 5xx or a dropped connection gets one retry,
honouring `Retry-After`. The User-Agent names the package, its version and
this repository.

What each source says about automated use, as checked on 2026-10-11:

- **Geneteka.** No terms of use are linked from
  [geneteka.genealodzy.pl](https://geneteka.genealodzy.pl/). Its
  `robots.txt` disallows nothing and sets `Crawl-delay: 120`. This server
  makes one request per tool call there, at least ten seconds apart.
- **The Poznań Project.** Its
  [about page](https://poznan-project.psnc.pl/page.php?page=about) says the
  database is "dostępna dla wszystkich użytkowników sieci poprzez bezpłatną
  wyszukiwarkę" (open to every internet user through a free search engine).
  It serves no `robots.txt`.
- **BaSIA.** No terms of use were found on
  [www.basia.famula.pl](https://www.basia.famula.pl/). Its `robots.txt` sets
  `Crawl-delay: 10`, disallows `/search.php` and other scripts, and says in a
  comment that robots may index information pages, "ale nie wyszukiwarkę ani
  skrypty pobierające dane" (but not the search engine or data-fetching
  scripts), because each search is a costly database query. This server
  posts the site's own search form at `/en/`, one search per tool call, at
  least ten seconds apart, and caches each answer for a day.
- **Szukaj w Archiwach.** The portal's unit and fonds pages sit behind
  Imperva's bot check, so this server never requests them; a person opens
  them in a browser. The photo host serves no `robots.txt` (it answers 400).
  The portal's own terms could not be read without a browser; the archives
  set the terms for reusing their scans, so check them before publishing one.

If a site asks you to stop, stop: tell the server's operator, and open an
issue so the project can change.

## How to read what comes back

- **An index row is a finding aid.** Every search answer says so. The row
  tells you which register, year and entry to read; the scan is the record.
- **Check coverage before trusting a zero.** `geneteka_search` with a `rid`
  and a span of years names the years Geneteka has not indexed
  (`years_not_indexed`). The Poznań Project and BaSIA publish no comparable
  list: their zeros say less.
- **"Too many" is not a zero.** The Poznań Project shows no entries when a
  search matches too many; `poznan_search` returns `too_many_results` with
  the counts, so narrow it. BaSIA lists only the first 250 entries of a
  search and says so (`truncated`).
- **Cite the archive's call number, not BaSIA's.** BaSIA writes call numbers
  its own way, and its middle (series) number can differ from the archive's.
  Every BaSIA row carries that warning. Take the Sygnatura from the unit page.
  Some BaSIA rows still link the retired `szukajwarchiwach.pl` domain, which no
  longer opens; those rows have no `unit_url`, only the reference written in
  the old link, and a note on finding the unit.
- **Who holds the book.** Geneteka rows carry the custodian Geneteka names (an
  archdiocesan archive, a state archive, a parish). Poznań Project rows say
  who holds the original register, from the project's own archive pages.
- **Names come in three languages.** A Polish family can appear as Wojciech,
  Adalbertus and Adalbert in three records. The Poznań Project's name groups
  bridge this for given names; for the others, search each form.
- **Comments are other researchers' words.** Poznań Project comments are
  returned without their authors' names or addresses.

## Deliberately not here

- **Szukaj w Archiwach's own pages.** They need a browser session past a bot
  check; a server driving a browser to get past it would be impersonating a
  person. The unit page stays with the person; the scan host, which is open,
  is what `swa_scan` uses.
- **Other indexes** (metryki.genealodzy.pl's scans, Kartenmeister, the
  Pomeranian Greif index). Proposals are welcome as issues.
- **Writing to any site**, including corrections and comments.
- **Working around bot checks.** A site that answers with a challenge is
  reported as `blocked` and left alone.

## Security

Tool arguments are written by a model, and the model reads text this server
does not control: index notes, comments, web pages. The server assumes that
text can steer the model, and limits what a steered model can make it do.

- **Which hosts.** Four, fixed in the code: `geneteka.genealodzy.pl`,
  `poznan-project.psnc.pl`, `www.basia.famula.pl` and
  `photos.szukajwarchiwach.gov.pl`. No argument names a host: arguments only
  fill in a search, and a scan's name must be 64 hexadecimal characters. A
  request hook refuses anything else, including an address taken from a
  response. Redirects are followed only within the same host.
- **How much.** A page over 10 MB, or a scan over 60 MB, is refused as it
  streams in.
- **Which files.** `swa_scan` creates one new file and never overwrites one.
  The bytes must be a JPEG, judged by their first bytes, and not the photo
  host's "file unavailable" picture. The file must end in `.jpg` or `.jpeg`;
  never a hidden file or folder, never under `~/Library`, and with
  `POLISH_ARCHIVES_DOWNLOAD_DIR` set, never outside it, all judged after links
  are resolved. A refused download leaves nothing on disk.
- **Site text is untrusted.** Names, notes and comments reach the model
  verbatim. The server's instructions tell the model to treat that text as
  material to weigh, never as instructions; the model still decides, so
  review what it proposes to do.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Development

```bash
uv sync --extra dev
uv run pytest                      # mocked with respx; never touches a site
uv run ruff check .
uv run ruff format --check .
uv run python -m tests.live_check  # paced calls to the live sites
```

The live check asks the sites what the recorded fixtures cannot: whether
their answers still have the shape the server reads. It takes a few minutes,
because it keeps to the same pacing. See [CONTRIBUTING.md](CONTRIBUTING.md)
for how the suite is organised, [docs/API-NOTES.md](docs/API-NOTES.md) for
what was observed of each site and when, and [docs/DESIGN.md](docs/DESIGN.md)
for why the server is shaped this way.

## Credits

The indexes are the work of thousands of volunteers of the Polskie
Towarzystwo Genealogiczne, the Poznań Project and the Wielkopolskie
Towarzystwo Genealogiczne "Gniazdo". The registers and their scans belong to
the archives that hold them.

## License

[MIT](LICENSE).
