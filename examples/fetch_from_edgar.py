"""
Fetch a fund's holdings filings from EDGAR and extract one.

This needs network access and a contact string for the SEC. Set your own email:

    export EDGAR_USER_AGENT="Your Name your.email@example.com"
    python examples/fetch_from_edgar.py            # New Alternatives Fund
    python examples/fetch_from_edgar.py 355767     # any fund filer CIK

It lists the filer's recent holdings filings, downloads the most recent pre 2019
N-Q, and prints the extracted portfolio.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from edgar_holdings import holdings_from_html
from edgar_holdings.fetch import download, list_holdings_filings, user_agent

DEFAULT_CIK = 355767  # New Alternatives Fund


def main() -> None:
    cik = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CIK
    print(f"User-Agent sent to EDGAR: {user_agent()}")

    filings = list_holdings_filings(cik, limit=40)
    pre2019_nq = [f for f in filings if f["form"] == "N-Q" and f["date"] < "2019"]
    target = pre2019_nq[0] if pre2019_nq else (filings[0] if filings else None)
    if target is None:
        print(f"No holdings filing found for CIK {cik}.")
        return

    print(f"\nExtracting {target['form']} filed {target['date']}")
    print(f"  {target['url']}")
    html = download(target["url"])
    holdings = holdings_from_html(html)

    print(f"\n{len(holdings)} holdings, total {holdings['market_value'].sum():,.0f} US dollars")
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 52)
    top = holdings.sort_values("weight_pct", ascending=False).head(10)
    print(top[["security_name", "asset_class", "weight_pct"]].to_string(index=False))


if __name__ == "__main__":
    main()
