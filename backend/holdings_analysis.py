"""
================================================================================
  HOLDINGS FILE PARSER  —  IT_Report_Equity Holdings
  Parses the broker holding snapshot file which contains pre-computed
  positions grouped into: Opening Assets / Long Term (ASSETS) / Short Term
================================================================================
"""

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import re

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Row index (0-based) where column headers live — used as fallback only
HEADER_ROW_INDEX = 38          # Row 39 in Excel = index 38

# Required columns in the holdings file
HOLDINGS_COLS = [
    "Scrip Name",
    "Buy Quantity", "Buy Rate", "Buy Amount", "Buy Date",
    "Sell Quantity", "Sell Rate", "Sell Amount", "Sell Date",
    "Net Quantity", "Current Amount", "P&L Amount", "Closing Price",
]

# Minimum columns that MUST appear in a header row for it to be valid
_HEADER_ANCHOR_COLS = {"Scrip Name", "Net Quantity", "Buy Quantity", "Buy Amount"}


def detect_holdings_header_row(source, max_scan: int = 60) -> int:
    """
    Auto-detect the 0-based row index that contains the holdings column headers.

    Scans up to max_scan rows looking for the row that contains the most
    HOLDINGS_COLS keywords. Falls back to HEADER_ROW_INDEX if nothing better found.

    Works for any broker format regardless of how many header/junk rows precede
    the actual data table.
    """
    try:
        if not isinstance(source, str):
            source.seek(0)
        raw = pd.read_excel(source, header=None, nrows=max_scan)
    except Exception:
        return HEADER_ROW_INDEX

    best_row   = HEADER_ROW_INDEX
    best_score = 0

    holdings_cols_upper = {c.strip().upper() for c in HOLDINGS_COLS}

    for i, row in raw.iterrows():
        row_vals = {str(v).strip().upper() for v in row if pd.notna(v) and str(v).strip()}
        score = len(holdings_cols_upper & row_vals)
        if score > best_score:
            best_score = score
            best_row   = i

    return best_row

# Group classification keywords
GROUP_KEYWORDS = {
    "Opening Assets" : ["OPENING ASSETS", "OPENING_ASSETS"],
    "Long Term"      : ["ASSETS"],
    "Short Term"     : ["SHORTTERM", "SHORT TERM", "SHORT_TERM"],
}

# ─────────────────────────────────────────────────────────────────────────────
#  CLIENT INFO EXTRACTION  (rows 1–14 are junk, no structured metadata)
# ─────────────────────────────────────────────────────────────────────────────

def extract_holdings_client_info(source) -> dict:
    """
    Extract whatever client info is available from the top of the holdings file.
    Scans first 14 rows for anything resembling a client name / ID / date range.
    """
    try:
        raw = pd.read_excel(source, header=None, nrows=14)
    except Exception:
        return {"company": "", "client_name": "", "client_id": "", "date_range": ""}

    info = {"company": "", "client_name": "", "client_id": "", "date_range": ""}

    for i in range(min(14, len(raw))):
        for j in range(min(10, raw.shape[1])):
            val = str(raw.iloc[i, j]).strip() if pd.notna(raw.iloc[i, j]) else ""
            if not val or val == "nan":
                continue
            vl = val.upper()
            if i == 0 and not info["company"]:
                info["company"] = val
            if any(k in vl for k in ["CLIENT", "NAME"]) and not info["client_name"]:
                # Try to grab the value next to it
                try:
                    nxt = str(raw.iloc[i, j + 1]).strip()
                    if nxt and nxt != "nan":
                        info["client_name"] = nxt
                except Exception:
                    info["client_name"] = val
            if any(k in vl for k in ["CLIENT ID", "CODE", "UCC"]) and not info["client_id"]:
                try:
                    nxt = str(raw.iloc[i, j + 1]).strip()
                    if nxt and nxt != "nan":
                        info["client_id"] = nxt
                except Exception:
                    pass
            if re.search(r"\d{2}[/-]\d{2}[/-]\d{2,4}", val) and not info["date_range"]:
                info["date_range"] = val

    return info


# ─────────────────────────────────────────────────────────────────────────────
#  GROUP DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def _classify_group(cell_value: str) -> str | None:
    """
    Given a cell value, return its group label or None if not a group header.
    All SHORTTERM_YYMM variants collapse to 'Short Term'.
    """
    v = str(cell_value).strip().upper()
    for group_label, keywords in GROUP_KEYWORDS.items():
        for kw in keywords:
            if kw in v:
                return group_label
    return None


def _is_total_row(row: pd.Series) -> bool:
    """
    Detect broker-inserted total/subtotal rows.
    These typically have 'total' in Scrip Name or all numeric cols are NaN
    except one summary column.
    """
    scrip = str(row.iloc[0]).strip().upper()
    return "TOTAL" in scrip or scrip in ("", "NAN")


def _is_junk_row(row: pd.Series) -> bool:
    """Detect completely empty or separator rows."""
    vals = [v for v in row if pd.notna(v) and str(v).strip() not in ("", "nan")]
    return len(vals) == 0


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN PARSER
# ─────────────────────────────────────────────────────────────────────────────

def parse_holdings_file(source) -> tuple:
    """
    Parse the IT_Report_Equity Holdings file.

    Parameters
    ----------
    source : file path (str) or BytesIO object

    Returns
    -------
    holdings_df  : DataFrame with columns including 'Group' and 'Source'
    client_info  : dict with client metadata
    """
    # ── 1. Extract client info ────────────────────────────────────────────
    import io
    if isinstance(source, (str,)):
        client_info = extract_holdings_client_info(source)
    else:
        source.seek(0)
        client_info = extract_holdings_client_info(source)

    # ── 2. Auto-detect header row (works for all broker formats) ─────────
    if isinstance(source, str):
        detected_header = detect_holdings_header_row(source)
    else:
        source.seek(0)
        detected_header = detect_holdings_header_row(source)

    # ── 3. Read with auto-detected header row ────────────────────────────
    if isinstance(source, str):
        df_raw = pd.read_excel(source, header=detected_header)
    else:
        source.seek(0)
        df_raw = pd.read_excel(source, header=detected_header)

    df_raw.columns = [str(c).strip() for c in df_raw.columns]

    # ── 4a. Identify available required columns ───────────────────────────
    available = [c for c in HOLDINGS_COLS if c in df_raw.columns]
    if "Scrip Name" not in df_raw.columns:
        raise ValueError(
            f"'Scrip Name' column not found in holdings file.\n"
            f"Auto-detected header at row {detected_header + 1} (1-based).\n"
            f"Found columns: {list(df_raw.columns)}\n"
            f"The file may have a non-standard layout — check that the column \'Scrip Name\' exists."
        )

    # ── 4. Walk rows, detect group headers and tag data rows ──────────────
    records      = []
    current_group = "Unknown"

    for idx, row in df_raw.iterrows():
        scrip_val = str(row.get("Scrip Name", "")).strip()

        # Skip completely blank rows
        if _is_junk_row(row):
            continue

        # Detect group header rows
        group = _classify_group(scrip_val)
        if group is not None:
            current_group = group
            continue

        # Skip total / subtotal rows
        if _is_total_row(row):
            continue

        # Skip rows where Scrip Name looks like a sub-header (all caps, no qty)
        net_qty = row.get("Net Quantity", None)
        if pd.isna(net_qty) and scrip_val.isupper() and len(scrip_val) > 5:
            # Likely a group label row we didn't catch — skip
            continue

        # ── Build clean record ────────────────────────────────────────────
        record = {"Group": current_group, "Source": "Holdings File"}

        for col in available:
            record[col] = row.get(col, np.nan)

        records.append(record)

    holdings_df = pd.DataFrame(records)

    if holdings_df.empty:
        return holdings_df, client_info

    # ── 5. Clean & type-cast ──────────────────────────────────────────────
    holdings_df["Scrip Name"] = (
        holdings_df["Scrip Name"]
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", " ", regex=True)
        .str.replace("\xa0", "", regex=False)
    )

    # Remove any remaining junk rows after cleaning
    holdings_df = holdings_df[
        holdings_df["Scrip Name"].notna() &
        (holdings_df["Scrip Name"] != "") &
        (holdings_df["Scrip Name"] != "NAN") &
        (~holdings_df["Scrip Name"].str.contains(
            r"TOTAL|GRAND|SUMMARY|SUBTOTAL", regex=True, na=False
        ))
    ].reset_index(drop=True)

    # Numeric columns
    num_cols = [
        "Buy Quantity", "Buy Rate", "Buy Amount",
        "Sell Quantity", "Sell Rate", "Sell Amount",
        "Net Quantity", "Current Amount", "P&L Amount", "Closing Price",
    ]
    for col in num_cols:
        if col in holdings_df.columns:
            holdings_df[col] = pd.to_numeric(
                holdings_df[col], errors="coerce"
            )

    # Date columns
    for col in ["Buy Date", "Sell Date"]:
        if col in holdings_df.columns:
            holdings_df[col] = pd.to_datetime(
                holdings_df[col], errors="coerce"
            )

    # Keep only rows with a positive net quantity (actual holdings)
    if "Net Quantity" in holdings_df.columns:
        holdings_df = holdings_df[
            holdings_df["Net Quantity"].fillna(0) > 0
        ].reset_index(drop=True)


    if "Buy Rate" in holdings_df.columns and "Avg Cost" not in holdings_df.columns:
        holdings_df["Avg Cost"] = holdings_df["Buy Rate"]

    if "P&L Amount" in holdings_df.columns and "Buy Amount" in holdings_df.columns:
        holdings_df["P&L %"] = (
            holdings_df["P&L Amount"] / holdings_df["Buy Amount"].replace(0, np.nan) * 100
        ).round(2)

    return holdings_df, client_info


