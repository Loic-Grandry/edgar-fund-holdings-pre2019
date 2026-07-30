"""
Turning raw filing HTML into labelled tables.

A fund report is one HTML file with many tables. Only one kind, the schedule of
investments, holds the portfolio. The rest are financial highlights, statements
of operations, sector breakdowns and fee tables. This module reads every table,
labels it, and repairs a common defect in older filings where the HTML has no
header cells at all.

Labelling uses three signals in order. The text just before a table is the
strongest, because a heading such as "Schedule of Investments" is explicit.
Column names are the next signal. Structure, meaning a long table with a CUSIP
column, is the fallback. This layered approach is what lets one code path read
filings from many fund families that all format their reports differently.
"""
from __future__ import annotations

import re
from io import StringIO

import pandas as pd
from bs4 import BeautifulSoup

# Text before a table. The first rule that matches wins, so specific labels come
# before generic ones.
_CONTEXT_RULES = [
    ("SoI", r"schedule of (?:portfolio )?investments?|portfolio of investments|"
            r"statement of net assets|investments? in securities|"
            r"consolidated schedule of investments"),
    ("FinancialHighlights", r"financial highlights?|selected per[- ]share data"),
    ("Operations", r"statement of operations|operating results"),
    ("Statement", r"statement of (?:assets|cash flow|changes in net assets)"),
    ("Performance", r"performance summary|total returns|fiscal[- ]year (?:total )?returns|"
                    r"cumulative (?:total )?returns?|average annual"),
    ("Expenses", r"about your fund.?s expenses|expense (?:ratio|example|table)|"
                 r"fees? and expenses"),
    ("TopHoldings", r"top (?:ten|10|20|twenty)|largest holdings|ten largest|"
                    r"principal holdings"),
    ("Profile", r"fund profile|portfolio characteristics?|sector (?:weight|allocation|"
                r"diversification)|industry breakdown|asset allocation"),
    ("ShareClass", r"share[- ]class characteristics?|class[- ]level data"),
    ("Objective", r"investment objective|fund objective"),
]

# Column names, used when the surrounding text is uninformative.
_COLUMN_RULES = [
    ("SoI", r"\b(?:cusip|shares?|principal amount|coupon|maturity|market value)\b"),
    ("FinancialHighlights", r"net asset value|investment activities|distributions|"
                            r"total return|ratios to average|portfolio turnover"),
    ("Performance", r"^1[- ]year$|^5[- ]year$|^10[- ]year$|^since inception$|^average annual"),
    ("Expenses", r"expense ratio|management fee|12b-1|annual fund operating"),
    ("ShareClass", r"^ticker symbol?$|^expense ratio$|class.*(shares?|ticker)"),
]

_CONTEXT_PATTERNS = [(tag, re.compile(p, re.IGNORECASE)) for tag, p in _CONTEXT_RULES]
_COLUMN_PATTERNS = [(tag, re.compile(p, re.IGNORECASE)) for tag, p in _COLUMN_RULES]


def classify_table(df: pd.DataFrame, context: str) -> str:
    """Label a table using its context, then its columns, then its structure."""
    if context:
        context_norm = re.sub(r"\s+", " ", context).strip()
        for tag, pattern in _CONTEXT_PATTERNS:
            if pattern.search(context_norm):
                return tag

    col_text = " | ".join(str(c) for c in df.columns)
    for tag, pattern in _COLUMN_PATTERNS:
        if pattern.search(col_text):
            return tag

    # A long table with a CUSIP or identifier column is a schedule of investments.
    if df.shape[0] >= 20:
        for col in df.columns:
            col_str = str(col).lower()
            if "cusip" in col_str or "identifier" in col_str:
                return "SoI"
        cols_lower = " ".join(str(c).lower() for c in df.columns)
        if "shares" in cols_lower and ("value" in cols_lower or "amount" in cols_lower):
            return "SoI"

    # Financial highlights recognised by the labels in the first column.
    if len(df) >= 4:
        first_col = " ".join(df.iloc[:, 0].dropna().astype(str).str.lower())
        if "net asset value" in first_col and (
            "total return" in first_col or "beginning of period" in first_col
        ):
            return "FinancialHighlights"

    return "Other"


def _columns_are_numeric_only(df: pd.DataFrame) -> bool:
    """True when pandas found no real header, only 0, 1, 2 or Unnamed columns."""
    for c in df.columns:
        s = str(c).strip()
        if not s.isdigit() and not s.lower().startswith("unnamed"):
            return False
    return True


def repair_header(df: pd.DataFrame) -> pd.DataFrame:
    """Promote the best text row to be the header when the HTML had none.

    Older pre XBRL filings often ship tables with no header cells, so pandas
    numbers the columns 0, 1, 2. This scans the first few rows, scores each by how
    many cells carry real words, and promotes the best one, merging any sub header
    rows above it. Without this step many older filings would lose their column
    meaning entirely.
    """
    if not _columns_are_numeric_only(df):
        return df

    def text_score(row) -> int:
        score = 0
        for val in row:
            if pd.isna(val):
                continue
            s = str(val).strip()
            if len(s) >= 2 and len(re.findall(r"[A-Za-z]", s)) >= 2:
                score += 1
        return score

    n_check = min(5, len(df))
    scores = [text_score(df.iloc[i]) for i in range(n_check)]
    if max(scores, default=0) < 2:
        return df

    best_idx = max(range(n_check), key=lambda i: (scores[i], i))

    new_columns = []
    for col_pos in range(df.shape[1]):
        parts = []
        for row_idx in range(best_idx + 1):
            val = df.iloc[row_idx, col_pos]
            if pd.isna(val):
                continue
            s = str(val).strip()
            if s and s.lower() != "nan":
                parts.append(s)
        new_columns.append(" ".join(parts) if parts else f"col_{col_pos}")

    seen = {}
    final_cols = []
    for i, c in enumerate(new_columns):
        if not c:
            c = f"col_{i}"
        if c in seen:
            seen[c] += 1
            c = f"{c}_{seen[c]}"
        else:
            seen[c] = 0
        final_cols.append(c)

    repaired = df.iloc[best_idx + 1:].copy()
    repaired.columns = final_cols
    return repaired.reset_index(drop=True)


def _table_context(tag) -> str:
    """Collect up to a few hundred characters of text before a table."""
    chunks = []
    prev = tag
    for _ in range(15):
        prev = prev.find_previous(string=True)
        if prev is None:
            break
        text = prev.strip()
        if text and len(text) > 3:
            chunks.append(text)
        if sum(len(c) for c in chunks) > 400:
            break
    return " | ".join(reversed(chunks))[:500]


def read_tables(html: str) -> list[dict]:
    """Read every table from filing HTML and label it.

    Returns a list of dictionaries, each with the table as a DataFrame, its
    label, and the text context that produced the label.
    """
    try:
        frames = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError:
        frames = []

    contexts = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for table in soup.find_all("table"):
            contexts.append(_table_context(table))
    except Exception:
        contexts = []

    out = []
    for i, df in enumerate(frames):
        if df.shape[0] < 2 or df.shape[1] < 2:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [
                " / ".join(str(c) for c in col if str(c) != "nan").strip()
                for col in df.columns
            ]
        df = repair_header(df)
        context = contexts[i] if i < len(contexts) else ""
        label = classify_table(df, context)
        out.append({"table": df, "label": label, "context": context})
    return out
