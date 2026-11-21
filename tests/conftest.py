import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
FIX = Path(__file__).parent / "fixtures"


def make_fca_xlsx(path, rows):
    """rows: (holder, issuer, isin, pct, date). Mimics FCA layout: title rows, then header."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Current Disclosures"
    ws.append(["Short positions (generated test fixture)"])
    ws.append([])
    ws.append(["Position Holder", "Name of Share Issuer", "ISIN", "Net Short Position (%)", "Position Date"])
    for r in rows:
        ws.append(list(r))
    wb.create_sheet("Historic Disclosures").append(["ignored"])
    wb.save(path)
