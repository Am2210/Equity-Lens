"""Financial statements, formula definitions and XBRL source lineage."""

import pandas as pd
import streamlit as st

from app.data import MEASURES, STATEMENTS, fiscal_date, scope, shown, statement_rows, workbench
from app.presentation import download, number_table, rule, source_link

book = workbench()
ticker, year = scope()
row = book.row(ticker, year)

group = st.segmented_control("Statement", list(STATEMENTS), default="Income statement",
                             selection_mode="single", key="statement_group")
group = group or "Income statement"
fields = STATEMENTS[group]

st.subheader(group, anchor=False)
st.caption(f"FY{year} · {source_link(row, 'Original 10-K')} · Accession {row.original_accession}")
frame = pd.DataFrame([
    {"Metric": MEASURES[field].name, "Value": shown(row[field], MEASURES[field].unit),
     "Unit": MEASURES[field].unit, "Definition": MEASURES[field].definition}
    for field in fields
])
number_table(frame, key="statement_values", numeric_columns=("Value",))
tag = group.lower().replace(" & ", "-").replace(" ", "-")
download("Download statement CSV", statement_rows(book, ticker, year, fields),
         f"equitylens-{ticker.lower()}-fy{year}-{tag}.csv", key="statement_download")

rule()
st.subheader("Inspect a metric", anchor=False)
metric = st.selectbox("Metric to inspect", fields, format_func=lambda field: MEASURES[field].name,
                      key=f"lineage_metric_{tag}")
measure = MEASURES[metric]
st.markdown(f"**{measure.name}** · {measure.definition}")
lineage = book.sources(ticker, year, metric)
if pd.isna(row[metric]):
    if metric == "interest_bearing_debt":
        st.info("The mapped total is unavailable because a required debt component is missing. "
                "Identified components are shown when disclosed in the indexed facts.")
    elif measure.prior_year and pd.isna(row.comparison_fiscal_year):
        st.info("This calculation requires a prior annual observation outside the selected series.")
    else:
        st.info("An eligible value is unavailable for this annual period.")

if lineage.empty:
    st.caption("No eligible selected facts are available for this metric.")
else:
    display = lineage[
        ["fiscal_year", "input_metric", "tag", "source_value", "unit", "coefficient",
         "start_date", "end_date", "filed", "accession", "filing_url"]
    ].rename(columns={
        "fiscal_year": "Report FY", "input_metric": "Input", "tag": "XBRL concept",
        "source_value": "Raw value", "unit": "Unit", "coefficient": "Weight",
        "start_date": "Fact start", "end_date": "Fact end", "filed": "Filed",
        "accession": "Accession", "filing_url": "SEC filing",
    })
    for column in ("Fact start", "Fact end", "Filed"):
        display[column] = display[column].map(lambda date: fiscal_date(date) if pd.notna(date) else None)
    st.dataframe(
        display, width="stretch", hide_index=True, key="statement_lineage",
        height=min(415, 38 + len(display) * 35),
        column_config={"SEC filing": st.column_config.LinkColumn(display_text="Open filing"),
                       "Report FY": st.column_config.NumberColumn(format="%d")},
    )
    st.caption("Weights identify signed inputs to standardized statement amounts. The selected ratio formula appears above.")
    download("Download source lineage CSV", lineage, f"equitylens-{ticker.lower()}-fy{year}-{metric}-sources.csv",
             key="lineage_download")
