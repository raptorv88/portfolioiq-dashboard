"""
================================================================================
  ISIN MASTER  —  NSE equity master with ISIN-based lookup
  
  Downloads NSE's EQUITY_L.csv which contains:
    SYMBOL, NAME OF COMPANY, ISIN NUMBER
  
  Provides:
    - scrip_name → ISIN  (fuzzy matching)
    - ISIN → canonical name
    - ISIN → NSE ticker (.NS suffix)
    - ISIN → yfinance-ready ticker
  
  Auto-refreshes weekly. Falls back to cached version if NSE is unreachable.
================================================================================
"""

import os
import re
import json
import datetime
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import requests

_DIR          = os.path.dirname(os.path.abspath(__file__))
NSE_CSV_PATH  = os.path.join(_DIR, "nse_equity_master.csv")

NSE_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer"   : "https://www.nseindia.com/",
    "Accept"    : "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_master_df      : pd.DataFrame = None
_isin_to_symbol : dict         = {}
_isin_to_name   : dict         = {}
_name_to_isin   : dict         = {}
_symbol_to_isin : dict         = {}
_loaded         : bool         = False


def _download_nse_master() -> bool:
    try:
        r = requests.get(NSE_URL, headers=NSE_HEADERS, timeout=20)
        if r.status_code == 200 and len(r.text) > 1000:
            with open(NSE_CSV_PATH, "w", encoding="utf-8") as f:
                f.write(r.text)
            return True
    except Exception as e:
        print(f"[isin_master] Download failed: {e}")
    return False


def _needs_refresh() -> bool:
    if not os.path.exists(NSE_CSV_PATH):
        return True
    age = datetime.datetime.now() - datetime.datetime.fromtimestamp(
        os.path.getmtime(NSE_CSV_PATH)
    )
    return age.days >= 7


_STRIP = re.compile(
    r"\b(LIMITED|LTD\.?|PRIVATE|PVT\.?|CORPORATION|CORP\.?|"
    r"INDUSTRIES|ENTERPRISE|ENTERPRISES|COMPANY|CO\.?|"
    r"SERVICES|SOLUTIONS|TECHNOLOGIES|TECHNOLOGY|TECH\.?|"
    r"SYSTEMS|GROUP|FINANCE|FINANCIAL|BANK|"
    r"PHARMACEUTICALS|PHARMACEUTICAL|PHARMA|"
    r"INFRASTRUCTURE|INFRA|DEVELOPERS|DEVELOPER|"
    r"HOLDINGS|HOLDING|INVESTMENTS|INVESTMENT|"
    r"MANAGEMENT|MANAGMT|ASSET|INDIA|INDIAN|"
    r"INTERNATIONAL|INTL\.?|NATIONAL|NAT\.?|"
    r"ENGINEERING|ENGG\.?|ENG\.?)\b",
    re.IGNORECASE
)

_SPECIAL = re.compile(r"[&\(\)\[\]\-\.,/\\\\]")
_SPACES  = re.compile(r"\s+")


def _norm(name: str) -> str:
    s = str(name).strip().upper()
    s = _SPECIAL.sub(" ", s)
    s = _STRIP.sub(" ", s)
    s = _SPACES.sub(" ", s).strip()
    # Remove single-character tokens left after stripping
    tokens = [t for t in s.split() if len(t) > 1]
    return " ".join(tokens)


def _load() -> None:
    global _master_df, _isin_to_symbol, _isin_to_name
    global _name_to_isin, _symbol_to_isin, _loaded

    if _loaded:
        return

    if _needs_refresh():
        _download_nse_master()

    if not os.path.exists(NSE_CSV_PATH):
        print("[isin_master] Master file not available — ISIN lookup disabled")
        _loaded = True
        return

    try:
        df = pd.read_csv(NSE_CSV_PATH)
        df.columns = df.columns.str.strip()

        if "SERIES" in df.columns:
            df = df[df["SERIES"].str.strip() == "EQ"]

        sym_col  = "SYMBOL"
        name_col = "NAME OF COMPANY"
        isin_col = "ISIN NUMBER"

        if not all(c in df.columns for c in [sym_col, name_col, isin_col]):
            print(f"[isin_master] Unexpected columns: {list(df.columns)}")
            _loaded = True
            return

        df[sym_col]  = df[sym_col].astype(str).str.strip()
        df[name_col] = df[name_col].astype(str).str.strip()
        df[isin_col] = df[isin_col].astype(str).str.strip()

        df = df[df[isin_col].str.match(r"^[A-Z]{2}[A-Z0-9]{10}$")]

        _master_df = df

        for _, row in df.iterrows():
            isin   = row[isin_col]
            symbol = row[sym_col]
            name   = row[name_col]
            normed = _norm(name)

            _isin_to_symbol[isin]   = symbol
            _isin_to_name[isin]     = name
            _name_to_isin[normed]   = isin
            _symbol_to_isin[symbol] = isin

        print(f"[isin_master] Loaded {len(df)} NSE equity records")
        _loaded = True

    except Exception as e:
        print(f"[isin_master] Load error: {e}")
        _loaded = True


def get_isin(scrip_name: str) -> str | None:
    """
    Look up ISIN for a scrip name.
    
    Strategy (in order of confidence):
      1. Direct NSE symbol match  (e.g. RELIANCE, ANANTRAJ)
      2. Exact normalised name match
      3. Starts-with match — 16+ char prefix, both names >= 10 chars
         (handles broker truncations like "GARDEN REACH SHIP&ENG LTD")
      4. Word overlap — majority of query words must appear in NSE name
         (min overlap = max(2, half of query word count))
    """
    _load()
    if not _name_to_isin:
        return None

    upper = scrip_name.strip().upper().rstrip(".")
    # Remove trailing LTD/LIMITED/LT for symbol check
    sym_clean = re.sub(r"\s+(LIMITED|LTD\.?|LT)$", "", upper).strip()
    # Direct symbol check
    if upper in _symbol_to_isin:
        return _symbol_to_isin[upper]
    if sym_clean in _symbol_to_isin:
        return _symbol_to_isin[sym_clean]

    normed = _norm(scrip_name)

    # 1. Exact normalised match
    if normed in _name_to_isin:
        return _name_to_isin[normed]

    # 2. Starts-with match — minimum 16 chars to avoid false positives
    if len(normed) >= 10:
        prefix = normed[:min(len(normed), 16)]
        for key, isin in _name_to_isin.items():
            if len(key) >= 10 and key.startswith(prefix):
                return isin
            if len(key) >= 10 and normed.startswith(key[:min(len(key), 16)]):
                return isin

    # 3. Word overlap — require majority of query words to match
    scrip_words = set(w for w in normed.split() if len(w) > 2)
    if len(scrip_words) >= 2:
        best_isin  = None
        best_score = 0
        # Need at least half the significant query words to match
        min_overlap = max(2, len(scrip_words) - 1)
        for key, isin in _name_to_isin.items():
            key_words = set(w for w in key.split() if len(w) > 2)
            overlap   = len(scrip_words & key_words)
            if overlap >= min_overlap and overlap > best_score:
                best_score = overlap
                best_isin  = isin
        if best_isin:
            return best_isin

    return None


def get_ticker(isin: str) -> str | None:
    _load()
    symbol = _isin_to_symbol.get(isin)
    return f"{symbol}.NS" if symbol else None


def get_canonical_name(isin: str) -> str | None:
    _load()
    return _isin_to_name.get(isin)


def get_isin_from_ticker(ticker: str) -> str | None:
    _load()
    sym = ticker.replace(".NS", "").replace(".BO", "").upper()
    return _symbol_to_isin.get(sym)


def resolve_scrip(scrip_name: str) -> dict:
    isin = get_isin(scrip_name)
    if isin:
        return {
            "isin"           : isin,
            "canonical_name" : get_canonical_name(isin),
            "ticker"         : get_ticker(isin),
            "matched"        : True,
        }
    return {"isin": None, "canonical_name": None, "ticker": None, "matched": False}


def resolve_all(scrip_names: list) -> dict:
    _load()
    return {name: resolve_scrip(name) for name in scrip_names}


def get_master_df() -> pd.DataFrame:
    _load()
    return _master_df if _master_df is not None else pd.DataFrame()


def refresh_master() -> bool:
    global _master_df, _isin_to_symbol, _isin_to_name
    global _name_to_isin, _symbol_to_isin, _loaded
    _master_df = None; _isin_to_symbol = {}; _isin_to_name = {}
    _name_to_isin = {}; _symbol_to_isin = {}; _loaded = False
    if os.path.exists(NSE_CSV_PATH):
        os.remove(NSE_CSV_PATH)
    _load()
    return len(_isin_to_symbol) > 0


def stats() -> dict:
    _load()
    return {
        "loaded"        : _loaded,
        "total_records" : len(_isin_to_symbol),
        "file_exists"   : os.path.exists(NSE_CSV_PATH),
        "file_age_days" : (
            (datetime.datetime.now() - datetime.datetime.fromtimestamp(
                os.path.getmtime(NSE_CSV_PATH)
            )).days if os.path.exists(NSE_CSV_PATH) else None
        ),
    }
