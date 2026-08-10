"""Unit tests for the CAGR / XIRR math (no DB needed)."""
import pytest
import returns


def test_cagr_doubling_two_years():
    c = returns.cagr(100000, 200000, '2024-07-21', '2026-07-21')
    assert c is not None and abs(c - 0.4142) < 0.01     # ~41.4%/yr


def test_cagr_none_without_dates_or_loss_of_capital():
    assert returns.cagr(100, 200, None) is None
    assert returns.cagr(0, 200, '2020-01-01') is None


def test_xirr_simple():
    r = returns.xirr([('2024-07-21', -100000), ('2026-07-21', 130000)])
    assert r is not None and abs(r - 0.14) < 0.01       # ~14%


def test_xirr_needs_both_signs():
    assert returns.xirr([('2024-01-01', -100), ('2025-01-01', -100)]) is None
    assert returns.xirr([('2024-01-01', 100)]) is None


def test_years_between():
    assert returns.years_between('2024-01-01', '2025-01-01') == pytest.approx(1.0, abs=0.01)
