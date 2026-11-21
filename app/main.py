"""Streamlit entry point for the EquityLens Research Atelier."""

import streamlit as st

from app.data import ISSUERS, NAMES, workbench
from app.presentation import hero, period_note, rule, stylesheet

st.set_page_config(page_title="EquityLens | The Research Atelier", layout="wide",
                   initial_sidebar_state="collapsed")

pages = [
    st.Page("views/overview.py", title="Research overview", default=True),
    st.Page("views/peers.py", title="Peer comparison", url_path="peers"),
    st.Page("views/statements.py", title="Financial statements", url_path="statements"),
    st.Page("views/research.py", title="Research assistant", url_path="research"),
    st.Page("views/valuation.py", title="Valuation & methodology", url_path="valuation"),
]
page = st.navigation(pages, position="top", expanded=True)
stylesheet()
book = workbench()
years = sorted(int(year) for year in book.annual.fiscal_year.unique())

if page.title == "Research overview":
    hero(years[0], years[-1], book.cutoff)
else:
    titles = {
        "Research assistant": "Research notebook",
        "Financial statements": "Financial statement explorer",
    }
    st.title(titles.get(page.title, page.title))

issuer_control, period_control, dates = st.columns([1.05, 0.72, 2.05], vertical_alignment="bottom")
with issuer_control:
    ticker = st.selectbox("Company", ISSUERS, format_func=lambda symbol: f"{NAMES[symbol]} · {symbol}",
                          key="scope_company")
with period_control:
    fiscal_year = st.selectbox("Fiscal year", list(reversed(years)), format_func=lambda year: f"FY{year}",
                               key="scope_year")
with dates:
    period_note(book.row(ticker, fiscal_year))
rule()
page.run()
