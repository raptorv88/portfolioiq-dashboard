"""
================================================================================
  XIRR ENGINE  —  Mathematically accurate Extended IRR
  ================================================================================

  CASH FLOW CONVENTION (standard finance):
    Negative = money OUT of your pocket  (BUY)
    Positive = money INTO your pocket    (SELL / current portfolio value)

  DESIGN PRINCIPLES for correctness:
  ─────────────────────────────────────────────────────────────────────────────
  1. SINGLE SOURCE OF TRUTH per scrip:
     • Trade report  → signed Amount column used directly (already correct sign)
     • Holdings file → ONLY used for scrips that have NO trade-report entries.
       For those, we reconstruct: buy_outflow = -(Net Qty × Avg Buy Rate)
       on the recorded Buy Date.  We do NOT use the raw Buy Amount column
       because it includes lots already sold (which would double-count with
       sell inflows from the same holdings row).

  2. NO DOUBLE-COUNTING:
     • If a scrip appears in BOTH files, the trade report cash flows take
       precedence (they are date-accurate).  Holdings file buy flows for that
       scrip are NOT added again — the trade report's BUY rows already cover
       the intra-period purchases.
     • Holdings file sell flows (Sell Qty > 0) are SKIPPED for scrips that
       also exist in the trade report, because those sells are already captured
       as positive Amounts in the trade report.

  3. CORRECT BUY AMOUNT FROM HOLDINGS FILE:
     • The Holdings file's "Buy Amount" = total cost of ALL historical lots
       (open + already sold).  Using it directly overstates the outflow.
     • Correct formula:  outflow = -(Net Quantity × Avg Buy Rate)
       This is exactly the cost basis of what you STILL HOLD from that file.

  4. TERMINAL CASH FLOW:
     • Today's effective portfolio value (Effective Price × Net Quantity,
       summed across all open positions) represents "if you sold everything
       today" — the final positive inflow.
     • Date = TODAY.

  5. DATE VALIDATION:
     • Any cash flow with a missing or future date is silently dropped.
     • Holdings file rows with no Buy Date are dropped (cannot anchor XIRR).
     • Trade report rows with no Trade Date are dropped.

  6. SCRIP-NAME NORMALISATION:
     • Both files apply the same _cn() clean-name function used in integrator.py
       to match scrip names across files correctly.

  7. XIRR SOLVER:
     • Primary  : pyxirr (most accurate, handles edge cases)
     • Fallback : scipy brentq  (wide bracket, high tolerance)
     • Returns None (not 0 or error) when computation is genuinely impossible.
================================================================================
"""

import warnings
warnings.filterwarnings("ignore")

# ISIN-based resolution
try:
    from isin_master import get_isin
    _ISIN_AVAILABLE = True
except ImportError:
    _ISIN_AVAILABLE = False

import re
import pandas as pd
import numpy as np
from datetime import date
from typing import Optional

try:
    from pyxirr import xirr as _pyxirr
    _USE_PYXIRR = True
except ImportError:
    _USE_PYXIRR = False
    from scipy.optimize import brentq

TODAY = pd.Timestamp(date.today())


# ─────────────────────────────────────────────────────────────────────────────
#  SCRIP NAME NORMALISER  (mirrors integrator.py _cn())
# ─────────────────────────────────────────────────────────────────────────────

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
    "PILANI INV & IND COR LTD"               : "PILANI INVESTMENTS",
    "ICICI PRUDENTIAL ASSET MANAGEM"         : "ICICI PRUDENTIAL AMC",
    "COAL INDIA LTD."                        : "COAL INDIA",
    "HERO MOTOCORP LTD."                     : "HERO MOTOCORP",
}


_xirr_isin_cache: dict = {}

def _cn(name: str) -> str:
    """
    Normalise scrip name using ISIN as primary key when available.
    Falls back to NAME_MAP overrides then auto suffix stripping.
    """
    if name in _xirr_isin_cache:
        return _xirr_isin_cache[name]

    s = str(name).strip().upper()
    s = re.sub(r"[.-]+$", "", s).strip()
    s = re.sub(r"\s+", " ", s)

    # 1. ISIN lookup
    if _ISIN_AVAILABLE:
        try:
            isin = get_isin(name)
            if isin:
                _xirr_isin_cache[name] = isin
                return isin
        except Exception:
            pass

    # 2. Manual NAME_MAP
    if s in _NAME_MAP:
        result = _NAME_MAP[s]
        _xirr_isin_cache[name] = result
        return result

    # 3. Auto-strip suffixes
    for pat in [
        r"\s+LIMITED$", r"\s+LTD$", r"\s+LT$", r"\s+L$",
        r"\s+PVT$", r"\s+PRIVATE$",
        r"\s+CORPORATION$", r"\s+CORP$", r"\s+COR$", r"\s+CO$",
    ]:
        stripped = re.sub(pat, "", s).strip()
        if stripped and stripped != s:
            s = stripped
            break

    _xirr_isin_cache[name] = s
    return s


# ─────────────────────────────────────────────────────────────────────────────
#  XIRR SOLVER
# ─────────────────────────────────────────────────────────────────────────────

def _xirr_scipy(cashflows: list) -> Optional[float]:
    """
    XIRR via scipy brentq — used when pyxirr is unavailable.
    cashflows: list of (pd.Timestamp, float)
    """
    dates   = [pd.Timestamp(d) for d, _ in cashflows]
    amounts = [float(a) for _, a in cashflows]

    if all(a >= 0 for a in amounts) or all(a <= 0 for a in amounts):
        return None

    t0    = min(dates)
    years = [(d - t0).days / 365.25 for d in dates]

    def npv(rate):
        try:
            return sum(a / (1 + rate) ** t for a, t in zip(amounts, years))
        except (ZeroDivisionError, OverflowError):
            return float("inf")

    try:
        # Try multiple brackets to handle unusual cases
        for lo, hi in [(-0.9999, 50.0), (-0.9999, 200.0), (-0.9999, 5.0)]:
            try:
                if npv(lo) * npv(hi) < 0:
                    result = brentq(npv, lo, hi, maxiter=2000, xtol=1e-10, rtol=1e-10)
                    return round(result * 100, 4)
            except Exception:
                continue
        return None
    except Exception:
        return None


def compute_xirr(cashflows: list) -> Optional[float]:
    """
    Compute XIRR.  Returns annualised rate as percentage (18.5 = 18.5% p.a.).
    Returns None when computation is impossible or data is insufficient.

    cashflows : list of (date-like, float)
                negative amount = outflow (buy)
                positive amount = inflow  (sell / terminal value)
    """
    if not cashflows or len(cashflows) < 2:
        return None

    # Drop zero flows and future-dated flows
    cashflows = [
        (pd.Timestamp(d), float(a))
        for d, a in cashflows
        if float(a) != 0 and pd.Timestamp(d) <= TODAY + pd.Timedelta(days=1)
    ]

    if len(cashflows) < 2:
        return None

    amounts = [a for _, a in cashflows]
    if all(a >= 0 for a in amounts) or all(a <= 0 for a in amounts):
        return None

    # Guard: need at least one negative AND one positive
    if not any(a < 0 for a in amounts) or not any(a > 0 for a in amounts):
        return None

    def _sanitise(val):
        if val is None:
            return None
        try:
            v = float(val)
        except (ValueError, TypeError):
            return None
        if np.isnan(v) or np.isinf(v):
            return None
        if abs(v) > 500:  # Cap at 500% — anything above is not meaningful
            return None
        return v

    if _USE_PYXIRR:
        try:
            dates_py = [pd.Timestamp(d).date() for d, _ in cashflows]
            amts_py  = [float(a) for _, a in cashflows]
            result   = _pyxirr(dates_py, amts_py)
            if result is None or (isinstance(result, float) and (np.isnan(result) or np.isinf(result))):
                return _sanitise(_xirr_scipy(cashflows))
            return _sanitise(round(float(result) * 100, 4))
        except Exception:
            return _sanitise(_xirr_scipy(cashflows))
    else:
        return _sanitise(_xirr_scipy(cashflows))


# ─────────────────────────────────────────────────────────────────────────────
#  CASH FLOW CONSTRUCTION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _build_trade_flows_per_scrip(
    trade_df: pd.DataFrame,
) -> dict:
    """
    Build a dict: {clean_scrip_name: [(date, signed_amount), ...]}
    from the raw trade DataFrame.

    Uses the pre-existing signed Amount column:
        BUY  trades → Amount is already negative  (outflow)
        SELL trades → Amount is already positive  (inflow)

    If Amount is 0 but Quantity and Price exist, reconstructs it with correct sign:
        BUY  → -(Quantity × Price)
        SELL → +(Quantity × Price)
    """
    result = {}

    if trade_df is None or trade_df.empty:
        return result

    required = {"Trade Date", "Scrip Name", "Action", "Quantity", "Price", "Amount"}
    if not required.issubset(set(trade_df.columns)):
        return result

    df = trade_df.copy()
    df["_cn"] = df["Scrip Name"].apply(_cn)
    df["Trade Date"] = pd.to_datetime(df["Trade Date"], errors="coerce")
    df["Quantity"]   = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).abs()
    df["Price"]      = pd.to_numeric(df["Price"],    errors="coerce").fillna(0)
    df["Amount"]     = pd.to_numeric(df["Amount"],   errors="coerce").fillna(0)
    df["Action"]     = df["Action"].astype(str).str.strip().str.upper()

    for cn, grp in df.groupby("_cn"):
        flows = []
        for _, row in grp.iterrows():
            dt     = row["Trade Date"]
            action = row["Action"]
            qty    = float(row["Quantity"])
            price  = float(row["Price"])
            amount = float(row["Amount"])

            # Skip rows with missing date or zero quantity
            if pd.isna(dt) or qty == 0:
                continue

            # Determine signed cash flow
            if action == "BUY":
                # Amount should be negative; if not, force it
                if amount == 0:
                    cf = -(qty * price)
                elif amount > 0:
                    cf = -abs(amount)   # some brokers report unsigned
                else:
                    cf = amount         # already negative — correct
            elif action == "SELL":
                # Amount should be positive
                if amount == 0:
                    cf = qty * price
                elif amount < 0:
                    cf = abs(amount)    # some brokers report unsigned
                else:
                    cf = amount         # already positive — correct
            else:
                continue  # skip unknown actions

            if cf != 0:
                flows.append((pd.Timestamp(dt), cf))

        if flows:
            result[cn] = flows

    return result


def _build_holdings_flows_for_holdings_only_scrips(
    holdings_df           : pd.DataFrame,
    trade_scrip_clean_names: set,
) -> dict:
    """
    Build cash flows ONLY for scrips that do NOT appear in the trade report.

    For each such scrip from the holdings file:
      - BUY outflow  : -(Net Quantity × Avg Buy Rate)  on  Buy Date
        (Net Quantity = what is still held; Avg Buy Rate = cost per share)
        This avoids double-counting lots that were already sold (those sells
        are not in the trade report for holdings-only scrips so we also add
        sell flows from the holdings file for these scrips only).

      - SELL inflow  : +(Sell Quantity × Sell Rate)  on  Sell Date
        (only if Sell Quantity > 0 and Sell Date is valid)

    Skips any row where Buy Date is missing.

    Returns dict: {clean_scrip_name: [(date, signed_amount), ...]}
    """
    result = {}

    if holdings_df is None or holdings_df.empty:
        return result

    if "Scrip Name" not in holdings_df.columns:
        return result

    df = holdings_df.copy()
    df["_cn"] = df["Scrip Name"].apply(_cn)

    for cn, grp in df.groupby("_cn"):
        # Skip scrips already covered by the trade report
        if cn in trade_scrip_clean_names:
            continue

        flows = []
        valid = True

        for _, row in grp.iterrows():
            buy_date  = row.get("Buy Date",       pd.NaT)
            net_qty   = row.get("Net Quantity",   np.nan)
            buy_rate  = row.get("Buy Rate",       np.nan)
            buy_amt   = row.get("Buy Amount",     np.nan)
            sell_date = row.get("Sell Date",      pd.NaT)
            sell_qty  = row.get("Sell Quantity",  np.nan)
            sell_rate = row.get("Sell Rate",      np.nan)
            sell_amt  = row.get("Sell Amount",    np.nan)

            # ── BUY cash flow ─────────────────────────────────────────────
            if pd.isna(buy_date):
                # Cannot anchor this row in time — skip entire scrip
                valid = False
                break

            buy_date_ts = pd.Timestamp(buy_date)

            # Reconstruct cost of what is STILL HELD (net_qty × avg_buy_rate)
            # This is the correct outflow — do NOT use Buy Amount directly
            # because Buy Amount = total cost of ALL lots including sold ones.
            net_qty_f  = float(net_qty)  if pd.notna(net_qty)  and float(net_qty)  > 0 else 0.0
            buy_rate_f = float(buy_rate) if pd.notna(buy_rate) and float(buy_rate) > 0 else 0.0

            # Fallback: if buy_rate is missing, derive from buy_amt / net_qty
            if buy_rate_f == 0 and net_qty_f > 0 and pd.notna(buy_amt) and float(buy_amt) > 0:
                buy_rate_f = float(buy_amt) / net_qty_f

            if net_qty_f > 0 and buy_rate_f > 0:
                outflow = -(net_qty_f * buy_rate_f)
                flows.append((buy_date_ts, outflow))

            # ── SELL cash flow ────────────────────────────────────────────
            # Only add if there is a valid sell recorded in the holdings file
            sell_qty_f  = float(sell_qty)  if pd.notna(sell_qty)  and float(sell_qty)  > 0 else 0.0
            sell_rate_f = float(sell_rate) if pd.notna(sell_rate) and float(sell_rate) > 0 else 0.0
            sell_amt_f  = float(sell_amt)  if pd.notna(sell_amt)  and float(sell_amt)  > 0 else 0.0

            if sell_qty_f > 0 and pd.notna(sell_date):
                sell_date_ts = pd.Timestamp(sell_date)
                # Prefer sell_qty × sell_rate; fallback to sell_amt column
                if sell_rate_f > 0:
                    inflow = sell_qty_f * sell_rate_f
                elif sell_amt_f > 0:
                    inflow = sell_amt_f
                else:
                    inflow = 0.0
                if inflow > 0:
                    flows.append((sell_date_ts, inflow))

        if valid and flows:
            result[cn] = flows

    return result


def _build_holdings_opening_flows_for_trade_scrips(
    holdings_df            : pd.DataFrame,
    trade_scrip_clean_names: set,
) -> dict:
    """
    For scrips that ARE in the trade report AND also in the holdings file,
    we need to add the OPENING position cost from the holdings file.

    The holdings file records buys BEFORE the trade report period begins.
    Those buys are NOT in the trade report — so we must add them.

    Correct cash flow:
      outflow = -(Net Quantity from holdings × Avg Buy Rate)  on  Buy Date

    We do NOT add sell flows here because:
      • Any sells recorded in the holdings file for these scrips correspond
        to lots sold WITHIN the holdings report period.
      • The trade report picks up subsequent sells and those are already
        in the trade flows.
      • The holdings file's Sell Qty shows lots sold BEFORE the trade period,
        their sell proceeds are already baked into the holdings-period P&L
        and do NOT belong in the same XIRR calculation that runs forward
        into the trade report period.

    Returns dict: {clean_scrip_name: [(date, signed_amount), ...]}
    """
    result = {}

    if holdings_df is None or holdings_df.empty:
        return result

    if "Scrip Name" not in holdings_df.columns:
        return result

    df = holdings_df.copy()
    df["_cn"] = df["Scrip Name"].apply(_cn)

    for cn, grp in df.groupby("_cn"):
        # Only for scrips that appear in BOTH files
        if cn not in trade_scrip_clean_names:
            continue

        flows = []

        for _, row in grp.iterrows():
            buy_date  = row.get("Buy Date",     pd.NaT)
            net_qty   = row.get("Net Quantity", np.nan)
            buy_rate  = row.get("Buy Rate",     np.nan)
            buy_amt   = row.get("Buy Amount",   np.nan)

            if pd.isna(buy_date):
                continue  # skip rows without buy date

            buy_date_ts = pd.Timestamp(buy_date)

            net_qty_f  = float(net_qty)  if pd.notna(net_qty)  and float(net_qty)  > 0 else 0.0
            buy_rate_f = float(buy_rate) if pd.notna(buy_rate) and float(buy_rate) > 0 else 0.0

            if buy_rate_f == 0 and net_qty_f > 0 and pd.notna(buy_amt) and float(buy_amt) > 0:
                buy_rate_f = float(buy_amt) / net_qty_f

            if net_qty_f > 0 and buy_rate_f > 0:
                outflow = -(net_qty_f * buy_rate_f)
                flows.append((buy_date_ts, outflow))

        if flows:
            result[cn] = flows

    return result


# ─────────────────────────────────────────────────────────────────────────────
#  AGGREGATOR — merges all flows for a scrip and deduplicates by date
# ─────────────────────────────────────────────────────────────────────────────

def _aggregate_flows(flows: list) -> list:
    """
    Aggregate multiple cash flows on the same date into a single flow.
    Sorts chronologically.
    """
    by_date = {}
    for dt, amt in flows:
        key = pd.Timestamp(dt).normalize()   # date-only key
        by_date[key] = by_date.get(key, 0.0) + float(amt)
    return sorted(by_date.items())


# ─────────────────────────────────────────────────────────────────────────────
#  TERMINAL CASH FLOW
# ─────────────────────────────────────────────────────────────────────────────

def _terminal_flow(unified_df: pd.DataFrame) -> float:
    """
    Sum of (Effective Price × Net Quantity) for all open positions.
    = liquidation value today = final positive cash inflow.
    """
    if "Current Value" in unified_df.columns:
        val = unified_df["Current Value"].fillna(0).sum()
    elif "Effective Price" in unified_df.columns and "Net Quantity" in unified_df.columns:
        val = (unified_df["Effective Price"].fillna(0) * unified_df["Net Quantity"].fillna(0)).sum()
    else:
        val = 0.0
    return float(val)


def _scrip_terminal(unified_df: pd.DataFrame, cn_scrip: str, clean_to_display: dict) -> float:
    """Current value for a single scrip (matched by clean name)."""
    display = clean_to_display.get(cn_scrip)
    if display is None:
        return 0.0
    rows = unified_df[unified_df["Scrip Name"] == display]
    if rows.empty:
        return 0.0
    if "Current Value" in rows.columns:
        return float(rows["Current Value"].fillna(0).sum())
    if "Effective Price" in rows.columns and "Net Quantity" in rows.columns:
        return float((rows["Effective Price"].fillna(0) * rows["Net Quantity"].fillna(0)).sum())
    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
#  PORTFOLIO-LEVEL XIRR
# ─────────────────────────────────────────────────────────────────────────────

def compute_portfolio_xirr(
    trade_df    : pd.DataFrame,
    holdings_df : pd.DataFrame,
    unified_df  : pd.DataFrame,
) -> dict:
    """
    Compute overall portfolio XIRR.

    Cash flow assembly:
      1. All trade report flows (signed Amount, per BUY/SELL action)
      2. Holdings opening flows for scrips that also appear in trade report
         (opening cost before trade report period)
      3. Holdings-only scrip flows (full lifecycle from holdings file)
      4. Terminal flow = today's portfolio value (positive inflow)

    Returns dict with xirr_pct, cashflows (for audit), totals.
    """
    trade_flows   = _build_trade_flows_per_scrip(trade_df)
    trade_scrips  = set(trade_flows.keys())

    # Opening flows (holdings file, for scrips ALSO in trade report)
    opening_flows = _build_holdings_opening_flows_for_trade_scrips(holdings_df, trade_scrips)

    # Full lifecycle flows (holdings file, for scrips NOT in trade report)
    holdings_only = _build_holdings_flows_for_holdings_only_scrips(holdings_df, trade_scrips)

    # Combine all flows
    all_flows = []
    for flows in trade_flows.values():
        all_flows.extend(flows)
    for flows in opening_flows.values():
        all_flows.extend(flows)
    for flows in holdings_only.values():
        all_flows.extend(flows)

    # Terminal cash flow
    terminal_val = _terminal_flow(unified_df)
    if terminal_val > 0:
        all_flows.append((TODAY, terminal_val))

    aggregated     = _aggregate_flows(all_flows)
    xirr_val       = compute_xirr(aggregated)
    total_invested = sum(-a for _, a in aggregated if a < 0)
    earliest       = min((d for d, _ in aggregated), default=None)

    return {
        "xirr_pct"      : xirr_val,
        "cashflows"      : aggregated,
        "total_invested" : round(total_invested, 2),
        "total_current"  : round(terminal_val,   2),
        "earliest_date"  : earliest,
        "flow_count"     : len(aggregated),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  PER-SCRIP XIRR
# ─────────────────────────────────────────────────────────────────────────────

def compute_xirr_per_scrip(
    trade_df    : pd.DataFrame,
    holdings_df : pd.DataFrame,
    unified_df  : pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute XIRR for each individual scrip.

    For each scrip:
      • If in trade report only   → use trade flows + terminal
      • If in holdings only       → use holdings flows (net qty × avg rate) + terminal
      • If in BOTH files          → use holdings opening flow + trade flows + terminal

    Returns DataFrame sorted by XIRR % descending.
    """
    trade_flows   = _build_trade_flows_per_scrip(trade_df)
    trade_scrips  = set(trade_flows.keys())

    opening_flows = _build_holdings_opening_flows_for_trade_scrips(holdings_df, trade_scrips)
    holdings_only = _build_holdings_flows_for_holdings_only_scrips(holdings_df, trade_scrips)

    # Build clean_name → display_name map from unified_df
    clean_to_display = {}
    if not unified_df.empty and "Scrip Name" in unified_df.columns:
        for name in unified_df["Scrip Name"].unique():
            clean_to_display[_cn(name)] = name

    # Collect all clean scrip names
    all_cn = (
        set(trade_flows.keys())
        | set(opening_flows.keys())
        | set(holdings_only.keys())
    )

    results = []
    for cn in sorted(all_cn):
        flows = []

        # Opening cost from holdings (for scrips in both files)
        flows.extend(opening_flows.get(cn, []))

        # Trade report flows
        flows.extend(trade_flows.get(cn, []))

        # Holdings-only scrip flows
        flows.extend(holdings_only.get(cn, []))

        if not flows:
            continue

        # Terminal cash flow for this scrip
        term = _scrip_terminal(unified_df, cn, clean_to_display)
        if term > 0:
            flows.append((TODAY, term))

        agg      = _aggregate_flows(flows)
        xirr_val = compute_xirr(agg)
        earliest = min((d for d, _ in agg if d <= TODAY), default=None)

        display_name = clean_to_display.get(cn, cn)
        results.append({
            "Scrip Name"      : display_name,
            "XIRR %"          : round(xirr_val, 2) if xirr_val is not None else None,
            "Cash Flow Count" : len(agg),
            "Earliest Buy"    : earliest,
            "Current Value"   : round(term, 2),
            "Note"            : "OK" if xirr_val is not None else "Could not compute",
        })

    df = pd.DataFrame(results)
    if not df.empty and "XIRR %" in df.columns:
        df = df.sort_values("XIRR %", ascending=False, na_position="last").reset_index(drop=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  PER-GROUP XIRR
# ─────────────────────────────────────────────────────────────────────────────

def compute_xirr_per_group(
    trade_df    : pd.DataFrame,
    holdings_df : pd.DataFrame,
    unified_df  : pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute XIRR grouped by holding category:
      Opening Assets, Long Term, Short Term, Trade Period.

    Groups scrips by their Group field in unified_df, then aggregates all
    their cash flows.
    """
    if unified_df.empty or "Group" not in unified_df.columns:
        return pd.DataFrame()

    trade_flows   = _build_trade_flows_per_scrip(trade_df)
    trade_scrips  = set(trade_flows.keys())
    opening_flows = _build_holdings_opening_flows_for_trade_scrips(holdings_df, trade_scrips)
    holdings_only = _build_holdings_flows_for_holdings_only_scrips(holdings_df, trade_scrips)

    # Map clean scrip name → group
    clean_to_display = {}
    scrip_to_group   = {}
    for _, row in unified_df.drop_duplicates(subset=["Scrip Name"]).iterrows():
        name = row["Scrip Name"]
        cn   = _cn(name)
        clean_to_display[cn] = name
        scrip_to_group[cn]   = row.get("Group", "Unknown")

    # Group-level current values
    group_cv = (
        unified_df.groupby("Group")["Current Value"].sum().to_dict()
        if "Current Value" in unified_df.columns else {}
    )

    groups = unified_df["Group"].unique().tolist()
    results = []

    for group in groups:
        group_scrips = {cn for cn, g in scrip_to_group.items() if g == group}

        flows = []
        for cn in group_scrips:
            flows.extend(opening_flows.get(cn, []))
            flows.extend(trade_flows.get(cn, []))
            flows.extend(holdings_only.get(cn, []))

        current_val = float(group_cv.get(group, 0))
        if current_val > 0:
            flows.append((TODAY, current_val))

        if not flows:
            results.append({
                "Group"           : group,
                "XIRR %"          : None,
                "Current Value"   : 0.0,
                "Cash Flow Count" : 0,
                "Note"            : "No dated cash flows",
            })
            continue

        agg      = _aggregate_flows(flows)
        xirr_val = compute_xirr(agg)

        results.append({
            "Group"           : group,
            "XIRR %"          : round(xirr_val, 2) if xirr_val is not None else None,
            "Current Value"   : round(current_val, 2),
            "Cash Flow Count" : len(agg),
            "Note"            : "OK" if xirr_val is not None else "Insufficient data",
        })

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values("Current Value", ascending=False).reset_index(drop=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  CASH FLOW AUDIT TABLE
# ─────────────────────────────────────────────────────────────────────────────

def build_cashflow_summary(cashflows: list) -> pd.DataFrame:
    """
    Convert aggregated (date, amount) list into a human-readable audit DataFrame.
    Shows date, net flow, flow type, and running cumulative invested amount.
    """
    if not cashflows:
        return pd.DataFrame()

    rows             = []
    running_invested = 0.0

    for dt, amt in sorted(cashflows):
        flow_type = "Inflow (Sell / Terminal Value)" if amt > 0 else "Outflow (Buy)"
        if amt < 0:
            running_invested += abs(amt)
        rows.append({
            "Date"               : pd.Timestamp(dt).strftime("%d %b %Y"),
            "Cash Flow (₹)"      : round(amt, 2),
            "Type"               : flow_type,
            "Cumul. Invested (₹)": round(running_invested, 2),
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
#  TOP-LEVEL ENTRY POINT  (called from streamlit_app.py)
# ─────────────────────────────────────────────────────────────────────────────

def run_xirr_analysis(
    trade_raw_df : pd.DataFrame,
    holdings_df  : pd.DataFrame,
    unified_df   : pd.DataFrame,
) -> dict:
    """
    Run all XIRR computations and return a results dict.

    Parameters
    ----------
    trade_raw_df : raw equity trade DataFrame (Trade Date, Scrip Name,
                   Action, Quantity, Price, Amount) — pre-FIFO, all trades
    holdings_df  : parsed holdings file DataFrame from holdings_analysis.py
    unified_df   : integrated holdings DataFrame from integrator.py
                   (must have Current Value, Effective Price, Net Quantity,
                    Scrip Name, Group columns)

    Returns
    -------
    dict with keys:
        portfolio  : dict   (xirr_pct, cashflows, totals)
        per_group  : DataFrame
        per_scrip  : DataFrame
        cf_summary : DataFrame  (audit trail of portfolio cash flows)
    """
    if trade_raw_df is None:
        trade_raw_df = pd.DataFrame()
    if holdings_df is None:
        holdings_df = pd.DataFrame()

    # Ensure Current Value exists in unified_df
    if "Current Value" not in unified_df.columns:
        if "Effective Price" in unified_df.columns and "Net Quantity" in unified_df.columns:
            unified_df = unified_df.copy()
            unified_df["Current Value"] = (
                unified_df["Effective Price"].fillna(0) * unified_df["Net Quantity"].fillna(0)
            )

    portfolio  = compute_portfolio_xirr(trade_raw_df, holdings_df, unified_df)
    per_group  = compute_xirr_per_group(trade_raw_df, holdings_df, unified_df)
    per_scrip  = compute_xirr_per_scrip(trade_raw_df, holdings_df, unified_df)
    cf_summary = build_cashflow_summary(portfolio["cashflows"])

    return {
        "portfolio"  : portfolio,
        "per_group"  : per_group,
        "per_scrip"  : per_scrip,
        "cf_summary" : cf_summary,
    }