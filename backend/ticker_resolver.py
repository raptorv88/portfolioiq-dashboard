"""
================================================================================
  TICKER RESOLVER  —  NSE/BSE auto-resolution for Indian stocks
  
  Strategy (in order):
  1. Static overrides (_EXTRA_OVERRIDES) — hardcoded known mappings
  2. Persistent cache (ticker_cache.json) — previously resolved
  3. NSE symbols master file (EQUITY_L.csv) — fuzzy name matching
  4. yfinance pattern-based guessing + verification
  5. yfinance Search API fallback
  
  The NSE master file is downloaded once and refreshed weekly automatically.
  This gives near-100% resolution for any Indian stock.
================================================================================
"""

import json
import os
import re
import warnings
import datetime
warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd
import requests

CACHE_FILE      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticker_cache.json")
NSE_MASTER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nse_symbols_master.csv")

# Refresh NSE master weekly
NSE_MASTER_URL  = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_MASTER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nseindia.com/",
}

# ─────────────────────────────────────────────────────────────────────────────
#  STATIC OVERRIDES — well-known mappings that are hard to auto-resolve
# ─────────────────────────────────────────────────────────────────────────────

_EXTRA_OVERRIDES = {
    # Banks
    "AXIS BANK LIMITED"                  : "AXISBANK.NS",
    "AXIS BANK"                          : "AXISBANK.NS",
    "KOTAK MAHINDRA BANK"                : "KOTAKBANK.NS",
    "KOTAK BANK"                         : "KOTAKBANK.NS",
    "YES BANK"                           : "YESBANK.NS",
    "FEDERAL BANK"                       : "FEDERALBN.NS",
    "INDUSIND BANK"                      : "INDUSINDBK.NS",
    "BANK OF INDIA"                      : "BANKINDIA.NS",
    "IDFC FIRST BANK LIMITED"            : "IDFCFIRSTB.NS",
    "IDFC FIRST BANK"                    : "IDFCFIRSTB.NS",
    "AU SMALL FINANCE BANK"              : "AUBANK.NS",
    "UJJIVAN SMALL FINANCE BANK"         : "UJJIVANSFB.NS",
    "UJJIVAN SMALL FINANC BANK"          : "UJJIVANSFB.NS",
    "UJJIVAN SMALL FINANCE BANK LIM"     : "UJJIVANSFB.NS",
    "RBL BANK"                           : "RBLBANK.NS",
    "BANDHAN BANK"                       : "BANDHANBNK.NS",
    "CSB BANK"                           : "CSBBANK.NS",
    "KARUR VYSYA BANK"                   : "KARURVYSYA.NS",
    "CITY UNION BANK"                    : "CUB.NS",
    "DCB BANK"                           : "DCBBANK.NS",
    "SOUTH INDIAN BANK"                  : "SOUTHBANK.NS",
    # Telecom
    "BHARTI AIRTEL LIMITED"              : "BHARTIARTL.NS",
    "BHARTI AIRTEL LTD."                 : "BHARTIARTL.NS",
    "BHARTI AIRTEL LTD"                  : "BHARTIARTL.NS",
    "BHARTI AIRTEL"                      : "BHARTIARTL.NS",
    "AIRTEL"                             : "BHARTIARTL.NS",
    "VODAFONE IDEA"                      : "IDEA.NS",
    "INDUS TOWERS"                       : "INDUSTOWER.NS",
    "TATA COMMUNICATIONS"                : "TATACOMM.NS",
    # IT
    "INFOSYS"                            : "INFY.NS",
    "WIPRO LTD."                         : "WIPRO.NS",
    "WIPRO"                              : "WIPRO.NS",
    "HCL TECHNOLOGIES"                   : "HCLTECH.NS",
    "TECH MAHINDRA"                      : "TECHM.NS",
    "MPHASIS"                            : "MPHASIS.NS",
    "PERSISTENT SYSTEMS"                 : "PERSISTENT.NS",
    "COFORGE"                            : "COFORGE.NS",
    "LTIMINDTREE"                        : "LTIM.NS",
    "BIRLASOFT LIMITED"                  : "BSOFT.NS",
    "BIRLASOFT"                          : "BSOFT.NS",
    "KPIT TECHNOLOGIES"                  : "KPITTECH.NS",
    "ORACLE FINANCIAL SERVICES"          : "OFSS.NS",
    "KALYANI INVEST CO LTD"              : "KICL.NS",
    # FMCG
    "HINDUSTAN UNILEVER"                 : "HINDUNILVR.NS",
    "ITC"                                : "ITC.NS",
    "NESTLE INDIA"                       : "NESTLEIND.NS",
    "BRITANNIA INDUSTRIES"               : "BRITANNIA.NS",
    "MARICO"                             : "MARICO.NS",
    "DABUR INDIA"                        : "DABUR.NS",
    "COLGATE PALMOLIVE"                  : "COLPAL.NS",
    "GODREJ CONSUMER PRODUCTS"           : "GODREJCP.NS",
    "VARUN BEVERAGES"                    : "VBL.NS",
    "TATA CONSUMER PRODUCTS"             : "TATACONSUM.NS",
    # Auto
    "MARUTI SUZUKI"                      : "MARUTI.NS",
    "MAHINDRA & MAHINDRA"                : "M&M.NS",
    "EICHER MOTORS"                      : "EICHERMOT.NS",
    "BAJAJ AUTO"                         : "BAJAJ-AUTO.NS",
    "TVS MOTOR COMPANY"                  : "TVSMOTOR.NS",
    "TVS MOTOR"                          : "TVSMOTOR.NS",
    "ASHOK LEYLAND"                      : "ASHOKLEY.NS",
    "BOSCH"                              : "BOSCHLTD.NS",
    "SAMVARDHANA MOTHERSON"              : "MOTHERSON.NS",
    "BALKRISHNA INDUSTRIES"              : "BALKRISIND.NS",
    "APOLLO TYRES"                       : "APOLLOTYRE.NS",
    "MRF"                                : "MRF.NS",
    # Pharma
    "SUN PHARMACEUTICAL"                 : "SUNPHARMA.NS",
    "SUN PHARMA"                         : "SUNPHARMA.NS",
    "DR REDDYS LABORATORIES"             : "DRREDDY.NS",
    "CIPLA"                              : "CIPLA.NS",
    "LUPIN"                              : "LUPIN.NS",
    "AUROBINDO PHARMA"                   : "AUROPHARMA.NS",
    "DIVI'S LABORATORIES"                : "DIVISLAB.NS",
    "DIVIS LABORATORIES"                 : "DIVISLAB.NS",
    "DIVI S LABORATORIES LTD"            : "DIVISLAB.NS",
    "TORRENT PHARMACEUTICALS"            : "TORNTPHARM.NS",
    "ALKEM LABORATORIES"                 : "ALKEM.NS",
    "IPCA LABORATORIES"                  : "IPCALAB.NS",
    "NATCO PHARMA"                       : "NATCOPHARM.NS",
    "ABBOTT INDIA"                       : "ABBOTINDIA.NS",
    # Energy / Power
    "POWER GRID CORPORATION"             : "POWERGRID.NS",
    "TATA POWER"                         : "TATAPOWER.NS",
    "ADANI POWER"                        : "ADANIPOWER.NS",
    "ADANI GREEN ENERGY"                 : "ADANIGREEN.NS",
    "JSW ENERGY"                         : "JSWENERGY.NS",
    "JSW ENERGY LTD"                     : "JSWENERGY.NS",
    "NTPC LTD"                           : "NTPC.NS",
    "NTPC LTD."                          : "NTPC.NS",
    "NTPC"                               : "NTPC.NS",
    "NHPC LTD"                           : "NHPC.NS",
    "NHPC LTD."                          : "NHPC.NS",
    "SJVN LTD"                           : "SJVN.NS",
    # Metals
    "HINDALCO INDUSTRIES"                : "HINDALCO.NS",
    "HINDALCO"                           : "HINDALCO.NS",
    "VEDANTA"                            : "VEDL.NS",
    "JINDAL STEEL AND POWER"             : "JINDALSTEL.NS",
    "JSW STEEL"                          : "JSWSTEEL.NS",
    "SAIL"                               : "SAIL.NS",
    "TATA STEEL LTD"                     : "TATASTEEL.NS",
    "TATA STEEL LTD."                    : "TATASTEEL.NS",
    # Infrastructure
    "LARSEN & TOUBRO LTD."               : "LT.NS",
    "LARSEN AND TOUBRO"                  : "LT.NS",
    "L&T"                                : "LT.NS",
    "DLF"                                : "DLF.NS",
    "GODREJ PROPERTIES"                  : "GODREJPROP.NS",
    "PRESTIGE ESTATES"                   : "PRESTIGE.NS",
    "OBEROI REALTY"                      : "OBEROIRLTY.NS",
    # Financial Services
    "HDFC LIFE INSURANCE"                : "HDFCLIFE.NS",
    "SBI LIFE INSURANCE"                 : "SBILIFE.NS",
    "ICICI PRUDENTIAL LIFE INSURANC"     : "ICICIPRULI.NS",
    "ICICI PRU LIFE INS CO LTD"          : "ICICIPRULI.NS",
    "ICICI LOMBARD"                      : "ICICIGI.NS",
    "MUTHOOT FINANCE"                    : "MUTHOOTFIN.NS",
    "BAJAJ FINSERV"                      : "BAJAJFINSV.NS",
    "BAJAJ FINSERV LTD."                 : "BAJAJFINSV.NS",
    "HDFC AMC"                           : "HDFCAMC.NS",
    "ANGEL ONE"                          : "ANGELONE.NS",
    "MOTILAL OSWAL"                      : "MOTILALOFS.NS",
    "KALYAN JEWELLERS INDIA LIMITED"     : "KALYANKJIL.NS",
    "KALYAN JEWELLERS IND LTD"           : "KALYANKJIL.NS",
    "HDB FINANCIAL SERVICES LIMITED"     : "HDBFS.NS",
    # Defence / PSU
    "GARDEN REACH SHIPBUILDERS & EN"     : "GRSE.NS",
    "GARDEN REACH SHIP&ENG LTD"         : "GRSE.NS",
    "GRSE"                               : "GRSE.NS",
    "HINDUSTAN CONSTRUCTION CO.LTD."     : "HCC.NS",
    # Consumer
    "TITAN COMPANY LIMITED"              : "TITAN.NS",
    "TITAN COMPANY"                      : "TITAN.NS",
    "TITAN"                              : "TITAN.NS",
    "TRENT"                              : "TRENT.NS",
    "PAGE INDUSTRIES"                    : "PAGEIND.NS",
    "BATA INDIA"                         : "BATAINDIA.NS",
    # Cement
    "ULTRATECH CEMENT"                   : "ULTRACEMCO.NS",
    "AMBUJA CEMENTS"                     : "AMBUJACEM.NS",
    "DALMIA BHARAT"                      : "DALBHARAT.NS",
    # Others
    "POLYCAB INDIA LIMITED"              : "POLYCAB.NS",
    "POLYCAB INDIA"                      : "POLYCAB.NS",
    "POLYCAB"                            : "POLYCAB.NS",
    "STATE BANK OF INDIA"                : "SBIN.NS",
    "SBI"                                : "SBIN.NS",
    "COAL INDIA LTD."                    : "COALINDIA.NS",
    "COAL INDIA"                         : "COALINDIA.NS",
    "HERO MOTOCORP LIMITED"              : "HEROMOTOCO.NS",
    "HERO MOTOCORP LTD"                  : "HEROMOTOCO.NS",
    "HERO MOTOCORP"                      : "HEROMOTOCO.NS",
    "BAJAJ HOUSING FINANCE LIMITED"      : "BAJAJHFL.NS",
    "BAJAJ HOUSING FINANCE"              : "BAJAJHFL.NS",
    "HDFC BANK LTD"                      : "HDFCBANK.NS",
    "HDFC BANK LTD."                     : "HDFCBANK.NS",
    "HDFC BANK"                          : "HDFCBANK.NS",
    "ICICI BANK LTD"                     : "ICICIBANK.NS",
    "ICICI BANK LTD."                    : "ICICIBANK.NS",
    "ICICI BANK"                         : "ICICIBANK.NS",
    "RELIANCE INDUSTRIES LTD."           : "RELIANCE.NS",
    "RELIANCE INDUSTRIES LTD"            : "RELIANCE.NS",
    "RELIANCE INDUSTRIES"                : "RELIANCE.NS",
    "TATA MOTORS LTD."                   : "TATAMOTORS.NS",
    "TATA MOTORS LIMITED"                : "TATAMOTORS.NS",
    "TATA MOTORS"                        : "TATAMOTORS.NS",
    "ADANI ENTERPRISES"                  : "ADANIENT.NS",
    "ADANI PORTS"                        : "ADANIPORTS.NS",
    "BAJAJ FINANCE LIMITED"              : "BAJFINANCE.NS",
    "BAJAJ FINANCE"                      : "BAJFINANCE.NS",
    "SHRIRAM FINANCE LIMITED"            : "SHRIRAMFIN.NS",
    "SHRIRAMFIN"                         : "SHRIRAMFIN.NS",
    "NUVAMA WEALTH MANAGEMENT LIMIT"     : "NUVAMA.NS",
    "NUVAMA WEALTH MANAGE LTD"           : "NUVAMA.NS",
    "MAX HEALTHCARE INSTITUTE LIMIT"     : "MAXHEALTH.NS",
    "MAX HEALTHCARE INS LTD"             : "MAXHEALTH.NS",
    "MAXHEALTH"                          : "MAXHEALTH.NS",
    "CRAFTSMAN AUTOMATION LIMITED"       : "CRAFTSMAN.NS",
    "CRAFTSMAN AUTOMATION LTD"           : "CRAFTSMAN.NS",
    "CMS INFO SYSTEMS LIMITED"           : "CMSINFO.NS",
    "GARWARE HI-TECH FILMS LIMITED"      : "GARFIBRES.NS",
    "GARWARE HI-TECH FILMS LTD"         : "GARFIBRES.NS",
    "RAYMOND LTD."                       : "RAYMOND.NS",
    "RAYMOND LIFESTYLE LIMITED"          : "RAYMONDLSL.NS",
    "PILANI INV & IND COR LTD"           : "PILANIENT.NS",
    "KALYANI INVEST CO LTD"              : "KALYANIINV.NS",
    "PEL"                                : "PEL.NS",
    "PIRAMAL ENTERPRISES LTD."           : "PEL.NS",
    "PIRAMAL ENTERPRISES LIMITED"        : "PEL.NS",
}

# ─────────────────────────────────────────────────────────────────────────────
#  NSE MASTER FILE
# ─────────────────────────────────────────────────────────────────────────────

_NSE_MASTER: pd.DataFrame = None   # loaded lazily


def _download_nse_master():
    """Download NSE equity master CSV and save locally."""
    try:
        r = requests.get(NSE_MASTER_URL, headers=NSE_MASTER_HEADERS, timeout=15)
        if r.status_code == 200:
            with open(NSE_MASTER_FILE, "w", encoding="utf-8") as f:
                f.write(r.text)
            return True
    except Exception:
        pass
    return False


def _load_nse_master() -> pd.DataFrame:
    """Load NSE master file, downloading if needed or stale (>7 days)."""
    global _NSE_MASTER
    if _NSE_MASTER is not None:
        return _NSE_MASTER

    # Check if local file is fresh (< 7 days old)
    needs_download = True
    if os.path.exists(NSE_MASTER_FILE):
        age = datetime.datetime.now() - datetime.datetime.fromtimestamp(
            os.path.getmtime(NSE_MASTER_FILE)
        )
        if age.days < 7:
            needs_download = False

    if needs_download:
        _download_nse_master()

    try:
        if os.path.exists(NSE_MASTER_FILE):
            df = pd.read_csv(NSE_MASTER_FILE)
            # NSE CSV columns: SYMBOL, NAME OF COMPANY, SERIES, ...
            # Keep only EQ series (equity, not derivatives)
            if "SERIES" in df.columns:
                df = df[df["SERIES"] == "EQ"]
            # Normalise company names
            name_col = "NAME OF COMPANY" if "NAME OF COMPANY" in df.columns else df.columns[1]
            sym_col  = "SYMBOL" if "SYMBOL" in df.columns else df.columns[0]
            df["_name_upper"] = df[name_col].astype(str).str.strip().str.upper()
            df["_ticker"]     = df[sym_col].astype(str).str.strip() + ".NS"
            _NSE_MASTER = df
            return df
    except Exception:
        pass
    return pd.DataFrame()


def _fuzzy_match_nse(scrip: str) -> str | None:
    """
    Try to match a scrip name against NSE master company names.
    Uses progressively looser matching.
    """
    df = _load_nse_master()
    if df.empty:
        return None

    scrip_upper = scrip.strip().upper()

    # 1. Exact match
    exact = df[df["_name_upper"] == scrip_upper]
    if not exact.empty:
        return exact.iloc[0]["_ticker"]

    # 2. Scrip name starts with NSE company name (truncated broker names)
    starts = df[df["_name_upper"].apply(lambda n: scrip_upper.startswith(n[:20]))]
    if not starts.empty:
        # Pick longest match
        best = starts.loc[starts["_name_upper"].str.len().idxmax()]
        return best["_ticker"]

    # 3. NSE company name starts with scrip name
    rev = df[df["_name_upper"].apply(lambda n: n.startswith(scrip_upper[:15]))]
    if not rev.empty:
        best = rev.loc[rev["_name_upper"].str.len().idxmin()]
        return best["_ticker"]

    # 4. Word-based matching — all first words match
    scrip_words = scrip_upper.split()[:3]
    if scrip_words:
        pattern = ".*".join(re.escape(w) for w in scrip_words[:2])
        word_match = df[df["_name_upper"].str.contains(pattern, regex=True, na=False)]
        if len(word_match) == 1:
            return word_match.iloc[0]["_ticker"]
        elif len(word_match) > 1:
            # Pick closest length
            word_match = word_match.copy()
            word_match["_len_diff"] = (word_match["_name_upper"].str.len() - len(scrip_upper)).abs()
            return word_match.loc[word_match["_len_diff"].idxmin()]["_ticker"]

    return None


# ─────────────────────────────────────────────────────────────────────────────
#  CACHE
# ─────────────────────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                data = json.load(f)
            # Remove stale __UNKNOWN__ entries so they get retried
            return {k: v for k, v in data.items() if v != "__UNKNOWN__"}
    except Exception:
        pass
    return {}


def _save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


_TICKER_CACHE: dict = _load_cache()


# ─────────────────────────────────────────────────────────────────────────────
#  TICKER VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def _verify_ticker(ticker: str) -> bool:
    try:
        data = yf.download(ticker, period="5d", interval="1d", progress=False, auto_adjust=True)
        return not data.empty and len(data) > 0
    except Exception:
        return False


def _get_info_safe(ticker: str) -> dict:
    try:
        t    = yf.Ticker(ticker)
        info = t.info
        if info.get("regularMarketPrice") or info.get("currentPrice") or info.get("marketCap"):
            return info
        fi = t.fast_info
        if hasattr(fi, "market_cap") and fi.market_cap:
            return {"sector": None, "marketCap": fi.market_cap}
    except Exception:
        pass
    return {}


# ─────────────────────────────────────────────────────────────────────────────
#  PATTERN-BASED GUESSER (fallback)
# ─────────────────────────────────────────────────────────────────────────────

_STRIP_WORDS = [
    r"\bLIMITED\b", r"\bLTD\.?\b", r"\bPVT\.?\b", r"\bPRIVATE\b",
    r"\bCORPORATION\b", r"\bCORP\.?\b", r"\bINDUSTRIES\b",
    r"\bENTERPRISES\b", r"\bCOMPANY\b", r"\bCO\.?\b",
    r"\bSERVICES\b", r"\bTECHNOLOGIES\b", r"\bTECHNOLOGY\b",
    r"\bSYSTEMS\b", r"\bGROUP\b", r"\bFINANCE\b", r"\bFINANCIAL\b",
    r"\bBANK\b", r"\bPHARMACEUTICALS\b", r"\bPHARMA\b",
    r"\bINFRASTRUCTURE\b", r"\bINFRA\b", r"\bDEVELOPERS\b",
    r"\bHOLDINGS\b", r"\bINVESTMENTS\b", r"\bMANAGEMENT\b",
]


def _clean_for_ticker(scrip: str) -> str:
    s = str(scrip).strip().upper()
    s = re.sub(r"[.,]+$", "", s)
    for pattern in _STRIP_WORDS:
        s = re.sub(pattern, "", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


def _candidate_tickers(scrip: str) -> list:
    bare    = _clean_for_ticker(scrip)
    compact = bare.replace(" ", "")
    words   = bare.split()
    first   = words[0] if words else bare

    candidates = [
        f"{compact}.NS", f"{compact}.BO",
        f"{first}.NS",   f"{first}.BO",
    ]
    if len(words) == 2:
        candidates += [f"{words[0]}{words[1]}.NS", f"{words[0]}{words[1]}.BO"]
    elif len(words) >= 3:
        candidates.append(f"{words[0]}{words[1]}.NS")
        abbr = "".join(w[0] for w in words if w)
        if len(abbr) >= 2:
            candidates.append(f"{abbr}.NS")

    seen, result = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


def _search_yfinance(scrip: str) -> str | None:
    try:
        results = yf.Search(scrip + " NSE India", max_results=5)
        quotes  = results.quotes
        if not quotes:
            return None
        for q in quotes:
            ticker   = q.get("symbol", "")
            exchange = q.get("exchange", "")
            if exchange in ("NSI", "BSE", "NSE") or ticker.endswith(".NS") or ticker.endswith(".BO"):
                return ticker
        return quotes[0].get("symbol")
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN RESOLVER
# ─────────────────────────────────────────────────────────────────────────────

def resolve_ticker(scrip: str, base_ticker_map: dict = None) -> str | None:
    """
    Resolve a scrip name to a yfinance ticker.
    Resolution order:
      1. base_ticker_map
      2. _EXTRA_OVERRIDES
      3. Persistent cache
      4. NSE master file fuzzy match  ← NEW primary method
      5. Pattern guessing + yfinance verify
      6. yfinance Search API
    """
    if base_ticker_map and scrip in base_ticker_map:
        t = base_ticker_map[scrip]
        return t if t != "__UNKNOWN__" else None

    if scrip in _EXTRA_OVERRIDES:
        return _EXTRA_OVERRIDES[scrip]

    if scrip in _TICKER_CACHE:
        return _TICKER_CACHE[scrip]

    # ── NSE master fuzzy match ────────────────────────────────────────────
    nse_ticker = _fuzzy_match_nse(scrip)
    if nse_ticker:
        _TICKER_CACHE[scrip] = nse_ticker
        _save_cache(_TICKER_CACHE)
        return nse_ticker

    # ── Pattern-based candidates ──────────────────────────────────────────
    for candidate in _candidate_tickers(scrip):
        if _verify_ticker(candidate):
            _TICKER_CACHE[scrip] = candidate
            _save_cache(_TICKER_CACHE)
            return candidate

    # ── yfinance search ───────────────────────────────────────────────────
    found = _search_yfinance(scrip)
    if found and _verify_ticker(found):
        _TICKER_CACHE[scrip] = found
        _save_cache(_TICKER_CACHE)
        return found

    # Don't cache failures — let them retry next time
    return None


def resolve_all_tickers(scrip_names: list, base_ticker_map: dict = None) -> dict:
    return {scrip: resolve_ticker(scrip, base_ticker_map) for scrip in scrip_names}


# ─────────────────────────────────────────────────────────────────────────────
#  SECTOR & CAP ENRICHMENT
# ─────────────────────────────────────────────────────────────────────────────

LARGE_CAP_THRESHOLD = 20_000
MID_CAP_THRESHOLD   =  5_000
SMALL_CAP_THRESHOLD =  1_000

_SECTOR_OVERRIDES = {
    "^NSEI"        : ("Index",     "Index/ETF"),
    "^NSEBANK"     : ("Index",     "Index/ETF"),
    "^BSESN"       : ("Index",     "Index/ETF"),
    "LIQUIDBETF.NS": ("ETF",       "Index/ETF"),
    "GOLDM-MCX.NS" : ("Commodity", "Commodity"),
}


def _classify_cap(mcap_cr) -> str:
    if mcap_cr is None:
        return "Unknown"
    try:
        m = float(mcap_cr)
        if m >= LARGE_CAP_THRESHOLD: return "Large Cap"
        if m >= MID_CAP_THRESHOLD:   return "Mid Cap"
        if m >= SMALL_CAP_THRESHOLD: return "Small Cap"
        return "Micro Cap"
    except Exception:
        return "Unknown"


def fetch_sector_cap_with_autoresolve(scrip_names: list, base_ticker_map: dict = None) -> dict:
    """Fetch sector and market-cap for a list of scrip names. Auto-resolves tickers."""

    # Step 1: resolve all tickers
    full_map = {}
    for scrip in scrip_names:
        if base_ticker_map and scrip in base_ticker_map:
            t = base_ticker_map[scrip]
            full_map[scrip] = (t if t != "__UNKNOWN__" else None, "static_map")
        elif scrip in _EXTRA_OVERRIDES:
            full_map[scrip] = (_EXTRA_OVERRIDES[scrip], "extra_override")
        elif scrip in _TICKER_CACHE:
            full_map[scrip] = (_TICKER_CACHE[scrip], "cache")
        else:
            ticker = resolve_ticker(scrip, base_ticker_map)
            full_map[scrip] = (ticker, "auto_resolved" if ticker else "unresolved")

    # Step 2: fetch info for unique tickers
    unique_tickers = {t for t, _ in full_map.values() if t}
    ticker_info    = {}

    for ticker in unique_tickers:
        if ticker in _SECTOR_OVERRIDES:
            sector, cap_cat = _SECTOR_OVERRIDES[ticker]
            ticker_info[ticker] = {"sector": sector, "market_cap_cr": None, "cap_category": cap_cat}
            continue

        info = _get_info_safe(ticker)
        if info:
            mcap    = info.get("marketCap") or info.get("market_cap")
            mcap_cr = round(float(mcap) / 1e7, 2) if mcap else None
            sector  = (
                info.get("sector")
                or info.get("industryDisp")
                or info.get("industry")
                or "Unknown"
            )
            ticker_info[ticker] = {
                "sector"        : sector,
                "market_cap_cr" : mcap_cr,
                "cap_category"  : _classify_cap(mcap_cr),
            }
        else:
            ticker_info[ticker] = {"sector": "Unknown", "market_cap_cr": None, "cap_category": "Unknown"}

    # Step 3: map back to scrip names
    result = {}
    for scrip, (ticker, resolved_by) in full_map.items():
        entry = dict(ticker_info.get(ticker, {"sector": "Unknown", "market_cap_cr": None, "cap_category": "Unknown"}))
        entry["ticker"]      = ticker
        entry["resolved_by"] = resolved_by
        result[scrip] = entry

    return result


# ─────────────────────────────────────────────────────────────────────────────
#  LIVE PRICE FETCH
# ─────────────────────────────────────────────────────────────────────────────

def fetch_live_prices_with_autoresolve(scrip_names: list, base_ticker_map: dict = None) -> dict:
    """Fetch live prices for scrip names. Auto-resolves tickers."""

    ticker_map_for_scrips = {}
    for scrip in scrip_names:
        if base_ticker_map and scrip in base_ticker_map:
            t = base_ticker_map[scrip]
            ticker_map_for_scrips[scrip] = t if t != "__UNKNOWN__" else None
        elif scrip in _EXTRA_OVERRIDES:
            ticker_map_for_scrips[scrip] = _EXTRA_OVERRIDES[scrip]
        elif scrip in _TICKER_CACHE:
            ticker_map_for_scrips[scrip] = _TICKER_CACHE[scrip]
        else:
            ticker_map_for_scrips[scrip] = resolve_ticker(scrip, base_ticker_map)

    ticker_to_scrips = {}
    for scrip, ticker in ticker_map_for_scrips.items():
        if ticker:
            ticker_to_scrips.setdefault(ticker, []).append(scrip)

    tickers     = list(ticker_to_scrips.keys())
    live_prices = {}

    if not tickers:
        return {s: None for s in scrip_names}

    try:
        raw = yf.download(tickers, period="1d", interval="1m",
                          group_by="ticker", progress=False, auto_adjust=True)
        for ticker in tickers:
            try:
                price = (
                    float(raw["Close"].dropna().iloc[-1])
                    if len(tickers) == 1
                    else float(raw[ticker]["Close"].dropna().iloc[-1])
                )
                live_prices[ticker] = price
            except Exception:
                live_prices[ticker] = None
    except Exception:
        live_prices = {t: None for t in tickers}

    # Daily fallback
    failed = [t for t, p in live_prices.items() if p is None]
    if failed:
        try:
            raw_d = yf.download(failed, period="5d", interval="1d",
                                group_by="ticker", progress=False, auto_adjust=True)
            for ticker in failed:
                try:
                    price = (
                        float(raw_d["Close"].dropna().iloc[-1])
                        if len(failed) == 1
                        else float(raw_d[ticker]["Close"].dropna().iloc[-1])
                    )
                    live_prices[ticker] = price
                except Exception:
                    live_prices[ticker] = None
        except Exception:
            pass

    result = {}
    for scrip, ticker in ticker_map_for_scrips.items():
        result[scrip] = live_prices.get(ticker) if ticker else None
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def get_extended_ticker_map(base_ticker_map: dict = None) -> dict:
    result = {}
    if base_ticker_map:
        result.update({k: v for k, v in base_ticker_map.items() if v != "__UNKNOWN__"})
    result.update(_EXTRA_OVERRIDES)
    result.update(_TICKER_CACHE)
    return result


def refresh_nse_master():
    """Force re-download of NSE master file."""
    global _NSE_MASTER
    _NSE_MASTER = None
    if os.path.exists(NSE_MASTER_FILE):
        os.remove(NSE_MASTER_FILE)
    return _download_nse_master()


def clear_cache():
    global _TICKER_CACHE
    _TICKER_CACHE = {}
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)


def get_cache_stats() -> dict:
    return {
        "total_cached" : len(_TICKER_CACHE),
        "cache_file"   : CACHE_FILE,
        "nse_master"   : "loaded" if _NSE_MASTER is not None else "not loaded",
        "nse_file"     : "exists" if os.path.exists(NSE_MASTER_FILE) else "missing",
    }
