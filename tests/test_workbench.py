"""Streamlit interaction checks against the built, validated research snapshot."""

from pathlib import Path
from shutil import copyfile

import duckdb
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.equitylens.filings import ANALYTICS, INDEX, WAREHOUSE
from app.data import _load_workbench, fingerprint

APP = Path(__file__).resolve().parents[1] / "app/main.py"
pytestmark = pytest.mark.skipif(
    not all(path.is_file() for path in (ANALYTICS, INDEX, WAREHOUSE)),
    reason="Build the frozen local warehouses and filing index using the README before UI tests.",
)


def start():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception
    return app


def html(app):
    return " ".join(element.proto.body for element in app.get("html"))


def buttons(app):
    return {button.label: button for button in app.button}


def test_scope_and_overview_history_carry_to_peer_page():
    app = start()
    assert "40,000" in html(app)
    assert len(app.get("plotly_chart")) == 3
    app.selectbox(key="scope_company").set_value("MA")
    app.selectbox(key="scope_year").set_value(2024)
    app.run()
    assert not app.exception
    assert "2024-01-01 to 2024-12-31" in html(app)
    assert "28,167" in html(app)
    app.switch_page("views/peers.py").run()
    assert not app.exception
    assert app.selectbox(key="scope_company").value == "MA"
    assert app.selectbox(key="scope_year").value == 2024
    app.selectbox(key="peer_metric").set_value("free_cash_flow_margin").run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 4
    assert app.dataframe[0].value.columns[2] == "Mastercard"
    assert "Download peer comparison CSV" in [element.proto.label for element in app.get("download_button")]


def test_statement_explorer_handles_missing_debt_and_exports_lineage():
    app = start()
    app.selectbox(key="scope_company").set_value("PYPL").run()
    app.switch_page("views/statements.py").run()
    assert not app.exception
    # Streamlit 1.52's AppTest serializes even a single-choice ButtonGroup as a list.
    app.button_group(key="statement_group").set_value(["Balance sheet"]).run()
    assert not app.exception
    app.button_group(key="statement_group").set_value(["Balance sheet"])
    app.selectbox(key="lineage_metric_balance-sheet").set_value("interest_bearing_debt").run()
    assert not app.exception
    assert any("required debt component is missing" in info.value for info in app.info)
    assert "LongTermDebtNoncurrent" in app.dataframe[1].value["XBRL concept"].tolist()
    assert "Download source lineage CSV" in [element.proto.label for element in app.get("download_button")]


def test_notebook_prompt_returns_real_answer_and_citations():
    app = start().switch_page("views/research.py").run()
    assert not app.exception
    buttons(app)["Free cash flow"].click().run()
    assert "Visa's FY2025" in app.text_area(key="research_draft").value
    buttons(app)["Run research"].click().run()
    assert not app.exception
    assert any("$21.577 billion" in text.value and "Derived calculation" in text.value for text in app.markdown)
    assert "https://www.sec.gov/" in app.dataframe[0].value["SEC source"].iloc[0]
    app.text_area(key="research_draft").set_value("What will Visa's stock price be next year?")
    buttons(app)["Run research"].click().run()
    assert any("do not establish an answer" in info.value for info in app.info)


def test_valuation_recalculates_and_rejects_invalid_rates():
    app = start().switch_page("views/valuation.py").run()
    assert not app.exception
    assert "312,049" in html(app)
    initial = app.dataframe[0].value.loc["10%", "2%"]
    app.number_input(key="dcf_discount").set_value(12.0).run()
    assert not app.exception
    assert app.dataframe[0].value.loc["12%", "2%"] < initial
    app.number_input(key="dcf_discount").set_value(2.0).run()
    assert not app.exception
    assert any("above terminal growth" in warning.value for warning in app.warning)
    assert not app.dataframe


def test_missing_revenue_keeps_issuer_year_and_other_filing_sources(tmp_path):
    database = tmp_path / "analytics.duckdb"
    copyfile(ANALYTICS, database)
    with duckdb.connect(str(database)) as connection:
        connection.execute("""
            DELETE FROM statement_lineage
            WHERE ticker = 'V' AND fiscal_year = 2025 AND metric = 'revenue'
        """)
        connection.execute("""
            UPDATE annual_financial_analytics SET revenue = NULL
            WHERE ticker = 'V' AND fiscal_year = 2025
        """)
    book = _load_workbench(fingerprint(database))
    row = book.row("V", 2025)
    assert pd.isna(row.revenue)
    assert row.operating_income == 23994000000
    assert row.filing_url.endswith("/v-20250930.htm")
