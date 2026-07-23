"""Parse Jhaveri Securities 'Portfolio Valuation Report - Fund Sub Category Wise' PDFs.

Word-position based parser (pdfplumber). One report generator, stable layout.
Column values are right-aligned, so tokens are assigned to columns by nearest
right-edge among the per-page header anchors. Every file passes reconciliation
gates or is flagged — no silent loads.

Format quirks handled (seen in real files):
- fund names wrap onto 1-2 continuation lines ~10pt below the row; real section
  headers sit >=15pt below, so a y-gap threshold disambiguates (a wrapped name
  like "... Hybrid - Segregated Portfolio 2 Reg-G" otherwise looks like a header)
- segregated-portfolio rows carry NA for cost/NAV/market value
- folio sometimes glues to the fund-name tail into one token ("Reg-G34229386")
- big percentages carry commas ("2,667.10"); minors have no PAN line

Usage:
    python parse_jhaveri.py --pdf-root /home/ubuntu/jhaveri_data/pdfs --out parsed.json
"""

# pdfplumber lives in the dedicated parse venv (/home/ubuntu/jhaveri_data/venv),
# deliberately not in the prod .venv:
# pyright: reportMissingImports=false
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pdfplumber

SUMMARY_FIELDS = [
    "lumpsum_purchases",
    "systematic_investments",
    "switch_ins",
    "redemptions",
    "systematic_withdrawals",
    "switch_outs",
    "dividend_payouts",
    "dividend_reinvested",
    "mv_equity",
    "mv_debt",
    "mv_hybrid",
    "mv_others",
    "mv_total",
    "overall_abs_return_pct",
    "overall_xirr_pct",
]
SUMMARY_X = [47, 115, 154, 226, 280, 336, 388, 439, 476, 536, 604, 654, 689, 737, 776]

# 13 numeric columns of a holding row, left to right; anchor = header token x1
HOLDING_COLS = [
    "inv_days",
    "investments",
    "withdrawals",
    "dividends_reinvested",
    "dividend_payouts",
    "balance_units",
    "avg_cost",
    "cost_amount",
    "nav",
    "market_value",
    "port_weight_pct",
    "abs_return_pct",
    "xirr_pct",
]
# fallback right-edge anchors (measured); refined per page from the header line
DEFAULT_ANCHORS = [272, 340, 380, 421, 463, 525, 560, 610, 655, 702, 733, 768, 799]

NUM_RE = re.compile(r"^-?[\d,]*\d(\.\d+)?$")
DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{2}$")
CATEGORY_RE = re.compile(
    r"^(Equity|Debt|Hybrid|Others|Solution Oriented|Commodities|Commodity|Gold|Fund of Funds)\s*-\s*(.+)$",
    re.I,
)
GLUED_FOLIO_RE = re.compile(r"^(.*?[A-Za-z-])(\d{6,}(?:/\d+)?)$")

FOLIO_X = 152
DATE_X = 215
NAME_MAX_X = 150
CONT_GAP = 13.0  # name continuations sit ~10pt below their row; new sections >=15pt


def _num(tok: str) -> Decimal | None:
    t = tok.replace(",", "")
    return Decimal(t) if NUM_RE.match(tok) and re.match(r"^-?\d+(\.\d+)?$", t) else None


def _is_bold(line: list[dict]) -> bool:
    return all("Bold" in w.get("fontname", "") for w in line if w["text"].strip())


def _lines(page) -> list[list[dict]]:
    words = page.extract_words(extra_attrs=["fontname"])
    out: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if out and abs(out[-1][0]["top"] - w["top"]) < 2.5:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in out]


def _header_anchors(lines: list[list[dict]]) -> list[float]:
    """Right edges of the 13 numeric column headers on this page."""
    for line in lines:
        toks = [w["text"] for w in line]
        if "Folio" in toks and "NAV" in toks and "Days" in toks:
            want = [
                "Days",
                "Ins",
                "Outs",
                "Reinv.",
                "Payouts",
                "Units",
                "Cost",
                "Amount",
                "NAV",
                "Value",
                "(%)",
                "(%)",
                "(%)",
            ]
            anchors, i = [], 0
            for w in line:
                if i < len(want) and w["text"] == want[i]:
                    anchors.append(w["x1"])
                    i += 1
            if i == len(want):
                return anchors
    return [float(a) for a in DEFAULT_ANCHORS]


def parse_pdf(path: Path) -> dict:
    res: dict = {"source_file": str(path), "holdings": [], "errors": []}
    with pdfplumber.open(path) as pdf:
        first = _lines(pdf.pages[0])
        _parse_header(first, res)
        current_cat: tuple[str, str] | None = None
        pending: dict | None = None
        pending_top = -100.0
        for pageno, page in enumerate(pdf.pages):
            lines = _lines(page) if pageno else first
            anchors = _header_anchors(lines)
            for line in lines:
                text = " ".join(w["text"] for w in line)
                top = line[0]["top"]
                if text.startswith(
                    ("Transactions are considered", "Investments include", "Note :")
                ):
                    m = re.search(
                        r"upto (\d{2}-\w{3}-\d{4}) , NAV is considered upto (\d{2}-\w{3}-\d{4})",
                        text,
                    )
                    if m:
                        res["txn_upto_date"] = (
                            datetime.strptime(m.group(1), "%d-%b-%Y").date().isoformat()
                        )
                        res["nav_upto_date"] = (
                            datetime.strptime(m.group(2), "%d-%b-%Y").date().isoformat()
                        )
                    pending = None
                    continue
                # wrapped fund-name continuation: entirely in the name zone,
                # close below its row, regular font (section headers are BOLD —
                # the deterministic discriminator; wrapped names can otherwise
                # look like headers and vice versa)
                if (
                    pending is not None
                    and top - pending_top < CONT_GAP
                    and line[-1]["x1"] < FOLIO_X
                    and not _is_bold(line)
                ):
                    pending["fund_name"] += " " + text
                    pending_top = top
                    continue
                m = CATEGORY_RE.match(text)
                if m and line[0]["x0"] < 60 and line[-1]["x1"] < 400 and _is_bold(line):
                    current_cat = (m.group(1).title(), text.strip())
                    pending = None
                    continue
                row = _parse_holding_line(line, anchors)
                if row is not None:
                    if current_cat is None:
                        res["errors"].append(f"holding before category header: {text[:60]}")
                        continue
                    row["asset_class"], row["sub_category"] = current_cat
                    res["holdings"].append(row)
                    pending, pending_top = row, top
                elif not any(abs(w["x1"] - a) < 6 for w in line for a in anchors[:1]):
                    pending = None  # any other content breaks continuation chains
    _validate(res)
    return res


def _parse_header(lines: list[list[dict]], res: dict) -> None:
    for line in lines:
        text = " ".join(w["text"] for w in line)
        m = re.search(r"\(As On (\d{2}/\d{2}/\d{4})\)", text)
        if m:
            res["as_on_date"] = datetime.strptime(m.group(1), "%d/%m/%Y").date().isoformat()
        if " Pg. " in f" {text} " and "client_name" not in res:
            toks = [w["text"] for w in line]
            m2 = re.search(r"PAN:\s*([A-Z]{5}\d{4}[A-Z])", text)
            if m2:
                res["pan"] = m2.group(1)
            name_toks = []
            for t in toks:
                if t in ("Pg.", "PAN:"):
                    break
                name_toks.append(t)
            name = " ".join(name_toks)
            cm = re.search(r"\[([A-Za-z0-9]+)\]", name)
            if cm:
                res["client_code"] = cm.group(1)
                name = (name[: cm.start()] + name[cm.end() :]).strip()
            res["client_name"] = re.sub(r"\s*\(Continued\)\s*$", "", name).strip()
        for pat, key in ((r"Mobile No : (.+)", "mobile"), (r"Email ID : (.+)", "email")):
            m3 = re.match(pat, text)
            if m3 and key not in res:
                res[key] = m3.group(1).strip()
    res.update(_parse_summary(lines))


def _parse_summary(lines: list[list[dict]]) -> dict:
    for line in lines:
        nums = [w for w in line if _num(w["text"]) is not None]
        if len(nums) >= 10:
            top = line[0]["top"]
            for other in lines:
                if other is not line and abs(other[0]["top"] - top) < 8:
                    nums.extend(w for w in other if _num(w["text"]) is not None)
            nums.sort(key=lambda w: w["x0"])
            if len(nums) != len(SUMMARY_FIELDS):
                return {
                    "errors_summary": f"summary has {len(nums)} numeric tokens, expected {len(SUMMARY_FIELDS)}"
                }
            out = {}
            for field, anchor, w in zip(SUMMARY_FIELDS, SUMMARY_X, nums, strict=True):
                if abs(w["x0"] - anchor) > 45:
                    return {
                        "errors_summary": f"summary token {w['text']}@{int(w['x0'])} far from anchor {anchor} ({field})"
                    }
                out[field] = str(_num(w["text"]))
            return out
    return {"errors_summary": "summary row not found"}


def _parse_holding_line(line: list[dict], anchors: list[float]) -> dict | None:
    name_words = [w["text"] for w in line if w["x0"] < NAME_MAX_X]
    folio = [
        w["text"]
        for w in line
        if FOLIO_X - 4 <= w["x0"] < DATE_X - 5 and not DATE_RE.match(w["text"])
    ]
    date_tok = [w["text"] for w in line if DATE_RE.match(w["text"]) and abs(w["x0"] - DATE_X) < 10]
    if name_words and date_tok and not folio:
        # folio glued onto the fund-name tail: "Reg-G34229386"
        m = GLUED_FOLIO_RE.match(name_words[-1])
        if m:
            name_words[-1] = m.group(1).rstrip("-")
            folio = [m.group(2)]
    if not (name_words and folio and date_tok):
        return None
    cells: dict[str, str | None] = {c: None for c in HOLDING_COLS}
    for w in line:
        if w["x0"] < DATE_X + 25:
            continue
        val = _num(w["text"])
        if val is None and w["text"] != "NA":
            continue
        col = min(range(len(anchors)), key=lambda i: abs(anchors[i] - w["x1"]))
        cells[HOLDING_COLS[col]] = None if w["text"] == "NA" else str(val)
    filled = sum(v is not None for v in cells.values())
    if filled < 6:
        return None
    row: dict = dict(cells)
    row["fund_name"] = " ".join(name_words)
    row["folio"] = folio[0]
    row["inv_since"] = datetime.strptime(date_tok[0], "%d/%m/%y").date().isoformat()
    row["inv_days"] = int(row["inv_days"]) if row["inv_days"] is not None else None
    return row


def _validate(res: dict) -> None:
    errs = res["errors"]
    if "errors_summary" in res:
        errs.append(res.pop("errors_summary"))
    if not res.get("pan") and not res.get("client_name"):
        errs.append("no client identity parsed")
    if not res["holdings"]:
        if Decimal(res.get("mv_total", "0") or "0") != 0:
            errs.append("no holdings parsed but stated total nonzero")
        return
    tol = Decimal("3")
    for h in res["holdings"]:
        if (
            h["market_value"] is not None
            and h["nav"] is not None
            and h["balance_units"] is not None
        ):
            mv = Decimal(h["market_value"])
            calc = Decimal(h["balance_units"]) * Decimal(h["nav"])
            if abs(calc - mv) > max(tol, abs(mv) * Decimal("0.002")):
                errs.append(f"units*nav != mv for {h['fund_name']}: {calc:.0f} vs {mv}")
    if "mv_total" in res:
        total = sum(
            Decimal(h["market_value"]) for h in res["holdings"] if h["market_value"] is not None
        )
        stated = Decimal(res["mv_total"])
        if abs(total - stated) > Decimal(len(res["holdings"])) * tol:
            errs.append(f"sum(holdings mv)={total} != stated total {stated}")
        wgt = sum(
            Decimal(h["port_weight_pct"])
            for h in res["holdings"]
            if h["port_weight_pct"] is not None
        )
        if stated > 0 and abs(wgt - 100) > Decimal("1.5"):
            errs.append(f"weights sum to {wgt}")
        parts = sum(Decimal(res[k]) for k in ("mv_equity", "mv_debt", "mv_hybrid", "mv_others"))
        if abs(parts - stated) > 2:
            errs.append(f"asset-class split {parts} != total {stated}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    results, bad = [], 0
    for path in sorted(Path(args.pdf_root).rglob("*.pdf")):
        try:
            res = parse_pdf(path)
        except Exception as e:
            res = {"source_file": str(path), "holdings": [], "errors": [f"exception: {e!r}"]}
        res["family_group"] = path.parent.name
        results.append(res)
        if res["errors"]:
            bad += 1
            print(f"FAIL {path.name}: {res['errors'][:2]}")
    Path(args.out).write_text(json.dumps(results, indent=1))
    ok = len(results) - bad
    print(f"\n{ok}/{len(results)} files parse+reconcile clean; {bad} flagged")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
