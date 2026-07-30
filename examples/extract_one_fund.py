"""
Extract one fund's portfolio from a real filing, offline.

This runs on a filing shipped with the repository, so it needs no network. It
walks through the pipeline stage by stage on the New Alternatives Fund N-Q from
late 2018, a standalone renewable energy fund, and prints what each stage does.

    python examples/extract_one_fund.py

The same filing can be scored live from EDGAR with examples/fetch_from_edgar.py.
"""
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from edgar_holdings import holdings_from_html, read_tables

SAMPLE = ROOT / "data" / "sample_new_alternatives_fund_2018_nq.htm"


def main() -> None:
    html = SAMPLE.read_text(encoding="utf-8")
    print(f"Filing: New Alternatives Fund, form N-Q, filed 2018-11-26")
    print(f"Raw HTML size: {len(html):,} characters")

    print("\nStage 1 and 2. Read every table and label it")
    tables = read_tables(html)
    labels = Counter(t["label"] for t in tables)
    print(f"  {len(tables)} tables found, labelled as: {dict(labels)}")
    print("  Only the tables labelled SoI are schedules of investments.")

    print("\nStage 3 to 5. Extract, classify and weight the holdings")
    holdings = holdings_from_html(html)
    print(f"  {len(holdings)} holdings kept after dropping accounting and noise rows")
    print(f"  asset classes: {dict(holdings['asset_class'].value_counts())}")
    total_mv = holdings["market_value"].sum()
    print(f"  total market value: {total_mv:,.0f} US dollars")
    print(f"  weights sum to {holdings['weight_pct'].sum():.1f} percent, as expected")

    print("\nLargest ten holdings by weight:")
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 52)
    top = holdings.sort_values("weight_pct", ascending=False).head(10)
    print(
        top[["security_name", "asset_class", "market_value", "weight_pct"]]
        .to_string(index=False)
    )

    out_csv = ROOT / "data" / "new_alternatives_holdings.csv"
    holdings.to_csv(out_csv, index=False)
    print(f"\nClean holdings table written to {out_csv.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
