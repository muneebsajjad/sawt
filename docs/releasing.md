# v0.1 launch checklist

The name is **Sawt** (صوت, "voice"). It appears as:

| Thing | Where it is set |
|---|---|
| Extension name | `extension/manifest.json` `name`, `extension/popup.html`, `extension/popup.js`, `extension/welcome.html` title, `PRIVACY.md` |
| PyPI package | `pyproject.toml` `name`, `extension/welcome.js` `PACKAGE`, README |
| CLI command | `pyproject.toml` `[project.scripts]` |

## 1. Publish the engine to PyPI

```bash
uv build                      # -> dist/*.whl and *.tar.gz
uv publish                    # needs a PyPI account + API token
```

Then on a clean machine: `uv tool install sawt && sawt serve`.

## 2. Publish the extension

```bash
cd extension && zip -r ../dist/extension-0.1.0.zip . -x '.*'
```

Upload at https://chrome.google.com/webstore/devconsole (one-time $5 developer fee).

## 3. Pin the extension ID (security, before announcing)

The store assigns the extension ID on first upload. Put it in
`src/sawt/serve.py` `PUBLISHED_EXTENSION_IDS`, bump the version, and publish the engine
again. Until then the server accepts any extension, and prints a warning saying so.
For a local unpacked copy, run `sawt serve --allow-extension <its id>`.

## Store listing

**Short description** (from the manifest, 108 chars):
> Listen to any article read aloud by a natural voice that runs on your own computer. Free, private, no cloud.

**Category:** Accessibility (alt: Productivity)

**Detailed description:**
> Turn any article, blog post or selected text into natural-sounding speech — without sending a
> word of it to the cloud.
>
> Sawt uses Kokoro, an open-source voice model, running on your own computer. There
> is no account, no subscription and no usage limit, and nothing you read leaves your machine.
>
> • One click or Alt+R reads the article, skipping menus, ads and sidebars
> • The sentence being spoken is highlighted and kept in view
> • Picks up where you left off on every page
> • 28 English voices, American and British, adjustable speed
> • Right-click any selection to hear just that
>
> Requires the free local voice engine (one command to install; setup steps open after install).
> macOS, Linux and Windows. English only for now.

**Single purpose:** Reads the text of the current web page aloud using a speech engine on the
user's own computer.

**Permission justifications:**

| Permission | Why |
|---|---|
| `activeTab` | Read the article text of the tab the user asks to hear, only when they ask |
| `scripting` | Inject the article extractor and the sentence highlighter into that tab |
| `offscreen` | Play audio from a background document, so reading continues after the popup closes |
| `storage` | Remember voice, speed and the last sentence read on each page |
| `contextMenus` | The "Read selection aloud" and "Read this page aloud" right-click items |
| Host `http://127.0.0.1:7865/*` | Talk to the voice engine running on the user's own computer; no remote host is contacted |

**Remote code:** No. All code is in the package; the only network peer is localhost.

**Data use disclosures:** Website content is handled only to produce speech, locally; not sold,
not transferred, not used for anything else. Privacy policy URL:
https://github.com/muneebsajjad/sawt/blob/main/PRIVACY.md

**Assets to make:** at least one 1280×800 screenshot (popup + highlighted article), a 440×280
promo tile, and the 30-second demo video for the launch posts.

## 4. Announce

Show HN ("Show HN: Read any article aloud with a voice model running on your own machine"),
r/selfhosted, r/LocalLLaMA. Lead with: free, private, no account, one command to install.
