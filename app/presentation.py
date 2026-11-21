"""Editorial UI components and shared Plotly formatting."""

from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.data import FOREST, INK, ISSUER_COLORS, MEASURES, NAMES, TERRACOTTA, USD_MILLION, fiscal_date, scaled, tabular_csv

BODY = "DM Sans, Arial, sans-serif"
SERIF = "Fraunces, Georgia, serif"
LINE = "#E5E0D6"
MUTED = "#535C54"
PLOT_CONFIG = {"displayModeBar": False, "scrollZoom": False}


def hero(first_year, last_year, cutoff):
    st.html(f"""
        <section class="atelier-hero" aria-labelledby="equitylens-title">
          <div class="atelier-hero__copy">
            <div class="atelier-hero__eyebrow">The Research Atelier</div>
            <h1 id="equitylens-title">EquityLens</h1>
            <p class="atelier-hero__subtitle">AI-Assisted Equity Research Workbench</p>
            <p class="atelier-hero__range">SEC 10-Ks · FY{first_year}–FY{last_year} · Cutoff {cutoff}</p>
          </div>
          <img class="atelier-hero__image" src="./app/static/atelier-architecture.webp" alt="">
        </section>
    """)


def stylesheet():
    st.html(Path(__file__).with_name("atelier.css"))


def rule():
    st.html('<hr class="atelier-rule">')


def period_note(row):
    st.html(f"""
        <div class="atelier-period">
            <strong>FY{row.fiscal_year} reporting period</strong>
            {fiscal_date(row.period_start)} to {fiscal_date(row.period_end)} · Filed {fiscal_date(row.original_filed)}
        </div>
    """)


def ledger(*entries):
    parts = [
        f'<div class="atelier-ledger__item"><div class="atelier-ledger__label">{escape(label)}</div>'
        f'<span class="atelier-ledger__value">{escape(value)}</span>'
        f'<div class="atelier-ledger__detail">{escape(detail)}</div></div>'
        for label, value, detail in entries
    ]
    st.html(f'<div class="atelier-ledger" style="--atelier-ledger-columns:{len(entries)};">{"".join(parts)}</div>')


def download(label, frame, filename, *, key=None):
    st.download_button(label, tabular_csv(frame), file_name=filename, mime="text/csv",
                       key=key, on_click="ignore")


def source_link(row, label=None):
    if pd.isna(row.filing_url):
        return f"Filing accession {row.original_accession}"
    return f"[{label or f'FY{row.fiscal_year} 10-K'}]({row.filing_url})"


def figure_layout(figure, title, y_label, height):
    figure.update_layout(
        template="none", height=height, title=dict(text=title, x=0.04, xanchor="left", y=0.96,
                                                  font=dict(family=SERIF, size=22, color=FOREST)),
        font=dict(family=BODY, color=INK, size=13), paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        margin=dict(l=56, r=22, t=62, b=48), hovermode="closest",
        hoverlabel=dict(bgcolor=FOREST, font=dict(family=BODY, color="#FFFFFF", size=13)),
        legend=dict(orientation="h", y=-0.18, x=0, font=dict(size=12)),
        xaxis=dict(showgrid=False, tickfont=dict(color=MUTED, size=11), linecolor=LINE, showline=True,
                   automargin=True, fixedrange=True),
        yaxis=dict(title=dict(text=y_label, font=dict(size=11, color=MUTED)), gridcolor=LINE,
                   zerolinecolor=LINE, tickfont=dict(color=MUTED, size=11), automargin=True, fixedrange=True),
    )
    return figure


def annual_figure(frame, field, fiscal_year, focus, *, height=280, title=None):
    measure = MEASURES[field]
    years = sorted(frame.fiscal_year.unique())
    populated_years = sorted(frame.loc[frame[field].notna(), "fiscal_year"].unique())
    if measure.prior_year and populated_years:
        years = [year for year in years if year >= populated_years[0]]
    labels = {
        "USD millions": ("USD millions", ",.0f", ",.0f", ""),
        "%": ("Percent", ".0%", ".2%", ""),
        "percentage points": ("Percentage points", ".1f", ".2f", " pp"),
        "×": ("Multiple", ".1f", ".2f", "×"),
    }
    axis_label, tick_format, hover_format, suffix = labels[measure.unit]
    figure = figure_layout(go.Figure(), title or measure.name, axis_label, height)
    colors = list(dict.fromkeys(frame.ticker))
    ordered = [ticker for ticker in [focus, *NAMES] if ticker in colors]
    for ticker in dict.fromkeys(ordered):
        selected = frame[frame.ticker.eq(ticker)].sort_values("fiscal_year")
        values = [scaled(value, measure.unit) for value in selected[field]]
        if all(value is None for value in values):
            continue
        figure.add_scatter(
            x=selected.fiscal_year.tolist(), y=values, name=NAMES[ticker], mode="lines+markers",
            connectgaps=False, line=dict(color=ISSUER_COLORS[ticker], width=3 if ticker == focus else 2.2),
            marker=dict(
                size=[9 if year == fiscal_year else 5 for year in selected.fiscal_year],
                line=dict(color="#FFFFFF", width=1.2),
                symbol={"V": "circle", "MA": "square", "PYPL": "diamond"}[ticker],
            ),
            customdata=[[fiscal_date(date), NAMES[ticker]] for date in selected.period_end],
            hovertemplate=(f"<b>%{{customdata[1]}}</b> · FY%{{x}}<br>%{{y:{hover_format}}}{suffix}"
                           f" {axis_label if measure.unit == 'USD millions' else ''}"
                           "<br>Period end %{customdata[0]}<extra></extra>"),
        )
    if not figure.data:
        figure.add_annotation(text="No eligible values in this fiscal window", font=dict(color=MUTED),
                              x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
        figure.update_yaxes(visible=False)
    figure.update_xaxes(tickmode="array", tickvals=years, ticktext=[f"FY{year}" for year in years],
                       range=[years[0] - 0.22, years[-1] + 0.22])
    figure.update_yaxes(tickformat=tick_format, ticksuffix=suffix)
    figure.update_layout(showlegend=len(figure.data) > 1)
    if len(figure.data) > 1:
        figure.update_layout(margin_b=68)
    return figure


def chart(frame, field, fiscal_year, focus, *, key, height=280, title=None):
    st.plotly_chart(annual_figure(frame, field, fiscal_year, focus, height=height, title=title),
                    theme=None, config=PLOT_CONFIG, width="stretch", key=key)


def forecast_figure(result):
    years = list(range(1, len(result.forecast_cash_flows) + 1))
    figure = figure_layout(go.Figure(), "Projected cash flow proxy", "USD millions", 275)
    for name, color, values in (
        ("Undiscounted", FOREST, result.forecast_cash_flows),
        ("Discounted", TERRACOTTA, result.discounted_forecast_cash_flows),
    ):
        figure.add_scatter(
            x=years, y=[float(value / USD_MILLION) for value in values], name=name, mode="lines+markers",
            marker=dict(size=7), line=dict(color=color, width=2.7),
            hovertemplate="%{y:,.0f} USD millions<extra>%{fullData.name}</extra>",
        )
    figure.update_layout(showlegend=True, margin_b=70)
    figure.update_xaxes(tickmode="array", tickvals=years, ticktext=[f"Year {year}" for year in years])
    figure.update_yaxes(tickformat=",.0f")
    return figure


def number_table(frame, *, key, numeric_columns=()):
    st.dataframe(frame, width="stretch", hide_index=True, key=key,
                 column_config={
                     name: st.column_config.TextColumn(width="medium")
                     for name in numeric_columns
                 },
                 height=min(390, 38 + len(frame) * 35))
