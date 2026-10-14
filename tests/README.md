# Browser checks

Run from the repository root:

```sh
python3 tests/browser_checks.py
```

Requires Python, the `playwright` Python package, and Chromium at `/usr/bin/chromium` (available in the cloud environment). The suite starts its own local HTTP server on a free port; no running development server or external services are required.

Checks include all 18 association mode combinations, practice with partial decks and up to five full decks, scoring, replacement/removal, keyboard controls, menu resizing, malformed preferences, continuous timers and expiry, mouse selection, native touch scrolling and dragging, interrupted gestures, and small-screen layouts. Tests use an isolated browser context and do not alter application data in your browser.
