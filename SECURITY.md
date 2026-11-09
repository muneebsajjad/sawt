# Security

## Reporting a vulnerability

Please do not open a public issue. Report it privately through
[a GitHub security advisory](https://github.com/muneebsajjad/sawt/security/advisories/new).
You should hear back within a week.

## What the engine trusts

The engine (`sawt serve`) listens on `127.0.0.1:7865` and answers a request only when:

- the `Host` header is `127.0.0.1` or `localhost` on that port, which stops DNS rebinding;
- it carries the `X-Sawt: 1` header, which a web page cannot send without a CORS
  preflight, and preflights are always refused;
- its `Origin` is absent (a local process) or is an allowed extension. Released builds pin the
  published extension's ID. An unpacked copy of `extension/` gets that same ID, because the
  manifest carries the store's public key; a copy with a different ID is added with
  `--allow-extension <id>` or `SAWT_EXTENSION_IDS`. With no ID pinned, any extension is accepted, and the engine
  prints a warning at startup saying so.

Anything that lets a web page, a remote host, or an unrelated extension make the engine speak,
read its cache, or learn what the user has been reading is in scope.

Model files are verified against pinned SHA-256 hashes before they are loaded.
