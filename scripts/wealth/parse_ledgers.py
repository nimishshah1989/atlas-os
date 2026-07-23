"""Parse Jhaveri back-office 'Folio Ledger' PDFs → per-client transaction JSON.

Same generator family as the valuation reports (parse_jhaveri.py): word-position
parsing with pdfplumber, per-page right-edge column anchors from the header row,
per-file reconciliation gates — no silent output.

Layout (observed on real files):
  repeated per fund-folio block (and re-printed at every page break):
    holder line   "A/B [Anyone or Survivor(s)]   Tax Status <ts>"
    advisor line  "Your Advisor : NAME [code] Branch : <branch>   KYC:Yes|No"
    a/c line      "A/C Type :Saving"
    fund line     "Fund <name>[ / <ISIN>]   Folio No. <folio>"     (ISIN optional)
    "Holding Type <t>" · "Debits  Credits" · column header
    rows: dated txns · dated "*** Stamp Duty|STT ... ***" charge annotations
          (folded into the txn row above) · undated "Opening Balance <units>"
          (page-break carry-forward when a segment of the same fund-folio is
          already open — verified against the running balance and dropped;
          a true brought-forward position when the block starts with it)
    bold totals row (no date) then "Market Value as on <d> : <mv> NAV : <nav>
    Abs.Ret.(%) <x> XIRR (%) <y>" closes the block.

Per-file gates (G1 family — parse-time self-checks; failures flag the file):
  * running balance: prev ± units == printed balance (0.001)
  * carry-forward Opening Balance == running balance at page break
  * bold totals row == sum of parsed rows (amounts ₹0.02, units 0.002)
  * final balance × block NAV ≈ block market value (max ₹3, 0.2%)
  * every numeric token lands on a known column anchor; unknown descriptions
    and unknown *** annotations are errors, so new row shapes surface loudly.

Usage:
  /home/ubuntu/jhaveri_data/venv/bin/python scripts/wealth/parse_ledgers.py \
      --pdf-root /home/ubuntu/jhaveri_data/ledgers --out ledger_parsed.json [--only NAME]
"""

# pdfplumber lives in the dedicated parse venv (/home/ubuntu/jhaveri_data/venv),
# deliberately not in prod .venv:
# pyright: reportMissingImports=false
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from decimal import Decimal
from multiprocessing import Pool
from pathlib import Path

import pdfplumber

NUM_RE = re.compile(r"^-?[\d,]*\d(\.\d+)?$")
DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{2}$")
DESC_MAX_X = 183.0  # description tokens live left of the Trade Price column
ANCHOR_TOL = 8.0  # numeric right-edge vs header anchor, data rows
TOTALS_TOL = 40.0  # bold totals row: debit-amount total prints ~25pt left

TXN_TYPES = [  # (regex on normalized description, canonical type)
    (re.compile(r"^sip\b|^sip installment", re.I), "sip"),
    (re.compile(r"^(initial )?purchase\b", re.I), "purchase"),
    (re.compile(r"^switch in\b|^stp in\b|^switchover in\b", re.I), "switch_in"),
    (re.compile(r"^switch out\b|^stp out\b|^switchover out\b", re.I), "switch_out"),
    (re.compile(r"^redemption\b|^redeem", re.I), "redemption"),
    (re.compile(r"^swp\b|^systematic withdrawal", re.I), "swp"),
    (re.compile(r"^dividend reinvest", re.I), "div_reinvest"),
    (re.compile(r"^(dividend|idcw)( payout| paid)?\b", re.I), "div_payout"),
    (re.compile(r"^bonus\b", re.I), "bonus"),
    (re.compile(r"^segregat", re.I), "segregation"),
    (re.compile(r"^transfer-?in\b", re.I), "transfer_in"),
    (re.compile(r"^transfer-?out\b", re.I), "transfer_out"),
    (re.compile(r"^pledge\b", re.I), "pledge"),
    (re.compile(r"^unpledge\b", re.I), "unpledge"),
    (re.compile(r"^dtp in\b", re.I), "dtp_in"),
    (re.compile(r"^dtp out\b", re.I), "dtp_out"),
    (re.compile(r"^scheme merged from", re.I), "merger_in"),
    (re.compile(r"^scheme merged to", re.I), "merger_out"),
    (re.compile(r"^transmission in", re.I), "transmission_in"),
    (re.compile(r"^transmission out", re.I), "transmission_out"),
    (re.compile(r"^reversal\b", re.I), "reversal"),
    (re.compile(r"^consolidation in", re.I), "consolidation_in"),
    (re.compile(r"^consolidation out", re.I), "consolidation_out"),
]
# rows that may carry units only in the balance column (implied by the jump)
JUMP_TYPES = {"transfer_in", "transfer_out", "merger_in", "merger_out",
              "transmission_in", "transmission_out", "consolidation_in", "consolidation_out"}
# product families whose printed NAV column is not the effective unit price
# (side-pocket paise NAVs, insurance-linked premium splits) — units+amounts still real
G2_EXEMPT_RE = re.compile(r"segregated|unit linked insurance", re.I)


def _num(tok: str) -> Decimal | None:
    t = tok.replace(",", "")
    return Decimal(t) if NUM_RE.match(tok) and re.match(r"^-?\d+(\.\d+)?$", t) else None


def _lines(page) -> list[list[dict]]:
    words = page.extract_words(extra_attrs=["fontname"])
    out: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if out and abs(out[-1][0]["top"] - w["top"]) < 2.5:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in out]


def _is_bold(line: list[dict]) -> bool:
    return all("Bold" in w.get("fontname", "") for w in line if w["text"].strip())


COL_NAMES = ["nav", "debit_amount", "stt", "debit_units", "credit_amount", "credit_units", "balance_units"]


def _header_anchors(line: list[dict]) -> list[float] | None:
    """Right edges of the 7 numeric columns from the 'Date Description Trade
    Price Amount STT Units Amount Units Balance Units' header row."""
    toks = [w["text"] for w in line]
    if toks[:2] != ["Date", "Description"] or "STT" not in toks:
        return None
    price = [w for w in line if w["text"] == "Price"]
    amounts = [w for w in line if w["text"] == "Amount"]
    stt = [w for w in line if w["text"] == "STT"]
    units = [w for w in line if w["text"] == "Units"]
    if not (len(price) == 1 and len(amounts) == 2 and len(stt) == 1 and len(units) == 3):
        return None
    return [
        price[0]["x1"], amounts[0]["x1"], stt[0]["x1"], units[0]["x1"],
        amounts[1]["x1"], units[1]["x1"], units[2]["x1"],
    ]


def _assign_columns(line: list[dict], anchors: list[float], errs: list[str], tol: float = ANCHOR_TOL) -> dict:
    """Assign numeric (and '-') tokens right of the description zone to columns
    by nearest right-edge anchor."""
    cells: dict[str, Decimal | None] = {c: None for c in COL_NAMES}
    for w in line:
        if w["x0"] < DESC_MAX_X or w["text"] == "***":  # annotation closer overlaps column zone
            continue
        val = _num(w["text"])
        if val is None and w["text"] != "-":
            errs.append(f"non-numeric token in column zone: {w['text']!r}@{int(w['x0'])}")
            continue
        dists = [abs(w["x1"] - a) for a in anchors]
        idx = dists.index(min(dists))
        if dists[idx] > tol:
            errs.append(f"token {w['text']!r} right-edge {int(w['x1'])} not on any anchor")
            continue
        col = COL_NAMES[idx]
        if cells[col] is not None:
            errs.append(f"column {col} double-filled ({cells[col]} then {w['text']})")
        cells[col] = val if val is not None else None  # '-' stays None
    return cells


def classify(desc: str) -> str | None:
    for rx, t in TXN_TYPES:
        if rx.search(desc):
            return t
    return None


def _new_seq(name: str | None) -> dict:
    return {
        "name": name,  # resolved scheme name (None until a continuation header names it)
        "rows": [],
        "balance": None,  # last verified (day-end) printed balance
        "prev_balance": None,
        "day": None, "day_acc": Decimal("0"),
        "day_last_bal": None, "prev_printed": None,
        "last_date": None,
        "pending_ob": None,  # Opening Balance awaiting resolution against the next row
        "folio": None,  # resolved folio (multi-folio blocks); block folio when None
        "alt_balance": None,  # my chain when a day-end print disagreed (lag suspect)
        "pending_break": None,  # (day, computed, printed) awaiting next-day verdict
    }


class Block:
    """One folio ledger block (spans page breaks). Some generator variants
    concatenate several schemes' sequences under one folio header with a single
    combined totals+MV close — sequences split on strict date regression and are
    named only when a page-break continuation header catches them mid-flight."""

    def __init__(self, fund_name: str, isin: str | None, folio: str, page: int):
        self.fund_name, self.isin, self.folio, self.page = fund_name, isin, folio, page
        self.seqs: list[dict] = [_new_seq(fund_name)]  # header names the first sequence
        self.seqs[0]["folio"] = folio
        self.totals: dict | None = None
        self.mv: dict | None = None
        self.closed = False

    @property
    def cur(self) -> dict:
        return self.seqs[-1]

    @property
    def rows(self) -> list[dict]:
        return [r for q in self.seqs for r in q["rows"]]


def parse_pdf(path: Path) -> dict:
    res: dict = {
        "source_file": path.name,
        "advisor_folder": path.parent.name,
        "client_name": None,
        "client_code": None,
        "report_date": None,
        "email": None,
        "mobile": None,
        "profile": {},  # joint_holders, holding_mode, tax_status, advisor_name, advisor_code, branch, kyc_ok, account_type
        "blocks": [],
        "errors": [],
        "warnings": [],
    }
    errs: list[str] = res["errors"]
    warns: list[str] = res["warnings"]
    open_block: Block | None = None
    anchors: list[float] | None = None

    def flush_day(b: Block):
        # verify the accumulated day's units against the day's last printed balance.
        # Printed day-ends occasionally lag one event (generator garbles same-day
        # sequences) — a first mismatch is held as a suspect and forgiven when the
        # NEXT day-end confirms our own chain instead of the printed one.
        q = b.cur
        tol = Decimal("0.002")
        if q["day"] is not None and q["day_last_bal"] is not None:
            printed = q["day_last_bal"]
            expected = (q["balance"] if q["balance"] is not None else Decimal("0")) + q["day_acc"]
            ok = abs(expected - printed) <= tol
            if not ok and q["alt_balance"] is not None:
                exp_alt = q["alt_balance"] + q["day_acc"]
                if abs(exp_alt - printed) <= tol:
                    ok = True  # our chain confirmed — earlier printed value was a lag artifact
                    q["pending_break"] = None
                    q["alt_balance"] = None
            if ok:
                if q["pending_break"] is not None:
                    # printed chain confirmed instead — the balance column disagrees
                    # with the row set; rows are still guarded by the totals check.
                    d0, c0, p0 = q["pending_break"]
                    warns.append(
                        f"balance-column break {b.fund_name[:40]} f{b.folio} {d0}: "
                        f"computed {c0} vs printed {p0}"
                    )
                    q["pending_break"] = None
                    q["alt_balance"] = None
            else:
                # ahead-shifted block-start opening? dropping it may reconcile exactly
                first = q["rows"][0] if q["rows"] else None
                ob_u = Decimal(first["units"]) if (first and first["txn_type"] == "opening_balance") else None
                if ob_u is not None and abs(expected - printed - ob_u) <= tol:
                    q["rows"].pop(0)
                elif q["pending_break"] is None:
                    q["pending_break"] = (q["day"], expected, printed)
                    q["alt_balance"] = expected  # carry our chain for the verdict
                else:
                    d0, c0, p0 = q["pending_break"]
                    warns.append(
                        f"balance-column break {b.fund_name[:40]} f{b.folio} {d0}: "
                        f"computed {c0} vs printed {p0}"
                    )
                    q["pending_break"] = (q["day"], expected, printed)
                    q["alt_balance"] = expected
            q["prev_balance"] = q["balance"]
            q["balance"] = printed
        q["day"], q["day_acc"] = None, Decimal("0")

    def finish_block(b: Block):
        flush_day(b)
        rows = []
        seq_meta = []
        for idx, q in enumerate(b.seqs):
            if q["pending_break"] is not None:
                d0, c0, p0 = q["pending_break"]
                warns.append(
                    f"balance-column break {b.fund_name[:40]} f{b.folio} {d0}: "
                    f"computed {c0} vs printed {p0} (unresolved at block end)"
                )
            for r in q["rows"]:
                r["seq"] = idx
                rows.append(r)
            final = q["rows"][-1]["balance_units"] if q["rows"] else None
            seq_meta.append({"idx": idx, "name": q["name"], "folio": q["folio"],
                             "n_rows": len(q["rows"]), "final_balance": final})
        res["blocks"].append(
            {
                "fund_name": b.fund_name, "isin": b.isin, "folio": b.folio, "page": b.page + 1,
                "rows": rows, "sequences": seq_meta, "totals": b.totals, "mv": b.mv,
            }
        )

    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages):
            lines = _lines(page)
            page_has_body = False  # any txn/opening/totals seen on this page yet
            i = 0
            while i < len(lines):
                line = lines[i]
                text = " ".join(w["text"] for w in line)
                first_x = line[0]["x0"]

                # ---- mini-report boundary: page numbering restarts at "Pg. 1 of N" ----
                pg = re.search(r"Pg\. (\d+) of (\d+)$", text)
                if pg and pg.group(1) == "1" and not (pno == 0 and open_block is None):
                    if open_block is not None and not open_block.closed:
                        if open_block.totals is None:
                            errs.append(
                                f"block {open_block.fund_name[:40]!r} f{open_block.folio} "
                                f"open at sub-report boundary p{pno + 1}"
                            )
                        finish_block(open_block)
                        open_block = None
                    i += 1
                    continue

                # ---- client header (page 1) ----
                if pno == 0 and res["client_name"] is None:
                    m = re.match(r"^(.+?) \[([A-Za-z0-9]+)\]( (\d{2}-\w{3}-\d{4}))?$", text)
                    if m and "Advisor" not in text and "/" not in m.group(1):
                        res["client_name"] = m.group(1).strip()
                        res["client_code"] = m.group(2)
                        if m.group(4):
                            res["report_date"] = datetime.strptime(m.group(4).strip(), "%d-%b-%Y").date().isoformat()
                        i += 1
                        continue
                if res["email"] is None and text.startswith("Email ID :"):
                    res["email"] = text.split(":", 1)[1].strip() or None
                    i += 1
                    continue
                if res["mobile"] is None and text.startswith("Mobile No :") and pno == 0 and first_x < 60:
                    res["mobile"] = text.split(":", 1)[1].strip() or None
                    i += 1
                    continue

                # ---- block headers (repeat at page breaks) ----
                if "Tax Status" in text and first_x < 60:
                    p = res["profile"]
                    if not p:
                        left = text.split("Tax Status")[0].strip()
                        p["tax_status"] = text.split("Tax Status")[1].strip()
                        hm = re.search(r"\[([^\]]+)\]\s*$", left)
                        p["holding_mode"] = hm.group(1).strip() if hm else None
                        p["joint_holders"] = left[: hm.start()].strip() if hm else left
                    i += 1
                    continue
                if text.startswith("Your Advisor"):
                    p = res["profile"]
                    if "advisor_name" not in p:
                        m = re.match(r"Your Advisor : (.+?) \[(\d+)\] Branch : (.+?)\s*(KYC:(\w+))?$", text)
                        if m:
                            p["advisor_name"], p["advisor_code"] = m.group(1).strip(), m.group(2)
                            p["branch"] = m.group(3).strip()
                            p["kyc_ok"] = m.group(5) == "Yes" if m.group(5) else None
                        else:
                            errs.append(f"unparsed advisor line: {text[:80]}")
                    i += 1
                    continue
                if "A/C Type" in text and "account_type" not in res["profile"]:
                    res["profile"]["account_type"] = text.split(":", 1)[1].strip()
                    i += 1
                    continue

                # ---- fund line: open or continue a block ----
                if text.startswith("Fund ") and line[0]["text"] == "Fund":
                    ftoks = list(line)
                    ftext = text
                    if "Folio No." not in ftext and i + 1 < len(lines):  # wrapped fund name
                        nxt = lines[i + 1]
                        ftoks = ftoks + list(nxt)
                        ftext = ftext + " " + " ".join(w["text"] for w in nxt)
                        i += 1
                    fm = re.match(
                        r"^Fund (.+?)(?: / ([A-Z]{2}[A-Z0-9]{9}\d))? Folio No\. (\S+(?: / \d+)?)$", ftext
                    )
                    if not fm:
                        errs.append(f"unparsed fund line p{pno + 1}: {ftext[:90]}")
                        i += 1
                        continue
                    name, isin, folio = fm.group(1).strip(), fm.group(2), fm.group(3)
                    if (
                        open_block is not None
                        and not open_block.closed
                        and open_block.totals is None  # totals row ends a block's txn list
                        and (open_block.folio == folio or not page_has_body)
                    ):
                        # page-break continuation. The repeated header names whichever
                        # sequence is open at the break — a different name (or folio!)
                        # resolves a concatenated multi-scheme/multi-folio sequence.
                        if (name, folio) == (open_block.fund_name, open_block.folio):
                            open_block.isin = open_block.isin or isin
                        else:
                            open_block.cur["name"] = name
                            open_block.cur["folio"] = folio
                    else:
                        if open_block is not None and not open_block.closed:
                            # dead/merged-away schemes end with totals but no MV line
                            if open_block.totals is None:
                                errs.append(
                                    f"block {open_block.fund_name[:40]!r} f{open_block.folio} never closed"
                                )
                            finish_block(open_block)
                        open_block = Block(name, isin, folio, pno)
                    i += 1
                    continue

                # ---- column header → per-page anchors ----
                got = _header_anchors(line)
                if got:
                    anchors = got
                    i += 1
                    continue

                # ---- inside a block ----
                b = open_block
                if b is None or b.closed or anchors is None:
                    i += 1
                    continue

                # Market Value close line
                if text.startswith("Market Value as on"):
                    m = re.match(
                        r"Market Value as on (\d{2}/\d{2}/\d{4})? ?: ([\d,.\-]+) NAV : ([\d,.]+)"
                        r"(?: Abs\.Ret\.\(%\) (-?[\d,.]+))?(?: XIRR \(%\) (-?[\d,.]+))?",
                        text,
                    )
                    if not m:
                        errs.append(f"unparsed MV line p{pno + 1}: {text[:90]}")
                    else:
                        b.mv = {
                            "mv_date": datetime.strptime(m.group(1), "%d/%m/%Y").date().isoformat()
                            if m.group(1) else None,
                            "market_value": str(_num(m.group(2))),
                            "nav": str(_num(m.group(3))),
                            "abs_ret_pct": str(_num(m.group(4))) if m.group(4) else None,
                            "xirr_pct": str(_num(m.group(5))) if m.group(5) else None,
                        }
                    b.closed = True
                    finish_block(b)
                    i += 1
                    continue

                # Opening Balance (undated)
                if text.startswith("Opening Balance"):
                    cells = _assign_columns(line, anchors, errs)
                    ob = cells["balance_units"]
                    q = b.cur
                    if ob is None:
                        errs.append(f"Opening Balance without balance units p{pno + 1}")
                    else:
                        ok_vals = {q["day_last_bal"], q["prev_printed"], q["balance"], q["prev_balance"]}
                        if any(v is not None and abs(v - ob) <= Decimal("0.001") for v in ok_vals):
                            pass  # page-break carry-forward (often one row stale) — drop
                        elif q["day_last_bal"] is None and q["balance"] is None and not q["rows"]:
                            # block start: a true brought-forward position (approx; may be
                            # retro-dropped by flush_day if the day-ends disprove it)
                            q["rows"].append(
                                {
                                    "txn_date": None, "txn_type": "opening_balance",
                                    "description_raw": text, "raw": {}, "nav": None, "units": str(ob),
                                    "amount": None, "stt": None, "stamp_duty": None, "tds": None,
                                    "balance_units": str(ob), "is_debit": False,
                                    "page": pno + 1, "approx": True,
                                }
                            )
                            q["balance"] = ob
                        else:
                            # mid-block restatement — resolve against the next dated row
                            q["pending_ob"] = (ob, pno + 1, text)
                    page_has_body = True
                    i += 1
                    continue

                # dated rows: txn or *** charge annotation
                if DATE_RE.match(line[0]["text"]):
                    dt = datetime.strptime(line[0]["text"], "%d/%m/%y").date().isoformat()
                    desc = " ".join(w["text"] for w in line[1:] if w["x0"] < DESC_MAX_X)
                    cells = _assign_columns(line, anchors, errs)
                    if desc.startswith("***"):
                        label = desc.strip("* ").lower()
                        amt = cells["credit_amount"] or cells["debit_amount"]
                        tgt = b.cur["rows"][-1] if b.cur["rows"] else None
                        if tgt is None or tgt["txn_date"] != dt:
                            errs.append(f"charge annotation with no matching txn p{pno + 1}: {desc[:50]}")
                        elif amt is None:
                            errs.append(f"charge annotation without amount p{pno + 1}: {desc[:50]}")
                        elif "stamp duty" in label:
                            tgt["stamp_duty"] = str(Decimal(tgt["stamp_duty"] or "0") + amt)
                        elif "tds" in label:
                            tgt["tds"] = str(Decimal(tgt["tds"] or "0") + amt)
                        elif "stt" in label:
                            tgt["stt"] = str(Decimal(tgt["stt"] or "0") + amt)
                        else:
                            errs.append(f"unknown annotation p{pno + 1}: {desc[:60]}")
                        if tgt is not None and amt is not None:
                            # some generators fold charge rows into the stated totals
                            col = "credit_amount" if cells["credit_amount"] is not None else "debit_amount"
                            tgt.setdefault("annot_raw", []).append([col, str(amt)])
                        i += 1
                        continue
                    ttype = classify(desc)
                    if ttype is None and not desc.strip():
                        moving = [cells[k] for k in ("debit_amount", "debit_units",
                                                     "credit_amount", "credit_units")]
                        if not any(moving):  # dated marker row (record-date NAV print)
                            i += 1
                            continue
                    if ttype is None:
                        errs.append(f"unknown txn description p{pno + 1}: {desc[:60]}")
                        ttype = "other"
                    du, cu = cells["debit_units"], cells["credit_units"]
                    is_debit = bool(du and du != 0)
                    units = du if is_debit else cu
                    amount = cells["debit_amount"] if is_debit else cells["credit_amount"]
                    if (units is None or units == 0) and (cells["credit_amount"] in (None, 0)) and cells[
                        "debit_amount"
                    ] not in (None, 0):
                        is_debit, units, amount = True, du, cells["debit_amount"]  # cash-out, no units (payouts)
                    bal = cells["balance_units"]
                    approx_row = False
                    if bal is None:
                        errs.append(f"txn without balance p{pno + 1} {desc[:40]}")
                    else:
                        q = b.cur
                        if q["pending_ob"] is not None:
                            ob, ob_page, ob_text = q["pending_ob"]
                            q["pending_ob"] = None
                            base = (q["balance"] if q["balance"] is not None else Decimal("0")) + q["day_acc"]
                            delta0 = (units or Decimal("0")) * (Decimal(-1) if is_debit else Decimal(1))
                            from_ob = ob + delta0
                            from_base = base + delta0
                            if bal is not None and abs(from_ob - bal) <= Decimal("0.002") and abs(
                                from_base - bal
                            ) > Decimal("0.002"):
                                # the ledger restates the balance (its own carry across a
                                # sub-report page); record the difference as an approx
                                # adjustment so units stay accounted, never silently
                                adj = ob - base
                                flush_day(b)
                                q["rows"].append(
                                    {
                                        "txn_date": None, "txn_type": "balance_adjust",
                                        "description_raw": ob_text + " [restated]", "raw": {},
                                        "nav": None, "units": str(abs(adj)), "amount": None,
                                        "stt": None, "stamp_duty": None, "tds": None,
                                        "balance_units": str(ob), "is_debit": adj < 0,
                                        "page": ob_page, "approx": True,
                                    }
                                )
                                q["balance"] = ob
                                q["day_last_bal"] = None
                                q["prev_printed"] = None
                            # else: stale carry-forward variant — drop silently
                        if q["last_date"] is not None and dt < q["last_date"]:
                            # strict date regression = a new concatenated sequence
                            # (multi-scheme folio variant); name unknown until a
                            # continuation header catches it.
                            flush_day(b)
                            b.seqs.append(_new_seq(None))
                            q = b.cur
                        if q["day"] is not None and dt != q["day"]:
                            flush_day(b)
                        q["day"] = dt
                        q["last_date"] = dt
                        if ttype in JUMP_TYPES and (units is None or units == 0):
                            # transfer/merger rows carry units only in the balance column
                            base = (q["balance"] if q["balance"] is not None else Decimal("0")) + q["day_acc"]
                            implied = bal - base
                            is_debit = implied < 0
                            units = abs(implied)
                            amount = None
                            approx_row = True  # units exact, cost basis unknown
                        if ttype in ("pledge", "unpledge"):
                            delta = Decimal("0")  # lien marker — printed balance unchanged
                        else:
                            delta = (units or Decimal("0")) * (Decimal(-1) if is_debit else Decimal(1))
                        q["day_acc"] += delta
                        q["prev_printed"] = q["day_last_bal"]
                        q["day_last_bal"] = bal
                    row = {
                        "txn_date": dt, "txn_type": ttype, "description_raw": desc,
                        "raw": {
                            k: str(cells[k])
                            for k in ("debit_amount", "debit_units", "credit_amount", "credit_units")
                            if cells[k] is not None
                        },
                        "nav": str(cells["nav"]) if cells["nav"] is not None else None,
                        "units": str(units) if units is not None else None,
                        "amount": str(amount) if amount is not None else None,
                        "stt": str(cells["stt"]) if cells["stt"] is not None else None,
                        "stamp_duty": None, "tds": None,
                        "balance_units": str(bal) if bal is not None else None,
                        "is_debit": is_debit, "page": pno + 1, "approx": approx_row,
                    }
                    b.cur["rows"].append(row)
                    page_has_body = True
                    i += 1
                    continue

                # bold totals row (no date, numerics only)
                if text in ("Debits Credits", "Debits", "Credits"):
                    i += 1
                    continue
                if _is_bold(line) and all(w["x0"] >= DESC_MAX_X for w in line) and len(line) >= 2:
                    flush_day(b)
                    cells = _assign_columns(line, anchors, errs, tol=TOTALS_TOL)
                    b.totals = {k: str(v) for k, v in cells.items() if v is not None}
                    page_has_body = True
                    i += 1
                    continue

                i += 1

    if open_block is not None and not open_block.closed:
        if open_block.totals is None:
            errs.append(f"file ended with open block {open_block.fund_name[:40]!r}")
        finish_block(open_block)
    _validate(res)
    return res


def _validate(res: dict) -> None:
    errs = res["errors"]
    if not res.get("client_name") or not res.get("client_code"):
        errs.append("no client identity parsed")
    if not res["blocks"]:
        errs.append("no fund blocks parsed")
    for b in res["blocks"]:
        rows = b["rows"]
        fid = f"{b['fund_name'][:40]} f{b['folio']}"
        g2_exempt = bool(G2_EXEMPT_RE.search(b["fund_name"])) or any(
            q.get("name") and G2_EXEMPT_RE.search(q["name"]) for q in b.get("sequences", [])
        )
        # per-row units × nav ≈ amount (G2 pre-check at parse time)
        for r in rows:
            if g2_exempt:
                break
            if r["approx"] or not (r["units"] and r["nav"] and r["amount"]):
                continue
            if r["txn_type"] in JUMP_TYPES:
                continue
            u, n, a = Decimal(r["units"]), Decimal(r["nav"]), Decimal(r["amount"])
            if u == 0 or a == 0:
                continue
            eff = a - Decimal(r["stamp_duty"] or "0") if not r["is_debit"] else a + Decimal(r["stt"] or "0")
            # G2 catches column misparses (orders of magnitude off), not tax eras.
            # One-sided windows absorb what the ledger legitimately nets out:
            #   div reinvest: DDT (up to ~34% corporate-debt era) / 10% TDS / 20% NRI
            #   debit side: exit loads (≤1%) up + NRI TDS on gains (≤34%) down
            # Sub-₹2500 rows skip (merger residues; misparse detection meaningless).
            if a < 2500:
                continue
            if r["txn_type"] == "div_reinvest":
                ok = eff * Decimal("0.60") - 3 <= u * n <= eff * Decimal("1.15") + 3
            elif r["is_debit"]:
                ok = u * n * Decimal("0.66") - 3 <= eff <= u * n * Decimal("1.011") + 3
            elif r["txn_date"] and r["txn_date"] < "2013-10-01":
                # entry-load era: loads baked into the printed price
                ok = abs(u * n - eff) <= max(Decimal("500"), abs(a) * Decimal("0.025"))
            else:
                ok = abs(u * n - eff) <= max(Decimal("3"), abs(a) * Decimal("0.002"))
            if not ok:
                errs.append(f"units*nav!=amount {fid} {r['txn_date']} {r['txn_type']}: {u * n:.2f} vs {eff}")
        # totals row vs sums
        if b["totals"]:
            t = b["totals"]
            sums = {
                col: sum(Decimal(r["raw"][col]) for r in rows if col in r.get("raw", {}))
                for col in ("debit_amount", "debit_units", "credit_amount", "credit_units")
            }
            annot = {"debit_amount": Decimal("0"), "credit_amount": Decimal("0")}
            for r in rows:
                for col, amt in r.get("annot_raw", []):
                    annot[col] += Decimal(amt)
            for k, v in sums.items():
                if k in t:
                    tol = (Decimal("0.02") if "amount" in k else Decimal("0.005")) + Decimal(
                        len(rows)
                    ) * Decimal("0.001")
                    stated = Decimal(t[k])
                    # some blocks fold charge annotations into the stated total, some don't
                    if abs(stated - v) > tol and abs(stated - v - annot.get(k, Decimal("0"))) > tol:
                        errs.append(f"totals mismatch {fid} {k}: stated {t[k]} vs computed {v}")
        # final balance × NAV ≈ MV (per sequence; a multi-scheme folio prints one
        # combined MV that a single NAV can only verify when ≤1 sequence is open)
        if b["mv"] and rows:
            finals = [
                Decimal(q["final_balance"]) for q in b.get("sequences", [])
                if q["final_balance"] is not None
            ]
            nonzero = [f for f in finals if abs(f) > Decimal("0.0005")]
            nav, mv = Decimal(b["mv"]["nav"]), Decimal(b["mv"]["market_value"])
            if len(nonzero) <= 1:
                last_bal = nonzero[0] if nonzero else Decimal("0")
                if abs(last_bal * nav - mv) > max(Decimal("3"), mv * Decimal("0.002")):
                    errs.append(f"balance*nav!=MV {fid}: {last_bal * nav:.0f} vs {mv}")
        if not b["mv"] and not b["totals"]:
            errs.append(f"block without Market Value close {fid}")


def _safe_parse(path: Path) -> dict:
    try:
        return parse_pdf(path)
    except Exception as e:  # noqa: BLE001 — surface, never crash the sweep
        return {"source_file": path.name, "advisor_folder": path.parent.name,
                "errors": [f"EXCEPTION {e!r}"], "blocks": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", help="substring filter on filename")
    ap.add_argument("--jobs", type=int, default=6)
    args = ap.parse_args()
    results, bad = [], 0
    paths = sorted(Path(args.pdf_root).rglob("*.pdf"))
    if args.only:
        paths = [p for p in paths if args.only.lower() in p.name.lower()]
    with Pool(args.jobs) as pool:
        results = pool.map(_safe_parse, paths)
    for res in results:
        if res["errors"]:
            bad += 1
            print(f"FAIL {res['source_file']}: {res['errors'][:3]}")
        elif res.get("warnings"):
            print(f"warn {res['source_file']}: {len(res['warnings'])} balance-column notes")
    Path(args.out).write_text(json.dumps(results, indent=0))
    n_txn = sum(len(b["rows"]) for r in results for b in r.get("blocks", []))
    print(f"{len(results)} files, {bad} flagged, {n_txn} txn rows")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
