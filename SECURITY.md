# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately rather than in a public
issue.

- If this repository has **Private vulnerability reporting** enabled, use the
  *Security* tab → *Report a vulnerability*. That channel is private to the
  repository maintainers.
- Otherwise, contact the repository owner through the account that owns this
  repository.

No other contact route is published here, because inventing one would send
reports nowhere.

Please include: what you observed, the steps to reproduce it, the version or
commit you tested, and the impact you believe it has. If a document is needed
to reproduce the issue, describe how to generate an equivalent one rather than
attaching a real document.

There is no bug-bounty programme.

## Supported versions

| Version | Supported |
|---|---|
| 1.0.x | Yes — current development line |

The application has not been released publicly, so there is no older version
to support.

## What this application does and does not do

This is a desktop application that runs entirely on the user's machine. That
shapes what a vulnerability means here.

**By design, the application:**

- makes no network connection of any kind; the packaged build does not even
  contain the socket, TLS or Qt Network binaries
- reads the user's documents read-only, and never executes them, follows
  links inside them or runs macros
- accepts local paths only — UNC paths, mapped network drives and URLs are
  refused
- stores its index, settings and logs under the current user's
  `%LOCALAPPDATA%`, so another user on the same machine cannot read them
  through the application
- keeps no document text, search terms or snippets in its log files

**Findings we consider security-relevant** include: any path that causes a
document's content to leave the machine; any way to make the application
execute a file; SQL or command injection through a file name, folder name or
search term; rendering document content as markup; a crash caused by a
malformed document that leaves the index corrupt; and anything that writes
document content into the log.

## Handling secrets

The application has no accounts, passwords, API keys or tokens, and reads no
`.env` file — there is nothing for it to leak. Contributors should keep it
that way:

- never commit credentials, tokens, keys or a populated `.env`;
- keep test fixtures synthetic — they are generated at run time by
  `tests/make_fixtures.py`, and no real document belongs in this repository;
- if a secret is ever committed, treat it as compromised: rotate or revoke it
  first, then remove it from the working tree and from history, and say which
  credential was affected without quoting its value.

## Design and verification detail

The engineering detail behind the claims above — the threat model, the
enforcement points and the release checklist — is in
[`docs/SECURITY.md`](docs/SECURITY.md). The verification results are in
[`docs/TEST_REPORT.md`](docs/TEST_REPORT.md).
