"""
A small EDGAR client for fund holdings filings.

Before 2019, funds disclosed their full portfolio on form N-Q every quarter and
inside the N-CSR annual and semi annual reports. N-Q was retired in 2019 when the
structured N-PORT form took over, which is exactly why the pre 2019 holdings have
to be recovered from HTML rather than read from a clean data feed.

The SEC asks every program to identify itself with a contact email in the request
header and to stay under ten requests per second. This client reads the contact
string from the EDGAR_USER_AGENT environment variable, so no personal address is
written into the code. Set it once in your shell with your own email:

    export EDGAR_USER_AGENT="Your Name your.email@example.com"
"""
from __future__ import annotations

import json
import os
import time
from urllib.request import Request, urlopen

BASE = "https://www.sec.gov"
DATA = "https://data.sec.gov"

# Forms that carry a full schedule of investments for a fund.
HOLDINGS_FORMS = ("N-Q", "N-CSR", "N-CSRS", "N-30D")

_FALLBACK_USER_AGENT = (
    "edgar-fund-holdings-pre2019 (set the EDGAR_USER_AGENT variable "
    "with your contact email)"
)

_MIN_INTERVAL_SECONDS = 0.2
_last_request = 0.0


def user_agent() -> str:
    """Return the User-Agent string, preferring the environment variable."""
    return os.environ.get("EDGAR_USER_AGENT", _FALLBACK_USER_AGENT)


def _get(url: str) -> bytes:
    global _last_request
    wait = _MIN_INTERVAL_SECONDS - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    request = Request(url, headers={"User-Agent": user_agent()})
    with urlopen(request) as response:
        data = response.read()
    _last_request = time.time()
    return data


def list_holdings_filings(cik: str | int, limit: int = 20) -> list[dict]:
    """List a filer's recent holdings filings, most recent first.

    Each item has the form, accession number, filing date and the URL of the
    primary document.
    """
    cik10 = str(int(cik)).zfill(10)
    submissions = json.loads(_get(f"{DATA}/submissions/CIK{cik10}.json"))
    recent = submissions["filings"]["recent"]

    out: list[dict] = []
    for form, accession, date, primary in zip(
        recent["form"],
        recent["accessionNumber"],
        recent["filingDate"],
        recent["primaryDocument"],
    ):
        if form not in HOLDINGS_FORMS:
            continue
        acc_nodash = accession.replace("-", "")
        url = f"{BASE}/Archives/edgar/data/{int(cik)}/{acc_nodash}/{primary}"
        out.append({"form": form, "accession": accession, "date": date, "url": url})
        if len(out) >= limit:
            break
    return out


def download(url: str) -> str:
    """Download a filing document and return it as text."""
    return _get(url).decode("utf-8", errors="replace")
