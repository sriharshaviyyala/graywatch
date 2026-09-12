**Find the network device that's lying to you.**

A gray failure — a device silently dropping traffic while its own counters read clean — defeats every monitoring tool, because every signal comes from the liar itself. GrayWatch never asks a device about itself: feed it path-aware probe results and it convicts the culprit on the disagreement between fabric experience and self-report, with an exact binomial verdict and every innocent device explicitly exonerated.

- One file, Python 3.10+ stdlib only, structurally read-only
- `python graywatch.py demo` → verdict in 30 seconds
- Localizes multiple simultaneous gray devices (exclusivity rule)
- Honest third state: "loss present, not localizable — add path diversity"
- Board-ready HTML report with the full disagreement matrix
