"""Illustrative discounted cash-flow proxy scenarios with hypothetical inputs."""

from dataclasses import dataclass
from decimal import Decimal, localcontext


@dataclass(frozen=True)
class Scenario:
    forecast_growth: Decimal
    forecast_years: int
    discount_rate: Decimal
    terminal_growth: Decimal


@dataclass(frozen=True)
class DiscountedCashFlows:
    forecast_cash_flows: tuple[Decimal, ...]
    discounted_forecast_cash_flows: tuple[Decimal, ...]
    forecast_present_value: Decimal
    terminal_present_value: Decimal
    total_present_value: Decimal


def discount_cash_flows(base_fcf: Decimal, scenario: Scenario) -> DiscountedCashFlows:
    """Project year-end cash flows; the output is a proxy present value in base units."""
    inputs = (base_fcf, scenario.forecast_growth, scenario.discount_rate, scenario.terminal_growth)
    if not all(value.is_finite() for value in inputs) or base_fcf <= 0:
        raise ValueError("A finite, positive base cash flow and finite rates are required.")
    if type(scenario.forecast_years) is not int or scenario.forecast_years < 1:
        raise ValueError("Forecast years must be a positive integer.")
    if scenario.forecast_growth <= -1 or scenario.terminal_growth <= -1:
        raise ValueError("Growth assumptions must be greater than -100%.")
    if scenario.discount_rate <= 0 or scenario.discount_rate <= scenario.terminal_growth:
        raise ValueError("The discount rate must be positive and exceed terminal growth.")

    with localcontext() as context:
        context.prec = 34
        years = range(1, scenario.forecast_years + 1)
        forecast = tuple(base_fcf * (1 + scenario.forecast_growth) ** year for year in years)
        discounted = tuple(
            cash_flow / (1 + scenario.discount_rate) ** year
            for year, cash_flow in zip(years, forecast, strict=True)
        )
        terminal_value = forecast[-1] * (1 + scenario.terminal_growth) / (
            scenario.discount_rate - scenario.terminal_growth
        )
        discounted_terminal = terminal_value / (1 + scenario.discount_rate) ** scenario.forecast_years
        forecast_pv = sum(discounted)
        return DiscountedCashFlows(
            forecast, discounted, forecast_pv, discounted_terminal, forecast_pv + discounted_terminal
        )


def sensitivity(base_fcf: Decimal, forecast_growth: Decimal, forecast_years: int,
                discount_rates: tuple[Decimal, ...], terminal_rates: tuple[Decimal, ...]):
    """Yield a long-form sensitivity grid keyed by discount and terminal growth."""
    for discount_rate in discount_rates:
        for terminal_rate in terminal_rates:
            scenario = Scenario(forecast_growth, forecast_years, discount_rate, terminal_rate)
            yield scenario, discount_cash_flows(base_fcf, scenario)
