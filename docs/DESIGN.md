# Design

Why the server is shaped the way it is, and what is out of scope by decision.

## The question it answers

"Is this baptism, marriage or burial in a Polish register, and where is the
scan?" For Wielkopolska and much of the rest of Poland, three volunteer
indexes answer the first half, each in its own way, and the state archives'
portal holds many of the scans. None of the four publishes an API. The
server reads each through the same requests its own web page makes, and
returns typed results that carry the evidence rules with them.

It began as a single-user script in a family-history project. The script's
request shapes and parsing were kept; what changed is the housing: an async
client with a fixed host list, pacing, a cache and structured errors, and
tool descriptions written for the model that calls them.

## Three indexes, one evidence model

- **An index row is a finding aid.** Every search answer carries a note
  saying so, and the server's instructions say it again. The row names a
  register, a year and an entry; the scan is what gets read and cited.
- **Coverage before a zero.** Geneteka publishes, parish by parish, which
  registers and years it has indexed. `geneteka_coverage` reads that list
  (cached a week), and `geneteka_search` with a register's `rid` names the
  years in a span that Geneteka has not indexed. A zero outside coverage is
  reported as a zero over what was searched, and the answer says so. The
  Poznań Project and BaSIA publish no such list, and their zero notes say
  their zeros mean less.
- **"Too many" is not "none".** The Poznań Project shows no entries when a
  search matches too many, only a map. Read naively, that is an empty
  result. The server reports `too_many_results` with the counts.
- **Cite the archive, not the index.** BaSIA's call numbers are its own
  rendering, and its middle (series) number does not always match the
  archive's. Every BaSIA row carries that warning, so it travels with the
  number however a row is quoted. The unit page's Sygnatura is what gets
  cited.
- **Who holds the book.** Geneteka names the custodian on each row; the
  Poznań Project links a page per archive. Those pages are fixed, so the 40
  seen on the build day ship as a table, and an unknown one is read once and
  cached for 90 days (at most three new ones per call, so a long result does
  not turn into a burst).

## Which hosts a request reaches

Four, fixed in `client.HOSTS`: `geneteka.genealodzy.pl`,
`poznan-project.psnc.pl`, `www.basia.famula.pl` and
`photos.szukajwarchiwach.gov.pl`. Unlike contentdm-mcp, whose sites are many
and partly chosen by the caller, no argument here names a host. Arguments
fill in a query string or a form body, and a scan's name must be 64
hexadecimal characters before it goes into a path. A request hook refuses
any other host or scheme, so a link found in a page cannot become a request,
and redirects are followed only within the same host.

Because the hosts are fixed, the per-connection public-address check of
contentdm-mcp (which guards hosts an argument can choose) is not needed
here; the allowlist does that work.

**Szukaj w Archiwach's own site is not on the list.** Its unit and fonds
pages sit behind Imperva, and are built for a person in a browser. A server
driving a headless browser past that check would be an automated client
pretending to be a person. So the unit page stays with the person: they
open it, read the Sygnatura, and copy each scan's name from its image
address. The photo host that serves those images is open, and `swa_scan`
uses it. The request hook names this reason when it refuses the portal.

## What swa_scan writes

The destination rules are contentdm-mcp's `get_image` rules, unchanged: an
absolute path; a new file, not even a dangling link; a `.jpg` or `.jpeg`
suffix; no hidden component; nothing under `~/Library` unless the operator's
`POLISH_ARCHIVES_DOWNLOAD_DIR` is there (an iCloud Drive folder, say) and the
file is inside it. Every check is made after links are resolved, and folders
are compared by identity.

The bytes must be a JPEG by their first bytes. The photo host answers a name
it does not hold with a 200 and a small "PLIK NIEDOSTĘPNY" (file
unavailable) picture, which a naive download would save as a scan. The
server refuses it by its SHA-256, and refuses any JPEG under 1000 pixels on
its long side, since a full scan is about 3500.

## Pacing and caching

The script paused four seconds between pages and kept to "a few queries a
minute". The client keeps that as a floor: one request at a time per host,
at least four seconds apart (configurable upward, never below four). Two
sites get ten seconds: BaSIA, where each search is a costly database query,
and Geneteka, the busiest of the volunteer indexes. One search is one
request at either, so the spacing costs a caller little; Geneteka is also
read one page per tool call, never a whole result in a burst. These are the
server's own limits. The sites' `robots.txt` files (BaSIA: a 10-second crawl
delay; Geneteka: 120 seconds, which would make a three-page search take six
minutes) are recorded in the README as facts, not followed.

Answers are cached on disk: the coverage list (2.5 MB) for a week, searches
for a day, the Poznań Project's name groups for 30 days, its archive pages
for 90. BaSIA and Poznań Project answers come whole, so their later pages
are served from the cached answer, with no new request. A failure, or a page
the parser cannot read, is never cached.

## Shape of the results

- **Pages of 50.** Geneteka pages on the server side; the other two are
  paged locally from one answer. Each answer says `page`, `pages` and
  `next_page`, so a caller asks for more rather than assuming the first page
  is all.
- **Empty fields are left out.** A row says only what the index says.
- **Polish labels stay Polish where they are data.** Geneteka's notes
  ("Data urodzenia: 15.04.1850 r.") are passed through as written; the
  model reads Polish, and a translation would be the server's guess.
- **Comments without authors.** Poznań Project comments are user-written
  and often carry an e-mail address. The server returns the comment's words
  and date only.

## Out of scope, by decision

- **Szukaj w Archiwach's unit, fonds and search pages.** Behind a bot check;
  see above. If the archives publish a machine interface for fonds and unit
  lists, it belongs here; none was found on 2026-10-11.
- **Writing to any site.** No corrections, comments or sign-ins.
- **Working around bot checks.** A Cloudflare or Imperva challenge is
  reported as `blocked`.
- **Bulk harvesting.** One search per call, paced; no tool walks a whole
  parish.
- **Reading the scan.** Handwriting recognition of Latin, Polish and German
  registers is not attempted; the scan is downloaded for a person, or a
  model, to read.

## Tests

- Everything is mocked with respx against **recorded** responses
  (`tests/fixtures/`), trimmed to a few entries. The examples are ordinary:
  the surname Kowalski in Kraków's St Mary's parish, and in the Poznań
  Project and BaSIA. The suite never touches a live site.
- Contract tests pin the tool surface as a client sees it: names and
  parameters (snapshot), descriptions present, dedented and within a size
  budget, the pitfalls present in the descriptions, annotations, no tool
  that raises when every site fails or answers with a page it cannot read,
  unknown parameters refused.
- `tests/test_swa_scan.py` takes the attacker's side for the one tool that
  writes: every destination rule, the placeholder picture, bytes that are
  not a JPEG, and a bot-check page in place of a scan.
- `tests/live_check.py` calls each site and checks the answers the server
  was built against, by hand.
