from django.core.checks import run_checks


def test_django_system_checks_pass() -> None:
    errors = run_checks()
    assert errors == []
