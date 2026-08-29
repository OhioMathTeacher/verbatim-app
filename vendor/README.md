# vendor

Third-party code, committed rather than fetched. A build must work on a machine with
no network, and a built page must open from `file://` with nothing beside it.

## Temml 0.11.11 — MIT

<https://temml.org> · <https://github.com/ronkok/Temml>

| file | what it is |
|---|---|
| `temml.min.js` | TeX to MathML. Inlined into every built page by `make_session_capture.py`. |
| `temml.css` | Temml's own spacing rules. The `@font-face` for `Temml.woff2` is stripped at build time — that font covers script capitals only, and shipping a rule pointing at a file we do not carry would make a self-contained page reach for something that is not there. |

MathML is drawn by the browser, so no maths fonts are shipped. Upgrading means replacing
both files and rebuilding; nothing else refers to a version.
