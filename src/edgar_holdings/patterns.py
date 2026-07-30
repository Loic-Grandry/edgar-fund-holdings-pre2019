"""
Shared parsing primitives and vocabulary.

This module holds the small, heavily reused building blocks that the rest of the
pipeline depends on: number parsing that understands accounting notation, the
column name patterns that map a messy header to a canonical field, the noise
vocabulary that removes accounting rows, and the forward fill helpers that
reattach a bond issuer to its coupon lines.

The regexes come from reading many real filings across fund families. They look
dense because filings are inconsistent. Each one is documented with the kind of
row it catches.
"""
from __future__ import annotations

import math
import re

import pandas as pd


def norm_col(name: str) -> str:
    """Normalise a column header to lowercase alphanumerics only.

    "% of Net Assets" becomes "ofnetassets", so small formatting differences
    between fund families stop mattering when we match column names.
    """
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def parse_number(value) -> float | None:
    """Parse a number written the way filings write them.

    Handles thousands separators, dollar and percent signs, and accounting
    parentheses for negatives, so "1,234,567.89", "$1,234" and "(1,234)" all
    parse. Dashes and asterisks, which filings use for a blank cell, return None.
    """
    if pd.isna(value):
        return None
    s = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
    if not s or s in ("-", "—", "–", "*"):
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        n = float(s)
    except ValueError:
        return None
    if math.isnan(n) or math.isinf(n):
        return None
    return -n if negative else n


# ---------------------------------------------------------------------------
# Column mapping for a schedule of investments.
#
# Fund families label the same column differently. One writes "Market Value",
# another "Value (USD)", a third just "Value". These patterns map any of them to
# a single canonical field name. The order inside each list matters, more
# specific patterns come first.
# ---------------------------------------------------------------------------

# These identifiers must match at the START of a normalised header, never in the
# middle, because "isin" is a substring of "arising", "comprising" and others.
PREFIX_MATCH_PATTERNS = {"cusip", "isin", "lei", "ticker"}

COLUMN_PATTERNS = {
    "security_name": ["securit", "issuer", "description", "investment", "holding",
                      "name", "company"],
    "cusip":         ["cusip"],
    "isin":          ["isin"],
    "ticker":        ["ticker", "symbol"],
    # market_value first, "Value" is more specific here than "Amount".
    "market_value":  ["marketvalue", "fairvalue", "valueusd", "valuein", "valueof",
                      "value"],
    # shares after, so "Principal Amount" lands here through "principal".
    "shares":        ["numberofshares", "shares", "principal", "quantity",
                      "facevalue", "facamount", "parvalue", "par", "units"],
    "pct_assets":    ["ofnetassets", "ofassets", "netassets", "percent", "pct",
                      "weight"],
    "coupon":        ["coupon", "interestrate", "rate"],
    "maturity":      ["maturitydate", "maturity", "matures", "duedate"],
}


# ---------------------------------------------------------------------------
# Noise vocabulary.
#
# A schedule of investments is interleaved with accounting rows: subtotals,
# section headers, cash flow lines, cost bases. These are not securities and
# must be dropped before weights are computed, otherwise the denominator is
# wrong. The three layers below catch exact labels, line beginnings and phrases
# that appear anywhere in a row.
# ---------------------------------------------------------------------------

_NOISE_EXACT = frozenset({
    "total", "total investments", "total portfolio", "total net assets",
    "total common stocks", "total common stock", "total equities", "total equity",
    "total bonds", "total fixed income", "total preferred stocks",
    "total preferred stock", "total other", "subtotal", "grand total", "net assets",
    "shares sold", "shares redeemed", "shares outstanding", "shares issued",
    "reinvestment of distributions", "reinvestment of dividends",
    "net investment income", "net realized gain", "net realized loss",
    "net unrealized gain", "net unrealized loss",
    "unrealized appreciation", "unrealized depreciation",
    "realized gain", "realized loss",
    "dividends", "distributions", "capital gains", "capital gains distribution",
    "total distributions", "total dividends", "total capital gains",
    "redemption fees", "redemption fee", "management fees", "advisory fees",
    "net income", "net loss", "other income", "other expense",
    "other", "other assets", "other liabilities", "other securities",
    "other assets and liabilities", "other assets liabilities net",
    "cash", "cash equivalents", "cash and cash equivalents",
    "accrued interest", "accrued expenses", "accrued dividends",
    "net capital transactions", "sold", "redeemed", "purchased",
    "beginning of period", "end of period", "beginning of year", "end of year",
    "net assets beginning of period", "net assets end of period",
    "net increase", "net decrease",
    "increase in net assets", "decrease in net assets",
    "n a", "na", "none", "nan",
    "paid-in capital", "paid in capital", "additional paid in capital",
    "retained earnings", "accumulated deficit",
    "tax cost", "aggregate cost", "cost basis", "amortized cost",
    "at cost", "at fair value", "at value",
    "bond", "bonds", "notes", "note", "warrant", "warrants",
    "equity", "equities", "stock", "stocks", "share", "shares",
    "fund", "funds", "portfolio", "portfolios",
    "written options", "purchased options", "forward contracts",
    "futures contracts", "swap contracts", "total return swaps",
    "interest rate swaps", "credit default swaps",
})

_NOISE_START = re.compile(
    r"^("
    r"proceeds\s+from\b|payments?\s+for\b|reinvestment\s+of\b|"
    r"net\s+assets?\b|net\s+increase\b|net\s+decrease\b|change\s+in\s+net\b|"
    r"beginning\s+of\s+(the\s+)?(period|year|fund)\b|"
    r"end\s+of\s+(the\s+)?(period|year|fund)\b|"
    r"total\s+net\s+assets\b|total\s+(common\s+)?stocks?\b|"
    r"total\s+(fixed\s+income|bonds?|equit|invest|portfolio|other\b)\b|"
    r"accrued\s+(interest|expenses?|dividends?|liabilit)\b|"
    r"payable\s+to\b|receivable\s+from\b|"
    r"unrealized\s+(gain|loss|appreciation|depreciation)\b|"
    r"realized\s+(gain|loss)\b|"
    r"distributions?\s+(paid|received|reinvested)\b|"
    r"dividends?\s+(paid|received|declared)\b|"
    r"shares?\s+(sold|redeemed|issued|outstanding|repurchased)\b|"
    r"net\s+(capital\s+)?transactions?\b|proceeds?\s+from\s+sales?\b"
    r")",
    re.IGNORECASE,
)

_NOISE_BODY = re.compile(
    r"\b("
    r"net\s+assets\s+(at\s+)?(beginning|end)|total\s+net\s+assets|"
    r"shares\s+outstanding|beginning\s+of\s+(the\s+)?period|"
    r"end\s+of\s+(the\s+)?period|per\s+share\b|12b-1|expense\s+ratio|"
    r"portfolio\s+turnover|paid[- ]in\s+capital|"
    r"unrealized\s+(appreciation|depreciation)|"
    r"net\s+unrealized\s+(appreciation|depreciation)|"
    r"tax\s+cost\b|aggregate\s+cost\b|amortized\s+cost\b|"
    r"at\s+fair\s+value\b|at\s+amortized\b"
    r")\b",
    re.IGNORECASE,
)

_SECTION_HEADER = re.compile(
    r"^(common\s+stocks?|preferred\s+stocks?|corporate\s+bonds?|"
    r"government\s+(bonds?|securities)|u\.?s\.?\s+treasur|agency\s+bonds?|"
    r"convertible\s+(bonds?|securities)|mortgage[- ]backed|asset[- ]backed|"
    r"exchange[- ]traded\s+funds?|equity\s+securities|"
    r"fixed\s+income\s+securities|short[- ]term\s+investments?|"
    r"money\s+market\s+(instruments?|securities|funds?)|"
    r"repurchase\s+agreements?|foreign\s+(securities|equities)|"
    r"international\s+securities|domestic\s+equities|"
    r"equity\s+funds?|bond\s+funds?|balanced\s+funds?)\s*$",
    re.IGNORECASE,
)

_NORM_NOISE = re.compile(r"[^a-z0-9\s]")
_COLLAPSE_SPACE = re.compile(r"\s+")


def is_noise_row(name: str) -> bool:
    """True when a row label is an accounting line or a section header.

    These rows carry numbers but are not securities, so they must be removed
    before the schedule can be read as a portfolio.
    """
    if not name:
        return True
    n = name.strip()
    if len(n) < 3:
        return True
    if re.match(r"^[\d\s\.\,\$\%\-\+\(\)]+$", n):
        return True
    n_norm = _COLLAPSE_SPACE.sub(" ", _NORM_NOISE.sub(" ", n.lower())).strip()
    if n_norm in _NOISE_EXACT:
        return True
    if _NOISE_START.match(n):
        return True
    if _NOISE_BODY.search(n):
        return True
    if _SECTION_HEADER.match(n):
        return True
    return False


# ---------------------------------------------------------------------------
# Forward fill helpers for grouped bond tables.
#
# In many filings a bond issuer is printed once as a header row with no value,
# then each maturity below carries only a coupon and a date. To recover a usable
# security name we remember the last issuer and prepend it to those coupon only
# rows. These helpers decide what is an issuer header, what is a coupon line, and
# what is just a column label to ignore.
# ---------------------------------------------------------------------------

_FF_SECTION = re.compile(
    r"written call|written put|purchased (call|put)|\boptions?\b|common stock|"
    r"preferred|convertible|corporate bond|municipal|\bwarrant|\brights?\b|"
    r"government|money market|exchange.?traded|investment compan|repurchase|"
    r"asset.?backed|mortgage.?backed|term loan|senior loan|u\.?s\.? treasur|"
    r"foreign|sovereign|short.?term|time deposit", re.I)

_FF_TERMS = re.compile(
    r"exercise price.*|expiration date.*|strike price.*|maturity date.*|"
    r"\d+(\.\d+)?\s?%|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b144a\b|\breg\s?s\b|"
    r"\bdue\b|\bmaturity\b|\bcoupon\b|zero coupon|\bseries\b\s*\S*|"
    r"\b20[0-4]\d\b|\$[\d.,]+", re.I)

_FF_COUPON = re.compile(
    r"^\s*(144a|reg\s?s|series\s+\S+)?\s*\d+(\.\d+)?\s?%|"
    r"exercise price|^\s*\d{1,2}/\d{1,2}/\d{2,4}|^\s*due\b|^\s*zero coupon", re.I)

_FF_FOOTNOTE_HEAD = re.compile(r"^\s*[\d†‡#*°^()]+\s+")
_FF_FOOTNOTE_TAIL = re.compile(r"\s*[†‡#*°^]+\s*$")

_FF_LABELS = {"coupon", "maturity", "rate", "description", "principal", "par",
              "value", "shares", "market value", "interest", "yield", "amount",
              "security", "name", "issuer", "cost", "fair value", "units",
              "quantity", "face amount", "total", "investments", "net assets"}


def ff_residual(name: str) -> str:
    """The alphabetic words left after removing coupon and date fragments.

    A real issuer header keeps words here. A pure coupon line does not.
    """
    n = _FF_TERMS.sub(" ", name.lower())
    n = re.sub(r"[^a-z ]", " ", n)
    return " ".join(t for t in n.split() if len(t) >= 3)


def ff_clean(name: str) -> str:
    """Strip leading and trailing footnote markers from a name."""
    return _FF_FOOTNOTE_TAIL.sub("", _FF_FOOTNOTE_HEAD.sub("", name)).strip()


def ff_is_label(name: str) -> bool:
    """True when the row is only column labels, not a real issuer."""
    n = re.sub(r"[%°#*()$]", "", name).strip().lower()
    tokens = n.split()
    return bool(tokens) and all(t in _FF_LABELS or len(t) <= 2 for t in tokens)


def ff_is_terms(name: str) -> bool:
    """True when the row is a coupon and date line with no issuer of its own."""
    return bool(_FF_COUPON.search(name)) and not ff_residual(name)
