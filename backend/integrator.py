"""
================================================================================
  INTEGRATOR  —  Merges Trade Report + Holdings File into unified portfolio
================================================================================
"""

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import yfinance as yf

from portfolio_analysis import (
    TICKER_MAP,
    LARGE_CAP_THRESHOLD, MID_CAP_THRESHOLD, SMALL_CAP_THRESHOLD,
    CORE_THRESHOLD, SATELLITE_THRESHOLD,
    separate_index_equity,
    calculate_equity_positions,
    calculate_index_pnl,
    portfolio_summary,
)

# ─────────────────────────────────────────────────────────────────────────────
#  AUTO TICKER RESOLVER
#  Handles scrips not present in TICKER_MAP — resolves via pattern matching,
#  yfinance search, and persistent cache.
# ─────────────────────────────────────────────────────────────────────────────
from ticker_resolver import (
    fetch_sector_cap_with_autoresolve,
    fetch_live_prices_with_autoresolve,
    get_extended_ticker_map,
)

# Build the extended ticker map (base + extra overrides + disk cache)
# This is rebuilt each session so newly cached tickers are always included.
_EXTENDED_TICKER_MAP = get_extended_ticker_map(TICKER_MAP)


def _refresh_extended_map():
    """Call this after new tickers may have been cached."""
    global _EXTENDED_TICKER_MAP
    _EXTENDED_TICKER_MAP = get_extended_ticker_map(TICKER_MAP)


# ─────────────────────────────────────────────────────────────────────────────
#  LIVE PRICE FETCH  (shared, handles both sources, auto-resolves new scrips)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_live_prices_unified(scrip_names: list) -> dict:
    """
    Given a list of scrip names, auto-resolve tickers and fetch live prices.
    New scrips not in TICKER_MAP are resolved automatically via pattern matching
    and yfinance search, then cached for future runs.

    Returns dict: {scrip_name: live_price_or_None}
    """
    result = fetch_live_prices_with_autoresolve(scrip_names, TICKER_MAP)
    _refresh_extended_map()
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  SECTOR & MARKET CAP FETCH  (auto-resolves unknown tickers)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_sector_and_cap_unified(scrip_names: list) -> dict:
    """
    Returns dict: {scrip_name: {"sector": ..., "market_cap_cr": ..., "cap_category": ...}}
    Automatically resolves tickers for any scrip not in TICKER_MAP.
    Resolution is cached persistently in ticker_cache.json.
    """
    raw = fetch_sector_cap_with_autoresolve(scrip_names, TICKER_MAP)
    _refresh_extended_map()
    # Strip the "ticker" and "resolved_by" keys to match the old interface
    result = {}
    for scrip, info in raw.items():
        result[scrip] = {
            "sector"        : info.get("sector",         "Unknown"),
            "market_cap_cr" : info.get("market_cap_cr",  None),
            "cap_category"  : info.get("cap_category",   "Unknown"),
        }
    return result


def _classify_cap(mcap_cr) -> str:
    if mcap_cr is None or pd.isna(mcap_cr):
        return "Unknown"
    if mcap_cr >= LARGE_CAP_THRESHOLD:
        return "Large Cap"
    if mcap_cr >= MID_CAP_THRESHOLD:
        return "Mid Cap"
    if mcap_cr >= SMALL_CAP_THRESHOLD:
        return "Small Cap"
    return "Micro Cap"


# ─────────────────────────────────────────────────────────────────────────────
#  TRADE REPORT → UNIFIED FORMAT CONVERTER
# ─────────────────────────────────────────────────────────────────────────────

def trade_holdings_to_unified(holdings_df: pd.DataFrame, realized_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert the FIFO-derived holdings DataFrame (from portfolio_analysis.py)
    into the unified schema.
    """
    rows = []
    for _, row in holdings_df.iterrows():
        rows.append({
            "Scrip Name"     : row["Scrip Name"],
            "Source"         : "Trade Report",
            "Group"          : "Trade Period",
            "Net Quantity"   : row["Open Qty"],
            "Avg Cost"       : row["Avg Cost"],
            "Buy Amount"     : row["Cost Value"],
            "Closing Price"  : np.nan,          # not available from trade report
            "P&L Amount"     : row.get("Realized P&L", np.nan),
            "Current Amount" : np.nan,          # will be filled after live price fetch
            "Live Price"     : np.nan,          # filled later
            "Price Used"     : "—",
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
#  HOLDINGS FILE → UNIFIED FORMAT CONVERTER
# ─────────────────────────────────────────────────────────────────────────────

def holdings_to_unified(holdings_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert the parsed holdings file DataFrame into unified schema.
    """
    rows = []
    for _, row in holdings_df.iterrows():
        rows.append({
            "Scrip Name"     : row["Scrip Name"],
            "Source"         : "Holdings File",
            "Group"          : row.get("Group", "Unknown"),
            "Net Quantity"   : row.get("Net Quantity",   np.nan),
            "Avg Cost"       : row.get("Buy Rate",       np.nan),
            "Buy Amount"     : row.get("Buy Amount",     np.nan),
            "Closing Price"  : row.get("Closing Price",  np.nan),
            "P&L Amount"     : row.get("P&L Amount",     np.nan),
            "Current Amount" : row.get("Current Amount", np.nan),
            "Live Price"     : np.nan,          # filled later
            "Price Used"     : "—",
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
#  WEIGHT CALCULATION  (combined across sources for same scrip)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_unified_weights(unified_df: pd.DataFrame) -> pd.DataFrame:
    """
    Weight is based on Current Value (Effective Price × Net Quantity).

    IMPORTANT — duplicate rows per scrip:
    When the same scrip appears in multiple rows (one from Holdings File,
    one from Trade Report), the Net Quantity on each row is ALREADY the
    combined net qty for that source.  We must NOT double-count by summing
    across rows.  Instead we:
      1. Compute Current Value per row.
      2. Deduplicate by Scrip Name to get ONE value per scrip (use max row,
         which holds the combined position after integration).
      3. Derive the total portfolio value from deduped scrip values.
      4. Assign Weight % back to every row for the same scrip.
    """
    df = unified_df.copy()

    # Step 1 — Current Value per row
    df["Current Value"] = (df["Effective Price"] * df["Net Quantity"]).fillna(0)

    # Step 2 — One representative value per scrip (take the largest row value,
    # which corresponds to the combined/integrated position)
    scrip_value = (
        df.groupby("Scrip Name")["Current Value"]
        .max()           # max row for that scrip = the fully-combined position row
        .reset_index()
        .rename(columns={"Current Value": "_scrip_cv"})
    )

    total_portfolio = scrip_value["_scrip_cv"].sum()

    if total_portfolio > 0:
        scrip_value["_weight"] = (scrip_value["_scrip_cv"] / total_portfolio * 100).round(4)
    else:
        scrip_value["_weight"] = 0.0

    # Step 3 — Map weights back to every row
    weight_map = scrip_value.set_index("Scrip Name")["_weight"]
    df["Weight %"] = df["Scrip Name"].map(weight_map).fillna(0.0)

    # Step 4 — Normalise so weights sum to exactly 100 % (handles rounding drift)
    weight_sum = df.drop_duplicates(subset=["Scrip Name"])["Weight %"].sum()
    if weight_sum > 0:
        scale = 100.0 / weight_sum
        df["Weight %"] = (df["Weight %"] * scale).round(2)

    return df


# ─────────────────────────────────────────────────────────────────────────────
#  ENS
# ─────────────────────────────────────────────────────────────────────────────

def _dedup_weights(unified_df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a one-row-per-scrip DataFrame with correct Weight %.
    Picks the row with the highest Weight % for each scrip (the integrated row).
    """
    return (
        unified_df.sort_values("Weight %", ascending=False)
        .drop_duplicates(subset=["Scrip Name"])
        .copy()
    )


def calculate_ens_unified(unified_df: pd.DataFrame) -> float:
    """
    ENS = 1 / Σ(w²)
    Uses deduplicated per-scrip weights so duplicate source rows don't inflate.
    """
    dedup = _dedup_weights(unified_df)
    scrip_weights = dedup["Weight %"] / 100
    scrip_weights = scrip_weights[scrip_weights > 0]
    if len(scrip_weights) == 0:
        return 0.0
    return round(1 / (scrip_weights ** 2).sum(), 2)


# ─────────────────────────────────────────────────────────────────────────────
#  CORE – SATELLITE – TAIL
# ─────────────────────────────────────────────────────────────────────────────

def calculate_cst_unified(unified_df: pd.DataFrame) -> dict:
    """
    Core/Satellite/Tail on combined scrip weights (deduplicated, normalised).
    Guarantees Core + Satellite + Tail = 100 %.
    """
    scrip_w = _dedup_weights(unified_df)[["Scrip Name", "Weight %"]].copy()

    # Normalise deduped weights to exactly 100 so buckets always sum to 100
    total_w = scrip_w["Weight %"].sum()
    if total_w > 0:
        scrip_w["Weight %"] = (scrip_w["Weight %"] / total_w * 100)

    core      = scrip_w[scrip_w["Weight %"] >= CORE_THRESHOLD]
    satellite = scrip_w[(scrip_w["Weight %"] >= SATELLITE_THRESHOLD) & (scrip_w["Weight %"] < CORE_THRESHOLD)]
    tail      = scrip_w[scrip_w["Weight %"] < SATELLITE_THRESHOLD]

    core_pct = round(core["Weight %"].sum(), 2)
    sat_pct  = round(satellite["Weight %"].sum(), 2)
    # Tail gets whatever is left so the three always sum to exactly 100
    tail_pct = round(100.0 - core_pct - sat_pct, 2)

    return {
        "Core Allocation %"      : core_pct,
        "Satellite Allocation %" : sat_pct,
        "Tail Allocation %"      : tail_pct,
        "Core Count"             : len(core),
        "Satellite Count"        : len(satellite),
        "Tail Count"             : len(tail),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  SECTOR ALLOCATION
# ─────────────────────────────────────────────────────────────────────────────

def sector_allocation_unified(unified_df: pd.DataFrame) -> dict:
    """
    Weight % per sector — deduplicated by scrip, normalised to 100.
    """
    dedup = _dedup_weights(unified_df)

    raw = (
        dedup.groupby("Sector")["Weight %"]
        .sum()
    )
    # Normalise to 100 %
    total = raw.sum()
    if total > 0:
        raw = (raw / total * 100).round(2)

    return raw.sort_values(ascending=False).to_dict()


# ─────────────────────────────────────────────────────────────────────────────
#  RECONCILIATION  —  Flag scrips in both files with qty mismatch
# ─────────────────────────────────────────────────────────────────────────────

def build_reconciliation(unified_df: pd.DataFrame) -> pd.DataFrame:
    """
    Full position reconciliation table.
    Shows IT Buy/Sell, Trade Buy/Sell, total net qty and status for every scrip.
    """
    cols = [
        "Scrip Name", "Source", "Group",
        "IT Buy Qty", "IT Sell Qty",
        "Trade Buy Qty", "Trade Sell Qty",
        "Total Buy Qty", "Total Sell Qty",
        "Net Quantity", "Status",
    ]
    avail = [c for c in cols if c in unified_df.columns]
    recon = unified_df[avail].copy()

    # Include closed positions from all_df if available (passed separately)
    return recon.sort_values("Status").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN INTEGRATION FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def integrate(
    trade_holdings_df   : pd.DataFrame | None,
    trade_realized_df   : pd.DataFrame | None,
    trade_index_pnl_df  : pd.DataFrame | None,
    holdings_file_df    : pd.DataFrame | None,
    trade_raw_df        : pd.DataFrame | None = None,
) -> dict:
    """
    Merge Trade Report + Holdings File into one unified portfolio.

    The FIFO engine in portfolio_analysis.py is seeded with Holdings File
    buy lots so sells in the Trade Report correctly match against historical
    buys — fixing wrong realized P&L and XIRR.

    Net Quantity per scrip = (Holdings Buy + Trade Buy) - (Holdings Sell + Trade Sell)
    so negative net quantities from cross-file sells are resolved correctly.
    """
    from portfolio_analysis import (
        build_opening_lots_from_holdings,
        calculate_equity_positions,
        separate_index_equity,
        calculate_index_pnl,
        preprocess_data,
    )
    import re

    # ── Name normalisation map ────────────────────────────────────────────
    _NAME_MAP = {
        "UJJIVAN SMALL FINANCE BANK LIM"         : "UJJIVAN SMALL FINANCE BANK",
        "UJJIVAN SMALL FINANC BANK"              : "UJJIVAN SMALL FINANCE BANK",
        "RELIANCE INDUSTRIES LTD"                : "RELIANCE INDUSTRIES",
        "RELIANCE INDUSTRIES LTD."               : "RELIANCE INDUSTRIES",
        "TATA CONSULTANCY SERVICES LTD"          : "TCS",
        "TATA CONSULTANCY SERVICES LTD."         : "TCS",
        "BAJAJ HOLDINGS & INVESTMENT LT"         : "BAJAJ HOLDINGS",
        "BAJAJ HOLDINGS & INVESTMENT LTD"        : "BAJAJ HOLDINGS",
        "HINDUSTAN PETROLEUM CORPORATIO"         : "HINDUSTAN PETROLEUM",
        "OIL AND NATURAL GAS CORPORATIO"         : "ONGC",
        "TATA MOTORS PASSENGER VEHICLES"         : "TATA MOTORS",
        "TATA MOTORS LIMITED"                    : "TATA MOTORS",
        "TATA MOTORS LTD"                        : "TATA MOTORS",
        "ZEE ENTERTAINMENT ENTERPRISES"          : "ZEE ENTERTAINMENT",
        "ZEE ENTERTAINMENT ENTERPRISES LTD"      : "ZEE ENTERTAINMENT",
        "INTERARCH BUILDING SOLUTIONS L"         : "INTERARCH BUILDING SOLUTIONS",
        "INTERARCH BLDNG SOLTN LTD"              : "INTERARCH BUILDING SOLUTIONS",
        "BAJAJ HOUSING FINANCE LIMITED"          : "BAJAJ HOUSING FINANCE",
        "BAJAJ HOUSING FINANCE LTD"              : "BAJAJ HOUSING FINANCE",
        "PUNE E - STOCK BROKING LIMITED"         : "PUNE E-STOCK BROKING",
        "JIO FINANCIAL SERVICES LIMITED"         : "JIO FINANCIAL SERVICES",
        "ARKADE DEVELOPERS LIMITED"              : "ARKADE DEVELOPERS",
        "NTPC LTD"                               : "NTPC",
        "NTPC LTD."                              : "NTPC",
        "HERO MOTOCORP LTD"                      : "HERO MOTOCORP",
        "HERO MOTOCORP LIMITED"                  : "HERO MOTOCORP",
        "BAJAJ FINSERV LTD"                      : "BAJAJ FINSERV",
        "NHPC LTD"                               : "NHPC",
        "NHPC LTD."                              : "NHPC",
        "SJVN LTD"                               : "SJVN",
        "BAJAJ FINANCE LIMITED"                  : "BAJAJ FINANCE",
        "HDFC BANK LTD"                          : "HDFC BANK",
        "HDFC BANK LTD."                         : "HDFC BANK",
        "ICICI BANK LTD"                         : "ICICI BANK",
        "ICICI BANK LTD."                        : "ICICI BANK",
        "TATA STEEL LTD"                         : "TATA STEEL",
        "TATA STEEL LTD."                        : "TATA STEEL",
        "ALSTONE TEXTILES (INDIA) LTD"           : "ALSTONE TEXTILES",
        "GUFIC BIOSCIENCES LTD"                  : "GUFIC BIOSCIENCES",
        "GUFIC BIOSCIENCES LTD."                 : "GUFIC BIOSCIENCES",
        "BALAJI AMINES LTD"                      : "BALAJI AMINES",
        "BALAJI AMINES LTD."                     : "BALAJI AMINES",
        "CUMMINS INDIA LTD"                      : "CUMMINS INDIA",
        "CUMMINS INDIA LTD."                     : "CUMMINS INDIA",
        "SHEELA FOAM LIMITED"                    : "SHEELA FOAM",
        "STATE BANK OF INDIA"                    : "SBI",
        "BOMBAY BURMAH TRADING COR"              : "BOMBAY BURMAH TRADING",
        "TIPS MUSIC LIMITED"                     : "TIPS MUSIC",
        "KALYANI INVEST CO LTD"                  : "KALYANI INVESTMENTS",
        "PILANI INV & IND COR LTD"              : "PILANI INVESTMENTS",
        "ICICI PRUDENTIAL ASSET MANAGEM"         : "ICICI PRUDENTIAL AMC",
        "COAL INDIA LTD."                        : "COAL INDIA",
        "HDFC BANK LTD."                         : "HDFC BANK",
        "HERO MOTOCORP LTD."                     : "HERO MOTOCORP",
        "NHPC LTD."                              : "NHPC",
        "NTPC LTD."                              : "NTPC",
    }

    def _cn(name: str) -> str:
        s = str(name).strip().upper().rstrip(".")
        s = re.sub(r"\s+", " ", s)
        return _NAME_MAP.get(s, s)

    # ── Step 1: Build opening lots from Holdings File ─────────────────────
    # These seed the FIFO queue so Trade Report sells match Holdings File buys
    opening_lots_raw = build_opening_lots_from_holdings(holdings_file_df) \
        if holdings_file_df is not None and not holdings_file_df.empty else {}

    # Also build a clean-name keyed version for cross-file matching
    opening_lots_clean = {}
    for scrip, lots in opening_lots_raw.items():
        opening_lots_clean[_cn(scrip)] = lots

    # ── Step 2: Re-run FIFO with opening lots seeded ─────────────────────
    if trade_raw_df is not None and not trade_raw_df.empty:
        equity_df = trade_raw_df[
            trade_raw_df.get("Segment", pd.Series(["Equity"] * len(trade_raw_df)))
            .str.strip().str.upper() == "EQUITY"
        ] if "Segment" in trade_raw_df.columns else trade_raw_df.copy()

        # Build opening_lots keyed by Trade Report scrip names
        # matching via clean name
        opening_lots_for_fifo = {}
        for scrip in equity_df["Scrip Name"].unique():
            clean = _cn(scrip)
            if clean in opening_lots_clean:
                opening_lots_for_fifo[scrip] = opening_lots_clean[clean]
            elif scrip in opening_lots_raw:
                opening_lots_for_fifo[scrip] = opening_lots_raw[scrip]

        trade_holdings_df, trade_realized_df = calculate_equity_positions(
            equity_df, opening_lots=opening_lots_for_fifo
        )
    else:
        equity_df = pd.DataFrame()

    # ── Step 3: Build unified holdings with correct net qty ───────────────
    # Aggregate trade report
    tr_buy = {}; tr_sell = {}; tr_amt = {}; tr_name = {}
    if not equity_df.empty:
        eq = equity_df.copy()
        eq["_c"] = eq["Scrip Name"].apply(_cn)
        for c, grp in eq.groupby("_c"):
            buys  = grp[grp["Action"] == "BUY"]
            sells = grp[grp["Action"] == "SELL"]
            tr_buy[c]  = float(buys["Quantity"].sum())
            tr_sell[c] = float(sells["Quantity"].sum())
            tr_amt[c]  = float(buys["Amount"].abs().sum()) if "Amount" in buys.columns \
                         else float((buys["Price"] * buys["Quantity"]).sum())
            tr_name[c] = grp["Scrip Name"].iloc[0]

    # Aggregate holdings file
    it_buy = {}; it_sell = {}; it_buy_amt = {}
    it_closing = {}; it_buy_rate = {}; it_group = {}
    it_buy_date = {}; it_name = {}

    if holdings_file_df is not None and not holdings_file_df.empty:
        hf = holdings_file_df.copy()
        hf["_c"] = hf["Scrip Name"].apply(_cn)
        bq_col = "Buy Quantity"  if "Buy Quantity"  in hf.columns else "Net Quantity"
        sq_col = "Sell Quantity" if "Sell Quantity" in hf.columns else None
        ba_col = "Buy Amount"    if "Buy Amount"    in hf.columns else None
        cl_col = "Closing Price" if "Closing Price" in hf.columns else None
        br_col = "Buy Rate"      if "Buy Rate"      in hf.columns else None
        gr_col = "Group"         if "Group"         in hf.columns else None
        bd_col = "Buy Date"      if "Buy Date"      in hf.columns else None

        for c, grp in hf.groupby("_c"):
            it_buy[c]      = float(grp[bq_col].sum())
            it_sell[c]     = float(grp[sq_col].sum())  if sq_col else 0.0
            it_buy_amt[c]  = float(grp[ba_col].sum())  if ba_col else 0.0
            it_closing[c]  = float(grp[cl_col].iloc[-1]) if cl_col and pd.notna(grp[cl_col].iloc[-1]) else 0.0
            it_buy_rate[c] = float(grp[br_col].mean()) if br_col else 0.0
            it_group[c]    = grp[gr_col].iloc[0]       if gr_col else "Unknown"
            it_buy_date[c] = grp[bd_col].min()         if bd_col else pd.NaT
            it_name[c]     = grp["Scrip Name"].iloc[0]

    # Combine
    all_scrips = set(tr_buy.keys()) | set(it_buy.keys())
    rows = []
    for c in sorted(all_scrips):
        _itb  = it_buy.get(c, 0.0);    _its  = it_sell.get(c, 0.0)
        _iba  = it_buy_amt.get(c, 0.0)
        _trb  = tr_buy.get(c, 0.0);    _trs  = tr_sell.get(c, 0.0)
        _tra  = tr_amt.get(c, 0.0)
        total_buy  = _itb + _trb
        total_sell = _its + _trs
        net_qty    = total_buy - total_sell
        total_inv  = _iba + _tra
        avg_cost   = round(total_inv / total_buy, 4) if total_buy > 0 else 0.0
        display    = it_name.get(c, tr_name.get(c, c))
        in_it      = _itb > 0 or _its > 0
        in_tr      = _trb > 0 or _trs > 0
        source     = "Both Files" if in_it and in_tr else ("Holdings File" if in_it else "Trade Report")
        status     = "OPEN" if net_qty > 0 else ("CLOSED" if net_qty == 0 else "ANOMALY")

        rows.append({
            "Scrip Name"     : display,
            "scrip_clean"    : c,
            "Source"         : source,
            "Group"          : it_group.get(c, "Trade Period"),
            "IT Buy Qty"     : _itb,
            "IT Sell Qty"    : _its,
            "Trade Buy Qty"  : _trb,
            "Trade Sell Qty" : _trs,
            "Total Buy Qty"  : total_buy,
            "Total Sell Qty" : total_sell,
            "Net Quantity"   : net_qty,
            "Avg Cost"       : avg_cost,
            "Buy Amount"     : round(total_inv, 2),
            "Closing Price"  : it_closing.get(c, 0.0),
            "Buy Date"       : it_buy_date.get(c, pd.NaT),
            "Status"         : status,
            "Live Price"     : np.nan,
            "Effective Price": np.nan,
            "Price Used"     : "—",
        })

    all_df = pd.DataFrame(rows)

    # ── Classify ANOMALY rows correctly before filtering ─────────────────
    #
    # ANOMALY = net_qty < 0 means sells > buys. Two distinct causes:
    #
    # Case A — Holdings file NOT uploaded, only Trade Report:
    #   Buy happened before the trade period — no buy record exists.
    #   This IS a real holding, we just don't know the cost basis.
    #   → Keep it, flag MISSING_BUY, net_qty = sell_qty, avg_cost = 0.
    #
    # Case B — BOTH files uploaded but net_qty still negative:
    #   Genuine FIFO mismatch — data itself is inconsistent.
    #   → Exclude from holdings, still visible in Reconciliation tab.
    #
    has_holdings_file = holdings_file_df is not None and not holdings_file_df.empty

    fixed_rows = []
    for row in all_df.to_dict('records'):
        if row["Net Quantity"] >= 0:
            fixed_rows.append(row)
            continue
        if not has_holdings_file and row["IT Buy Qty"] == 0:
            # Case A: only trade report, buy predates report period
            row = dict(row)
            row["Net Quantity"] = row["Trade Sell Qty"]
            row["Status"]       = "MISSING_BUY"
            row["Avg Cost"]     = 0.0
            row["Buy Amount"]   = 0.0
        else:
            # Case B: both files, still negative → genuine anomaly
            row = dict(row)
            row["Status"] = "ANOMALY"
        fixed_rows.append(row)

    all_df = pd.DataFrame(fixed_rows)

    # OPEN + MISSING_BUY → holdings  |  ANOMALY + CLOSED → recon only
    unified = all_df[all_df["Status"].isin(["OPEN", "MISSING_BUY"])].copy().reset_index(drop=True)

    if unified.empty:
        raise ValueError("No open positions found after combining both files.")

    # ── Fetch live prices for ALL scrips ─────────────────────────────────
    all_scrips   = unified["Scrip Name"].unique().tolist()
    live_price_map = fetch_live_prices_unified(all_scrips)

    # ── Apply price priority chain: Live → Closing Price → Avg Cost ───────
    def _effective_price(row):
        live    = live_price_map.get(row["Scrip Name"])
        closing = row.get("Closing Price", np.nan)
        avg     = row.get("Avg Cost",      np.nan)

        if live is not None and not pd.isna(live):
            return live, "Live"
        if not pd.isna(closing) and closing > 0:
            return closing, "Closing (Report End)"
        if not pd.isna(avg) and avg > 0:
            return avg, "Avg Cost"
        return np.nan, "—"

    unified["Live Price"] = unified["Scrip Name"].map(
        lambda s: live_price_map.get(s)
    )
    prices_used = unified.apply(_effective_price, axis=1)
    unified["Effective Price"] = [p[0] for p in prices_used]
    unified["Price Used"]      = [p[1] for p in prices_used]

    # ── Weights (combined per scrip) ───────────────────────────────────────
    unified = calculate_unified_weights(unified)

    # ── Current value per row ─────────────────────────────────────────────
    unified["Current Value"] = (unified["Effective Price"] * unified["Net Quantity"]).round(2)

    # ── Unrealized P&L per row (where we have avg cost) ───────────────────
    unified["Unrealized P&L"] = (
        (unified["Effective Price"] - unified["Avg Cost"]) * unified["Net Quantity"]
    ).round(2)

    unified["Unrealized P&L %"] = (
        (unified["Unrealized P&L"] / unified["Buy Amount"].replace(0, np.nan)) * 100
    ).round(2)

    # (Broker P&L Amount not available in new merged schema — computed values used)

    # ── Sector & Market Cap ───────────────────────────────────────────────
    meta = fetch_sector_and_cap_unified(all_scrips)
    unified["Sector"]          = unified["Scrip Name"].map(lambda s: meta.get(s, {}).get("sector",        "Unknown"))
    unified["Market Cap (Cr)"] = unified["Scrip Name"].map(lambda s: meta.get(s, {}).get("market_cap_cr", np.nan))
    unified["Cap Category"]    = unified["Scrip Name"].map(lambda s: meta.get(s, {}).get("cap_category",  "Unknown"))

    # ── Ticker column ──────────────────────────────────────────────────────
    unified["Ticker"] = unified["Scrip Name"].map(_EXTENDED_TICKER_MAP)

    # ── Analytics ─────────────────────────────────────────────────────────
    ens        = calculate_ens_unified(unified)
    allocation = calculate_cst_unified(unified)
    sector_wt  = sector_allocation_unified(unified)
    # Cap summary — deduplicated and normalised to 100 %
    _cap_raw = (
        _dedup_weights(unified)
        .groupby("Cap Category")["Weight %"]
        .sum()
    )
    _cap_total = _cap_raw.sum()
    if _cap_total > 0:
        _cap_raw = (_cap_raw / _cap_total * 100).round(2)
    cap_summary = _cap_raw.to_dict()
    recon = build_reconciliation(all_df)

    # ── Realized P&L summary ──────────────────────────────────────────────
    realized_total = (
        trade_realized_df["Realized P&L"].sum()
        if trade_realized_df is not None and not trade_realized_df.empty
        else 0.0
    )

    # ── Portfolio summary ─────────────────────────────────────────────────
    total_cost    = unified["Buy Amount"].fillna(0).sum()
    total_current = unified["Current Value"].fillna(0).sum()
    total_unreal  = unified["Unrealized P&L"].fillna(0).sum()
    total_pnl     = total_unreal + realized_total
    unreal_pct    = (total_unreal / total_cost * 100) if total_cost else 0.0

    summary = {
        "Total Cost Value (₹)"         : round(total_cost,    2),
        "Total Current Value (₹)"      : round(total_current, 2),
        "Total Unrealized P&L (₹)"     : round(total_unreal,  2),
        "Total Unrealized P&L %"       : round(unreal_pct,    2),
        "Total Realized P&L (₹)"       : round(realized_total,2),
        "Total P&L (Realized + Unreal)" : round(total_pnl,    2),
        "Number of Open Positions"     : unified["Scrip Name"].nunique(),
        "Total Rows"                   : len(unified),
    }

    return {
        "unified"       : unified,
        "realized"      : trade_realized_df if trade_realized_df is not None else pd.DataFrame(),
        "index_pnl"     : trade_index_pnl_df if trade_index_pnl_df is not None else pd.DataFrame(),
        "summary"       : summary,
        "ens"           : ens,
        "allocation"    : allocation,
        "sector_wt"     : sector_wt,
        "cap_summary"   : cap_summary,
        "reconciliation": recon,
    }