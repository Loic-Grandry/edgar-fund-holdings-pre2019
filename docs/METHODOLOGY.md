# Methodology

This document explains why recovering pre 2019 fund holdings is hard, and how the
pipeline handles it. The problem is that the same portfolio can be printed in many
different ways, and a single rigid parser would fail on most of them. The
pipeline is built as a stack of strategies that go from the cleanest case to the
most degraded, so one code path can read filings from hundreds of fund families.

## Why this is hard

Since 2019, funds report their holdings on form N-PORT, which is structured data
that any tool can read directly. Before 2019 there was no such thing. A fund
disclosed its portfolio as HTML tables inside its N-Q and N-CSR filings, and each
fund family designed those tables its own way. There was no shared schema and no
validation, only a rendering meant for human eyes.

Concretely, across families you meet at least these variations:

- Different column names for the same field. One family writes "Market Value",
  another "Value (USD)", a third simply "Value". Shares can be "Shares", "Number
  of Shares", "Principal Amount" or "Par".
- Tables with no header cells at all. Older pre XBRL filings often ship a table
  where the first row is really the header but is not tagged as one, so a naive
  reader labels the columns 0, 1, 2.
- The security name folded into a section title rather than a column, so the
  value columns are clean but the name column is missing.
- Bonds printed as an issuer header followed by rows that carry only a coupon and
  a maturity, with no issuer of their own.
- Schedules interleaved with accounting rows, subtotals, sector headers and
  balance lines that carry numbers but are not securities.
- One trust filing that bundles several funds, each portfolio one after another.

A parser that assumes one layout works on one family and breaks on the next. The
design goal here is one pipeline that degrades gracefully across all of them.

## The pipeline as a stack of strategies

```
raw filing HTML
      |
      v
[A] read every table, label it, repair missing headers      (tables.py)
      |
      v
[B] for each schedule of investments, extract holding rows   (extract.py)
      three strategies tried in order:
        1. mapped     headers are clean, map columns to fields
        2. recovered  values labelled, name column lost, find it
        3. positional nothing labelled, read by column position
      |
      v
[C] classify each row by asset class, drop accounting noise   (classify.py)
      |
      v
[D] compute each holding's weight over the portfolio total    (holdings.py)
      |
      v
clean holdings table, one row per security, weights sum to 100
```

## A. Reading and labelling tables

Every table in the filing is read. Each one is labelled using three signals in
order of reliability. The text just before a table is the strongest, since a
heading such as "Schedule of Investments" is explicit. Column names are the next
signal. Structure, meaning a long table that carries a CUSIP column or both a
shares and a value column, is the fallback. Only tables labelled as a schedule of
investments go forward. Financial highlights, statements of operations, sector
breakdowns and fee tables are set aside.

When pandas finds no header cells, the header repair step scans the first few
rows, scores each by how many cells carry real words, promotes the best one, and
merges any sub header row above it. This single step is what saves the many older
filings that ship headerless tables.

## B. Extracting holdings, three strategies

This is where fund family differences bite hardest, so the extractor tries three
strategies from cleanest to most degraded.

1. **Mapped.** The table has proper headers. Each column is matched to a canonical
   field through a set of name patterns, so "Market Value", "Value (USD)" and
   "Value" all map to the same field. This is the common path for large families.

2. **Name recovery.** The value columns mapped cleanly but no name column was
   found, usually because the name sat in a section title. The extractor keeps the
   good value columns and takes the leftmost mostly text column as the name.

3. **Positional.** Nothing mapped, because the table was fully degenerate. The
   extractor reads by position. The leftmost text column is the name. Among the
   numeric columns, the one with the largest typical magnitude is the market
   value, a column whose values never exceed roughly 100 is the percent of net
   assets, and a smaller numeric column is the share count.

Bonds get an extra pass. When an issuer is printed once as a header with no value
and the rows below carry only a coupon and a date, the extractor remembers the
last issuer and prepends it, so "5.00% due 2027" becomes "Issuer, 5.00% due
2027". The same idea reattaches a bare equity share class such as "Class R6" to
its parent fund.

## C. Classifying and cleaning

Each extracted row is classified by name into an asset class: equity, bond, fund,
sovereign, derivative or cash. Two of the labels, accounting and noise, mean the
row is not a real holding, so it is dropped. This is the last defence against
rows that slipped through, such as subtotals, cost bases, cash flow lines and
sector totals.

Two cases are worth calling out because they are common and easy to get wrong.

- A row that starts with "Total" is almost always a subtotal, but not always. Total
  S.A. and Total System Services are real companies. The classifier treats a
  leading "Total" as accounting only when no corporate suffix or brand word
  follows, so subtotals go and companies stay.
- Securitised tranches such as CMBS and CMO often read as "Class B" with a year at
  the end. They are debt, so the bond rules catch the tranche signals before the
  fund rules can misfile them.

## D. Weights

Once the real holdings are known, each weight is its market value over the total
market value of the portfolio, so the weights sum to about one hundred. This
assumes the filing covers a single fund, which is the case for a standalone
registrant like the one in the worked example. A trust filing that bundles many
funds needs one more step first, attributing each schedule to its fund using the
fund name printed above it, before weights can be computed per fund.

## Scaling, and what this repository does and does not do

The worked example runs on a single fund so the result is easy to check by eye,
and it is verified: the extracted total ties to the filing's own reported total to
the dollar. The layered design is what lets one code path read filings whose
layout differs, and each strategy is a fallback for the previous one, so a filing
that a strict parser would drop is still read through a lower rung of the stack.

This repository is the readable core of that method, not the hardened production
system it comes from. Testing it across several fund families shows both its reach
and its limits. It extracts cleanly on layouts close to the demonstrated one, and
it fails or misreads on layouts far from it, for two main reasons seen in testing.
Some filers place the schedule in a separate document from the primary file, so
the extractor has to be pointed at the right document. And on a few unusual
layouts the value column heuristic picks the wrong numeric column, which shows up
as an implausible portfolio total. The production pipeline built during the
internship adds the per family handling and the multi document logic needed to run
across the whole pre 2019 universe. Reproducing all of that is beyond the scope of
this focused repository, whose goal is to make the method readable and to prove it
on a real fund.
