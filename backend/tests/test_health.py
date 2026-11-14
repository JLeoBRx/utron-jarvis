import pytest

from safra.monitoring.health import HealthRegistry


def test_all_ok():
    registry = HealthRegistry()
    registry.register("a", lambda: True)
    registry.register("b", lambda: (True, "tudo certo"))
    report = registry.report()
    assert report.status == "ok" and [c.name for c in report.checks] == ["a", "b"]
    assert report.as_dict()["checks"][1]["detail"] == "tudo certo"


def test_non_critical_failure_degrades_and_critical_failure_fails():
    registry = HealthRegistry()
    registry.register("voz", lambda: (False, "sem microfone"), critical=False)
    assert registry.report().status == "degraded"
    registry.register("banco", lambda: False)
    assert registry.report().status == "failed"


def test_a_check_that_raises_is_isolated_and_does_not_leak_its_message():
    def broken():
        raise RuntimeError("caminho interno /segredo/x")

    registry = HealthRegistry()
    registry.register("quebrada", broken, critical=False)
    registry.register("boa", lambda: True)
    report = registry.report()
    assert report.status == "degraded"
    broken_result = report.checks[0]
    assert not broken_result.ok and "segredo" not in broken_result.detail and "RuntimeError" in broken_result.detail
    assert report.checks[1].ok


def test_duplicate_names_are_refused():
    registry = HealthRegistry()
    registry.register("a", lambda: True)
    with pytest.raises(ValueError):
        registry.register("a", lambda: True)
