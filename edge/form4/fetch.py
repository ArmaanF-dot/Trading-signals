"""Fetch Form 4 filings from EDGAR (current-filings Atom feed -> index page -> XML)."""
import re
import xml.etree.ElementTree as ET

import config
from edge import http

ATOM = "{http://www.w3.org/2005/Atom}"


def _get(url: str) -> str:
    headers = {"User-Agent": config.sec_user_agent(), "Accept-Encoding": "gzip, deflate"}
    return http.get(url, headers=headers, min_interval=config.SEC_MIN_INTERVAL).text


def parse_feed(atom_text: str) -> list[dict]:
    """Return [{accession, form_type, index_url}] from an EDGAR Atom page."""
    out = []
    for entry in ET.fromstring(atom_text).findall(f"{ATOM}entry"):
        m = re.search(r"accession-number=([\d-]+)", entry.findtext(f"{ATOM}id", ""))
        link = entry.find(f"{ATOM}link")
        cat = entry.find(f"{ATOM}category")
        if not m or link is None:
            continue
        out.append({
            "accession": m.group(1),
            "form_type": cat.get("term", "") if cat is not None else "",
            "index_url": link.get("href", ""),
        })
    return out


def list_recent_filings(pages: int = config.FORM4_FEED_PAGES) -> list[dict]:
    """Paginate the feed; a filing appears once per party so dedupe by accession."""
    seen, filings = set(), []
    for p in range(pages):
        url = f"{config.FORM4_FEED_URL}&start={p * config.FORM4_FEED_PAGE_SIZE}"
        for f in parse_feed(_get(url)):
            if f["accession"] not in seen and f["form_type"] in ("4", "4/A"):
                seen.add(f["accession"])
                filings.append(f)
    return filings


def find_xml_url(index_html: str) -> str | None:
    """Pick the raw ownership XML from a filing index page (skip the xsl-rendered copy)."""
    for href in re.findall(r'href="([^"]+\.xml)"', index_html, flags=re.I):
        if "/xsl" not in href.lower():
            return href if href.startswith("http") else config.SEC_BASE + href
    return None


def fetch_filing_xml(index_url: str) -> str | None:
    xml_url = find_xml_url(_get(index_url))
    return _get(xml_url) if xml_url else None
