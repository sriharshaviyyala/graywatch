# Copyright 2026 Sriharsha Viyyala. Apache-2.0.
"""GrayWatch test suite: conviction, exoneration, multi-culprit handling,
statistical sanity, and CLI round-trips."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import graywatch as gw


def test_demo_convicts_the_right_device():
    analysis = gw.triangulate(gw.demo_probes(gray_device="spine1"))
    assert len(analysis.verdicts) == 1
    v = analysis.verdicts[0]
    assert v.suspect == "spine1" and v.confidence > 0.99
    assert v.clean_paths == 0 and v.lossy_paths >= 3
    assert "spine2" in analysis.exonerated


def test_verdict_carries_exact_chance_odds():
    v = gw.triangulate(gw.demo_probes(gray_device="spine1")).verdicts[0]
    assert v.p_chance < 0.001
    assert v.odds.startswith("1 in ")


def test_clean_fabric_stays_clean():
    analysis = gw.triangulate(gw.demo_probes(loss_pct=0.0))
    assert analysis.clean and not analysis.verdicts


def test_two_simultaneous_grays_both_localized():
    probes = gw.demo_probes(gray_device="spine1")
    for p in probes:
        if "leaf2" in p.path:
            p.loss_pct = round(p.loss_pct + 3.0, 3)
    analysis = gw.triangulate(probes)
    assert {v.suspect for v in analysis.verdicts} == {"spine1", "leaf2"}


def test_refuses_to_convict_without_corroboration():
    probes = gw.demo_probes(loss_pct=0.0)
    probes[0].loss_pct = 5.0
    analysis = gw.triangulate(probes)
    assert not analysis.verdicts and analysis.lossy_total == 1


def test_binom_tail_sanity():
    assert abs(gw._binom_tail(1, 1, 0.5) - 0.5) < 1e-9
    assert abs(gw._binom_tail(2, 1, 0.5) - 0.75) < 1e-9
    assert gw._binom_tail(10, 10, 0.1) < 1e-9
    assert abs(gw._binom_tail(5, 0, 0.3) - 1.0) < 1e-9


def test_determinism():
    a = gw.triangulate(gw.demo_probes())
    b = gw.triangulate(gw.demo_probes())
    assert [(v.suspect, v.odds) for v in a.verdicts] == \
           [(v.suspect, v.odds) for v in b.verdicts]


def test_cli_demo_and_analyze(tmp_path):
    out = tmp_path / "r.html"
    assert gw.main(["demo", "-o", str(out)]) == 0
    html = out.read_text()
    assert "GRAY FAILURE(S) TRIANGULATED" in html and "spine1" in html

    pj = tmp_path / "probes.json"
    pj.write_text(json.dumps([{"src": p.src, "dst": p.dst, "path": p.path,
                               "loss_pct": p.loss_pct}
                              for p in gw.demo_probes()]))
    assert gw.main(["analyze", str(pj), "-o", str(tmp_path / "r2.html")]) == 0
