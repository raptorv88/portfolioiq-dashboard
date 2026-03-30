import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import yfinance as yf
from collections import deque


# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

UPLOADED_FILE = "A"

TICKER_MAP = {
    "ALLIED BLENDERS AND DISTILLERS"    : "ABDL.NS",
    "ALSTONE TEXTILES (INDIA) LTD"      : "ALSTONE.BO",
    "ARKADE DEVELOPERS LIMITED"         : "ARKADE.NS",
    "BAJAJ AUTO LTD."                   : "BAJAJ-AUTO.NS",
    "BAJAJ FINANCE LIMITED"             : "BAJFINANCE.NS",
    "BAJAJ FINSERV LTD"                 : "BAJAJFINSV.NS",
    "BAJAJ HOLDINGS & INVESTMENT LT"    : "BAJAJHLDNG.NS",
    "BAJAJ HOUSING FINANCE LIMITED"     : "BAJAJHFL.NS",
    "BAJAJ HOUSING FINANCE LTD"         : "BAJAJHFL.NS",
    "BALAJI AMINES LTD."                : "BALAMINES.NS",
    "BANK OF BARODA"                    : "BANKBARODA.NS",
    "BANKEX"                            : "^BSEBANK",
    "BANKNIFTY"                         : "^NSEBANK",
    "BFAM - LIQUIDBETF"                 : "LIQUIDBETF.NS",
    "BILLIONBRAINS GARAGE VN L"         : "GROWW.NS",
    "BOMBAY BURMAH TRADING COR"         : "BBTC.NS",
    "CANARA BANK"                       : "CANBK.NS",
    "COAL INDIA LTD."                   : "COALINDIA.NS",
    "CUMMINS INDIA LTD."                : "CUMMINSIND.NS",
    "FINNIFTY"                          : "^CNXFIN",
    "GODAVARI BIOREFINERIES LIMITED"    : "GODAVARIB.NS",  # Fixed missing .NS
    "GODAWARI POWER & ISPAT LTD."       : "GPIL.NS",
    "GUFIC BIOSCIENCES LTD."            : "GUFICBIO.NS",
    "HDFC BANK LTD."                    : "HDFCBANK.NS",
    "HERO MOTOCORP LTD."                : "HEROMOTOCO.NS", # Standardized to .NS to match manual maps
    "HINDUSTAN COPPER LTD."             : "HINDCOPPER.NS",
    "HINDUSTAN PETROLEUM CORPORATIO"    : "HINDPETRO.NS",
    "ICICI BANK LTD."                   : "ICICIBANK.NS",
    "ICICI PRUDENTIAL ASSET MANAGEM"    : "ICICIPRULI.NS",
    "INTERARCH BUILDING SOLUTIONS L"    : "INTERARCH.NS",  # Standardized to .NS to match manual maps
    "JIO FINANCIAL SERVICES LIMITED"    : "JIOFIN.NS",
    "KALYANI INVEST CO LTD"             : "KALYANIINV.NS", # Standardized to .NS to match manual maps
    "LENSKART SOLUTIONS LTD"            : "LENSKART.NS",
    "NHPC LTD."                         : "NHPC.NS",
    "NIFTY"                             : "^NSEI",
    "NTPC LTD."                         : "NTPC.NS",
    "OIL AND NATURAL GAS CORPORATIO"    : "ONGC.NS",
    "PILANI INV & IND COR LTD"          : "PILANIINV.NS",
    "PIRAMAL ENTERPRISES LTD."          : "PEL.NS",
    "PUNE E - STOCK BROKING LIMITED"    : "PESB.BO",       # Standardized to match manual maps
    "PUNJAB NATIONAL BANK"              : "PNB.NS",
    "RELIANCE INDUSTRIES LTD."          : "RELIANCE.NS",
    "SANATHAN TEXTILES LIMITED"         : "SANATHAN.NS",
    "SHEELA FOAM LIMITED"               : "SFL.NS",
    "SHREE CEMENT LTD."                 : "SHREECEM.NS",
    "SENSEX"                            : "^BSESN",
    "SJVN LTD"                          : "SJVN.NS",
    "STATE BANK OF INDIA"               : "SBIN.NS",
    "TATA CONSULTANCY SERVICES LTD."    : "TCS.NS",
    "TATA MOTORS PASSENGER VEHICLES"    : "TMPV.NS",
    "TATA MOTORS LIMITED"               : "TATAMOTORS.NS",
    "TATA STEEL LTD."                   : "TATASTEEL.NS",
    "TIPS MUSIC LIMITED"                : "TIPSMUSIC.NS",
    "UJJIVAN SMALL FINANCE BANK LIM"    : "UJJIVANSFB.NS", # Standardized to .NS to match manual maps
    "ZEE ENTERTAINMENT ENTERPRISES"     : "ZEEL.NS",
}


# Scrips that are index / derivative instruments (no physical holding)
INDEX_KEYWORDS = r"NIFTY|SENSEX|BANKNIFTY|FINNIFTY|BANKEX"

# Market cap thresholds (in INR crores, SEBI classification)
LARGE_CAP_THRESHOLD  = 20_000   # ≥ ₹20,000 Cr
MID_CAP_THRESHOLD    =  5_000   # ₹5,000 – ₹19,999 Cr
SMALL_CAP_THRESHOLD  =  1_000   # ₹1,000 – ₹4,999 Cr
# Below ₹1,000 Cr → Micro Cap

# Core / Satellite / Tail thresholds (weight %)
CORE_THRESHOLD      = 5.0    # ≥ 5 %
SATELLITE_THRESHOLD = 1.0    # 1 % – 4.99 %
# Below 1 % → Tail


# ─────────────────────────────────────────────────────────────────────────────
#  1. DATA LOADING & PREPROCESSING
# ─────────────────────────────────────────────────────────────────────────────

# Default number of rows to skip before the column header row
DEFAULT_SKIP_ROWS = 30

# Required trade columns
REQUIRED_COLS = ["Scrip Name", "Segment", "Quantity", "Price",
                 "Trade Date", "Action", "Amount"]


def extract_client_info(filepath: str) -> dict:
    """
    Extract client metadata from the broker report header rows.

    Layout (1-indexed rows):
        Row 1  : Company name
        Row 2  : Report title  (e.g. Financial Year Report of Trades)
        Row 3  : Date range
        Row 4  : Client Name (col A)  |  Client ID (col B)

    Returns a dict with keys: client_name, client_id, date_range, company
    """
    raw = pd.read_excel(filepath, header=None, nrows=4)

    def _cell(row, col):
        try:
            val = raw.iloc[row, col]
            return str(val).strip() if pd.notna(val) else ""
        except Exception:
            return ""

    return {
        "company"     : _cell(0, 0),
        "report_title": _cell(1, 0),
        "date_range"  : _cell(2, 0),
        "client_name" : _cell(3, 0),
        "client_id"   : _cell(3, 1),
    }


def detect_header_row(filepath: str, max_scan: int = 50) -> int:
    """
    Auto-detect the row index (0-based) of the actual column header
    by scanning for a row that contains the most REQUIRED_COLS keywords.

    Falls back to DEFAULT_SKIP_ROWS if nothing better is found.
    """
    raw = pd.read_excel(filepath, header=None, nrows=max_scan)

    best_row   = DEFAULT_SKIP_ROWS
    best_score = 0

    for i, row in raw.iterrows():
        row_vals = [str(v).strip() for v in row if pd.notna(v)]
        score    = sum(1 for col in REQUIRED_COLS if col in row_vals)
        if score > best_score:
            best_score = score
            best_row   = i

    return best_row   # 0-based row index → use as skiprows


def load_data(filepath: str, skip_rows: int = None) -> tuple:
    """
    Load the broker trade Excel report, skipping all header junk.

    Parameters
    ----------
    filepath  : path to the .xlsx file
    skip_rows : number of rows to skip before the column header row.
                If None, auto-detects using detect_header_row().

    Returns
    -------
    df          : DataFrame of trade records
    client_info : dict with client_name, client_id, date_range, company
    skip_used   : int — the skip_rows value actually used (useful for UI)
    """
    # 1. Extract client metadata from top rows (always read raw)
    client_info = extract_client_info(filepath)

    # 2. Determine how many rows to skip
    if skip_rows is None:
        skip_rows = detect_header_row(filepath)

    # 3. Load the actual trade data
    df = pd.read_excel(filepath, skiprows=skip_rows)
    df.columns = df.columns.str.strip()

    # 4. Drop completely empty rows (common in broker exports)
    df = df.dropna(how="all").reset_index(drop=True)

    # 5. Validate required columns
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Could not find required columns after skipping {skip_rows} rows.\n"
            f"Missing: {missing}\n"
            f"Found columns: {list(df.columns)}\n"
            f"Try adjusting the 'rows to skip' value."
        )

    return df[REQUIRED_COLS].copy(), client_info, skip_rows


def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean strings, parse dates, validate actions."""
    df["Scrip Name"] = (
        df["Scrip Name"]
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", " ", regex=True)
        .str.replace("\xa0", "", regex=False)
    )

    df["Action"] = df["Action"].astype(str).str.strip().str.upper()
    df["Trade Date"] = pd.to_datetime(df["Trade Date"])
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).abs()
    df["Price"]    = pd.to_numeric(df["Price"],    errors="coerce").fillna(0)
    df["Amount"]   = pd.to_numeric(df["Amount"],   errors="coerce").fillna(0)
    mask = (df["Price"] == 0) & (df["Quantity"] > 0)
    df.loc[mask, "Price"] = (df.loc[mask, "Amount"] / df.loc[mask, "Quantity"]).abs()

    df = df.sort_values("Trade Date").reset_index(drop=True)
    return df

def separate_index_equity(df: pd.DataFrame):
    """Split trades into equity and index/derivative buckets."""
    # Use Segment column as primary filter — most reliable
    mask = (
        df["Segment"].str.upper().str.strip().isin(["FNO", "F&O", "DERIVATIVE", "INDEX"]) |
        df["Scrip Name"].str.contains(INDEX_KEYWORDS, regex=True)
    )
    index_df  = df[mask].copy()
    equity_df = df[~mask].copy()
    return equity_df, index_df

def run_fifo(trades: pd.DataFrame, initial_lots: list = None):
    buy_queue     = deque()   # each element: [qty_remaining, cost_price]
    realized_pnl  = 0.0
    realized_rows = []

    # ── Seed queue with historical lots from Holdings File ────────────────
    if initial_lots:
        for qty, cost in initial_lots:
            if qty > 0 and cost >= 0:
                buy_queue.append([int(qty), float(cost)])

    for _, row in trades.iterrows():
        action = row["Action"]
        qty    = int(row["Quantity"])
        price  = float(row["Price"])
        date   = row["Trade Date"]
        

        if action == "BUY":
            buy_queue.append([qty, price])

        elif action == "SELL":
            qty_to_sell  = qty
            sell_proceeds = qty * price
            cost_of_sold  = 0.0

            while qty_to_sell > 0 and buy_queue:
                lot_qty, lot_price = buy_queue[0]

                if lot_qty <= qty_to_sell:
                    cost_of_sold  += lot_qty * lot_price
                    qty_to_sell   -= lot_qty
                    buy_queue.popleft()
                else:
                    cost_of_sold          += qty_to_sell * lot_price
                    buy_queue[0][0]       -= qty_to_sell
                    qty_to_sell            = 0

            trade_pnl    = sell_proceeds - cost_of_sold
            realized_pnl += trade_pnl

            realized_rows.append({
                "Date"          : date,
                "Sell Qty"      : qty,
                "Sell Price"    : price,
                "Sell Proceeds" : round(sell_proceeds, 2),
                "Cost of Sold"  : round(cost_of_sold,  2),
                "Realized P&L"  : round(trade_pnl,     2),
            })

    # Summarise open lots
    open_lots      = list(buy_queue)
    total_open_qty = sum(l[0] for l in open_lots)
    total_open_cost= sum(l[0] * l[1] for l in open_lots)
    avg_cost       = (total_open_cost / total_open_qty) if total_open_qty > 0 else 0.0


    return realized_pnl, open_lots, avg_cost, total_open_qty, realized_rows
def fetch_live_prices(holdings_df: pd.DataFrame) -> pd.DataFrame:
    from ticker_resolver import fetch_live_prices_with_autoresolve, get_extended_ticker_map

    holdings_df = holdings_df.copy()

    # Build extended ticker map (base + extra overrides + cached resolutions)
    extended_map = get_extended_ticker_map(TICKER_MAP)
    holdings_df["Ticker"] = holdings_df["Scrip Name"].map(extended_map)

    scrip_names = holdings_df["Scrip Name"].tolist()
    live_price_map = fetch_live_prices_with_autoresolve(scrip_names, TICKER_MAP)

    holdings_df["Live Price"] = holdings_df["Scrip Name"].map(live_price_map)
    return holdings_df



def build_opening_lots_from_holdings(holdings_df: pd.DataFrame) -> dict:
    result = {}
    if holdings_df is None or holdings_df.empty:
        return result

    for scrip, grp in holdings_df.groupby("Scrip Name"):
        net_qty = float(grp["Net Quantity"].sum()) if "Net Quantity" in grp.columns else 0.0
        if net_qty <= 0:
            continue

        # Derive avg cost per share
        buy_qty = float(grp["Buy Quantity"].sum()) if "Buy Quantity" in grp.columns else 0.0
        buy_amt = float(grp["Buy Amount"].sum())   if "Buy Amount"   in grp.columns else 0.0

        if buy_qty > 0 and buy_amt > 0:
            avg_cost = buy_amt / buy_qty
        elif "Buy Rate" in grp.columns:
            avg_cost = float(grp["Buy Rate"].mean())
        else:
            avg_cost = 0.0

        result[str(scrip).strip().upper()] = [(net_qty, avg_cost)]

    return result


def calculate_equity_positions(
    equity_df    : pd.DataFrame,
    opening_lots : dict = None,
):

    holdings_rows  = []
    realized_rows  = []

    if opening_lots is None:
        opening_lots = {}

    for scrip, group in equity_df.groupby("Scrip Name"):
        group = group.sort_values("Trade Date")

        # Look up opening lots for this scrip — try exact name first,
        # then normalised (strip trailing dots/spaces)
        init = (
            opening_lots.get(scrip)
            or opening_lots.get(str(scrip).strip().upper())
            or opening_lots.get(str(scrip).strip().upper().rstrip("."))
        )

        r_pnl, open_lots, avg_cost, open_qty, r_rows = run_fifo(
            group, initial_lots=init
        )

        for r in r_rows:
            r["Scrip Name"] = scrip
            realized_rows.append(r)

        if open_qty > 0:
            holdings_rows.append({
                "Scrip Name"     : scrip,
                "Open Qty"       : open_qty,
                "Avg Cost"       : round(avg_cost, 4),
                "Cost Value"     : round(open_qty * avg_cost, 2),
                "Realized P&L"   : round(r_pnl, 2),
            })

    holdings_df = pd.DataFrame(holdings_rows)
    realized_df = pd.DataFrame(realized_rows) if realized_rows else pd.DataFrame(
        columns=["Scrip Name", "Date", "Sell Qty", "Sell Price",
                 "Sell Proceeds", "Cost of Sold", "Realized P&L"]
    )
    return holdings_df, realized_df

# ─────────────────────────────────────────────────────────────────────────────
#  4. UNREALIZED P&L
# ─────────────────────────────────────────────────────────────────────────────

def calculate_unrealized_pnl(holdings_df: pd.DataFrame) -> pd.DataFrame:
    """
    Unrealized P&L = (Live Price - Avg Cost) × Open Qty
    Unrealized P&L % = Unrealized P&L / Cost Value × 100
    Current Value = Live Price × Open Qty
    """
    df = holdings_df.copy()

    df["Current Value"]      = df["Live Price"] * df["Open Qty"]
    df["Unrealized P&L"]     = (df["Current Value"]) - (df["Avg Cost"] * df["Open Qty"])
    df["Unrealized P&L %"] = (df["Unrealized P&L"] / df["Cost Value"] * 100).round(2)
    df["Current Value"]      = df["Current Value"].round(2)
    df["Unrealized P&L"]     = df["Unrealized P&L"].round(2)

    return df


# ─────────────────────────────────────────────────────────────────────────────
#  5. PORTFOLIO WEIGHTS
# ─────────────────────────────────────────────────────────────────────────────

def calculate_weights(holdings_df: pd.DataFrame) -> pd.DataFrame:
    """
    Weight is based on CURRENT VALUE (Live Price × Open Qty).
    Falls back to Cost Value where Live Price is unavailable.
    """
    df = holdings_df.copy()

    df["Value for Weight"] = df["Current Value"].fillna(df["Cost Value"])

    total_portfolio_value = df["Value for Weight"].sum()

    if total_portfolio_value > 0:
        df["Weight"]   = df["Value for Weight"] / total_portfolio_value
    else:
        df["Weight"]   = 0.0

    df["Weight %"] = (df["Weight"] * 100).round(2)
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  6. ENS 
# ─────────────────────────────────────────────────────────────────────────────

def calculate_ens(df: pd.DataFrame) -> float:
    """Effective Number of Stocks = 1 / Σ(w²)"""
    if "Weight %" not in df.columns:
        raise ValueError("Weight % column not found.")

    weights = int(df["Weight %"] / 100)
    weights = int(weights[weights > 0])

    if len(weights) == 0:
        return 0

    ens = 1 / (weights ** 2).sum()
    return int(ens)


# ─────────────────────────────────────────────────────────────────────────────
#  7. CORE – SATELLITE – TAIL
# ─────────────────────────────────────────────────────────────────────────────

def calculate_core_satellite_tail(df: pd.DataFrame) -> dict:
    """
    Core      : Weight % ≥ 5
    Satellite : 1 ≤ Weight % < 5
    Tail      : Weight % < 1
    """
    if "Weight %" not in df.columns:
        raise ValueError("Weight % column not found.")

    core      = df[df["Weight %"] >= CORE_THRESHOLD]
    satellite = df[(df["Weight %"] >= SATELLITE_THRESHOLD) & (df["Weight %"] < CORE_THRESHOLD)]
    tail      = df[df["Weight %"] < SATELLITE_THRESHOLD]


    return {
        "Core Allocation %"      : round(core["Weight %"].sum(),      2),
        "Satellite Allocation %"  : round(satellite["Weight %"].sum(), 2),
        "Tail Allocation %"       : round(tail["Weight %"].sum(),      2),
        "Core Count"             : len(core),
        "Satellite Count"        : len(satellite),
        "Tail Count"             : len(tail),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  8. SECTOR FETCH
# ─────────────────────────────────────────────────────────────────────────────

def fetch_sectors(holdings_df: pd.DataFrame) -> pd.DataFrame:
    """
    Fetch sector from yfinance .info for each unique ticker.
    Automatically resolves tickers for scrips not in TICKER_MAP.
    """
    from ticker_resolver import fetch_sector_cap_with_autoresolve

    df = holdings_df.copy()
    scrip_names = df["Scrip Name"].tolist()

    meta = fetch_sector_cap_with_autoresolve(scrip_names, TICKER_MAP)
    df["Sector"] = df["Scrip Name"].map(lambda s: meta.get(s, {}).get("sector", "Unknown"))
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  9. MARKET CAP FETCH & CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def get_market_cap(holdings_df: pd.DataFrame) -> pd.DataFrame:
    """
    Fetch market cap from yfinance (returned in INR for .NS / .BO tickers).
    Convert to crores ( ÷ 1e7 ).
    Automatically resolves tickers for scrips not in TICKER_MAP.
    """
    from ticker_resolver import fetch_sector_cap_with_autoresolve

    df = holdings_df.copy()
    scrip_names = df["Scrip Name"].tolist()

    meta = fetch_sector_cap_with_autoresolve(scrip_names, TICKER_MAP)
    df["Market Cap (Cr)"] = df["Scrip Name"].map(
        lambda s: meta.get(s, {}).get("market_cap_cr", None)
    )
    return df


def market_cap_category(holdings_df: pd.DataFrame):
    """
    Classify into Large / Mid / Small / Micro Cap using SEBI thresholds (INR Cr).
    Returns updated df and a summary dict of Weight % per category.
    """
    if "Market Cap (Cr)" not in holdings_df.columns:
        raise ValueError("Market Cap (Cr) column not found.")

    def classify(mcap):
        if pd.isna(mcap):
            return "Unknown"
        elif mcap >= LARGE_CAP_THRESHOLD:
            return "Large Cap"
        elif mcap >= MID_CAP_THRESHOLD:
            return "Mid Cap"
        elif mcap >= SMALL_CAP_THRESHOLD:
            return "Small Cap"
        else:
            return "Micro Cap"

    df = holdings_df.copy()
    df["Cap Category"] = df["Market Cap (Cr)"].apply(classify)

    summary = (
        df.groupby("Cap Category")["Weight %"]
        .sum()
        .round(2)
        .to_dict()
    )
    return df, summary


# ─────────────────────────────────────────────────────────────────────────────
#  10. INDEX / DERIVATIVE P&L
#      Amount column is SIGNED (negative = outflow/buy, positive = inflow/sell)
#      P&L per scrip = sum of all signed amounts
# ─────────────────────────────────────────────────────────────────────────────

def calculate_index_pnl(index_df: pd.DataFrame) -> pd.DataFrame:
    """
    For index/derivative trades:
        P&L = Σ(Amount)   [Amount is signed: buys are negative, sells positive]

    Returns a DataFrame with one row per scrip showing:
        Total Buy Amount, Total Sell Amount, Net P&L
    """
    if index_df.empty:
        return pd.DataFrame(columns=[
            "Scrip Name", "Buy Amount", "Sell Amount", "Net P&L"
        ])

    df = index_df.copy()

    buy_amt  = df[df["Action"] == "BUY"].groupby("Scrip Name")["Amount"].sum().rename("Buy Amount")
    sell_amt = df[df["Action"] == "SELL"].groupby("Scrip Name")["Amount"].sum().rename("Sell Amount")
    net_pnl  = df.groupby("Scrip Name")["Amount"].sum().rename("Net P&L")

    result = pd.concat([buy_amt, sell_amt, net_pnl], axis=1).fillna(0).reset_index()
    result["Buy Amount"]  = result["Buy Amount"].round(2)
    result["Sell Amount"] = result["Sell Amount"].round(2)
    result["Net P&L"]     = result["Net P&L"].round(2)

    return result


# ─────────────────────────────────────────────────────────────────────────────
#  11. PORTFOLIO SUMMARY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def portfolio_summary(holdings_df: pd.DataFrame, realized_df: pd.DataFrame) -> dict:
    """High-level portfolio summary statistics."""
    total_cost_value     = holdings_df["Cost Value"].sum()
    total_current_value  = holdings_df["Current Value"].fillna(holdings_df["Cost Value"]).sum()
    total_unrealized     = holdings_df["Unrealized P&L"].fillna(0).sum()
    total_realized       = realized_df["Realized P&L"].sum() if not realized_df.empty else 0.0
    total_pnl            = total_realized + total_unrealized
    unrealized_pct       = (total_unrealized / total_cost_value * 100) if total_cost_value else 0

    return {
        "Total Cost Value (₹)"        : round(total_cost_value,    2),
        "Total Current Value (₹)"     : round(total_current_value, 2),
        "Total Unrealized P&L (₹)"    : round(total_unrealized,    2),
        "Total Unrealized P&L %"      : round(unrealized_pct,      2),
        "Total Realized P&L (₹)"      : round(total_realized,      2),
        "Total P&L (Realized + Unreal)": round(total_pnl,          2),
        "Number of Open Positions"    : len(holdings_df),
    }
''

def sector_allocation(holdings_df: pd.DataFrame) -> dict:
    """Weight % grouped by Sector."""
    if "Sector" not in holdings_df.columns:
        return {}
    return (
        holdings_df.groupby("Sector")["Weight %"]
        .sum()
        .round(2)
        .sort_values(ascending=False)
        .to_dict()
    )


# ─────────────────────────────────────────────────────────────────────────────
#  12. DISPLAY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _divider(char="─", width=90):
    print(char * width)

def _section(title: str):
    _divider("═")
    print(f"  {title}")
    _divider("═")

def _sub_section(title: str):
    _divider()
    print(f"  {title}")
    _divider()

def print_dataframe(df: pd.DataFrame, float_fmt="{:.2f}"):
    """Pretty-print a DataFrame with consistent float formatting."""
    formatted = df.copy()
    for col in formatted.select_dtypes(include=[float, np.floating]).columns:
        formatted[col] = formatted[col].map(lambda x: float_fmt.format(x) if pd.notna(x) else "N/A")
    print(formatted.to_string(index=False))


def display_holdings(holdings_df: pd.DataFrame):
    _sub_section("OPEN EQUITY HOLDINGS — WEIGHTS, P&L & LIVE PRICES")
    cols = [
        "Scrip Name", "Open Qty", "Avg Cost", "Live Price",
        "Cost Value", "Current Value",
        "Unrealized P&L", "Unrealized P&L %",
        "Realized P&L", "Weight %",
        "Sector", "Cap Category",
    ]
    available = [c for c in cols if c in holdings_df.columns]
    print_dataframe(holdings_df[available])


def display_realized(realized_df: pd.DataFrame):
    _sub_section("REALIZED P&L — FIFO TRADE-BY-TRADE DETAIL")
    if realized_df.empty:
        print("  No realized trades found.")
        return
    cols = ["Scrip Name", "Date", "Sell Qty", "Sell Price",
            "Sell Proceeds", "Cost of Sold", "Realized P&L"]
    print_dataframe(realized_df[cols])


def display_index_pnl(index_pnl_df: pd.DataFrame):
    _sub_section("INDEX / DERIVATIVE P&L  (Signed Amount Method)")
    if index_pnl_df.empty:
        print("  No index/derivative trades found.")
        return
    print_dataframe(index_pnl_df)


def display_summary(summary: dict, title="PORTFOLIO SUMMARY"):
    _sub_section(title)
    for k, v in summary.items():
        print(f"  {k:<40} : {v:>15,.2f}" if isinstance(v, float)
              else f"  {k:<40} : {v:>15}")


def display_dict(d: dict, title=""):
    if title:
        _sub_section(title)
    for k, v in d.items():
        print(f"  {k:<35} : {v}")



def main():
    _section("PORTFOLIO ANALYSIS ")

    # ── Load & preprocess ──────────────────────────────────────────────────
    print("\n[1/9]  Loading trade data ...")
    df, client_info, skip_used = load_data(UPLOADED_FILE)
    df = preprocess_data(df)
    print(f"       {len(df)} trade records loaded.")
    print(f"       Client   : {client_info.get('client_name', 'N/A')}")
    print(f"       ClientID : {client_info.get('client_id',   'N/A')}")
    print(f"       Period   : {client_info.get('date_range',  'N/A')}")
    print(f"       Rows skipped (auto-detected): {skip_used}")

    # ── Split equity vs index/derivatives ─────────────────────────────────
    print("[2/9]  Separating equity from index/derivative trades ...")
    equity_df, index_df = separate_index_equity(df)
    print(f"       Equity trades   : {len(equity_df)}")
    print(f"       Index/Deriv     : {len(index_df)}")

    # ── FIFO engine ───────────────────────────────────────────────────────
    print("[3/9]  Running FIFO engine ...")
    holdings_df, realized_df = calculate_equity_positions(equity_df)
    print(f"       Open positions  : {len(holdings_df)}")
    print(f"       Realized trades : {len(realized_df)}")

    # ── Live prices ───────────────────────────────────────────────────────
    print("[4/9]  Fetching live prices from yfinance ...")
    holdings_df = fetch_live_prices(holdings_df)
    fetched = holdings_df["Live Price"].notna().sum()
    print(f"       Live prices fetched for {fetched}/{len(holdings_df)} positions.")

    # ── Unrealized P&L ────────────────────────────────────────────────────
    print("[5/9]  Computing unrealized P&L ...")
    holdings_df = calculate_unrealized_pnl(holdings_df)

    # ── Weights ───────────────────────────────────────────────────────────
    print("[6/9]  Calculating portfolio weights ...")
    holdings_df = calculate_weights(holdings_df)

    # ── Sector & Market Cap ───────────────────────────────────────────────
    print("[7/9]  Fetching sectors & market cap data ...")
    holdings_df = fetch_sectors(holdings_df)
    holdings_df = get_market_cap(holdings_df)
    holdings_df, cap_summary = market_cap_category(holdings_df)

    # ── Index P&L ─────────────────────────────────────────────────────────
    print("[8/9]  Computing index/derivative P&L ...")
    index_pnl_df = calculate_index_pnl(index_df)

    # ── Summary metrics ───────────────────────────────────────────────────
    print("[9/9]  Computing summary metrics ...")
    summary   = portfolio_summary(holdings_df, realized_df)
    ens       = calculate_ens(holdings_df)
    allocation= calculate_core_satellite_tail(holdings_df)
    sector_wt = sector_allocation(holdings_df)

    # ─────────────────────────────────────────────────────────────────────
    #  OUTPUT
    # ─────────────────────────────────────────────────────────────────────
    print("\n\n")
    _section("RESULTS")

    # 1. Holdings table
    display_holdings(holdings_df)

    # 2. Realized P&L detail
    display_realized(realized_df)

    # 3. Index / Derivative P&L
    display_index_pnl(index_pnl_df)

    # 4. Portfolio summary
    display_summary(summary)

    # 5. ENS
    _sub_section("EFFECTIVE NUMBER OF STOCKS  (ENS = 1 / Σw²)")
    print(f"  ENS  :  {int(ens)}")
    print(f"  Interpretation: Portfolio behaves like ~{int(ens)} equally-weighted stocks.")

    # 6. Core – Satellite – Tail
    display_dict(allocation, title="CORE – SATELLITE – TAIL ALLOCATION")

    # 7. Sector breakdown
    display_dict(sector_wt,  title="SECTOR ALLOCATION  (Weight %)")

    # 8. Market Cap breakdown
    display_dict(cap_summary, title="MARKET CAP ALLOCATION  (Weight %)")

    _divider("═")
    print("  Analysis complete.")
    _divider("═")

    # ── Return all artefacts (useful when importing into Streamlit) ────────
    return {
        "holdings"      : holdings_df,
        "realized"      : realized_df,
        "index_pnl"     : index_pnl_df,
        "summary"       : summary,
        "ens"           : ens,
        "allocation"    : allocation,
        "sector_wt"     : sector_wt,
        "cap_summary"   : cap_summary,
        "client_info"   : client_info,
    }



if __name__ == "__main__":
    results = main()
