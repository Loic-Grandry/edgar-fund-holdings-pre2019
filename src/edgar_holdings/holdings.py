"""
From a raw filing to a clean holdings table.

This ties the pieces together. Given the HTML of one filing, it reads the tables,
keeps the schedules of investments, extracts holding rows from each, classifies
every row by asset class, drops the rows that are accounting noise, and computes
each holding's weight as its market value over the table total.

The result is one tidy DataFrame, one row per holding, with a weight column that
sums to roughly one hundred within each schedule.
"""
from __future__ import annotations

import pandas as pd

from .classify import classify
from .extract import DEFAULT_OPTS, extract_holdings
from .tables import read_tables

# Rows in these classes are not real holdings and are removed.
_DROP_CLASSES = {"NOISE", "ACCOUNTING"}

_COLUMNS = ["security_name", "asset_class", "market_value", "shares",
            "pct_assets", "cusip", "weight_pct", "source_table"]


def holdings_from_html(html: str, opts: dict | None = None) -> pd.DataFrame:
    """Extract a clean holdings table from one filing's HTML.

    Parameters
    ----------
    html:
        The filing document text.
    opts:
        Extraction options passed through to :func:`extract_holdings`.

    Returns
    -------
    A DataFrame with one row per holding, including asset class and a weight in
    percent. The weight is a holding's market value over the filing total, so it
    sums to roughly one hundred across the portfolio.

    This assumes the filing covers a single fund, which is the common case for a
    standalone registrant. A trust filing that bundles several funds needs an
    extra step first, attributing each schedule to its fund using the fund name
    printed above it, before weights can be computed per fund.
    """
    opts = opts or DEFAULT_OPTS
    tables = read_tables(html)

    records = []
    for table_index, item in enumerate(tables):
        if item["label"] != "SoI":
            continue
        rows = extract_holdings(item["table"], opts)
        if not rows:
            continue
        for row in rows:
            asset_class = classify(row.get("security_name") or "")
            if asset_class in _DROP_CLASSES:
                continue
            records.append({
                "security_name": row.get("security_name"),
                "asset_class": asset_class,
                "market_value": row.get("market_value"),
                "shares": row.get("shares"),
                "pct_assets": row.get("pct_assets"),
                "cusip": row.get("cusip"),
                "weight_pct": None,
                "source_table": table_index,
            })

    df = pd.DataFrame(records, columns=_COLUMNS)
    total_mv = df["market_value"].dropna().sum()
    if total_mv > 0:
        df["weight_pct"] = (df["market_value"] / total_mv * 100).round(6)
    return df
