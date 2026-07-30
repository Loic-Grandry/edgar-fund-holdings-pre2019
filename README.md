# Recovering pre 2019 fund holdings from SEC filings

This project reconstructs the portfolio of a US mutual fund from the raw HTML of
its filings with the Securities and Exchange Commission. It takes a filing as it
sits on EDGAR, strips it down, finds the schedule of investments among dozens of
other tables, reads each holding with its market value, classifies it by asset
class, removes the accounting noise, and returns a clean table where the weights
sum to one hundred.

The focus is the period before 2019, which is the hard period, for a reason
explained just below. Everything runs on public data and open source tools.

This is a simplified, readable version of a larger research project built during
an internship, which covers the full universe of pre 2019 SEC filing formats for
US mutual funds. This repository handles a few common fund typographies and proves
the method on one fund, verified to the dollar. It is a demonstration of how the
problem is solved, not the production system that runs across every format.

## The problem, and why it is worth solving

Since 2019, funds file their holdings on form N-PORT. N-PORT is structured data,
so anyone can read a fund's portfolio directly, field by field, with no parsing.

Before 2019 there was nothing like it. A fund disclosed its holdings as HTML
tables buried inside its quarterly N-Q filing and its N-CSR annual report. Those
tables were built to be printed and read by a person, not by a machine. There was
no shared schema, no validation, and every fund family formatted its report its
own way. If you want a consistent panel of who held what before 2019, you have to
read that HTML and rebuild the data yourself.

That is what this pipeline does, and doing it well is mostly a matter of coping
with how differently the same portfolio can be printed.

## Why it is hard: one portfolio, many typographies

The same holding, say five million dollars of a wind turbine maker, shows up in
filings in ways that share almost no common structure across fund families:

- The value column is called "Market Value" at one family, "Value (USD)" at
  another, plain "Value" at a third. Shares can be "Shares", "Number of Shares",
  "Principal Amount" or "Par".
- Many older filings ship tables with no header cells at all, so a naive reader
  sees columns numbered 0, 1, 2 with no idea which is the name and which is the
  value.
- Sometimes the security name is folded into a section title instead of a real
  column, so the numbers are clean but the name is missing.
- Bonds are often printed as an issuer line followed by rows that carry only a
  coupon and a maturity date, with no issuer of their own.
- Every schedule is interleaved with subtotals, sector headers and balance lines
  that carry numbers but are not securities.

A parser written for one family breaks on the next. The pipeline is therefore
built as a stack of strategies that go from the cleanest layout to the most
degraded, so a single code path reads filings from many families. The full logic
is written out in [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

This repository is the readable, self contained core of a larger pipeline built
during a research internship. The worked example below is verified to the dollar,
and the code handles a range of layouts, but it is a demonstration of the method
rather than a hardened universal parser. Some fund families format their filings
in ways that need the extra handling described under Limitations. It shows how the
problem is solved and proves it on a real fund, and does not claim a clean
extraction from every filing ever made.

## Worked example, on a real filing

The repository ships one real filing, the New Alternatives Fund N-Q from late
2018. It is a standalone renewable energy fund, so its portfolio is a single
clean schedule. Run the extraction offline with no network:

```bash
python examples/extract_one_fund.py
```

Output:

```
Filing: New Alternatives Fund, form N-Q, filed 2018-11-26
Raw HTML size: 109,788 characters

Stage 1 and 2. Read every table and label it
  9 tables found, labelled as: {'SoI': 5, 'Other': 4}

Stage 3 to 5. Extract, classify and weight the holdings
  42 holdings kept after dropping accounting and noise rows
  asset classes: {'EQUITY_OR_UNKNOWN': 36, 'BOND': 5, 'FUND': 1}
  total market value: 175,095,568 US dollars
  weights sum to 100.0 percent, as expected

Largest ten holdings by weight:
                     security_name       asset_class   weight_pct
              Orsted A/S (Denmark) EQUITY_OR_UNKNOWN     5.82
 Brookfield Renewable Partners LP  EQUITY_OR_UNKNOWN     5.61
    Hannon Armstrong Sustainable   FUND                 5.52
 Vestas Wind Systems A/S (Denmark) EQUITY_OR_UNKNOWN     5.41
       Pattern Energy Group, Inc.  EQUITY_OR_UNKNOWN     5.39
```

The pipeline finds the five schedule tables among nine, reads 42 real holdings,
drops the subtotals and the balance line, classifies each security, and produces
weights that sum to one hundred. The largest positions are exactly the renewable
energy leaders you would expect to see in this fund, recovered from raw HTML.

This example is verified, not just plausible. The extracted portfolio total of
175,095,568 dollars ties to the filing's own reported total investments figure to
the dollar, which is the strongest check there is that nothing was double counted,
missed or misread.

To run it live against EDGAR instead, set your own contact email and call the
fetch example:

```bash
export EDGAR_USER_AGENT="Your Name your.email@example.com"
python examples/fetch_from_edgar.py 355767
```

## Repository layout

```
edgar-fund-holdings-pre2019/
├── src/edgar_holdings/
│   ├── fetch.py       download N-Q and N-CSR filings from EDGAR
│   ├── tables.py      read HTML tables, label them, repair missing headers
│   ├── extract.py     read holdings from a schedule, three fallback strategies
│   ├── classify.py    asset class of a security, drop accounting noise
│   ├── patterns.py    number parsing, column patterns, noise and bond helpers
│   └── holdings.py    tie it together into one clean holdings table
├── data/
│   └── sample_new_alternatives_fund_2018_nq.htm   one real filing, for offline runs
├── docs/
│   └── METHODOLOGY.md   the full pipeline, stage by stage
├── examples/
│   ├── extract_one_fund.py   the offline worked example above
│   └── fetch_from_edgar.py   the same thing live from EDGAR
└── tests/
    └── test_pipeline.py
```

## Installation

```bash
pip install -r requirements.txt
```

The dependencies are pandas for the data, lxml and beautifulsoup4 for the HTML.

## A note on EDGAR and privacy

The SEC asks every program that downloads from EDGAR to identify itself with a
contact email and to stay under ten requests per second. This project reads that
contact string from the `EDGAR_USER_AGENT` environment variable, so no personal
address is written into the code. Set it to your own email before running
anything that touches the network. The offline example needs none of this.

## Limitations

These are stated plainly because the repo is meant to be read and trusted, not
oversold. I tested the pipeline on several fund families beyond the shipped
example and found real gaps, listed here.

- The worked example is a single fund. A trust filing that bundles several funds
  needs an extra step first, matching each schedule to its fund by the name
  printed above it, before weights can be computed per fund. The methodology note
  describes this step.
- Holdings are not always in the filing's primary document. Some filers put only
  the certifications in the primary file and the schedule in a separate document,
  so pointing the extractor at the right file matters. The example uses a filing
  where the schedule is in the primary document.
- The value column heuristics are tuned on common layouts. On an unusual layout
  the extractor can pick the wrong numeric column, which shows up as an
  implausible portfolio total. Comparing the extracted total against the filing's
  own reported total, as the worked example does, is the right way to catch this.
- The classifier and the extractor are rule based. They are tuned on a large
  sample of real filings, but a filing with a layout far from the demonstrated
  ones can lose rows or misread values. The design goal is high recall with clean
  output on common layouts, not perfection on every document ever filed.
- Identifiers such as CUSIP are captured when a filing prints them, which many
  pre 2019 filings do not. Matching holdings to a security master by name is a
  separate problem outside this repository.

## Context

This is a focused, self contained version of a holdings reconstruction pipeline
built during a research internship on US mutual funds. The full research pipeline
covers the entire universe of pre 2019 SEC filing formats, with the per family
handling and multi document logic needed to run across several thousand funds.

This repository is deliberately smaller. It handles a few common fund
typographies, keeps one clean worked example that is verified to the dollar, and
lays out the core logic so the method can be read and reproduced end to end. It is
meant to show clearly how the extraction works and to prove it on a real fund, not
to reproduce the full production system.
