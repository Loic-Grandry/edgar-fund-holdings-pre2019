"""
Reading holdings out of a schedule of investments table.

This is the heart of the pipeline and the part that varies most across fund
families. The same portfolio can be printed in three broadly different ways, and
the extractor tries three strategies in order, from the cleanest to the most
degraded.

1. Mapped extraction. The table has proper headers, so each column maps to a
   canonical field through the column patterns. This is the common case for
   Vanguard, Fidelity and other large families.

2. Name recovery. The value columns are labelled but the security name column
   was lost, usually because the name sat in a section title rather than a real
   column. The extractor keeps the good value columns and finds the leftmost text
   column to use as the name.

3. Positional extraction. Nothing is labelled, because the source HTML had no
   header cells at all. This happens with older pre XBRL filings from families
   such as Prudential and SunAmerica. The extractor reads the table by position:
   the leftmost text column is the name, the numeric column with the largest
   typical magnitude is the market value, a column bounded by 100 is the percent,
   and a smaller numeric column is shares.

Along the way it also forward fills bond issuers onto their coupon only rows, and
it drops subtotals and breakdown tables that would inflate the totals.
"""
from __future__ import annotations

import re

import pandas as pd

from . import patterns
from .patterns import (
    COLUMN_PATTERNS,
    PREFIX_MATCH_PATTERNS,
    ff_clean,
    ff_is_label,
    ff_is_terms,
    ff_residual,
    is_noise_row,
    norm_col,
    parse_number,
)

_SECTION_HEADER = re.compile(
    r"common stock|preferred|convertible|corporate|municipal|treasury|government|"
    r"bonds?|notes?|securities|investments|principal|shares|par\b|value|equity|"
    r"fund|sovereign|asset.?backed|mortgage|repurchase|short.?term|—|–|%", re.I)

_BREAKDOWN = re.compile(
    r"breakdown|allocation|composition|summary|weighting|diversification|"
    r"by (sector|country|industry|type)", re.I)

_CUSIP = re.compile(r"^[A-Z0-9]{8}[0-9]$")

# Subtotal rows such as "Total Common Stocks" would double count value. A real
# issuer such as "Total S.A." is spared because a class of security must follow.
_SUBTOTAL = re.compile(
    r"^\s*total\b.*\b(investment|securit|bond|note|stock|fund|obligation|capital|"
    r"debt|equity|net asset|common|preferred|municipal|corporate|portfolio|"
    r"government|treasury|cash|holding|value|partnership|interest)", re.I)

# Fragments of an equity share class, such as a bare "Class R6".
_CLASS_FRAGMENT = re.compile(r"^\s*(class|cl|cls|ser|series)\.?\s+[a-z0-9]{1,4}\s*$", re.I)

# Derivative and contract section headers to drop in the stricter noise mode.
_NOISE_STRICT = re.compile(
    r"^\s*(credit|equity|foreign exchange|interest rate|commodity|forward|futures|"
    r"written|purchased)\s+(contracts?|options?)\s*$|"
    r"^\s*(total return swaps?|centrally cleared|when issued|collateral)\b", re.I)


def _is_subtotal(name: str) -> bool:
    return bool(_SUBTOTAL.search(name))


def _is_class_fragment(name: str) -> bool:
    return bool(_CLASS_FRAGMENT.match(ff_clean(name)))


def _is_noise(name: str, strict: bool) -> bool:
    if is_noise_row(name):
        return True
    return strict and bool(_NOISE_STRICT.match(name.strip()))


def _looks_degenerate(columns) -> bool:
    cols = [str(c) for c in columns]
    if not cols:
        return False
    base = re.sub(r"_\d+$", "", cols[0])
    repeated = base and sum(1 for c in cols if c.startswith(base)) >= max(2, len(cols) // 2)
    return repeated or bool(_SECTION_HEADER.search(cols[0]))


def _is_breakdown(df: pd.DataFrame) -> bool:
    return any(_BREAKDOWN.search(str(c)) for c in df.columns)


def _column_stats(series: pd.Series):
    """Fraction numeric, fraction text, and typical magnitude of a column."""
    values = series.dropna().astype(str)
    values = values[~values.str.strip().str.lower().isin(["", "nan", "none"])]
    if len(values) == 0:
        return 0.0, 0.0, None
    values = values.head(300)
    parsed = [parse_number(x) for x in values]
    numeric = [x for x in parsed if x is not None]
    numeric_share = len(numeric) / len(values)
    text_share = sum(1 for p in parsed if p is None) / len(values)
    median = sorted(abs(x) for x in numeric)[len(numeric) // 2] if numeric else None
    all_percent = bool(numeric) and all(0 <= x <= 110 for x in numeric)
    return numeric_share, text_share, (median, all_percent)


def _find_cusip_column(df: pd.DataFrame):
    for col in df.columns:
        values = df[col].dropna().astype(str).str.strip().str.upper()
        if len(values) and values.map(lambda x: bool(_CUSIP.match(x))).mean() >= 0.3:
            return col
    return None


def _emit_rows(df, name_col, mv_col, sh_col, pct_col, cusip_col, opts):
    strict = opts.get("noise") == "strict"
    bonds_ff = opts.get("bonds_ff", True)
    equity_ff = opts.get("equity_ff", True)
    out = []
    current_issuer = ""
    for _, row in df.iterrows():
        name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
        if not name or name.lower() in ("nan", "none"):
            continue
        if _is_noise(name, strict) or _is_subtotal(name):
            continue
        mv = parse_number(row[mv_col]) if mv_col else None
        sh = parse_number(row[sh_col]) if sh_col else None
        pct = parse_number(row[pct_col]) if pct_col else None
        cusip = str(row[cusip_col]).strip() if cusip_col and pd.notna(row[cusip_col]) else None

        has_value = mv is not None or sh is not None or pct is not None
        if not has_value:
            # A row with no value updates the issuer context for forward fill.
            if patterns._FF_SECTION.search(name) or ff_is_label(name):
                current_issuer = ""
            elif ff_residual(name):
                current_issuer = ff_clean(name)
            continue

        if bonds_ff and current_issuer and ff_is_terms(name):
            name = f"{current_issuer}, {name}"
        elif equity_ff and current_issuer and _is_class_fragment(name):
            name = f"{current_issuer}, {name}"
        elif ff_residual(name) and not ff_is_label(name) and not _is_class_fragment(name):
            current_issuer = ff_clean(name)

        out.append({"security_name": name, "market_value": mv, "shares": sh,
                    "pct_assets": pct, "cusip": cusip})
    return out


def _map_columns(df: pd.DataFrame) -> dict:
    """Map filing columns to canonical field names through the patterns."""
    mapping, used = {}, set()
    for canonical, plist in COLUMN_PATTERNS.items():
        for col in df.columns:
            if col in used:
                continue
            col_n = norm_col(col)
            matched = False
            for p in plist:
                if canonical in PREFIX_MATCH_PATTERNS:
                    matched = col_n == p or col_n.startswith(p)
                else:
                    matched = p in col_n
                if matched:
                    break
            if matched:
                mapping[canonical] = col
                used.add(col)
                break

    # If no name or cusip column was found, take the leftmost mostly text column.
    if "security_name" not in mapping and "cusip" not in mapping:
        candidates = [c for c in df.columns if c not in used and
                      (c in ("col_0", "col_1") or (str(c).isdigit() and int(str(c)) < 4))]
        best, best_ratio = None, 0.05
        for col in candidates:
            values = df[col].dropna().astype(str)
            if len(values) == 0:
                continue
            text = sum(1 for v in values if parse_number(v) is None
                       and v.strip().lower() not in ("", "nan", "none"))
            ratio = text / max(len(df), 1)
            if ratio > best_ratio:
                best_ratio, best = ratio, col
        if best:
            mapping["security_name"] = best
            used.add(best)

    # When a numeric field mapped to a mostly text column, try a sibling column.
    def numeric_ratio(col):
        values = df[col].dropna().head(300)
        return sum(1 for x in values if parse_number(x) is not None) / len(values) if len(values) else 0.0

    def best_numeric(base):
        if numeric_ratio(base) >= 0.25:
            return base
        for suffix in ("_1", "_2", "_3"):
            if base + suffix in df.columns and numeric_ratio(base + suffix) >= 0.25:
                return base + suffix
        return base

    for field in ("shares", "market_value", "pct_assets"):
        if field in mapping:
            mapping[field] = best_numeric(mapping[field])
    return mapping


def _positional(df: pd.DataFrame, opts: dict):
    """Read a fully unlabelled table by column position."""
    stats = {c: _column_stats(df[c]) for c in df.columns}
    name_col = next((c for c in df.columns if stats[c][1] >= 0.4), None)
    if name_col is None:
        return []
    used = {name_col}
    numeric = [c for c in df.columns if c not in used and stats[c][0] >= 0.3 and stats[c][2]]
    pct_col = next((c for c in numeric if stats[c][2][1]), None)
    value_cands = [c for c in numeric if c != pct_col]
    value_cands.sort(key=lambda c: stats[c][2][0] or 0)
    mv_col = value_cands[-1] if value_cands else None
    sh_col = value_cands[0] if len(value_cands) >= 2 else None
    return _emit_rows(df, name_col, mv_col, sh_col, pct_col, _find_cusip_column(df), opts)


DEFAULT_OPTS = {"bonds_ff": True, "equity_ff": True, "noise": "strict"}


def extract_holdings(df: pd.DataFrame, opts: dict | None = None) -> list[dict]:
    """Extract holding rows from one schedule of investments table.

    Tries mapped extraction, then name recovery, then positional extraction.
    Returns a list of dictionaries with security_name, market_value, shares,
    pct_assets and cusip. Market value and shares may be None when the table
    does not carry them.
    """
    opts = opts or DEFAULT_OPTS

    mapping = _map_columns(df)
    if "security_name" in mapping or "cusip" in mapping:
        rows = _emit_rows(
            df,
            mapping.get("security_name") or mapping.get("cusip"),
            mapping.get("market_value"),
            mapping.get("shares"),
            mapping.get("pct_assets"),
            mapping.get("cusip") if "security_name" in mapping else None,
            opts,
        )
        if rows:
            return rows

    if _is_breakdown(df):
        return []

    # Name recovery: value columns exist but the name column was lost.
    has_numeric = any(k in mapping for k in ("market_value", "shares", "pct_assets"))
    if has_numeric and "security_name" not in mapping:
        used = set(mapping.values())
        stats = {c: _column_stats(df[c]) for c in df.columns}
        name_col = next((c for c in df.columns if c not in used and stats[c][1] >= 0.4), None)
        if name_col:
            rows = _emit_rows(df, name_col, mapping.get("market_value"),
                              mapping.get("shares"), mapping.get("pct_assets"),
                              _find_cusip_column(df), opts)
            if rows:
                return rows

    # Positional: nothing labelled at all.
    if _looks_degenerate(df.columns):
        rows = _positional(df, opts)
        if rows:
            return rows

    return []
