"""
edgar_holdings
==============

Recover the portfolio of a US mutual fund from a pre 2019 SEC filing.

Before the structured N-PORT form arrived in 2019, funds disclosed their holdings
as HTML tables inside N-Q and N-CSR filings, formatted differently by every fund
family. This package reads that raw HTML and returns a clean holdings table with
asset classes and weights.

Typical use::

    from edgar_holdings import holdings_from_html
    from edgar_holdings.fetch import download

    html = download(filing_url)
    holdings = holdings_from_html(html)
    print(holdings.head())
"""
from __future__ import annotations

from .classify import CATEGORIES, classify
from .extract import extract_holdings
from .holdings import holdings_from_html
from .tables import classify_table, read_tables, repair_header

__all__ = [
    "holdings_from_html",
    "read_tables",
    "classify_table",
    "repair_header",
    "extract_holdings",
    "classify",
    "CATEGORIES",
]
