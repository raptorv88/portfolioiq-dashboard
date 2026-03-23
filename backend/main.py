"""
Portfolio Analysis API
FastAPI backend that wraps the existing Python analysis modules
and adds auth + persistent SQLite storage.

Run with:
    uvicorn main:app --reload --port 8000
"""

import io
import os
import sys
import json
import uuid
import datetime
from pathlib import Path
from typing import Optional

# ── point imports to your analysis folder ────────────────────────────────────
# Analysis .py files live in the same folder as main.py
ANALYSIS_DIR = Path(__file__).parent
sys.path.insert(0, str(ANALYSIS_DIR))

from fastapi import (
    FastAPI, Depends, HTTPException, UploadFile,
    File, Form, status, Request
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from sqlalchemy import (
    create_engine, Column, String, Text,
    DateTime, ForeignKey, Boolean
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

from passlib.context import CryptContext
from jose import JWTError, jwt

import pandas as pd
import numpy as np

import logging
from logging.handlers import RotatingFileHandler

# ── Logging Setup ─────────────────────────────────────────────────────────────
LOG_FILE = Path(__file__).parent / "app.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger("portfolioiq")
# ─────────────────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────────────────

SECRET_KEY      = os.getenv("SECRET_KEY", "change-this-in-production-portfolio-2024")
ALGORITHM       = "HS256"
TOKEN_EXPIRE_H  = 24
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres@localhost:5432/portfolio_db"
)

pwd_ctx       = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")



# ─────────────────────────────────────────────────────────────────────────────
#  DATABASE MODELS
# ─────────────────────────────────────────────────────────────────────────────

engine = create_engine(DB_URL, pool_size=10, max_overflow=20)
Base     = declarative_base()
SessionF = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class User(Base):
    __tablename__ = "users"
    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username   = Column(String, unique=True, nullable=False)
    email      = Column(String, unique=True, nullable=False)
    full_name  = Column(String, nullable=False)
    hashed_pw  = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_active  = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    snapshots  = relationship("Snapshot", back_populates="user", cascade="all, delete")





class Snapshot(Base):
    """One row per analysis run — stores everything as JSON for later replay."""
    __tablename__    = "snapshots"
    id               = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id          = Column(String, ForeignKey("users.id"), nullable=False)
    label            = Column(String, nullable=False)
    created_at       = Column(DateTime, default=datetime.datetime.utcnow)
    client_name      = Column(String, default="")
    client_id        = Column(String, default="")
    date_range       = Column(String, default="")
    trade_file_name  = Column(String, default="")
    hold_file_name   = Column(String, default="")
    summary_json     = Column(Text, nullable=False)
    unified_json     = Column(Text, nullable=False)
    realized_json    = Column(Text, default="[]")
    index_pnl_json   = Column(Text, default="[]")
    recon_json       = Column(Text, default="[]")
    sector_json      = Column(Text, default="{}")
    cap_json         = Column(Text, default="{}")
    allocation_json  = Column(Text, default="{}")
    ens_value        = Column(String, default="0")
    xirr_port_json   = Column(Text, default="{}")
    xirr_group_json  = Column(Text, default="[]")
    xirr_scrip_json  = Column(Text, default="[]")
    buy_trades_json  = Column(Text, default="[]")
    user             = relationship("User", back_populates="snapshots")


Base.metadata.create_all(bind=engine)
def get_db():
    db = SessionF()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
#  AUTH HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def hash_password(pw: str) -> str:
    return pwd_ctx.hash(pw)

def verify_password(pw: str, hashed: str) -> bool:
    return pwd_ctx.verify(pw, hashed)

def create_token(data: dict) -> str:
    exp = datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_EXPIRE_H)
    return jwt.encode({**data, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expired. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload  = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise exc
    except JWTError:
        raise exc
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise exc
    return user

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    logger.info(f"ADMIN ACCESS | user={current_user.username}")
    return current_user


# ─────────────────────────────────────────────────────────────────────────────
#  JSON HELPERS
# ─────────────────────────────────────────────────────────────────────────────

class SafeEncoder(json.JSONEncoder):
    """
    Handles NaN, Infinity, numpy types, and pandas Timestamps safely.
    Python's json module bypasses default() for float NaN/Inf, so we
    override iterencode to sanitise the entire object tree first.
    """
    def default(self, obj):
        if isinstance(obj, (pd.Timestamp, datetime.datetime, datetime.date)):
            return obj.isoformat()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            f = float(obj)
            return None if (np.isnan(f) or np.isinf(f)) else f
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        return super().default(obj)


def _sanitise(obj):
    """Recursively replace NaN/Inf floats with None before JSON encoding."""
    if isinstance(obj, float):
        return None if (np.isnan(obj) or np.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitise(v) for v in obj]
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        return None if (np.isnan(f) or np.isinf(f)) else f
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    return obj


def safe_json(obj) -> str:
    """Convert any object to JSON string, safely handling NaN/Inf."""
    return json.dumps(_sanitise(obj), cls=SafeEncoder)


def df_to_str(df) -> str:
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return "[]"
    return safe_json(df.to_dict(orient="records"))

def d_to_str(d: dict) -> str:
    return safe_json(d or {})


# ─────────────────────────────────────────────────────────────────────────────
#  ANALYSIS RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_full_analysis(trade_bytes: Optional[bytes], holding_bytes: Optional[bytes]) -> dict:
    from portfolio_analysis import (
        DEFAULT_SKIP_ROWS, REQUIRED_COLS,
        separate_index_equity, calculate_equity_positions,
        build_opening_lots_from_holdings, calculate_index_pnl, preprocess_data,
    )
    from holdings_analysis import parse_holdings_file
    from integrator import integrate
    from xirr_engine import run_xirr_analysis

    trade_holdings_df  = None
    trade_realized_df  = None
    trade_index_pnl_df = None
    holdings_file_df   = None
    trade_client_info  = {}
    hold_client_info   = {}
    equity_df          = pd.DataFrame()

    if trade_bytes:
        buf      = io.BytesIO(trade_bytes)
        raw_meta = pd.read_excel(buf, header=None, nrows=4)
        buf.seek(0)

        def _cell(r, c):
            try:
                v = raw_meta.iloc[r, c]
                return str(v).strip() if pd.notna(v) else ""
            except Exception:
                return ""

        trade_client_info = {
            "company"      : _cell(0, 0),
            "report_title" : _cell(1, 0),
            "date_range"   : _cell(2, 0),
            "client_name"  : _cell(3, 0),
            "client_id"    : _cell(3, 1),
        }

        raw_scan = pd.read_excel(buf, header=None, nrows=60)
        buf.seek(0)
        best_row, best_score = DEFAULT_SKIP_ROWS, 0
        for i, row in raw_scan.iterrows():
            row_vals = [str(v).strip() for v in row if pd.notna(v)]
            score    = sum(1 for col in REQUIRED_COLS if col in row_vals)
            if score > best_score:
                best_score = score
                best_row   = i

        df = pd.read_excel(buf, skiprows=best_row)
        df.columns = df.columns.str.strip()
        df = df.dropna(how="all").reset_index(drop=True)

        missing = [c for c in REQUIRED_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"Trade Report missing columns: {missing}. Found: {list(df.columns)}")

        df        = preprocess_data(df[REQUIRED_COLS].copy())
        equity_df, index_df = separate_index_equity(df)

        if holding_bytes:
            buf2 = io.BytesIO(holding_bytes)
            holdings_file_df, hold_client_info = parse_holdings_file(buf2)

        opening_lots = (
            build_opening_lots_from_holdings(holdings_file_df)
            if holdings_file_df is not None else {}
        )
        trade_holdings_df, trade_realized_df = calculate_equity_positions(
            equity_df, opening_lots=opening_lots
        )
        trade_index_pnl_df = calculate_index_pnl(index_df)

    if holding_bytes and holdings_file_df is None:
        buf2 = io.BytesIO(holding_bytes)
        holdings_file_df, hold_client_info = parse_holdings_file(buf2)

    results = integrate(
        trade_holdings_df, trade_realized_df, trade_index_pnl_df,
        holdings_file_df, trade_raw_df=equity_df if trade_bytes else None,
    )

    xirr_result = {}
    try:
        hld = holdings_file_df if holdings_file_df is not None else pd.DataFrame()
        xirr_result = run_xirr_analysis(equity_df, hld, results["unified"])
    except Exception as e:
        xirr_result = {"error": str(e), "portfolio": {}, "per_group": pd.DataFrame(), "per_scrip": pd.DataFrame()}

    client = trade_client_info if trade_client_info.get("client_name") else hold_client_info

    unified = results["unified"]

    # ── Recalculate CST / Sector / Cap with full precision ────────────────
    # The integrator uses round(2) on each weight row which causes rounding
    # losses. We recompute from scratch using full-precision current values.
    allocation = results["allocation"].copy()
    sector_wt  = results["sector_wt"].copy()
    cap_sum    = results["cap_summary"].copy()

    try:
        if not unified.empty and "Current Value" in unified.columns:
            # Deduplicate — one row per scrip using combined current value
            dedup = (
                unified.groupby("Scrip Name", as_index=False)
                .agg({"Current Value": "sum", "Sector": "first", "Cap Category": "first"})
            )
            total = dedup["Current Value"].sum()

            if total > 0:
                dedup["_w"] = dedup["Current Value"] / total * 100  # full precision

                # ── CST ───────────────────────────────────────────────────
                CORE_T = 5.0
                SAT_T  = 1.0
                core_pct = dedup.loc[dedup["_w"] >= CORE_T, "_w"].sum()
                sat_pct  = dedup.loc[(dedup["_w"] >= SAT_T) & (dedup["_w"] < CORE_T), "_w"].sum()
                tail_pct = dedup.loc[dedup["_w"] < SAT_T, "_w"].sum()
                cst_sum  = core_pct + sat_pct + tail_pct
                if cst_sum > 0:
                    allocation["Core Allocation %"]      = round(core_pct / cst_sum * 100, 2)
                    allocation["Satellite Allocation %"] = round(sat_pct  / cst_sum * 100, 2)
                    allocation["Tail Allocation %"]      = round(
                        100 - allocation["Core Allocation %"] - allocation["Satellite Allocation %"], 2
                    )
                    allocation["Tail Allocation %"]      = max(0.0, allocation["Tail Allocation %"])
                allocation["Core Count"]      = int((dedup["_w"] >= CORE_T).sum())
                allocation["Satellite Count"] = int(((dedup["_w"] >= SAT_T) & (dedup["_w"] < CORE_T)).sum())
                allocation["Tail Count"]      = int((dedup["_w"] < SAT_T).sum())
                
                # ── Sector ────────────────────────────────────────────────
                sec_raw = dedup.groupby("Sector")["_w"].sum()
                sec_t   = sec_raw.sum()
                if sec_t > 0:
                    sec_scaled = (sec_raw / sec_t * 100).round(2)
                    diff = round(100 - sec_scaled.sum(), 2)
                    if diff != 0:
                        sec_scaled[sec_scaled.idxmax()] = round(sec_scaled.max() + diff, 2)
                    sector_wt = sec_scaled.sort_values(ascending=False).to_dict()

                # ── Cap ───────────────────────────────────────────────────
                cap_raw = dedup.groupby("Cap Category")["_w"].sum()
                cap_t   = cap_raw.sum()
                if cap_t > 0:
                    cap_scaled = (cap_raw / cap_t * 100).round(2)
                    diff = round(100 - cap_scaled.sum(), 2)
                    if diff != 0:
                        cap_scaled[cap_scaled.idxmax()] = round(cap_scaled.max() + diff, 2)
                    cap_sum = cap_scaled.to_dict()
    except Exception:
        pass  # fall back to original values if anything goes wrong
    try:
        cst_total = (
            allocation.get('Core Allocation %', 0) +
            allocation.get('Satellite Allocation %', 0) +
            allocation.get('Tail Allocation %', 0)
        )
        if cst_total > 100 or cst_total <= 0:
            pos = unified[unified['Current Value'].fillna(0) > 0].copy()
            if not pos.empty:
                dedup2 = pos.groupby('Scrip Name')['Current Value'].sum()
                total2 = dedup2.sum()
                if total2 > 0:
                    w = dedup2 / total2 * 100
                    allocation['Core Allocation %']      = round(float(w[w >= 5].sum()), 2)
                    allocation['Satellite Allocation %'] = round(float(w[(w >= 1) & (w < 5)].sum()), 2)
                    allocation['Tail Allocation %']      = round(max(0.0, 100 - allocation['Core Allocation %'] - allocation['Satellite Allocation %']), 2)
                    allocation['Core Count']      = int((w >= 5).sum())
                    allocation['Satellite Count'] = int(((w >= 1) & (w < 5)).sum())
                    allocation['Tail Count']      = int((w < 1).sum())
    except Exception:
        pass

    # ── Build buy_trades: all BUY rows from trade report ─────────────────
    buy_trades_df = pd.DataFrame()
    try:
        if not equity_df.empty:
            buys = equity_df[equity_df["Action"] == "BUY"][
                ["Scrip Name", "Trade Date", "Quantity", "Price"]
            ].copy()
            buys = buys.rename(columns={
                "Trade Date" : "Buy Date",
                "Quantity"   : "Buy Qty",
                "Price"      : "Buy Price",
            })
            buys["Buy Date"] = buys["Buy Date"].astype(str)
            buy_trades_df = buys.sort_values("Buy Date").reset_index(drop=True)
    except Exception:
        pass

    return {
        "unified"        : unified,
        "realized"       : results.get("realized", pd.DataFrame()),
        "index_pnl"      : results.get("index_pnl", pd.DataFrame()),
        "summary"        : results["summary"],
        "ens"            : results["ens"],
        "allocation"     : allocation,
        "sector_wt"      : sector_wt,
        "cap_summary"    : cap_sum,
        "reconciliation" : results.get("reconciliation", pd.DataFrame()),
        "client"         : client,
        "xirr"           : xirr_result,
        "buy_trades"     : buy_trades_df,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  PYDANTIC SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class RegisterBody(BaseModel):
    username  : str
    email     : str
    full_name : str
    password  : str

class TokenOut(BaseModel):
    access_token : str
    token_type   : str = "bearer"
    user         : dict


# ─────────────────────────────────────────────────────────────────────────────
#  APP
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Portfolio Analysis API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/auth/register", response_model=TokenOut)
def register(body: RegisterBody, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username.strip().lower()).first():
        raise HTTPException(400, "Username already taken")
    if db.query(User).filter(User.email == body.email.strip().lower()).first():
        raise HTTPException(400, "Email already registered")

    u = User(
        username  = body.username.strip().lower(),
        email     = body.email.strip().lower(),
        full_name = body.full_name.strip(),
        hashed_pw = hash_password(body.password),
    )
    db.add(u); db.commit(); db.refresh(u)
    logger.info(f"NEW USER | username={u.username} | email={u.email}")
    return TokenOut(
        access_token=create_token({"sub": u.username}),
        user={"id": u.id, "username": u.username, "email": u.email, "full_name": u.full_name, "is_admin": u.is_admin}
    )


@app.post("/auth/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == form.username.strip().lower()).first()
    if not u or not verify_password(form.password, u.hashed_pw):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    logger.info(f"USER LOGIN | username={u.username} | email={u.email}")
    return TokenOut(
        access_token=create_token({"sub": u.username}),
       user={"id": u.id, "username": u.username, "email": u.email, "full_name": u.full_name, "is_admin": u.is_admin}
    )


@app.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "email": user.email, "full_name": user.full_name, "is_admin": user.is_admin}



# ── Analysis ──────────────────────────────────────────────────────────────────

@app.post("/analysis/run")
async def run_analysis_endpoint(
    trade_file   : Optional[UploadFile] = File(None),
    holding_file : Optional[UploadFile] = File(None),
    label        : str = Form(""),
    user         : User = Depends(get_current_user),
    db           : Session = Depends(get_db),
):
    if trade_file is None and holding_file is None:
        raise HTTPException(400, "Upload at least one file")

    tb = await trade_file.read()   if trade_file   else None
    hb = await holding_file.read() if holding_file else None

    try:
        R = run_full_analysis(tb, hb)
    except Exception as e:
        logger.error(f"ANALYSIS FAILED | user={user.username} | error={str(e)}", exc_info=True)
        raise HTTPException(500, f"Analysis failed: {e}")

    xirr      = R["xirr"]
    xirr_port  = xirr.get("portfolio", {}) if isinstance(xirr, dict) else {}
    xirr_group = xirr.get("per_group", pd.DataFrame()) if isinstance(xirr, dict) else pd.DataFrame()
    xirr_scrip = xirr.get("per_scrip", pd.DataFrame()) if isinstance(xirr, dict) else pd.DataFrame()

    client     = R["client"]
    snap_label = label.strip() or datetime.datetime.now().strftime("Analysis %d %b %Y, %H:%M")

    snap = Snapshot(
        user_id         = user.id,
        label           = snap_label,
        client_name     = client.get("client_name", ""),
        client_id       = client.get("client_id", ""),
        date_range      = client.get("date_range", ""),
        trade_file_name = trade_file.filename  if trade_file  else "",
        hold_file_name  = holding_file.filename if holding_file else "",
        summary_json    = d_to_str(R["summary"]),
        unified_json    = df_to_str(R["unified"]),
        realized_json   = df_to_str(R["realized"]),
        index_pnl_json  = df_to_str(R["index_pnl"]),
        recon_json      = df_to_str(R["reconciliation"]),
        sector_json     = d_to_str(R["sector_wt"]),
        cap_json        = d_to_str(R["cap_summary"]),
        allocation_json = d_to_str(R["allocation"]),
        ens_value       = str(R["ens"]),
        xirr_port_json  = d_to_str({k: v for k, v in xirr_port.items() if k != "cashflows"}),
        xirr_group_json = df_to_str(xirr_group if isinstance(xirr_group, pd.DataFrame) else pd.DataFrame()),
        xirr_scrip_json = df_to_str(xirr_scrip if isinstance(xirr_scrip, pd.DataFrame) else pd.DataFrame()),
        buy_trades_json = df_to_str(R["buy_trades"] if isinstance(R.get("buy_trades"), pd.DataFrame) else pd.DataFrame()),
    )
    db.add(snap); db.commit(); db.refresh(snap)
    logger.info(f"ANALYSIS COMPLETE | user={user.username} | client={client.get('client_name','unknown')} | label={snap_label}")

    # Build payload — route everything through SafeEncoder so NaN/Inf never crash
    payload_str = safe_json({
        "snapshot_id" : snap.id,
        "label"       : snap.label,
        "summary"     : R["summary"],
        "ens"         : R["ens"],
        "allocation"  : R["allocation"],
        "sector_wt"   : json.loads(snap.sector_json),
        "cap_summary" : json.loads(snap.cap_json),
        "unified"     : json.loads(snap.unified_json),
        "realized"    : json.loads(snap.realized_json),
        "index_pnl"   : json.loads(snap.index_pnl_json),
        "recon"       : json.loads(snap.recon_json),
        "client"      : client,
        "xirr"        : {
            "portfolio" : json.loads(snap.xirr_port_json),
            "per_group" : json.loads(snap.xirr_group_json),
            "per_scrip" : json.loads(snap.xirr_scrip_json),
        },
        "buy_trades"  : json.loads(snap.buy_trades_json),
    })
    return Response(content=payload_str, media_type="application/json")


# ── History ───────────────────────────────────────────────────────────────────

@app.get("/history")
def list_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    snaps = (
        db.query(Snapshot)
        .filter(Snapshot.user_id == user.id)
        .order_by(Snapshot.created_at.desc())
        .all()
    )
    return [
        {
            "id"          : s.id,
            "label"       : s.label,
            "created_at"  : s.created_at.isoformat(),
            "client_name" : s.client_name,
            "client_id"   : s.client_id,
            "date_range"  : s.date_range,
            "trade_file"  : s.trade_file_name,
            "hold_file"   : s.hold_file_name,
            "summary"     : json.loads(s.summary_json),
        }
        for s in snaps
    ]


@app.get("/history/{snap_id}")
def get_snapshot(snap_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.query(Snapshot).filter(Snapshot.id == snap_id, Snapshot.user_id == user.id).first()
    if not s:
        raise HTTPException(404, "Snapshot not found")
    snap_payload = {
        "id"          : s.id,
        "label"       : s.label,
        "created_at"  : s.created_at.isoformat(),
        "client_name" : s.client_name,
        "client_id"   : s.client_id,
        "date_range"  : s.date_range,
        "summary"     : json.loads(s.summary_json),
        "ens"         : s.ens_value,
        "allocation"  : json.loads(s.allocation_json),
        "sector_wt"   : json.loads(s.sector_json),
        "cap_summary" : json.loads(s.cap_json),
        "unified"     : json.loads(s.unified_json),
        "realized"    : json.loads(s.realized_json),
        "index_pnl"   : json.loads(s.index_pnl_json),
        "recon"       : json.loads(s.recon_json),
        "xirr"        : {
            "portfolio" : json.loads(s.xirr_port_json),
            "per_group" : json.loads(s.xirr_group_json),
            "per_scrip" : json.loads(s.xirr_scrip_json),
        },
        "buy_trades"  : json.loads(s.buy_trades_json if s.buy_trades_json else "[]"),
    }
    return Response(content=safe_json(snap_payload), media_type="application/json")


@app.delete("/history/{snap_id}")
def delete_snapshot(snap_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.query(Snapshot).filter(Snapshot.id == snap_id, Snapshot.user_id == user.id).first()
    if not s:
        raise HTTPException(404, "Snapshot not found")
    db.delete(s); db.commit()
    return {"deleted": snap_id}

@app.get("/analysis/nifty-return")
async def get_nifty_return(user: User = Depends(get_current_user)):
    try:
        import yfinance as yf
        import datetime
        
        end   = datetime.date.today()
        start = end - datetime.timedelta(days=365)
        
        nifty = yf.Ticker("^NSEI")
        hist  = nifty.history(start=str(start), end=str(end))
        
        if hist.empty or len(hist) < 2:
            return {"return_pct": None, "error": "No data"}
        
        # Use first and last available trading day
        start_price = float(hist["Close"].iloc[0])
        end_price   = float(hist["Close"].iloc[-1])
        ret         = round((end_price - start_price) / start_price * 100, 2)
        
        logger.info(f"Nifty 1Y return: {ret}% (from {hist.index[0].date()} to {hist.index[-1].date()})")
        return {"return_pct": ret}
    except Exception as e:
        logger.error(f"Nifty fetch failed: {e}")
        return {"return_pct": None, "error": str(e)}


@app.get("/health")
def health():
    return {"status": "ok"}

