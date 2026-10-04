from decimal import Decimal

import pytest

from app.risk.position_size import floor_step, position_size
from app.risk.risk_manager import RiskManager
from tests.conftest import make_signal

D = Decimal


@pytest.mark.parametrize(
    "action,stop,tp", [("LONG", "98000", "103000"), ("SHORT", "102000", "97000")]
)
def test_risk_one_percent_not_five_percent(settings, action, stop, tp):
    plan = RiskManager(settings).plan(make_signal(action=action, stop_loss=stop), D(1000), D(1000))
    assert plan.quantity == D("0.005")
    assert plan.risk_budget == D(10)
    assert plan.estimated_loss == D(10)
    assert plan.take_profit == D(tp)
    assert plan.notional == D(500)


def test_fees_and_slippage_are_budgeted(settings):
    settings.paper_fee_rate = D("0.0005")
    settings.paper_slippage_bps = D(2)
    plan = RiskManager(settings).plan(make_signal(), D(1000), D(1000))
    assert plan.entry == D(100020)
    assert plan.quantity == D("0.004")
    assert plan.estimated_loss <= plan.risk_budget


def test_balance_is_dynamic(settings):
    risk = RiskManager(settings)
    assert risk.plan(make_signal(), D(2000), D(2000)).quantity == D("0.010")
    assert risk.plan(make_signal(), D(500), D(500)).quantity == D("0.002")


def test_max_notional_and_quantity(settings):
    settings.max_notional = D(300)
    settings.max_quantity = D("0.002")
    plan = RiskManager(settings).plan(make_signal(), D(10000), D(10000))
    assert plan.quantity == D("0.002")
    assert plan.notional <= settings.max_notional


def test_margin_cap(settings):
    settings.max_notional = D(100000)
    settings.max_quantity = D(10)
    plan = RiskManager(settings).plan(make_signal(stop_loss="99999"), D(1000), D(1000))
    assert plan.notional / settings.leverage <= D(900)
    assert plan.estimated_loss <= D(10)


@pytest.mark.parametrize("balance", ["0", "-1"])
def test_no_funds(settings, balance):
    with pytest.raises(ValueError):
        RiskManager(settings).plan(make_signal(), D(balance), D(balance))


def test_reject_quantity_below_minimum(settings):
    with pytest.raises(ValueError, match="minimums"):
        RiskManager(settings).plan(make_signal(), D(1), D(1))


def test_round_non_power_of_ten_step():
    assert floor_step(D("0.016"), D("0.005")) == D("0.015")
    assert position_size(D(10), D(100), D("0.099"), D("0.005")) == D("0.095")


def test_tick_rounding_cannot_increase_short_risk(settings):
    plan = RiskManager(settings).plan(
        make_signal(action="SHORT", stop_loss="102000.09"), D(1000), D(1000)
    )
    assert plan.stop_loss == D(102000)
    assert plan.estimated_loss <= D(10)
