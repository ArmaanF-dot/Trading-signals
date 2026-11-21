"""Parse EDGAR Form 4 ownership XML into open-market purchase rows."""
import xml.etree.ElementTree as ET

COLUMNS = [
    "accession", "form_type", "issuer_cik", "issuer", "ticker",
    "owner_cik", "owner", "role", "is_director", "is_officer", "officer_title",
    "is_ten_pct", "date", "shares", "price", "value",
]


def _text(node, path: str) -> str:
    el = node.find(path) if node is not None else None
    return (el.text or "").strip() if el is not None and el.text else ""


def _flag(node, path: str) -> bool:
    return _text(node, path).lower() in ("1", "true")


def _float(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _role(is_director: bool, is_officer: bool, title: str, is_ten: bool) -> str:
    parts = []
    if is_officer:
        parts.append(title or "Officer")
    if is_director:
        parts.append("Director")
    if is_ten:
        parts.append("10% owner")
    return ", ".join(parts) or "Other"


def parse_form4(xml_text: str, accession: str) -> list[dict]:
    """Return one dict per (reporting owner, open-market purchase transaction).

    Keeps only nonDerivative transactions with code "P" and price > 0.
    """
    root = ET.fromstring(xml_text)
    form_type = _text(root, "documentType") or "4"
    issuer = root.find("issuer")
    issuer_cik = _text(issuer, "issuerCik")
    issuer_name = _text(issuer, "issuerName")
    ticker = _text(issuer, "issuerTradingSymbol").upper()

    owners = []
    for ro in root.findall("reportingOwner"):
        rel = ro.find("reportingOwnerRelationship")
        is_dir, is_off, is_ten = _flag(rel, "isDirector"), _flag(rel, "isOfficer"), _flag(rel, "isTenPercentOwner")
        title = _text(rel, "officerTitle")
        owners.append({
            "owner_cik": _text(ro, "reportingOwnerId/rptOwnerCik"),
            "owner": _text(ro, "reportingOwnerId/rptOwnerName"),
            "role": _role(is_dir, is_off, title, is_ten),
            "is_director": is_dir, "is_officer": is_off,
            "officer_title": title, "is_ten_pct": is_ten,
        })

    rows = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        if _text(tx, "transactionCoding/transactionCode") != "P":
            continue
        if _text(tx, "transactionAmounts/transactionAcquiredDisposedCode/value") not in ("A", ""):
            continue
        shares = _float(_text(tx, "transactionAmounts/transactionShares/value"))
        price = _float(_text(tx, "transactionAmounts/transactionPricePerShare/value"))
        date = _text(tx, "transactionDate/value")[:10]
        if not shares or shares <= 0 or price is None or price <= 0 or not date:
            continue
        for o in owners:
            rows.append({
                "accession": accession, "form_type": form_type,
                "issuer_cik": issuer_cik, "issuer": issuer_name, "ticker": ticker,
                **o, "date": date, "shares": shares, "price": price,
                "value": round(shares * price, 2),
            })
    return rows
