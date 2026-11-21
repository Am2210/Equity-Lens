"""Export numerical evidence, narrative observations and static research charts."""

import csv
from pathlib import Path

NAMES = {"V": "Visa", "MA": "Mastercard", "PYPL": "PayPal"}
EXPORTS = {
    "annual_financial_analytics": "ticker, fiscal_year",
    "statement_metrics": "cik, fiscal_year, metric",
    "statement_lineage": "ticker, fiscal_year, metric, input_metric",
    "peer_growth_summary": "ticker",
    "peer_benchmark": "ticker",
    "peer_insight_evidence": "insight, ticker",
    "illustrative_cash_flow_sensitivity": "ticker, discount_rate, terminal_growth",
}


def records(connection, query):
    result = connection.execute(query)
    names = [column[0] for column in result.description]
    return [dict(zip(names, values, strict=True)) for values in result.fetchall()]


def percent(value):
    return f"{value:.2%}" if value is not None else "unavailable"


def billions(value):
    return f"${value / 1_000_000_000:.3f}B" if value is not None else "unavailable"


def multiple(value):
    return f"{value:.2f}×" if value is not None else "unavailable"


def dispersion(value):
    return f"{value * 100:.2f} pp" if value is not None else "unavailable"


def insight_sentence(row):
    company = NAMES[row["ticker"]]
    year = row["fiscal_year"]
    first = row["from_year"]
    value = row["value"]
    context = row["context_value"]
    sentences = {
        "largest_revenue_increase": lambda: (
            f"{company} had the largest dollar revenue increase, {billions(value)} "
            f"from FY{first} to FY{year} ({percent(context)})."
        ),
        "largest_operating_margin_move": lambda: (
            f"{company} had the largest absolute operating margin move, "
            f"{value * 100:+.2f} percentage points from FY{first} to FY{year}, "
            f"ending at {percent(context)}."
        ),
        "highest_ocf_cagr": lambda: (
            f"{company} had the highest operating cash flow CAGR at {percent(value)} "
            f"over FY{first}–FY{year}."
        ),
        "highest_latest_operating_margin": lambda: (
            f"{company} had the highest FY{year} operating margin at {percent(value)}."
        ),
        "highest_latest_asset_turnover": lambda: (
            f"{company} had the highest FY{year} asset turnover at {multiple(value)}."
        ),
        "highest_latest_roa": lambda: (
            f"{company} had the highest FY{year} return on average assets at {percent(value)}."
        ),
        "largest_growth_consistency_shift": lambda: (
            f"{company} showed the largest absolute shift in revenue growth dispersion. "
            f"Sample standard deviation moved from {(context - value) * 100:.2f} pp "
            f"in FY{first}–FY{first + 1} to {context * 100:.2f} pp in FY{year - 1}–FY{year}. "
            "Each window contains two growth observations."
        ),
    }
    return sentences[row["insight"]]()


def write_peer_report(connection, directory):
    snapshot = connection.execute("SELECT as_of_date, first_fiscal_year, last_fiscal_year FROM analysis_snapshot").fetchone()
    cutoff, first, last = snapshot
    latest = records(connection, "SELECT * FROM peer_benchmark ORDER BY ticker")
    insights = records(connection, "SELECT * FROM peer_insight_evidence ORDER BY insight, ticker")
    rows = [
        "# EquityLens peer benchmarking", "",
        f"Original SEC annual filings for FY{first}–FY{last}. Filing-date cutoff {cutoff}.",
        "Visa closes September 30. Mastercard and PayPal close December 31. Each fiscal-year label follows its issuer's own reporting calendar.",
        "", f"## FY{last} comparisons and historical growth", "",
    ]
    for row in latest:
        rows.append(
            f"- **{NAMES[row['ticker']]}** ({row['period_end']}). "
            f"Revenue {billions(row['revenue'])}, with year-over-year growth of {percent(row['revenue_growth'])}. "
            f"FY{first}–FY{last} revenue CAGR {percent(row['revenue_cagr'])}. "
            f"Operating margin {percent(row['operating_margin'])} and net margin {percent(row['net_profit_margin'])}. "
            f"Operating cash flow {billions(row['operating_cash_flow'])} and free cash flow {billions(row['free_cash_flow'])} "
            f"({percent(row['free_cash_flow_margin'])} of revenue). "
            f"Return on average assets {percent(row['return_on_assets'])} and turnover {multiple(row['asset_turnover'])}. "
            f"Annual revenue growth sample standard deviation {dispersion(row['revenue_growth_stddev'])} "
            f"across {row['revenue_growth_observations']} observations."
        )
    rows.extend(["", "## Calculated observations", ""])
    rows.extend(f"- {insight_sentence(row)}" for row in insights)
    rows.extend([
        "", "## Basis for comparison", "",
        "Visa and Mastercard operate global payment networks. PayPal operates a digital payments platform that includes branded checkout, payment processing and consumer and merchant credit. Revenue presentation, asset composition, settlement balances and funding structures affect the ratios. Assessing business quality, market share or investment attractiveness requires additional evidence. [Visa FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/v-20250930.htm#) [Mastercard FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1141391/000114139126000013/ma-20251231.htm#) [PayPal FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1633917/000163391726000024/pypl-20251231.htm#)",
        "",
        "The volatility figures describe historical revenue growth dispersion. PayPal's later comparative cash flows and assets can differ from originally reported values. Each year uses its original filing and return on assets uses the average of opening and closing assets presented together in that filing.",
        "", "## Hypothetical cash-flow scenarios", "",
        "The sensitivity CSV uses FY2025 reported operating cash flow less defined CapEx as an unadjusted cash-flow proxy. It applies a hypothetical five-year forecast with 5% annual growth, discount rates of 8%, 10% and 12%, and terminal growth rates of 1%, 2% and 3%. These are illustrative proxy present values. The cash-flow basis, financing, excess cash, other adjustments and share counts have not been modeled for an equity or enterprise valuation.",
    ])
    (directory / "peer_benchmark.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_charts(connection, directory):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.ticker import PercentFormatter

    series = records(connection, "SELECT * FROM annual_financial_analytics ORDER BY fiscal_year, ticker")
    grouped = {ticker: [row for row in series if row["ticker"] == ticker] for ticker in NAMES}
    palette = {"V": "#1D538C", "MA": "#AD4A16", "PYPL": "#237467"}
    first, last = min(row["fiscal_year"] for row in series), max(row["fiscal_year"] for row in series)
    cutoff = connection.execute("SELECT as_of_date FROM analysis_snapshot").fetchone()[0]
    charts = {
        "revenue-profitability.png": (
            "Revenue growth and operating profitability",
            [
                ("revenue", "Reported revenue", "USD billions", "usd"),
                ("revenue_growth", "Year-over-year revenue growth", "Change (%)", "percent"),
                ("operating_margin", "Operating margin", "Operating income / revenue (%)", "percent"),
                ("net_profit_margin", "Net profit margin", "Net income / revenue (%)", "percent"),
            ],
        ),
        "cash-asset-efficiency.png": (
            "Cash generation and asset efficiency",
            [
                ("operating_cash_flow", "Operating cash flow", "USD billions", "usd"),
                ("free_cash_flow_margin", "Free cash flow margin", "FCF / revenue (%)", "percent"),
                ("return_on_assets", "Return on average assets", "Net income / average assets (%)", "percent"),
                ("asset_turnover", "Asset turnover", "Revenue / average assets (×)", "multiple"),
            ],
        ),
    }
    for filename, (title, panels) in charts.items():
        figure = Figure(figsize=(12, 7.5), dpi=160, facecolor="#FAFBFD")
        FigureCanvasAgg(figure)
        axes = figure.subplots(2, 2)
        for axis, (key, label, units, scale) in zip(axes.flat, panels, strict=True):
            for ticker, group in grouped.items():
                values = [float(row[key]) if row[key] is not None else float("nan") for row in group]
                if scale == "usd":
                    values = [value / 1_000_000_000 for value in values]
                axis.plot([row["fiscal_year"] for row in group], values, color=palette[ticker],
                          marker="o", linewidth=2.0, markersize=4, label=NAMES[ticker])
            axis.set_title(label, loc="left", weight="bold", fontsize=12)
            axis.set_ylabel(units, fontsize=9)
            axis.set_xlabel("Issuer fiscal year", fontsize=9)
            start = first + 1 if key == "revenue_growth" else first
            axis.set_xticks(range(start, last + 1), [f"FY{year}" for year in range(start, last + 1)])
            axis.set_xlim(start - 0.25, last + 0.25)
            if scale == "percent":
                axis.yaxis.set_major_formatter(PercentFormatter(xmax=1))
            axis.grid(axis="y", color="#D9DFE8", linewidth=0.6)
            axis.spines[["top", "right"]].set_visible(False)
        handles, labels = axes[0, 0].get_legend_handles_labels()
        figure.suptitle(title, x=0.08, y=0.966, ha="left", weight="bold", fontsize=21)
        figure.legend(handles, labels, loc="upper right", bbox_to_anchor=(0.985, 0.948), ncols=3, frameon=False)
        figure.text(0.08, 0.024, f"Source: SEC original 10-Ks · FY{first}–FY{last} · Cutoff {cutoff} · Visa closes September 30; MA and PYPL close December 31.",
                    fontsize=8.5, color="#36455A")
        figure.subplots_adjust(top=0.86, bottom=0.11, left=0.08, right=0.97, hspace=0.55, wspace=0.33)
        figure.savefig(directory / filename, facecolor=figure.get_facecolor())


def export_analytics(connection, directory: Path):
    counts = {}
    for name, order in EXPORTS.items():
        result = connection.execute(f"SELECT * FROM {name} ORDER BY {order}")
        rows = result.fetchall()
        with (directory / f"{name}.csv").open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(column[0] for column in result.description)
            writer.writerows(rows)
        counts[name] = len(rows)
    write_peer_report(connection, directory)
    write_charts(connection, directory)
    return counts
