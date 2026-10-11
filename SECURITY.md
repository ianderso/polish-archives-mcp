# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately, through GitHub's
[private vulnerability reporting](https://github.com/ianderso/polish-archives-mcp/security/advisories/new)
(the **Report a vulnerability** button on the repository's Security tab), not
in a public issue. Include what an attacker controls, what they gain, and the
steps to reproduce it.

You should hear back within a week. Fixes are released for the latest version
only.

## Scope

In scope: this server — the requests it makes, the files it writes (its cache
and the scans `swa_scan` saves), and anything a tool argument or a site's
response can make it do.

Out of scope: Geneteka, the Poznań Project, BaSIA and Szukaj w Archiwach
themselves, which this project does not operate. Report problems with those
to the societies or the archives that run them.

## The security model, briefly

- **No credentials.** None of the four sites needs a key or an account. The
  server holds none and sends none, and keeps no cookies past a session.
- **Tool arguments are treated as the attacker's.** A model writes them, and
  the model reads index notes, user comments and web pages that may carry
  injected instructions. Everything below is about what such an argument can
  make the server do.
- **Four hosts, fixed in the code.** `geneteka.genealodzy.pl`,
  `poznan-project.psnc.pl`, `www.basia.famula.pl` and
  `photos.szukajwarchiwach.gov.pl`, over https. No argument names a host:
  search arguments are placed in a query string or a form body, URL-encoded,
  and a scan's name must be 64 hexadecimal characters before it is placed in
  a path. A request hook refuses any other host or scheme, including an
  address taken from a response, so a link in a page cannot become a
  request.
- **Redirects are followed by hand,** and only within the same host over
  https. A redirect anywhere else is reported to the caller and not
  followed.
- **Bounded answers.** A page over 10 MB or a scan over 60 MB is refused as
  it streams in, whether or not its size was declared.
- **Read-only calls.** The server sends the same GET and POST requests the
  sites' own search pages send. It never submits a correction, a comment or
  a sign-in.
- **Local writes.** The cache lives under `POLISH_ARCHIVES_CACHE_DIR`, in files
  named by a hash of the request and written atomically. `swa_scan` writes
  only the absolute path it is given, and only if that path, with its links
  resolved, ends in `.jpg` or `.jpeg`, has no hidden component, is not under
  `~/Library`, and lies inside `POLISH_ARCHIVES_DOWNLOAD_DIR` when that is set
  (the operator's folder may itself be hidden or under `~/Library`; what a
  model adds below it may not). The bytes must be a JPEG by their first bytes,
  and not the photo host's "file unavailable" picture. The file is created
  exclusively (an existing file or link is never overwritten or followed) and
  removed if writing fails; a refused download writes nothing at all.
- **Site responses carry untrusted text.** Names, indexer notes and user
  comments reach the model verbatim, which makes them a channel for prompt
  injection. The server's instructions tell the model to treat that text as
  material, not as instructions, but the model still decides what to do next.
  User comments are returned without their authors' names or e-mail
  addresses. An injection that leads the model to misuse this server's own
  tools is in scope; one that leads it to misuse other tools the client has
  connected is a client concern.
- **`POLISH_ARCHIVES_CONTACT` is checked** for newlines and parentheses before
  it is placed in the User-Agent header.
