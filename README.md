# GrayWatch

[![ci](https://github.com/sriharshaviyyala/graywatch/actions/workflows/ci.yml/badge.svg)](https://github.com/sriharshaviyyala/graywatch/actions)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

**Find the network device that's lying to you.**

Every dashboard is green. Interfaces up, zero CRC errors, no syslog. And your
payments team is screaming about timeouts. That's a **gray failure** — a
device silently dropping traffic while its own counters read clean — and it's
the most feared failure mode in modern fabrics, because every monitoring tool
you own consumes telemetry *from the liar itself*.

Hyperscalers solved this internally a decade ago (Microsoft's Pingmesh, the
007 paper). GrayWatch brings the technique to everyone else: one file, zero
dependencies, read-only.

```
⚠ GRAY FAILURE: spine1  (99.9% confidence, chance odds 1 in 16,807)
   in 5 lossy paths, 0 clean paths; self-report clean=True
   → drain from ECMP, re-probe, service the hardware

✓ exonerated: gpufab1, leaf1, leaf2, leaf3, leaf4, spine2
```

## Quick start

```bash
python graywatch.py demo                       # 30 seconds to a verdict
python graywatch.py analyze your-probes.json   # your fabric
```

Output: a terminal verdict plus a board-ready HTML report with the full
disagreement matrix, corroborating paths, and the recommended drain procedure.

## How it works

**Never ask a device about itself.** Feed GrayWatch probe results that record
the *path* each probe transited — from TWAMP, a ping-mesh cron job,
SR-steered probes, whatever you already run:

```json
[{"src": "leaf1", "dst": "leaf3", "path": ["leaf1", "spine2", "leaf3"], "loss_pct": 2.4}]
```

The conviction invariant: a device present in **≥ N lossy paths and zero
clean paths**, while self-reporting healthy, is convicted by the
disagreement itself. In an ECMP fabric, innocent devices necessarily appear
on clean paths via the healthy spine — so the same matrix that convicts the
culprit explicitly **exonerates** everyone else. An exclusivity rule
localizes multiple simultaneous gray devices without smearing blame.

Confidence is an **exact binomial probability**, not a heuristic: the chance
an innocent device would show this lossy/clean split at the fabric's
measured background loss rate. The demo's "1 in 16,807" is (1/7)⁵ — simple
enough to check by hand, which is the point.

When loss is present but not localizable, GrayWatch says so (distinct exit
code) and tells you what probe diversity to add. Refusing to guess is a
feature.

## Guarantees

- **Read-only, structurally** — there is no code path that writes to a
  device. ~400 lines; read it before you run it.
- **Zero dependencies** — Python 3.10+ standard library only.
- **Deterministic** — same input, same verdict, same odds.

## Probe data requirements

Each record needs `src`, `dst`, `path` (ordered device names the probe
transited), `loss_pct`. Tunables: `--threshold` (lossy cutoff, default 0.5%)
and `--min-lossy` (corroboration minimum, default 3). More endpoint pairs
and per-path steering = stronger convictions; the statistics scale
automatically.

## Roadmap

Per-interface conviction (same invariant, finer hops), probe-source
integrations (TWAMP responders, SR-policy steering), probe diversity against
flow-selective failures.

## License

Apache-2.0 — see [LICENSE](LICENSE).
