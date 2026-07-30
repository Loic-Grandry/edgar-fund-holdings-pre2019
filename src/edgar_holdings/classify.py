"""
Asset class of a security, from its name alone.

Once a row has been extracted from a schedule of investments, its name is enough
to place it in an asset class. This labels each holding, and catches rows that
slipped through the noise filter, which come back as ACCOUNTING or NOISE and get
dropped.

The classifier is a set of ordered tests. Order is priority. Accounting and
noise are removed first, then cash, sovereign, derivative, bond and fund are
tested in that sequence, and anything left is treated as an equity or an
unidentified real holding.

A note on two hard cases that this ordering fixes:

- Securitised tranches, meaning CMBS, CMO and ABS, often read as "Class B" with
  a year at the end. An earlier version sent them to FUND because of the word
  Class. They are debt, so BOND now catches the tranche signals first.
- A bare "Class A" or a brand such as "BlackRock, Inc." is not a fund. FUND now
  requires a structural token such as fund, portfolio, etf or a retirement share
  class, so brands stay equities and tranches stay bonds.
"""
from __future__ import annotations

import re

_NOISE_NUMERIC = re.compile(r"^[\d\s\.\,\$\%\-\+\(\)\*\#\@\!/\\]+$")

_CURRENCIES = frozenset({
    "eur", "usd", "gbp", "jpy", "chf", "cad", "aud", "nzd", "sek", "nok", "dkk",
    "hkd", "sgd", "krw", "inr", "brl", "mxn", "zar", "try", "pln", "czk", "huf",
    "thb", "myr", "idr", "php", "vnd", "egp", "aed", "sar", "qar", "kwd", "bhd",
    "rub", "cny", "twd", "ils", "clp", "cop", "pen", "ars", "uah",
    "euro", "dollar", "pound", "yen", "franc", "won", "rupee", "real",
})

_ACC_EXACT = frozenset({
    "total", "subtotal", "grand total", "totals", "total investments",
    "total portfolio", "total net assets", "total common stocks",
    "total common stock", "total equities", "total equity", "total bonds",
    "total fixed income", "total other", "total preferred stocks",
    "total preferred stock", "net assets", "net assets 100", "net assets 100 0",
    "paid-in capital", "paid in capital", "additional paid in capital",
    "capital paid in", "net capital paid in", "shares of beneficial interest",
    "retained earnings", "accumulated deficit", "accumulated undistributed",
    "tax cost", "aggregate cost", "cost basis", "amortized cost", "at cost",
    "at fair value", "at value", "cost of investments", "federal tax cost",
    "federal income tax cost", "cost for federal income tax",
    "investment securities at value", "investments at value",
    "investments in securities", "portfolio investments at value",
    "in unaffiliated securities", "non affiliated issuers", "affiliated issuers",
    "unrealized appreciation", "unrealized depreciation",
    "gross unrealized appreciation", "gross unrealized depreciation",
    "net unrealized appreciation", "net unrealized depreciation",
    "net unrealized appreciation depreciation", "realized gain", "realized loss",
    "net realized gain", "net realized loss", "net investment income",
    "net income", "net loss", "dividends", "distributions", "capital gains",
    "total distributions", "redemption fees", "management fees", "advisory fees",
    "shares sold", "shares redeemed", "shares outstanding", "shares reinvested",
    "reinvestment of distributions", "reinvestment of dividends",
    "beginning balance", "ending balance", "beginning of period", "end of period",
    "beginning of year", "end of year", "net increase", "net decrease",
    "increase in net assets", "decrease in net assets",
    "net capital transactions", "net transactions in fund shares",
    "proceeds from shares sold", "payments for shares redeemed",
    "purchases additions", "sales reductions", "purchases/additions",
    "sales/reductions", "receivable for fund shares sold",
    "receivable for investments sold", "payable for fund shares redeemed",
    "payable for investments purchased", "accrued interest", "accrued expenses",
    "accrued dividends", "prepaid expenses", "prepaid", "deferred income",
    "securities lending collateral", "collateral", "margin deposit",
    "other assets and liabilities", "other assets liabilities net",
    "totals", "securities", "investments", "sold", "redeemed", "purchased",
    "n a", "na", "undistributed net investment income", "shares of beneficial",
})

# Sector and country subtotals are accounting rows, not holdings.
_ACC_SECTOR = frozenset({
    "information technology", "consumer discretionary", "consumer staples",
    "health care", "healthcare", "financials", "industrials", "materials",
    "utilities", "energy", "communication services", "real estate", "telecom",
    "telecommunication services", "common stocks", "preferred stocks",
    "corporate bonds", "government bonds", "government securities", "agency bonds",
    "equity securities", "fixed income securities", "long term corporate debt",
    "corporate debt securities", "foreign government obligations",
    "mortgage-backed securities", "asset-backed securities",
    "collateralized mortgage obligations", "other industrials", "term loans",
    "common stock", "preferred stock", "u s government and agency obligations",
    "government and agency obligations", "gold bullion", "money market funds",
    "mutual funds", "equities", "bonds",
})

_ACC_COUNTRY = frozenset({
    "united states", "united kingdom", "japan", "germany", "france",
    "switzerland", "canada", "australia", "china", "south korea", "brazil",
    "india", "netherlands", "sweden", "spain", "italy", "hong kong", "singapore",
    "taiwan", "denmark", "norway", "finland", "belgium", "austria", "portugal",
    "israel", "mexico", "indonesia", "malaysia", "thailand", "philippines",
    "vietnam", "turkey", "russia", "south africa", "chile", "colombia", "peru",
    "argentina", "egypt", "poland", "czech republic", "hungary", "greece",
    "ireland", "luxembourg", "new zealand", "saudi arabia", "all other countries",
    "all other", "other countries", "international", "emerging markets",
    "developed markets", "europe", "asia", "latin america", "north america",
    "pacific", "middle east", "africa", "eurozone", "u s", "u k", "usa", "uk",
})

_ACC_START = re.compile(
    r"^(\(cost\s*\$|\(identified cost|\(amortized cost|\(cost\s|proceeds from|"
    r"payments? for|reinvestment of|net assets?\b|net investments?\s+\d|"
    r"net investment\s+\d|accrued |payable (to|for)\b|receivable (from|for)\b|"
    r"unrealized |realized |distributions? (paid|received)|"
    r"dividends? (paid|declared)|shares? (sold|redeemed|issued|outstanding|reinvested)|"
    r"net (capital |unrealized |realized |investment )|cost of |"
    r"federal (tax|income)|aggregate cost|tax cost|in unaffiliated|non.affiliated|"
    r"affiliated issuers|portfolio invest|investment securities|gross unrealized|"
    r"accumulated undistributed|undistributed net|shares of beneficial|"
    r"capital paid in|net capital paid|beginning balance|ending balance|"
    r"purchases/|sales/|collateral|securities lending)",
    re.IGNORECASE)

_ACC_BODY = re.compile(
    r"\b(net assets (at )?(beginning|end)|total net assets|shares outstanding|"
    r"per share\b|12b.1|expense ratio|portfolio turnover|paid.in capital|"
    r"at fair value\b|identified cost \$|for (federal |income )?tax purposes|"
    r"gross unrealized|net unrealized)\b",
    re.IGNORECASE)

_ACC_PAREN_COST = re.compile(r"^\((?:identified |amortized )?cost\s*\$?[\d,\.]*", re.IGNORECASE)
_ACC_NET_INV = re.compile(r"^net investments?\s+\d{2,3}\.?\d*\s*%", re.IGNORECASE)

# A section subtotal always starts with "Total". A real company can too, such as
# Total S.A. or Total System Services, so a leading "Total" is only accounting
# when no corporate suffix or brand word follows.
_TOTAL_LEAD = re.compile(r"^\s*total\s+\S", re.IGNORECASE)
_CORP_SUFFIX = re.compile(
    r"\b(s\.?a\.?|s\.?e\.?|plc|inc|corp|ltd|co|n\.?v\.?|a\.?g\.?|a\.?b\.?|spa|oyj|"
    r"asa|group|holding|system|technolog|energies|petroleum|financ|bancorp)\b",
    re.IGNORECASE)
# Standard schedule footer lines that balance the portfolio to net assets.
_ACC_OTHER_ASSETS = re.compile(
    r"(other assets|liabilities)\s+in excess of|net other assets|"
    r"other assets\s+(net|less)|excess of (other assets|liabilities)", re.IGNORECASE)

_CASH = re.compile(
    r"^(cash( and| &)? cash equivalents?|cash equivalents?|"
    r"repurchase agreement|repo\b|tri.party repo|overnight)", re.IGNORECASE)

_SOVEREIGN = re.compile(
    r"^(republic of|kingdom of|province of|state of |government of |"
    r"peoples republic|federal republic|commonwealth of|municipalit|"
    r"international bank for reconstruction|european bank for reconstruction|"
    r"inter.american development|asian development bank|international finance corp|"
    r"european investment bank|world bank|ibrd|ifc|iadb|eib\b|ebrd\b|"
    r"african development bank)", re.IGNORECASE)

_DERIVATIVE = re.compile(
    r"\b(futures?|forward contract|option|swap|warrant|rights?\b|e-mini|eurodollar|"
    r"euribor|straddle|strangle|credit default|total return swap|interest rate swap|"
    r"currency swap|index future|equity future|cds\b|irs\b|trs\b|"
    r"exp\.?\s+(?:19|20)\d{2})\b", re.IGNORECASE)

_BOND = re.compile(
    r"\b(\d+\.?\d*\s*%|due\s+\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|zero coupon|"
    r"floating rate|variable rate|treasury (note|bill|bond)|t-bill|t-note|"
    r"treasury\s+\d|bund|gilt|jgb|oat\b|btp\b|senior (note|bond|secured|unsecured)|"
    r"subordinated|convertible note|municipal bond|general obligation|revenue bond|"
    r"mortgage.backed|asset.backed|cdo|clo|cmbs|rmbs|certificate of deposit|"
    r"commercial paper|medium.term note|callable)\b", re.IGNORECASE)

# Securitisation tranche signals that a plain bond pattern misses.
_BOND_TRANCHE = re.compile(
    r"(\bser\.?\s*\d{2}\b|\bseries\s+\d{2}[- ]|\b\d{2}-[a-z]{1,3}\d{0,2}\b|"
    r"\b144a\b|\bclass\s+[a-z]{1,2}\d?\b\s*,.*\b(19|20)\d{2}\b|\b(io|po)\b\s*,)",
    re.IGNORECASE)
_BOND_COUPON_S = re.compile(r"\b\d+\.\d+\s*s\b")        # coupon such as "5.118s"
_BOND_YEAR_MATURITY = re.compile(r",\s*(19|20)\d{2}\s*$")  # maturity such as ", 2045"

# FUND needs a structural token, so a bare share class or a brand is not a fund.
_FUND = re.compile(
    r"\b(fund\b|portfolio\b|etf\b|reit\b|master portfolio|index fund|"
    r"allocation fund|class (r[0-6]|nav)\b|money market|liquidity fund)\b",
    re.IGNORECASE)

_NON_ALNUM = re.compile(r"[^a-z0-9\s]")
_SPACES = re.compile(r"\s+")


def _normalise(name: str) -> str:
    return _SPACES.sub(" ", _NON_ALNUM.sub(" ", name.lower())).strip()


CATEGORIES = ["EQUITY_OR_UNKNOWN", "BOND", "FUND", "SOVEREIGN", "DERIVATIVE",
              "CASH", "ACCOUNTING", "NOISE"]


def classify(name_raw) -> str:
    """Return the asset class of a security name.

    One of the labels in :data:`CATEGORIES`. ACCOUNTING and NOISE mean the row is
    not a real holding and should be dropped.
    """
    if not name_raw or not isinstance(name_raw, str):
        return "NOISE"
    n = name_raw.strip()
    if len(n) < 3 or _NOISE_NUMERIC.match(n):
        return "NOISE"
    nl = _normalise(n)
    if nl in _CURRENCIES:
        return "NOISE"

    if _ACC_PAREN_COST.match(n) or _ACC_NET_INV.match(n):
        return "ACCOUNTING"
    if nl in _ACC_EXACT or nl in _ACC_SECTOR or nl in _ACC_COUNTRY:
        return "ACCOUNTING"
    if _ACC_START.match(n) or _ACC_BODY.search(n):
        return "ACCOUNTING"
    if _ACC_OTHER_ASSETS.search(n):
        return "ACCOUNTING"
    if _TOTAL_LEAD.match(n) and not _CORP_SUFFIX.search(n):
        return "ACCOUNTING"

    if _CASH.match(n):
        return "CASH"
    if _SOVEREIGN.match(n):
        return "SOVEREIGN"
    if _DERIVATIVE.search(n):
        return "DERIVATIVE"
    if (_BOND.search(n) or _BOND_TRANCHE.search(n)
            or _BOND_COUPON_S.search(n) or _BOND_YEAR_MATURITY.search(n)):
        return "BOND"
    if _FUND.search(n):
        return "FUND"
    return "EQUITY_OR_UNKNOWN"
