"""Streamlit entry point for the EquityLens Research Atelier."""

import logging
from pathlib import Path
import sys

import streamlit as st

# The Streamlit console script adds app/ to sys.path. Imports use the repository root.
ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data import ISSUERS, NAMES, workbench
from app.presentation import hero, period_note, rule, stylesheet
from src.equitylens.bootstrap import BootstrapError, ensure_data


@st.cache_resource(show_spinner="Preparing the verified SEC snapshot…")
def prepare_snapshot():
    ensure_data()
    return True


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
try:
    prepare_snapshot()
except BootstrapError:
    logging.getLogger(__name__).exception("EquityLens snapshot initialization failed.")
    st.error("The bundled SEC snapshot could not be initialized. Check the app logs for the failed step, then reload to retry.")
    st.stop()
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
