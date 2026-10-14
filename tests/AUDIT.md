# Browser audit

The audit reproduced and corrected these defects:

- Practice keyboard shortcuts continued working while Theory or Associations was open, potentially finishing a hidden recall session.
- Backspace replaced the last placed card with the selected pool card instead of removing it.
- Keyboard selection could move to a card outside the horizontally scrolled deck without revealing it.
- Returning from multi-deck results to single-deck results lost the results grid layout.
- Slot accessibility labels continued saying “empty” after a card was placed or replaced.
- Negative and excessive custom time values bypassed the HTML input bounds.
- Unsupported persisted association settings could produce invalid training modes.
- One- and two-letter fragments could incorrectly pass image-answer checking.
- Resetting, finishing, or switching decks during a gesture left its document/window listeners attached.
- The dock covered almost the entire recall board in a short landscape viewport.
- Shared action verbs and fuzzy matching of generic verbs could accept an action from another card.
- Answers, replacements, removals, deck switches, and drag releases could be accepted after the recall deadline before a delayed timer callback ran.
- Returning to the page or the practice tab could expose an expired attempt until the next interval callback.
- Stale handlers could mutate a finished or reset attempt.
- Repeated Enter could advance groups, and repeated starts could replace a running sequence.
- Switching away from practice during a drag left its gesture handlers active.
- System-clock changes affected visible-page timing. Visible practice now uses monotonic elapsed time; hidden intervals also account for wall time when the browser suspends its monotonic clock.

The practice stress test performs 1,200 seeded placements, replacements, removals, and deck switches, checking card conservation and filled-slot counts after every operation. Boundary tests distinguish an answer at 1,999 ms from one at the 2,000 ms deadline, including keyboard input and interrupted drag release.

A simultaneous system-clock change while a browser suspends its clock in a hidden page cannot be distinguished from genuine elapsed time using local clocks alone. Tests model these clocks and visibility events; physical sleep and clock changes on every device remain unverified.

Verification uses the 39 test methods in `browser_checks.py`. Matrix cases cover all 18 association configurations, partial decks, up to five full decks, all card input codes, wrong and empty recall scoring, continuous timing without pause and actual timer expiry, interrupted dragging, mouse selection across every remaining card, native touch scrolling and dropping, unavailable/malformed browser storage, sidebar collapse and responsive transitions, and narrow/landscape layouts.

Run `python3 tests/browser_checks.py` from the repository root. The checks run in headless Chromium with desktop and emulated mobile viewports. They do not establish compatibility with Safari, Firefox, or a physical touchscreen device.
