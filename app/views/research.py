"""The offline research notebook, with filing evidence and a source register."""

from dataclasses import asdict
from html import escape
import sqlite3

import duckdb
import pandas as pd
import streamlit as st

from app.data import NAMES, answer, scope, shown, workbench
from app.presentation import download, rule, source_link
from src.equitylens.filings import INDEX


def use_prompt(question):
    st.session_state["research_draft"] = question


def evidence_table(result):
    citations = tuple(dict.fromkeys(citation for claim in result.claims for citation in claim.citations))
    if not citations:
        return
    refs = pd.DataFrame([asdict(citation) for citation in citations])
    display = refs[["company", "fiscal_year", "period_end", "filed", "form", "section", "metric", "locator", "url"]]
    with st.expander("Source register"):
        st.dataframe(
            display.rename(columns={
                "company": "Issuer", "fiscal_year": "FY", "period_end": "Period end", "filed": "Filed",
                "form": "Form", "section": "Section", "metric": "Metric", "locator": "Locator", "url": "SEC source",
            }),
            hide_index=True, width="stretch", key="notebook_source_register",
            column_config={"SEC source": st.column_config.LinkColumn(display_text="Open SEC filing"),
                           "FY": st.column_config.NumberColumn(format="%d")},
        )
        download("Download citations CSV", refs, "equitylens-research-citations.csv", key="notebook_citations")


book = workbench()
ticker, year = scope()
company = NAMES[ticker]
st.caption("Offline analytical mode · Verified financial calculations and original 10-K excerpts")

if not INDEX.is_file():
    st.info("The filing index is unavailable. Build it with the offline command in README.md, then reload.")
    st.stop()

main, side = st.columns([2.04, 1])
with main:
    with st.form("research_form", clear_on_submit=False, border=True):
        question = st.text_area("Research question", key="research_draft", height=105, max_chars=500,
                                placeholder=f"What was {company}'s FY{year} free cash flow?")
        asked = st.form_submit_button("Run research", type="primary")
    if asked:
        if question.strip():
            try:
                with st.spinner("Checking the local filings and financial tables…"):
                    st.session_state["notebook_result"] = ((ticker, year), question.strip(), answer(question.strip()))
            except (OSError, ValueError, duckdb.Error, sqlite3.Error):
                st.session_state.pop("notebook_result", None)
                st.error("The local sources could not be read together. Rebuild the index from the same analytics snapshot.")
        else:
            st.session_state.pop("notebook_result", None)
            st.info("Enter a question or choose a suggested one.")

    stored = st.session_state.get("notebook_result")
    result = stored[2] if stored and stored[0] == (ticker, year) and stored[1] == question.strip() else None
    if result is not None:
        st.subheader("Findings", anchor=False)
        for claim in result.claims:
            st.markdown(f"**{claim.kind}**\n\n{claim.text}")
            st.caption(" · ".join(
                f"[{citation.company} FY{citation.fiscal_year} · filed {citation.filed}]({citation.url})"
                for citation in claim.citations
            ))
        for limitation in result.limitations:
            st.info(limitation)
        for context in result.context:
            st.caption(context)
        evidence_table(result)

with side:
    st.subheader("Suggested questions", anchor=False)
    for label, prompt in (
        ("Free cash flow", f"What was {company}'s FY{year} free cash flow?"),
        ("Compare operating margins", f"Which company had the highest operating margin in FY{year}?"),
        ("Cybersecurity risks", f"What cybersecurity risks did {company} disclose in FY{year}?"),
    ):
        st.button(label, key=f"notebook_prompt_{label}", width="stretch", on_click=use_prompt, args=(prompt,))

    rule()
    st.subheader("Financial context", anchor=False)
    if result and result.claims:
        contexts = sorted({(citation.ticker, citation.fiscal_year) for claim in result.claims for citation in claim.citations},
                          key=lambda pair: (-pair[1], pair[0]))
        newest = {}
        for issuer, fiscal_year in contexts:
            newest.setdefault(issuer, fiscal_year)
        contexts = list(newest.items())
    else:
        contexts = [(ticker, year)]
    for issuer, fiscal_year in contexts:
        item = book.row(issuer, fiscal_year)
        values = (
            ("Revenue", shown(item.revenue, "USD millions")),
            ("Operating margin", shown(item.operating_margin, "%")),
            ("Free cash flow", shown(item.free_cash_flow, "USD millions")),
        )
        entries = "".join(f"<div><dt>{escape(label)}</dt><dd>{escape(value)}</dd></div>"
                          for label, value in values)
        st.html(f'<section class="atelier-context"><strong>{escape(NAMES[issuer])} · FY{fiscal_year}</strong>'
                f"<dl>{entries}</dl></section>")
        st.caption(f"Amounts in USD millions · {source_link(item, 'SEC 10-K')}")
