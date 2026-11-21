"""Peer benchmarks retaining the companies' own fiscal reporting periods."""

import pandas as pd
import streamlit as st

from app.data import ISSUERS, MEASURES, NAMES, PEER_MEASURES, fiscal_window, scope, shown, statement_rows, workbench
from app.presentation import chart, download, number_table, source_link

book = workbench()
focus, year = scope()
tickers = (focus, *(ticker for ticker in ISSUERS if ticker != focus))
history = book.history(tickers, year)
peer_rows = {ticker: book.row(ticker, year) for ticker in tickers}

selector, context = st.columns([1, 2], vertical_alignment="bottom")
with selector:
    metric = st.selectbox("Trend metric", PEER_MEASURES, index=1,
                          format_func=lambda field: MEASURES[field].name, key="peer_metric")
with context:
    st.caption(f"Comparing original annual filings through FY{year}. Visa closes September 30. "
               "Mastercard and PayPal close December 31.")

chart(history, metric, year, focus, key="peer_trend", height=340)

st.subheader(f"FY{year} financial comparison", anchor=False)
table = pd.DataFrame([
    {"Metric": MEASURES[field].name, "Unit": MEASURES[field].unit,
     **{NAMES[ticker]: shown(peer_rows[ticker][field], MEASURES[field].unit) for ticker in tickers}}
    for field in PEER_MEASURES
])
number_table(table, key="peer_matrix", numeric_columns=tuple(NAMES[ticker] for ticker in tickers))
st.caption(" · ".join(
    f"{source_link(row, NAMES[ticker] + ' 10-K')} ({fiscal_window(row)})"
    for ticker, row in peer_rows.items()
))
download("Download peer comparison CSV",
         pd.concat([statement_rows(book, ticker, year, PEER_MEASURES) for ticker in tickers], ignore_index=True),
         f"equitylens-peers-fy{year}.csv", key="peer_download")

st.subheader("Profitability and cash generation", anchor=False)
profit, cash = st.columns(2)
with profit:
    chart(history, "operating_margin", year, focus, key="peer_profitability", height=270)
with cash:
    chart(history, "free_cash_flow", year, focus, key="peer_cash", height=270)
if metric != "revenue_growth":
    chart(history, "revenue_growth", year, focus, key="peer_growth", height=270)

st.subheader("Peer-relative observations", anchor=False)
available = [(ticker, row[metric]) for ticker, row in peer_rows.items() if pd.notna(row[metric])]
if len(available) == len(tickers):
    best = max(value for _, value in available)
    names = ", ".join(NAMES[ticker] for ticker, value in available if value == best)
    measure = MEASURES[metric]
    unit = f" {measure.unit}" if measure.unit == "USD millions" else ""
    st.markdown(f"**{names} recorded the highest {measure.name.lower()} in FY{year}** "
                f"at {shown(best, measure.unit)}{unit}. " +
                " · ".join(
                    source_link(book.row(ticker, filing_year), f"{NAMES[ticker]} FY{filing_year} 10-K")
                    for ticker in tickers for filing_year in (
                        [int(peer_rows[ticker].comparison_fiscal_year), year] if measure.prior_year else [year]
                    )
                ))
else:
    st.caption("A complete peer ranking is unavailable for this metric and fiscal year.")
st.caption("These measures describe reported performance across different operating models and fiscal windows.")
