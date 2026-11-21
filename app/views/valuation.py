"""Interactive hypothetical DCF scenarios using the validated valuation functions."""

from decimal import Decimal

import pandas as pd
import streamlit as st

from app.data import MEASURES, NAMES, USD_MILLION, scope, shown, workbench
from app.presentation import PLOT_CONFIG, download, forecast_figure, ledger, rule, source_link
from src.equitylens.valuation import Scenario, discount_cash_flows

book = workbench()
ticker, year = scope()
row = book.row(ticker, year)
company = NAMES[ticker]

st.subheader("Illustrative cash flow scenarios", anchor=False)
st.caption(f"{company} FY{year} starting free cash flow · {source_link(row, 'Original SEC 10-K')}")
st.markdown(
    "Discount a hypothetical cash flow stream using reported free cash flow as a proxy. "
    "An equity or per-share valuation would require a defined cash flow basis and adjustments for debt, excess cash, and share count."
)

growth_col, horizon_col, discount_col, terminal_col = st.columns(4)
with growth_col:
    growth = st.number_input("Annual cash flow growth (%)", min_value=-90.0, max_value=50.0, value=5.0,
                             step=0.5, key="dcf_growth")
with horizon_col:
    years = st.number_input("Forecast years", min_value=1, max_value=15, value=5, step=1, key="dcf_years")
with discount_col:
    discount = st.number_input("Discount rate (%)", min_value=0.5, max_value=50.0, value=10.0,
                               step=0.5, key="dcf_discount")
with terminal_col:
    terminal = st.number_input("Terminal growth (%)", min_value=-20.0, max_value=25.0, value=2.0,
                               step=0.5, key="dcf_terminal")

scenario = Scenario(Decimal(str(growth)) / 100, years, Decimal(str(discount)) / 100,
                    Decimal(str(terminal)) / 100)
base = Decimal(str(row.free_cash_flow)) if pd.notna(row.free_cash_flow) else None
if base is None or base <= 0:
    st.info("This scenario requires a positive, available annual free cash flow proxy.")
elif discount <= terminal:
    st.warning("Set the discount rate above terminal growth to calculate present value.")
else:
    result = discount_cash_flows(base, scenario)
    terminal_share = result.terminal_present_value / result.total_present_value
    ledger(
        ("Base free cash flow", shown(base, "USD millions"), f"Derived from FY{year} · USD millions"),
        ("Illustrative proxy present value", shown(result.total_present_value, "USD millions"), "USD millions"),
        ("Terminal share of present value", shown(terminal_share, "%"), "Under the selected assumptions"),
    )
    forecast, sensitivity = st.columns([1, 1.03])
    with forecast:
        st.plotly_chart(forecast_figure(result), config=PLOT_CONFIG, theme=None, width="stretch", key="dcf_forecast")
        st.caption(f"Forecast PV USD {shown(result.forecast_present_value, 'USD millions')} million · "
                   f"Terminal PV USD {shown(result.terminal_present_value, 'USD millions')} million")
    with sensitivity:
        st.subheader("Present value sensitivity", anchor=False)
        st.caption("USD millions · Discount rates by row · Terminal growth by column")
        discounts = sorted({max(Decimal("0.005"), scenario.discount_rate + Decimal(delta))
                            for delta in ("-0.02", "-0.01", "0", "0.01", "0.02")})
        terminals = [scenario.terminal_growth + Decimal(delta) for delta in ("-0.01", "-0.005", "0", "0.005", "0.01")]
        values = []
        for rate in discounts:
            for terminal_rate in terminals:
                alternative = Scenario(scenario.forecast_growth, years, rate, terminal_rate)
                present_value = (float(discount_cash_flows(base, alternative).total_present_value / USD_MILLION)
                                 if rate > terminal_rate else None)
                values.append({
                    "Issuer": company, "Base FY": year, "Base FCF (USD millions)": float(base / USD_MILLION),
                    "Discount rate (%)": float(rate * 100), "Terminal growth (%)": float(terminal_rate * 100),
                    "Forecast growth (%)": growth, "Forecast years": years, "Proxy PV (USD millions)": present_value,
                })
        raw = pd.DataFrame(values)
        matrix = raw.pivot(index="Discount rate (%)", columns="Terminal growth (%)", values="Proxy PV (USD millions)")
        matrix.index = [f"{value:g}%" for value in matrix.index]
        matrix.columns = [f"{value:g}%" for value in matrix.columns]
        matrix.index.name = "Discount rate"
        st.dataframe(matrix.style.highlight_null(color="#F0EBDF").format("{:,.0f}", na_rep="—"),
                     width="stretch", key="dcf_sensitivity")
        download("Download sensitivity CSV", raw, f"equitylens-{ticker.lower()}-fy{year}-dcf.csv", key="dcf_download")

rule()
st.subheader("Methodology and data limits", anchor=False)
with st.expander("Valuation method", expanded=True):
    st.markdown(
        "The selected fiscal year’s free cash flow anchors the forecast. Annual growth applies beginning in Year 1. "
        "The engine discounts each year-end cash flow and a Gordon-growth terminal amount from the end of the forecast. "
        "Cells where terminal growth equals or exceeds the discount rate are unavailable."
    )
with st.expander("Financial definitions"):
    for field in ("revenue_growth", "operating_margin", "net_profit_margin", "return_on_assets",
                  "asset_turnover", "free_cash_flow", "free_cash_flow_margin", "ocf_to_net_income"):
        item = MEASURES[field]
        st.markdown(f"**{item.name}** · {item.definition}")
with st.expander("Filing basis and research coverage"):
    st.markdown(
        f"The filing-date cutoff is **{book.cutoff}**, inclusive. Financial amounts use the original 10-K for each "
        "issuer-year. Later comparative figures remain distinguishable in the research assistant. Visa closes "
        "September 30, while Mastercard and PayPal close December 31. The local text index contains Business, "
        "Risk Factors, and Management’s Discussion and Analysis. Missing values remain blank in downloads."
    )
