# Portfolio Analysis Dashboard
## Complete Setup Guide — From Zero to Running

---

## PART 1 — HOW DATA STORAGE WORKS (Very Basic Explanation)

This is a question that often confuses people, so let me explain it step by step
before we get to the technical setup.

### What is "storing data"?

When you run an analysis on the dashboard, the Python code:
- Reads your Excel files
- Does all the calculations (FIFO, XIRR, sector allocation, etc.)
- Returns results as numbers and tables

Without storage, those results disappear the moment you close the browser tab.

**Storage means:** we save those results somewhere permanent, so you can come
back tomorrow (or next month) and still see what the portfolio looked like today.

---

### What tool do we use? SQLite Database

Think of SQLite as a very organized Excel file that lives on the server.

  Excel:   rows and columns you see visually
  SQLite:  rows and columns the computer manages automatically

SQLite creates a single file on disk called `portfolio_data.db`.
Every analysis run adds one row to a table called `snapshots`.
That's all there is to it.

---

### What exactly gets stored per analysis run?

Every time you click "Run Analysis", the backend saves:

  - Who ran it (which user)
  - When it ran (date + time)
  - What label you gave it
  - Client name and ID from the trade report header
  - The entire unified holdings table (as JSON)
  - Summary KPIs (total value, P&L, etc.)
  - Sector weights, cap breakdown, allocation
  - XIRR results (portfolio, per group, per scrip)
  - Reconciliation table
  - Which files were uploaded

**Why JSON?** JSON is just a text format that can store any structured data —
tables, numbers, lists. It's like a very precise way of writing the data down
in a text file. The database stores it as text and we read it back whenever needed.

---

### Where is the data physically stored?

    your_project/
      backend/
        portfolio_data.db     ← this file IS your database
                                 it grows with every analysis run

You can open this file with a free tool called "DB Browser for SQLite"
(sqlitebrowser.org) to inspect or export the data whenever you want.

---

### How is user login secured?

1. You register with a username + password
2. The password is NEVER stored in plain text
   It is "hashed" (scrambled irreversibly) using bcrypt — the industry standard
3. When you log in, the server checks your password against the hash
4. If correct, it gives you a "token" — a random string that expires in 24 hours
5. Every request from your browser sends this token to prove who you are
6. The server checks the token on every request

This is identical to how banking apps work.

---

## PART 2 — ARCHITECTURE OVERVIEW

```
Browser (React)
    │  HTTP requests (JSON)
    ▼
FastAPI Backend  ←──── all your existing Python analysis code unchanged
    │
    ├── SQLite DB (stores snapshots)
    └── portfolio_analysis.py
        integrator.py
        holdings_analysis.py
        xirr_engine.py
        ticker_resolver.py
```

**React** = the visual interface (login page, dashboard, charts)
**FastAPI** = Python web server that handles login, runs analysis, stores data
**SQLite** = the database that persists everything

The Streamlit dashboard still works exactly as before — this is a separate,
more professional interface built on top of the same code.

---

## PART 3 — FOLDER STRUCTURE

```
portfolio_app/
  backend/
    main.py              ← FastAPI server (auth + analysis endpoints + DB)
    requirements.txt     ← Python dependencies
    portfolio_data.db    ← Created automatically on first run

  frontend/
    package.json         ← Node/React dependencies
    vite.config.js       ← Dev server config (proxies API calls to backend)
    tailwind.config.js   ← CSS framework config
    index.html           ← HTML entry point
    src/
      main.jsx           ← React entry point
      App.jsx            ← Routes (login/register/dashboard/history)
      index.css          ← Global styles and design tokens
      context/
        AuthContext.jsx  ← Login state (persisted in localStorage)
      pages/
        LoginPage.jsx    ← Sign in form
        RegisterPage.jsx ← Create account form
        DashboardPage.jsx← Upload + run analysis + all 6 tabs
        HistoryPage.jsx  ← List all saved snapshots
        SnapshotPage.jsx ← View a specific saved snapshot
      components/
        AppShell.jsx     ← Sidebar + topbar layout
        KpiCard.jsx      ← Metric display card
        DataTable.jsx    ← Sortable/searchable table

  analysis/              ← COPY ALL YOUR EXISTING .py FILES HERE
    portfolio_analysis.py
    holdings_analysis.py
    integrator.py
    xirr_engine.py
    ticker_resolver.py
    ticker_cache.json
```

---

## PART 4 — SETUP INSTRUCTIONS

### Step 1: Install Python dependencies

Open a terminal, navigate to the backend folder, and run:

```bash
cd portfolio_app/backend
pip install fastapi uvicorn[standard] python-multipart sqlalchemy \
            passlib[bcrypt] python-jose[cryptography] \
            pandas numpy openpyxl yfinance pyxirr scipy
```

### Step 2: Copy your analysis files

Copy all these files into the `analysis/` folder:
- portfolio_analysis.py
- holdings_analysis.py
- integrator.py
- xirr_engine.py
- ticker_resolver.py
- ticker_cache.json (if it exists)

### Step 3: Start the backend server

```bash
cd portfolio_app/backend
uvicorn main:app --reload --port 8000
```

You should see:
  INFO:     Started server process
  INFO:     Application startup complete.
  INFO:     Uvicorn running on http://127.0.0.1:8000

### Step 4: Install Node.js (if not already installed)

Download from nodejs.org — choose the LTS (Long Term Support) version.
After installation, verify with:

```bash
node --version    # should show v18.x.x or higher
npm --version     # should show 9.x.x or higher
```

### Step 5: Install React dependencies

```bash
cd portfolio_app/frontend
npm install
```

This downloads all the React libraries into a `node_modules` folder.
It only needs to be done once (or after any package.json change).

### Step 6: Start the React development server

```bash
cd portfolio_app/frontend
npm run dev
```

You should see:
  VITE v5.x  ready in 300ms
  ➜  Local:   http://localhost:3000/

### Step 7: Open the dashboard

Open your browser and go to:  http://localhost:3000

You will see the login page. Click "Create one" to register your account.

---

## PART 5 — USING THE DASHBOARD

### First time
1. Click "Create one" on the login page
2. Fill in your name, username, email, password
3. You'll be taken straight to the dashboard

### Running an analysis
1. Drag and drop your Trade Report (.xlsx) into the first zone
2. Drag and drop your Holdings File (.xlsx) into the second zone
3. Optionally type a label like "Q1 2024 Review"
4. Click "Run Analysis"
5. The backend runs all calculations, saves a snapshot, returns results
6. All 6 tabs appear: Holdings, P&L, Allocation, XIRR, Reconciliation, Derivatives

### Viewing history
1. Click "History" in the left sidebar
2. All your previous runs appear, newest first
3. Click "View" on any row to see the full analysis from that date
4. Click "Delete" to permanently remove a snapshot

---

## PART 6 — WHAT CHANGED VS THE STREAMLIT VERSION

| Feature              | Streamlit (before)    | React+FastAPI (now)        |
|----------------------|-----------------------|----------------------------|
| Login / auth         | No login              | Full login + registration  |
| Data storage         | Nothing saved         | Every run saved to SQLite  |
| History              | Not available         | Full history with dates    |
| Interface            | Streamlit widgets     | Custom React UI            |
| Analysis logic       | Unchanged             | Unchanged (same .py files) |
| XIRR                 | Tab 6                 | XIRR tab (same engine)     |
| Offline capability   | Yes                   | Requires local server      |

**The analysis itself — FIFO, XIRR, sector allocation, reconciliation —
is 100% identical. Not a single line of analysis code was changed.**

---

## PART 7 — TROUBLESHOOTING

**"Module not found" errors in backend**
→ Make sure all .py files are copied to the `analysis/` folder
→ Check that `ANALYSIS_DIR` in main.py points to the right path

**"Cannot connect to server" in browser**
→ Make sure the backend is running on port 8000
→ Make sure the frontend is running on port 3000
→ The vite.config.js proxies all /auth, /analysis, /history calls to port 8000

**CORS errors in browser console**
→ Confirm the backend is running
→ Check that allow_origins in main.py includes http://localhost:3000

**"Username already taken" on register**
→ The database already has that username — try a different one
→ If testing, you can delete portfolio_data.db to reset all users and data

---

## PART 8 — DEPLOYING FOR PRODUCTION

For internal company use beyond a single laptop, the setup would be:

1. Backend → deploy to a Linux server using:
   `uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2`
   Or package it behind nginx

2. Frontend → build a static bundle:
   `cd frontend && npm run build`
   Then serve the `dist/` folder via nginx or any static host

3. Database → SQLite is fine for small teams.
   For 10+ concurrent users, migrate to PostgreSQL (just change DB_URL)

4. Change SECRET_KEY → set the environment variable:
   `export SECRET_KEY="your-long-random-secret-here"`
