# -*- coding: utf-8 -*-
r"""What fleet_probe must get right.

The two mistakes this file exists to prevent, both of which really happened in this
workspace on the morning of 2026-09-11:

  1. Calling a live door dead because it did not answer 200. CONTROL on :8896 answers 403
     (it is auth-gated) and eran4's coder doors answer 404 on /v1/models. A probe that tests
     `code == 200` reports a healthy fleet as half dead.
  2. Hanging. A probe that blocks blocks the agent that called it, and an agent that has
     stopped answering looks exactly like a broken fleet.

No network is touched here: the HTTP layer and ssh are replaced by fakes.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import almido_fleet as F  # noqa: E402


@pytest.fixture()
def offline(monkeypatch):
    """Nothing in this module may reach the real world unless a test asks for it."""
    monkeypatch.setattr(F, "_http", lambda url, timeout: {"code": 200, "ms": 1})
    monkeypatch.setattr(F, "probe_host", lambda n, i, t: {"host": n, "verdict": "VERIFIED",
                                                          "uptime": "up 5:00"})
    monkeypatch.setattr(F, "tailnet", lambda t: {"verdict": "VERIFIED", "nodes": [],
                                                 "online": 0, "total": 0})
    monkeypatch.setattr(F, "ramchat", lambda t: {"verdict": "VERIFIED", "summary": "up"})
    monkeypatch.setattr(F, "INVENTORY", F.Path(r"Z:\no-such-inventory.json"))


# ------------------------------------------------------------------ the 403 lesson
@pytest.mark.parametrize("code,alive,expected", [
    (403, [0], "VERIFIED"),     # CONTROL: auth-gated, and ALIVE
    (404, [0], "VERIFIED"),     # eran4's coder doors: wrong path, and ALIVE
    (400, [0], "VERIFIED"),     # ERAN's window: wants its own path, and ALIVE
    (502, [0], "VERIFIED"),     # a proxy answering at all is a live proxy...
    (502, [200], "BROKEN"),     # ...but the 480B door must really SERVE, so 502 is broken
    (200, [200], "VERIFIED"),
    (0, [0], "BROKEN"),         # nothing answered: the only real death
])
def test_a_door_is_alive_if_it_answers(monkeypatch, code, alive, expected):
    monkeypatch.setattr(F, "_http", lambda url, timeout: {"code": code, "ms": 3})
    out = F.probe_door({"name": "d", "url": "http://x/", "alive_codes": alive}, {}, 1)
    assert out["verdict"] == expected, out


def test_a_broken_door_says_why(monkeypatch):
    monkeypatch.setattr(F, "_http", lambda url, timeout: {"code": 0, "ms": 3,
                                                          "error": "connection refused"})
    out = F.probe_door({"name": "d", "url": "http://x/", "alive_codes": [0]}, {}, 1)
    assert out["verdict"] == "BROKEN"
    assert "connection refused" in out["why"]


def test_the_control_door_really_is_declared_403_friendly():
    """A regression fence on the TABLE itself, not just on the logic: CONTROL, the coder
    doors and ERAN's window must all be declared alive-on-any-answer."""
    by_name = {d["name"]: d for d in F.DEFAULT_DOORS}
    for name in ("CONTROL", "QUORUM", "ERAN-window"):
        assert 0 in by_name[name]["alive_codes"], name
    # and the two that must really serve a model are NOT
    for name in ("480B", "eran4:8450"):
        assert by_name[name]["alive_codes"] == [200], name


# ------------------------------------------------------------------ the tailnet fallback
def test_a_lan_refusal_falls_back_to_the_tailnet(monkeypatch):
    """CLAUDE.md's own rule: 'before calling a DGX down, every box answers on Tailscale
    too'. On 2026-09-11 ERAN's window refused its LAN address and answered over Tailscale
    in the same second."""
    seen = []

    def http(url, timeout):
        seen.append(url)
        return {"code": 0, "error": "refused"} if "192.168" in url else {"code": 400, "ms": 5}

    monkeypatch.setattr(F, "_http", http)
    hosts = {"eran1": {"lan": "<lan-ip>", "tailscale": "<tailnet-ip>"}}
    out = F.probe_door({"name": "w", "url": "http://{eran1}:8820/", "alive_codes": [0]},
                       hosts, 1)
    assert out["verdict"] == "VERIFIED"
    assert out["http_code"] == 400
    assert "tailnet" in out.get("via", "")
    assert len(seen) == 2 and "192.168" in seen[0] and "100.104" in seen[1]


def test_the_fallback_is_not_tried_when_the_lan_answers(monkeypatch):
    seen = []
    monkeypatch.setattr(F, "_http", lambda url, timeout: seen.append(url) or {"code": 200, "ms": 1})
    F.probe_door({"name": "w", "url": "http://{eran1}:8820/", "alive_codes": [0]},
                 {"eran1": {"lan": "1.1.1.1", "tailscale": "2.2.2.2"}}, 1)
    assert len(seen) == 1


# ------------------------------------------------------------------ not hanging
def test_the_whole_probe_is_budgeted(monkeypatch, offline):
    """One door that never answers must not hold the probe past its budget. It is reported
    UNKNOWN with its own evidence -- never quietly dropped, and never waited on."""
    def slow(url, timeout):
        time.sleep(30)
        return {"code": 200}

    monkeypatch.setattr(F, "_http", slow)
    t0 = time.time()
    res = F.probe(doors=[{"name": "slow", "url": "http://x/", "alive_codes": [0]}],
                  timeout=1, budget=3, include_hosts=False, include_tailnet=False)
    assert time.time() - t0 < 12, "the budget was not honoured"
    assert res["doors"][0]["verdict"] == "UNKNOWN"
    assert "budget" in res["doors"][0]["error"]


def test_every_check_carries_its_own_timeout(monkeypatch, offline):
    seen = []
    monkeypatch.setattr(F, "_http", lambda url, timeout: seen.append(timeout) or {"code": 200})
    F.probe(timeout=8, include_hosts=False, include_tailnet=False)
    assert seen and all(0 < t <= 8 for t in seen)


def test_the_per_check_timeout_is_capped_at_eight_seconds():
    assert F.PER_CHECK_TIMEOUT <= 8.0


# ------------------------------------------------------------------ the inventory
def test_the_builtin_table_is_used_when_the_inventory_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(F, "INVENTORY", tmp_path / "nope.json")
    hosts, source = F.load_hosts()
    assert hosts is F.DEFAULT_HOSTS
    assert "built-in" in source
    # the addresses MEASURED on 2026-09-11, after eran4 and eran2 both moved
    assert hosts["eran4"]["lan"] == "<lan-ip>"
    assert hosts["eran2"]["lan"] == "<lan-ip>"


def test_the_inventory_file_wins_when_it_exists(monkeypatch, tmp_path):
    inv = tmp_path / "fleet_inventory.json"
    inv.write_text('{"hosts": {"eran4": {"lan": "10.9.9.9"}}}', encoding="utf-8")
    monkeypatch.setattr(F, "INVENTORY", inv)
    hosts, source = F.load_hosts()
    assert hosts["eran4"]["lan"] == "10.9.9.9"
    assert str(inv) in source
    # merged, not replaced: the boxes it does not mention keep their measured addresses
    assert hosts["eran1"]["lan"] == "<lan-ip>"


def test_a_corrupt_inventory_does_not_take_the_probe_down(monkeypatch, tmp_path):
    """Another agent maintains that file. A half-written JSON must not turn into a dead
    probe -- it must turn into the built-in table plus a visible reason."""
    inv = tmp_path / "fleet_inventory.json"
    inv.write_text('{"hosts": {"eran4": ', encoding="utf-8")
    monkeypatch.setattr(F, "INVENTORY", inv)
    hosts, source = F.load_hosts()
    assert hosts is F.DEFAULT_HOSTS
    assert "unreadable" in source


# ------------------------------------------------------------------ the shape of an answer
def test_probe_returns_one_json_and_one_line(offline):
    res = F.probe(include_hosts=True, include_tailnet=True)
    assert res["read_only"] is True
    assert isinstance(res["summary"], str) and "VERIFIED" in res["summary"]
    assert len(res["doors"]) == len(F.DEFAULT_DOORS)
    import json
    json.dumps(res)          # it must really serialise -- it goes over stdio


def test_the_summary_names_what_is_broken():
    res = {"doors": [{"name": "480B", "verdict": "BROKEN"},
                     {"name": "QUORUM", "verdict": "VERIFIED"}],
           "hosts": [], "elapsed_s": 1.0, "tailnet": {"online": 6, "total": 10}}
    line = F.summarize(res)
    assert "480B" in line and "1/2 VERIFIED" in line and "6/10" in line


def test_it_is_read_only_by_construction():
    """No verb in this module may start, stop, restart or write anything on the fleet.
    Grep the source -- a future edit that adds one has to delete this test on purpose."""
    src = (F.Path(F.__file__)).read_text(encoding="utf-8")
    body = src.split('"""', 2)[-1]        # skip the module docstring, which discusses them
    for forbidden in ("systemctl start", "systemctl restart", "systemctl stop",
                      "subprocess.Popen", "shell=True"):
        assert forbidden not in body, forbidden


# ------------------------------------------------------------ the real inventory's schema
def test_the_inventory_spelling_is_translated_not_ignored():
    """fleet_inventory.json writes `lan_ip` / `tailnet_ip`; this module and every door
    template use `lan` / `tailscale`. Without the translation the inventory would parse
    fine and change NOTHING -- the built-in (and eventually stale) addresses would keep
    winning, which is the exact bug the inventory was created to end."""
    out = F._normalise({"lan_ip": "10.1.1.1", "tailnet_ip": "<tailnet-ip>", "ssh": "box"})
    assert out["lan"] == "10.1.1.1"
    assert out["tailscale"] == "<tailnet-ip>"
    assert out["ssh"] == "box"


def test_a_device_with_no_shell_is_skipped_not_called_broken(monkeypatch, tmp_path):
    """The printer, the phone, the Quest and the A70 are in the inventory with ssh: null.
    Sshing them produced four confident BROKEN rows for things that were never broken."""
    inv = tmp_path / "fleet_inventory.json"
    inv.write_text('{"hosts": {"printer": {"lan_ip": "<lan-ip>", "ssh": null},'
                   ' "eran1": {"lan_ip": "<lan-ip>", "ssh": "eran1"}}}', encoding="utf-8")
    monkeypatch.setattr(F, "INVENTORY", inv)
    monkeypatch.setattr(F, "_http", lambda url, timeout: {"code": 200, "ms": 1})
    monkeypatch.setattr(F, "probe_host", lambda n, i, t: {"host": n, "verdict": "VERIFIED"})
    monkeypatch.setattr(F, "tailnet", lambda t: {"verdict": "VERIFIED", "nodes": [], "online": 0, "total": 0})
    monkeypatch.setattr(F, "ramchat", lambda t: {"verdict": "VERIFIED"})
    res = F.probe(doors=[], include_hosts=True, include_tailnet=False)
    by = {h["host"]: h for h in res["hosts"]}
    assert by["printer"]["verdict"] == "SKIPPED"
    assert "no ssh" in by["printer"]["why"]
    assert by["eran1"]["verdict"] == "VERIFIED"
    # and a SKIPPED row must not drag the headline down: the four DGX boxes merged in from
    # the built-in table are the only ones counted, and none of them is BROKEN.
    assert "4/4 VERIFIED" in res["summary"]
    assert "BROKEN" not in res["summary"]
