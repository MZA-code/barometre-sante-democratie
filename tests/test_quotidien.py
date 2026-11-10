import datetime as dt

import pytest

from ops import quotidien


def targets(day):
    return [t for t, _ in quotidien.steps(day)]


def test_every_source_is_collected_before_rebuild():
    plan = targets(dt.date(2026, 11, 5))  # jeudi
    assert plan[-4:] == ["rebuild", "prototype-data", "deployer", "publier-issues"]
    assert {
        "collect-an",
        "collect-legi",
        "collect-jorf",
        "collect-constit",
        "collect-datagouv",
    } <= set(plan)
    assert "verify-raw" not in plan


def test_archive_is_verified_on_sundays():
    assert targets(dt.date(2026, 11, 8))[-1] == "verify-raw"


def test_senate_is_collected_weekly_before_rebuild():
    sunday = targets(dt.date(2026, 11, 8))
    assert sunday.index("collect-senat") < sunday.index("rebuild")
    assert "collect-senat" not in targets(dt.date(2026, 11, 5))


def test_only_current_legislature_is_downloaded_daily():
    assert dict(quotidien.COLLECTES)["collect-an"] == ("AN_LEGISLATURES=17",)


NOUVEAUTES: list = []


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(quotidien, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(quotidien, "STATE_PATH", tmp_path / "exports" / "etat.json")
    monkeypatch.setattr(quotidien, "LOCK_PATH", tmp_path / ".lock")
    sent = []
    monkeypatch.setattr(quotidien, "notify", lambda title, body: sent.append((title, body)))
    monkeypatch.setattr(quotidien.nouveautes, "DEFAULT_DB_PATH", tmp_path / "t.sqlite")
    monkeypatch.setattr(
        quotidien.nouveautes,
        "run",
        lambda conn, day, echecs=(): NOUVEAUTES.append((day, echecs)) or {"nouveaux": 0},
    )
    monkeypatch.setattr(quotidien, "wait_for_network", lambda **_: True)
    NOUVEAUTES.clear()
    return sent


def fake_steps(failing=()):
    def run_step(target, variables, log):
        return {"etape": target, "code": 1 if target in failing else 0, "duree_s": 0.0}

    return run_step


def test_failure_sends_one_desktop_notification(isolated, monkeypatch):
    monkeypatch.setattr(quotidien, "run_step", fake_steps({"collect-jorf", "rebuild"}))
    assert quotidien.main([]) == 1
    assert len(isolated) == 1
    title, body = isolated[0]
    assert "échec" in title
    assert "collect-jorf" in body and "rebuild" in body and "make etat" in body


def test_success_sends_no_notification(isolated, monkeypatch):
    monkeypatch.setattr(quotidien, "run_step", fake_steps())
    assert quotidien.main([]) == 0
    assert isolated == []


def test_unexpected_error_is_notified_and_raised(isolated, monkeypatch):
    def boom(*_):
        raise OSError("disque plein")

    monkeypatch.setattr(quotidien, "run_step", boom)
    with pytest.raises(OSError):
        quotidien.main([])
    assert len(isolated) == 1 and "disque plein" in isolated[0][1]


def test_notify_never_raises_without_notify_send(monkeypatch):
    def missing(*_, **__):
        raise FileNotFoundError("notify-send")

    monkeypatch.setattr(quotidien.subprocess, "run", missing)
    quotidien.notify("titre", "texte")  # ne lève pas


def test_new_facts_are_summarized_only_after_a_successful_rebuild(isolated, monkeypatch):
    monkeypatch.setattr(quotidien, "run_step", fake_steps())
    quotidien.main([])
    assert len(NOUVEAUTES) == 1
    monkeypatch.setattr(quotidien, "run_step", fake_steps({"rebuild"}))
    quotidien.main([])
    assert len(NOUVEAUTES) == 1


def test_failed_collections_are_passed_to_the_summary(isolated, monkeypatch):
    monkeypatch.setattr(quotidien, "run_step", fake_steps({"collect-jorf", "collect-rsf"}))
    quotidien.main([])
    assert NOUVEAUTES[-1][1] == ["collect-jorf", "collect-rsf"]


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_network_wait_returns_as_soon_as_dns_answers():
    clock, calls = FakeClock(), []

    def resolve(host, port):
        calls.append(host)
        if len(calls) < 3:
            raise OSError("Temporary failure in name resolution")

    assert quotidien.wait_for_network(
        hosts=("a.example",),
        resolve=resolve,
        sleep=clock.sleep,
        clock=clock.monotonic,
        timeout_s=600,
        interval_s=15,
    )
    assert len(calls) == 3 and clock.now == 30


def test_network_wait_gives_up_after_timeout():
    clock = FakeClock()

    def resolve(host, port):
        raise OSError("Temporary failure in name resolution")

    assert not quotidien.wait_for_network(
        resolve=resolve, sleep=clock.sleep, clock=clock.monotonic, timeout_s=60, interval_s=15
    )
    assert clock.now == 60


def test_collections_run_even_without_network(isolated, monkeypatch):
    ran = []

    def run_step(target, variables, log):
        ran.append(target)
        return {"etape": target, "code": 0, "duree_s": 0.0}

    monkeypatch.setattr(quotidien, "wait_for_network", lambda **_: False)
    monkeypatch.setattr(quotidien, "run_step", run_step)
    quotidien.main([])
    assert "collect-an" in ran and "rebuild" in ran


def test_d7_titres_apres_gdelt_et_decisions_avant_rebuild():
    plan = targets(dt.date(2026, 11, 5))
    assert plan.index("collect-gdelt-trad") < plan.index("collect-titres") < plan.index("rebuild")
    assert plan.index("collect-decisions") < plan.index("rebuild")
    assert dict(quotidien.COLLECTES)["collect-gdelt-trad"] == ("GDELT_JOURS=10",)


def test_d7_flux_rss_collectes_chaque_jour():
    plan = targets(dt.date(2026, 11, 5))
    assert plan.index("collect-rss") < plan.index("rebuild")
