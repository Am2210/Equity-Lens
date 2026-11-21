"""Selected issuer's statement overview and traceable trend observations."""

import pandas as pd
import streamlit as st

from app.data import NAMES, scope, shown, workbench
from app.presentation import chart, ledger, source_link

book = workbench()
ticker, year = scope()
row = book.row(ticker, year)
company = NAMES[ticker]

st.header(f"{company} financial performance", anchor=False)
st.caption(f"FY{year} · Amounts in USD millions · " + source_link(row, "Original SEC 10-K"))
growth_detail = (f"{shown(row.revenue_growth, '%', signed=True)} year over year"
                 if pd.notna(row.revenue_growth) else "No prior year in scope")
margin_detail = (f"{shown(row.operating_margin_change, 'percentage points', signed=True)} year over year"
                 if pd.notna(row.operating_margin_change) else "No prior year in scope")
ledger(
    ("Revenue", shown(row.revenue, "USD millions"), growth_detail),
    ("Operating margin", shown(row.operating_margin, "%"), margin_detail),
    ("Free cash flow", shown(row.free_cash_flow, "USD millions"),
     f"{shown(row.free_cash_flow_margin, '%')} of revenue"),
)

st.subheader("Financial trends", anchor=False)
history = book.history((ticker,), year)
left, center, right = st.columns(3)
for area, field in (
    (left, "revenue"), (center, "operating_margin"), (right, "free_cash_flow"),
):
    with area:
        chart(history, field, year, ticker, key=f"overview_{field}", height=235)

st.subheader("Research notes", anchor=False)
if pd.notna(row.revenue_growth):
    prior = book.row(ticker, int(row.comparison_fiscal_year))
    direction = "rose" if row.revenue_growth > 0 else "fell" if row.revenue_growth < 0 else "was flat"
    change = f" {shown(abs(row.revenue_growth), '%')}" if row.revenue_growth else ""
    st.markdown(f"**Revenue {direction}{change} year over year.** "
                f"{source_link(prior)} · {source_link(row)}")
if pd.notna(row.free_cash_flow):
    st.markdown(f"**Free cash flow was USD {shown(row.free_cash_flow, 'USD millions')} million.** "
                f"Operating cash flow of {shown(row.operating_cash_flow, 'USD millions')} million less "
                f"capital expenditure of {shown(row.capex, 'USD millions')} million. {source_link(row)}")
