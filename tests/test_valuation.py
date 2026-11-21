from decimal import Decimal

import pytest

from src.equitylens.valuation import Scenario, discount_cash_flows, sensitivity


def test_no_growth_perpetuity_matches_known_value():
    case = Scenario(Decimal(0), 5, Decimal("0.10"), Decimal(0))
    result = discount_cash_flows(Decimal(100), case)
    assert result.forecast_cash_flows == (100,) * 5
    assert float(result.total_present_value) == pytest.approx(1000)


def test_sensitivity_responds_to_terminal_growth_and_discount_rate():
    cases = list(sensitivity(
        Decimal(100), Decimal("0.05"), 5,
        (Decimal("0.08"), Decimal("0.12")), (Decimal("0.01"), Decimal("0.03")),
    ))
    slow_growth_low_rate, fast_growth_low_rate, slow_growth_high_rate, _ = [
        result.total_present_value for _, result in cases
    ]
    assert fast_growth_low_rate > slow_growth_low_rate > slow_growth_high_rate


@pytest.mark.parametrize("base,scenario", [
    (Decimal(-1), Scenario(Decimal(0), 5, Decimal("0.10"), Decimal(0))),
    (Decimal(100), Scenario(Decimal(0), 0, Decimal("0.10"), Decimal(0))),
    (Decimal(100), Scenario(Decimal(0), 5, Decimal("0.02"), Decimal("0.02"))),
    (Decimal(100), Scenario(Decimal(-1), 5, Decimal("0.10"), Decimal(0))),
])
def test_ineligible_valuation_inputs_are_rejected(base, scenario):
    with pytest.raises(ValueError):
        discount_cash_flows(base, scenario)
