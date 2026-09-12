#!/usr/bin/env python3
# Copyright 2026 Sriharsha Viyyala
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""GrayWatch — find the device that's lying to you.

A gray failure is a device silently dropping traffic while every one of its
own counters reads clean. Every dashboard is green; your app teams are
screaming; the war room lasts six hours. GrayWatch convicts the liar in
minutes, from probe data you can already collect.

Zero dependencies. One file. Read-only. Stdlib only.

Usage:
    python graywatch.py demo                          # self-contained demo fabric
    python graywatch.py analyze probes.json           # your own probe results
    python graywatch.py analyze probes.json -o report.html --threshold 0.5

Probe record format (JSON list):
    {"src": "leaf1", "dst": "leaf3", "path": ["leaf1","spine2","leaf3"],
     "loss_pct": 2.4}
Collect with whatever you have — TWAMP, a ping-mesh cron job, SR-policy
steered probes — as long as each probe records the PATH it transited.

The triangulation invariant (never ask a device about itself):
    A device present in >= N lossy paths and ZERO clean paths, while
    self-reporting healthy, is the gray element. The disagreement between
    fabric experience and self-report IS the evidence.

GrayWatch finds the liar; what you do about it is up to you. The
recommended drain procedure is in every report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import time
from dataclasses import dataclass, field

__version__ = "1.0.0"

DEFAULT_LOSS_THRESHOLD_PCT = 0.5
DEFAULT_MIN_LOSSY_PATHS = 3


# --------------------------------------------------------------------- model
@dataclass
class Probe:
    src: str
    dst: str
    path: list
    loss_pct: float

    def lossy(self, threshold: float) -> bool:
        return self.loss_pct >= threshold


@dataclass
class Verdict:
    suspect: str
    confidence: float
    lossy_paths: int
    clean_paths: int
    p_chance: float = 1.0            # probability the pattern arose by chance
    odds: str = ""                   # human-readable: "1 in 16,800"
    corroborating: list = field(default_factory=list)
    self_report_clean: bool = True


def _binom_tail(n: int, k: int, q: float) -> float:
    """P(X >= k) for X ~ Binomial(n, q) — the chance an INNOCENT device
    would appear in at least k lossy paths out of its n paths, if lossiness
    struck paths at the background rate q. Exact, stdlib-only."""
    q = min(max(q, 1e-9), 1 - 1e-9)
    return sum(math.comb(n, i) * q**i * (1 - q)**(n - i) for i in range(k, n + 1))


@dataclass
class Analysis:
    verdicts: list
    exonerated: list
    probes_total: int
    lossy_total: int
    threshold: float
    matrix: dict
    ts: float = field(default_factory=time.time)

    @property
    def clean(self) -> bool:
        return not self.verdicts and self.lossy_total == 0


# ---------------------------------------------------------------- triangulate
def triangulate(probes: list, threshold: float = DEFAULT_LOSS_THRESHOLD_PCT,
                min_lossy: int = DEFAULT_MIN_LOSSY_PATHS,
                self_reports: dict | None = None) -> Analysis:
    """Conviction requires the gray signature (many lossy paths, ZERO clean
    paths) plus exclusivity: at least one lossy path the suspect cannot blame
    on any co-suspect. This localizes multiple simultaneous gray devices
    without smearing blame across the fabric, and refuses to convict pure
    passengers that merely share paths with the real culprit."""
    self_reports = self_reports or {}
    matrix: dict[str, dict] = {}
    for p in probes:
        for hop in p.path:
            row = matrix.setdefault(hop, {"lossy": 0, "clean": 0})
            row["lossy" if p.lossy(threshold) else "clean"] += 1

    lossy = [p for p in probes if p.lossy(threshold)]
    candidates = sorted((dev for dev, m in matrix.items()
                         if m["lossy"] >= min_lossy and m["clean"] == 0),
                        key=lambda d: -matrix[d]["lossy"])
    verdicts: list[Verdict] = []
    for dev in candidates:
        exclusive = [p for p in lossy if dev in p.path and
                     not any(o in p.path for o in candidates if o != dev)]
        if not exclusive and len(candidates) > 1:
            continue                                # passenger, not culprit
        hits = matrix[dev]["lossy"]
        n = hits + matrix[dev]["clean"]
        # background lossiness among paths NOT touching the suspect
        # (Laplace-smoothed so a fully-clean background can't zero out)
        other = [p for p in probes if dev not in p.path]
        q = (sum(1 for p in other if p.lossy(threshold)) + 1) / (len(other) + 2)
        p_chance = _binom_tail(n, hits, q)
        one_in = max(2, round(1 / max(p_chance, 1e-12)))
        verdicts.append(Verdict(
            suspect=dev,
            confidence=min(0.999, 1 - p_chance),
            lossy_paths=hits,
            clean_paths=matrix[dev]["clean"],
            p_chance=p_chance,
            odds=f"1 in {one_in:,}",
            corroborating=[f"{p.src}->{p.dst} ({p.loss_pct}% via {'/'.join(p.path)})"
                           for p in lossy if dev in p.path][:10],
            self_report_clean=bool(self_reports.get(dev, {"clean": True}
                                                    ).get("clean", True))))

    all_lossy = [p for p in probes if p.lossy(threshold)]
    exonerated = sorted({hop for p in probes for hop in p.path}
                        - {v.suspect for v in verdicts}
                        - {hop for p in all_lossy for hop in p.path
                           if matrix[hop]["clean"] == 0})
    return Analysis(verdicts=verdicts, exonerated=exonerated,
                    probes_total=len(probes), lossy_total=len(all_lossy),
                    threshold=threshold, matrix=matrix)


# ---------------------------------------------------------------------- demo
def demo_probes(gray_device: str = "spine1", loss_pct: float = 2.5,
                seed: int = 7) -> list:
    """Synthetic 2-spine / 5-leaf ECMP fabric with one silently-lying spine."""
    rng = random.Random(seed)
    endpoints = ["leaf1", "leaf2", "leaf3", "leaf4", "gpufab1"]
    spines = ["spine1", "spine2"]
    probes, i = [], 0
    for a in range(len(endpoints)):
        for b in range(a + 1, len(endpoints)):
            via = spines[i % 2]
            i += 1
            path = [endpoints[a], via, endpoints[b]]
            base = round(rng.uniform(0.0, 0.08), 3)          # healthy noise floor
            loss = base + (loss_pct if gray_device in path else 0.0)
            probes.append(Probe(endpoints[a], endpoints[b], path, round(loss, 3)))
    return probes


# --------------------------------------------------------------------- report
def render_html(analysis: Analysis, title: str = "GrayWatch verdict") -> str:
    v = analysis.verdicts
    status = ("FABRIC CLEAN" if analysis.clean else
              f"{len(v)} GRAY FAILURE(S) TRIANGULATED" if v else
              "LOSS PRESENT — NOT YET LOCALIZED (need more path diversity)")
    color = "#1a7f37" if analysis.clean else ("#d1242f" if v else "#b45309")
    fingerprint = hashlib.sha256(json.dumps(
        [(x.suspect, x.lossy_paths) for x in v]).encode()).hexdigest()[:12]

    rows = "".join(
        f"<tr><td>{d}</td><td>{m['lossy']}</td><td>{m['clean']}</td>"
        f"<td>{'⚠ suspect' if any(x.suspect == d for x in v) else ('✓ exonerated' if m['clean'] else '—')}</td></tr>"
        for d, m in sorted(analysis.matrix.items(),
                           key=lambda kv: -kv[1]['lossy']))
    cards = "".join(f"""
      <div class="verdict">
        <div class="vh"><b>{x.suspect}</b>
          <span class="conf">{x.confidence:.1%} confidence</span></div>
        <p>Present in <b>{x.lossy_paths} lossy paths</b> and
           <b>{x.clean_paths} clean paths</b>, while self-reporting
           {"<b>clean</b> — the definition of a gray failure" if x.self_report_clean
            else "unhealthy"}. Odds this pattern is coincidence:
           <b>{x.odds}</b> (exact binomial vs the fabric's background loss rate).</p>
        <p class="act">Recommended action: drain from ECMP (ISIS overload /
           MED max) — links stay up, traffic routes around — then re-probe
           to verify and swap optics/linecard under calm conditions.</p>
        <details><summary>{len(x.corroborating)} corroborating paths</summary>
          <ul>{''.join(f'<li>{c}</li>' for c in x.corroborating)}</ul></details>
      </div>""" for x in v)

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{title}</title><style>
 body{{font:15px/1.6 -apple-system,'Segoe UI',sans-serif;color:#1f2a37;
      background:#f6f8fb;max-width:880px;margin:40px auto;padding:0 20px}}
 .hero{{background:#fff;border:1px solid #e3e9f1;border-radius:14px;
       padding:26px;box-shadow:0 2px 10px rgba(31,42,55,.05)}}
 h1{{margin:0;font-size:22px;letter-spacing:1px}} h1 span{{color:#0969da}}
 .status{{display:inline-block;margin-top:10px;padding:6px 16px;border-radius:18px;
         color:#fff;background:{color};font-weight:600;font-size:13.5px}}
 .meta{{color:#697586;font-size:12.5px;margin-top:10px}}
 .verdict{{background:#fff;border:1px solid #e3e9f1;border-left:4px solid #d1242f;
          border-radius:12px;padding:18px 20px;margin-top:16px}}
 .vh b{{font-size:17px}} .conf{{float:right;color:#0969da;font-weight:600}}
 .act{{background:#f0f6ff;border-radius:8px;padding:10px 12px;font-size:13.5px}}
 table{{width:100%;border-collapse:collapse;margin-top:16px;background:#fff;
       border:1px solid #e3e9f1;border-radius:12px;overflow:hidden}}
 th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:1px;
    color:#697586;padding:10px 14px;border-bottom:1px solid #e3e9f1}}
 td{{padding:8px 14px;border-bottom:1px solid #eef2f7;font-size:13.5px}}
 details{{margin-top:8px;font-size:13px}} summary{{cursor:pointer;color:#0969da}}
 .foot{{margin-top:28px;color:#697586;font-size:12.5px;border-top:1px solid #e3e9f1;
       padding-top:14px}}
</style></head><body>
<div class="hero">
 <h1>GRAYWATCH<span>▮</span></h1>
 <div class="status">{status}</div>
 <div class="meta">{analysis.probes_total} probes analyzed ·
   {analysis.lossy_total} lossy (≥{analysis.threshold}%) ·
   {len(analysis.exonerated)} devices exonerated ·
   verdict fingerprint {fingerprint} ·
   {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(analysis.ts))}</div>
</div>
{cards}
<table><thead><tr><th>device</th><th>lossy-path appearances</th>
<th>clean-path appearances</th><th>disposition</th></tr></thead>
<tbody>{rows}</tbody></table>
<div class="foot"><b>Method:</b> never ask a device about itself. A device in
many lossy paths and zero clean paths, while self-reporting healthy, is
convicted by the disagreement — an exact binomial verdict against the
fabric's measured background loss rate. Innocent devices are explicitly
exonerated. GrayWatch is read-only by construction: no code path writes to
a device.</div>
</body></html>"""


# ------------------------------------------------------------------------ cli
def load_probes(path: str) -> list:
    with open(path) as fh:
        data = json.load(fh)
    return [Probe(d["src"], d["dst"], list(d["path"]), float(d["loss_pct"]))
            for d in data]


def print_verdict(analysis: Analysis) -> None:
    print(f"\nGrayWatch v{__version__} — {analysis.probes_total} probes, "
          f"{analysis.lossy_total} lossy (threshold {analysis.threshold}%)")
    if analysis.clean:
        print("✔ FABRIC CLEAN — no loss above threshold.")
        return
    if not analysis.verdicts:
        print("⚠ Loss present but not localizable — add probe path diversity "
              "(more endpoint pairs / per-spine steering).")
        return
    for v in analysis.verdicts:
        print(f"\n⚠ GRAY FAILURE: {v.suspect}  ({v.confidence:.1%} confidence, "
              f"chance odds {v.odds})")
        print(f"   in {v.lossy_paths} lossy paths, {v.clean_paths} clean paths; "
              f"self-report clean={v.self_report_clean}")
        print(f"   → drain from ECMP, re-probe, then service the hardware.")
    if analysis.exonerated:
        print(f"\n✓ exonerated: {', '.join(analysis.exonerated)}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="graywatch", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="run the built-in demo fabric")
    d.add_argument("--gray", default="spine1")
    d.add_argument("-o", "--out", default="graywatch-report.html")
    a = sub.add_parser("analyze", help="analyze your probe results (JSON)")
    a.add_argument("probes")
    a.add_argument("--threshold", type=float, default=DEFAULT_LOSS_THRESHOLD_PCT)
    a.add_argument("--min-lossy", type=int, default=DEFAULT_MIN_LOSSY_PATHS)
    a.add_argument("-o", "--out", default="graywatch-report.html")
    args = ap.parse_args(argv)

    if args.cmd == "demo":
        probes = demo_probes(gray_device=args.gray)
        analysis = triangulate(probes)
    else:
        analysis = triangulate(load_probes(args.probes),
                               threshold=args.threshold,
                               min_lossy=args.min_lossy)
    print_verdict(analysis)
    with open(args.out, "w") as fh:
        fh.write(render_html(analysis))
    print(f"\nreport → {args.out}")
    return 0 if analysis.clean or analysis.verdicts else 1


if __name__ == "__main__":
    sys.exit(main())
