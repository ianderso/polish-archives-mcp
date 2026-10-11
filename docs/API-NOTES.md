# Site notes

What each site actually answers, observed with plain HTTP and the project's
User-Agent, at least four seconds apart per site (ten for BaSIA). None of
these interfaces is documented; they are what each site's own search page
sends. Observed 2026-10-11, about 60 requests in all.

## Geneteka (geneteka.genealodzy.pl)

### Coverage list: `GET /rejestry.php?lang=pol`

- One HTML page, 2.46 MB, answered in 1.3 s. No cookie needed.
- A table with one row per region: name, number of parishes, number of
  registers, then every register as
  `<a class="B" href="index.php?rid=8959&amp;w=06mp&amp;op=gt" title="1687-1700,1714-51,...">Kraków WNMP (Mariacki)</a> <font ...>1687-1909 U;</font>`.
  `class` is B (births), S (marriages) or D (deaths). `title` holds the years
  indexed; the `<font>` after it only the first and last.
- 16,093 registers in 21 regions on the day.
- Years are shortened to the digits that change: `1741-55,90,98,1810-1930`
  is 1741-1755, 1790, 1798 and 1810-1930. A `title` can be empty: the
  register is listed with no years.
- A register is named by its parish, sometimes with a qualifier in
  parentheses (`(mojż.)` Jewish, `(ewang.)` Protestant, `(gr.-kat.)` Greek
  Catholic) or a suffix (`USC` civil registry).

### Search: `GET /api/getAct.php`

- Query: `draw=1&start=<row>&length=50&op=gt&lang=pol&bdm=<B|S|D>&w=<region>&rid=<rid or B|S|D>&search_lastname=&search_name=&search_lastname2=&search_name2=&from_date=&to_date=`, plus `exac=1` for an exact surname.
- The page's own JavaScript sends `X-Requested-With: XMLHttpRequest` and a
  Referer of the matching `index.php?...` page; the server does the same.
- The answer is DataTables JSON served as `text/html; charset=UTF-8`:
  `{"draw", "recordsTotal", "recordsFiltered", "data": [...], "parishes": {...}}`.
- `parishes` names the registers searched:
  `{"06mp": [[8959, "Kraków WNMP (Mariacki)", "0.0", "małopolskie"]]}`, or `[]`
  when a whole region was searched.
- Without `exac`, Kowalski also matched Kowalska and Kowalewska, in any
  name column (the child's, the mother's, "other surnames").
- A births or deaths row has nine cells before the last: year, entry, given
  name, surname, father, mother's given name, mother's surname, parish,
  place. A marriages row: year, entry, groom's given name and surname,
  groom's parents, bride's given name and surname, bride's parents, parish.
- A name cell can carry its own note:
  `Jakubowski<img src="images/i.png" title="Inne nazwiska: Kowalski ">`.
- The last cell is HTML. `i.png`'s title holds the indexer's notes,
  separated by `&#013;` ("Uwagi: Skan 116", "Data ślubu: 18.11.1860 r.");
  `z.png`'s title names the custodian ("Miejsce przechowywania ksiąg:
  &#013;Archiwum Narodowe w Krakowie &#013;&#013;30-960 Kraków, ul. Sienna
  16") inside a link to its website; `a.png` names the indexer; an `s.png`
  link is the scan (here a Szukaj w Archiwach unit page); `fix.php?gid=N` is
  the correction form, and `gid` is the entry's id.
- A search with no matches answers `recordsTotal: 0` and still names the
  registers searched.
- `robots.txt`: `User-agent: *`, an empty `Disallow`, `Crawl-delay: 120`,
  `Disallow: /cgi-bin/`.

## The Poznań Project (poznan-project.psnc.pl)

### The form: `GET /`

- The extended-search form's `groom_firstname` and `bride_firstname` selects
  hold the name groups: 52 for grooms and 50 for brides on the day, each a
  number and a label such as `25` = "Joannes / Jan / Johann" or `1` =
  "Adalbert(us) / Wojciech". `0` is any; `99` is "none of the above".
- Parentheses mark optional letters: `Apol(l)onia`, `Maria(nna)`.

### Results: `POST /getresults.php`

- Form: `action=extended&extended_window_lastname_mode=<both|any>&groom_firstname=&groom_lastname=&bride_firstname=&bride_lastname=&lastname=&parish_id=&parish_distance=&year_from=&year_to=&last_update=&confession=<0-3>&threshold=<50-100>`,
  with `X-Requested-With: XMLHttpRequest`. Each search took about 6 s
  (5.3 s of it the site's own query time).
- An HTML fragment: a statistics box ("Wyniki zgodne: 37", "Wyniki powyżej
  progu 80%: 46"), then one block per marriage, each starting
  `<div class="small-toolbox">`.
- A block's `<h3 class="result exact1">` (or `rough1`) holds the register
  type ("Parafia katolicka"), the parish in `<b>`, and "wpis 5 / 1850".
  The groom and bride are `<li class="groom">` and `<li class="bride">`, or
  `groom_widow` and `bride_widow`, with age, parents and "Dodatkowe
  informacje". A similarity bar `bar80.gif` is rounded to tens; the figure
  after it ("81%") is exact.
- User comments are `<li class="comment">` with the author's name and often
  an e-mail address. The server keeps only the comment and its date.
- "Akt oryginalny" links `pages/arch_location/archN.htm`, a fixed page
  saying who holds the original register ("The original record for this
  marriage is held in the State Archive in Włocławek, Poland."). Pages 1 to
  40 were read on the day; there are more.
- **Too many matches:** Kowalski as groom, 1850-1855, any given name,
  matched 323 exactly and 452 above the threshold. The answer then holds the
  statistics, "Zbyt duża liczba wyników. Ogranicz kryteria wyszukiwania…" and
  a map of parishes, and no entries.
- **No matches:** "Nie znaleziono pasujących zapisów".
- No `robots.txt` (404).

## BaSIA (www.basia.famula.pl)

### Search: `POST /en/`

- The extended-search form, as the page posts it:
  `p_count=<n>&od=<year>&do=<year>&placename=&distance=<km>&type_unit=<any|usc|kat|ewa|other>&type_record=<any|a|b|c|z>&datefrom=2011-01-28&dateto=<today>&showplaces=&showtype=block&showdate=none&search_ext=szukaj&search_ext_button=Search`,
  and for each person `fname<i>`, `lname<i>`, `sex<i>`, `type<i>`, `sim<i>`
  from 0. `type_record` a, b, c are birth, marriage, death.
- The answer is a whole page (490 KB for 104 entries), answered in about
  2 s. Entries are grouped by map area in `resgroup` blocks; each is
  `<div class='result_box …' id='resboxid<ID>'>`, with a left box
  (`lbox`: register, record type, year, book, people with a similarity bar
  per name, "Indexer notes", "Other people appearing in the document") and a
  right box (`rbox`: archive, call number and scan, indexer, date added,
  ID, links).
- The archive link is `showbox.php?id=<code>`: the archive's number (11 AP
  Kalisz, 53 AP Poznań, 54 its Konin branch) or a short code (AAP, the
  archdiocesan archive in Poznań).
- The scan link is usually
  `https://www.szukajwarchiwach.gov.pl/jednostka/-/jednostka/<id>#scan<n>`,
  with the text "772/1/19, scan 122". 2 of 104 entries on the day linked the
  retired `https://szukajwarchiwach.pl/11/730/0/1/25/str/1/4/15/#select53`
  instead. Parish entries held at the archdiocesan archive carry a call
  number ("PM 015/7") and no link.
- The unit page for "772/1/19, scan 122" (opened in a browser) gave the
  Sygnatura 11/772/0/1/19: here BaSIA's series number matched. It does not
  always.
- The total is in the map legend's script: "wszystkie pasujące wpisy: 104".
- **More than 250 matches:** Kowalski, 1800-1900, matched 43,684; the page
  lists the first 250 and says "Wyników jest więcej niż 250…" in
  `<p class='results-truncated'>`, and "The number of search results
  exceeded maximum value."
- **No matches:** "No search results for your query".
- Each entry has a permalink `/record/<base64>`, whose decoded form is
  `<archive>_<fonds>_<series>_<unit>_<scan>_…_<year>_<token>_<unit type>_<record type>`.
- `robots.txt`: a comment (in Polish) that robots may index information
  pages but not the search or the data scripts, since each search is a
  costly database query; `Crawl-delay: 10`; `Disallow` for `/search.php`,
  `/search_ajax.php`, `/getjson.php`, `/getcsv.php`, `/show_record.php`,
  `/skany.php` and others. `/en/` is not disallowed.

## Szukaj w Archiwach

### Unit pages: `www.szukajwarchiwach.gov.pl/jednostka/-/jednostka/<id>`

- Behind Imperva (Incapsula); built for a browser. **Not fetched by this
  server.** Opened once in a browser on the day: the page for AP Kalisz
  11/772/0/1/19 (Żerków civil registry, births 1880) showed its Sygnatura,
  dates and 219 scans, and each scan's image address carries its
  64-character hex name. Another unit page answered "Portlety jest
  tymczasowo niedostępny" (the portlet is temporarily unavailable), as the
  portal often does.

### Photo host: `GET https://photos.szukajwarchiwach.gov.pl/<name>_max`

- Open: no cookie, no challenge. Served through Imperva's CDN
  (`x-cdn: Imperva`), which sets cookies the server does not need.
- `<name>_max` is the full-size scan: 3500 x 2393 px, 647 KB for a microfilm
  target card (scan 1 of the unit above).
- **A name it does not hold** answers 200 with `image/jpeg`: a 379 x 273,
  12,137-byte picture reading "PLIK NIEDOSTĘPNY" (SHA-256
  `6fbf02e0…3f562c`). The server refuses it.
- `robots.txt` answers 400 (an object-store error).
