"""
Tests for the holdings pipeline. Run with: python -m pytest
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from edgar_holdings import classify, holdings_from_html, read_tables, repair_header

SAMPLE = ROOT / "data" / "sample_new_alternatives_fund_2018_nq.htm"
HTML = SAMPLE.read_text(encoding="utf-8")


def test_parse_number_handles_accounting_notation():
    from edgar_holdings.patterns import parse_number
    assert parse_number("1,234,567.89") == 1234567.89
    assert parse_number("(1,234)") == -1234
    assert parse_number("$500") == 500
    assert parse_number("—") is None
    assert parse_number("12.5%") == 12.5


def test_classifier_separates_real_companies_from_subtotals():
    # Subtotals and accounting footers are dropped.
    assert classify("Total Common Stocks") == "ACCOUNTING"
    assert classify("Total Alternate Energy") == "ACCOUNTING"
    assert classify("Other Assets in Excess of Liabilities") == "ACCOUNTING"
    # Companies whose name starts with Total must survive.
    assert classify("Total S.A.") == "EQUITY_OR_UNKNOWN"
    assert classify("Total System Services, Inc.") == "EQUITY_OR_UNKNOWN"


def test_classifier_asset_classes():
    assert classify("US Treasury Note 2.5% due 2027") == "BOND"
    assert classify("Vanguard Total Bond Market ETF") == "FUND"
    assert classify("Republic of Indonesia") == "SOVEREIGN"
    assert classify("Cash and Cash Equivalents") == "CASH"


def test_header_repair_promotes_a_text_row():
    # A table with no header, first row carries the labels.
    df = pd.DataFrame([
        ["Security", "Shares", "Value"],
        ["Apple Inc.", "100", "15000"],
        ["Microsoft Corp.", "50", "20000"],
    ])
    repaired = repair_header(df)
    assert "Security" in repaired.columns
    assert len(repaired) == 2


def test_end_to_end_on_sample_filing():
    holdings = holdings_from_html(HTML)
    # A real renewable energy fund with dozens of holdings.
    assert len(holdings) > 30
    # Weights are computed over the whole portfolio and sum to about 100.
    assert abs(holdings["weight_pct"].sum() - 100.0) < 0.5
    # No accounting subtotal leaked in as a large holding.
    assert holdings["weight_pct"].max() < 15.0
    # Recognisable renewable energy names came through.
    names = " ".join(holdings["security_name"].str.lower())
    assert "brookfield renewable" in names
    assert "vestas" in names


def test_soi_tables_are_detected():
    tables = read_tables(HTML)
    labels = [t["label"] for t in tables]
    assert "SoI" in labels
