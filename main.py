import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import re
from datetime import datetime
from typing import Optional, Tuple
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText

# Import your existing modules
from sec_edgar import get_latest_8k_url, download_filing_text
from ticker_utils import get_cik_for_ticker
from extractfrompdf import extract_total_eth_holdings, extract_diluted_shares_anywhere

app = FastAPI(title="MNAV Analysis API", version="1.0.0")

# Enable CORS for frontend (allow all origins for now)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Email settings - use environment variables in production
SMTP_SERVER = "in-v3.mailjet.com"
SMTP_PORT = 587
MAILJET_USER = os.getenv("MAILJET_USER", "ad6944548828bc7ffc0582ffbb09fcb6")
MAILJET_PASS = os.getenv("MAILJET_PASS", "10a20df16440c695fbd8108d958dba80")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "Jsorkin123@gmail.com")

# PostgreSQL connection settings
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Fallback for Railway auto-generated env vars
    DATABASE_URL = f"postgresql://{os.getenv('PGUSER')}:{os.getenv('PGPASSWORD')}@{os.getenv('PGHOST')}:{os.getenv('PGPORT')}/{os.getenv('PGDATABASE')}"

@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

# Database initialization
def init_database():
    """Initialize PostgreSQL database with required tables"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Table to track processed 8-K filings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS filings_processed (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(10) NOT NULL,
                accession_number VARCHAR(50) NOT NULL,
                filing_date DATE NOT NULL,
                filing_url TEXT NOT NULL,
                shares_added INTEGER DEFAULT 0,
                eth_holdings INTEGER DEFAULT 0,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, accession_number)
            )
        ''')
        
        # Table to track current company data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS company_data (
                ticker VARCHAR(10) PRIMARY KEY,
                total_diluted_shares BIGINT NOT NULL,
                base_shares BIGINT NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()

# Pydantic models
class MNAVResponse(BaseModel):
    ticker: str
    eth_price: float
    stock_price: float
    eth_holdings: int
    diluted_shares: int
    treasury_value: float
    mnav_per_share: float
    market_cap: float
    mnav_multiple: float
    last_updated: str
    filings_processed: int

class EmailRequest(BaseModel):
    email: str
    mnav_data: MNAVResponse

class InitializeRequest(BaseModel):
    ticker: str
    total_diluted_shares_outstanding: int

# Utility functions
def get_eth_price() -> float:
    """Fetch current ETH price from CoinGecko"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": "ethereum", "vs_currencies": "usd"}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()["ethereum"]["usd"]
    except Exception as e:
        print(f"[WARN] CoinGecko API failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch ETH price")

def get_stock_price(ticker: str) -> float:
    """Fetch current stock price from Yahoo Finance REST endpoint"""
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        result = data["quoteResponse"]["result"]
        if not result:
            raise Exception("No data found for ticker")
        price = result[0].get("regularMarketPrice")
        if price is None:
            raise Exception("Price not found in Yahoo response")
        return float(price)
    except Exception as e:
        print(f"[WARN] Yahoo Finance fetch failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch {ticker} stock price")

def get_company_data(ticker: str) -> Optional[Tuple[int, str]]:
    """Get current diluted shares and last update timestamp for a ticker"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT total_diluted_shares, last_updated FROM company_data WHERE ticker = %s',
            (ticker,)
        )
        result = cursor.fetchone()
        return result if result else None

def update_company_data(ticker: str, total_shares: int):
    """Update the total diluted shares for a ticker"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO company_data (ticker, total_diluted_shares, base_shares, last_updated)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (ticker) 
            DO UPDATE SET 
                total_diluted_shares = EXCLUDED.total_diluted_shares,
                last_updated = CURRENT_TIMESTAMP
        ''', (ticker, total_shares, total_shares))
        conn.commit()

def get_last_processed_filing(ticker: str) -> Optional[str]:
    """Get the accession number of the last processed 8-K filing"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT accession_number FROM filings_processed WHERE ticker = %s ORDER BY filing_date DESC LIMIT 1',
            (ticker,)
        )
        result = cursor.fetchone()
        return result[0] if result else None

def add_processed_filing(ticker: str, accession_number: str, filing_date: str, 
                        filing_url: str, shares_added: int, eth_holdings: int):
    """Add a new processed filing to the database"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO filings_processed 
            (ticker, accession_number, filing_date, filing_url, shares_added, eth_holdings)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, accession_number) DO NOTHING
        ''', (ticker, accession_number, filing_date, filing_url, shares_added, eth_holdings))
        conn.commit()

def get_filings_count(ticker: str) -> int:
    """Get the number of processed filings for a ticker"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM filings_processed WHERE ticker = %s', (ticker,))
        result = cursor.fetchone()
        return result[0] if result else 0

def check_and_process_new_filings(ticker: str) -> Tuple[int, int]:
    """
    1) Get our most recent information about SBET
    2) Look up most recent 8-K filing with "item 8.01 other events" 
    3) If filing is newer than what we have, process it
    4) Return (current_eth_holdings, total_diluted_shares)
    """
    print(f"[INFO] Step 1: Getting current data for {ticker}")
    
    # Step 1: Get our most recent information about SBET
    company_data = get_company_data(ticker)
    if not company_data:
        raise HTTPException(
            status_code=404, 
            detail=f"No data found for {ticker}. Please initialize first."
        )
    
    current_total_shares, last_updated = company_data
    last_processed_accession = get_last_processed_filing(ticker)
    
    # Get current ETH holdings from last processed filing
    current_eth = 0
    if last_processed_accession:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT eth_holdings FROM filings_processed WHERE ticker = %s AND accession_number = %s',
                (ticker, last_processed_accession)
            )
            result = cursor.fetchone()
            if result:
                current_eth = result[0]
    
    print(f"[INFO] Current state: {current_total_shares:,} shares, {current_eth:,} ETH, last filing: {last_processed_accession}")
    
    # Step 2: Look up most recent 8-K filing from SEC
    print(f"[INFO] Step 2: Looking up latest 8-K filing for {ticker}")
    cik = get_cik_for_ticker(ticker)
    latest_8k_url = get_latest_8k_url(cik)
    
    if not latest_8k_url:
        print(f"[INFO] No 8-K filings found for {ticker}")
        return current_eth, current_total_shares
    
    # Extract accession number from the latest filing URL
    # URL format: /data/1981535/000164117225020521/form8-k.htm
    print(f"[DEBUG] Parsing URL: {latest_8k_url}")
    
    accession_match = re.search(r'/(\d{18})/', latest_8k_url)
    if accession_match:
        # Convert 18-digit format to standard dashed format
        acc_num = accession_match.group(1)
        latest_accession = f"{acc_num[:10]}-{acc_num[10:12]}-{acc_num[12:]}"
        print(f"[DEBUG] Extracted 18-digit: {acc_num} -> {latest_accession}")
    else:
        # Try standard dashed format
        accession_match = re.search(r'/(\d{10}-\d{2}-\d{6})/', latest_8k_url)
        if accession_match:
            latest_accession = accession_match.group(1)
            print(f"[DEBUG] Extracted dashed format: {latest_accession}")
        else:
            print(f"[WARN] Could not extract accession number from URL: {latest_8k_url}")
            # Let's see what patterns we can find
            all_numbers = re.findall(r'\d+', latest_8k_url)
            print(f"[DEBUG] All numbers found in URL: {all_numbers}")
            return current_eth, current_total_shares
    
    print(f"[INFO] Latest 8-K accession: {latest_accession}")
    
    # Step 3: Check if this filing is newer than what we have
    if latest_accession == last_processed_accession:
        print(f"[INFO] Latest 8-K already processed. No new data to extract.")
        return current_eth, current_total_shares
    
    print(f"[INFO] Step 3: New 8-K filing found! Processing: {latest_accession}")
    
    # Download and process the new filing
    filing_text = download_filing_text(latest_8k_url)
    if not filing_text:
        print(f"[WARN] Could not download filing text from: {latest_8k_url}")
        return current_eth, current_total_shares
    
    # Use extractfrompdf.py logic to get ETH holdings and new issued shares
    print(f"[INFO] Extracting data from filing text...")
    new_eth_holdings = extract_total_eth_holdings(filing_text)
    new_issued_shares = extract_diluted_shares_anywhere(filing_text)
    
    # Also try backup extraction
    try:
        from sec_edgar import extract_eth_and_shares
        backup_eth, backup_shares = extract_eth_and_shares(filing_text)
        if not new_eth_holdings and backup_eth:
            new_eth_holdings = backup_eth
        if not new_issued_shares and backup_shares:
            new_issued_shares = backup_shares
    except:
        pass
    
    # Update our values
    if new_eth_holdings:
        current_eth = new_eth_holdings
        print(f"[INFO] Updated ETH holdings: {current_eth:,}")
    
    if new_issued_shares:
        # Add new issued shares to our total diluted shares
        current_total_shares += new_issued_shares
        print(f"[INFO] Added {new_issued_shares:,} new shares. Total now: {current_total_shares:,}")
        
        # Update database with new total
        update_company_data(ticker, current_total_shares)
    
    # Record this filing as processed
    filing_date = datetime.now().strftime('%Y-%m-%d')
    add_processed_filing(ticker, latest_accession, filing_date, latest_8k_url, 
                        new_issued_shares or 0, new_eth_holdings or 0)
    
    print(f"[INFO] Step 4: Updated database. Final values: {current_eth:,} ETH, {current_total_shares:,} shares")
    
    return current_eth, current_total_shares

# API Routes
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    try:
        init_database()
        print("[INFO] PostgreSQL database initialized")
    except Exception as e:
        print(f"[ERROR] Database initialization failed: {e}")

@app.post("/api/initialize/{ticker}")
async def initialize_ticker(ticker: str, request: InitializeRequest):
    """Initialize a ticker with base diluted shares count"""
    ticker = ticker.upper()
    
    # Verify ticker exists
    try:
        get_cik_for_ticker(ticker)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found")
    
    # Initialize company data
    update_company_data(ticker, request.total_diluted_shares_outstanding)
    
    return {
        "message": f"Initialized {ticker} with {request.total_diluted_shares_outstanding:,} base diluted shares",
        "ticker": ticker,
        "base_shares": request.total_diluted_shares_outstanding
    }

@app.get("/api/analyze/{ticker}", response_model=MNAVResponse)
async def analyze_ticker(ticker: str):
    """Analyze a ticker and return MNAV metrics"""
    ticker = ticker.upper()
    
    try:
        # Check for new filings and get current data
        eth_holdings, diluted_shares = check_and_process_new_filings(ticker)
        
        # Get live prices
        eth_price = get_eth_price()
        stock_price = get_stock_price(ticker)
        
        # Calculate metrics
        treasury_value = eth_holdings * eth_price
        mnav_per_share = treasury_value / diluted_shares if diluted_shares > 0 else 0
        market_cap = stock_price * diluted_shares if diluted_shares > 0 else 0
        mnav_multiple = market_cap / treasury_value if treasury_value > 0 else 0
        
        # Get filing count
        filings_count = get_filings_count(ticker)
        
        return MNAVResponse(
            ticker=ticker,
            eth_price=eth_price,
            stock_price=stock_price,
            eth_holdings=eth_holdings,
            diluted_shares=diluted_shares,
            treasury_value=treasury_value,
            mnav_per_share=mnav_per_share,
            market_cap=market_cap,
            mnav_multiple=mnav_multiple,
            last_updated=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            filings_processed=filings_count
        )
        
    except Exception as e:
        print(f"[ERROR] Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/email")
async def send_email_report(request: EmailRequest):
    """Send MNAV report via email"""
    try:
        data = request.mnav_data
        
        subject = f"{data.ticker} MNAV Report"
        body = f"""
✅ {data.ticker} MNAV REPORT
Generated at: {data.last_updated}

ETH Price: ${data.eth_price:,.2f}
{data.ticker} Stock Price: ${data.stock_price:,.2f}

Aggregate ETH Holdings: {data.eth_holdings:,} ETH
Diluted Shares Outstanding: {data.diluted_shares:,}

Treasury Value: ${data.treasury_value:,.2f}
MNAV per Share: ${data.mnav_per_share:,.2f}
Market Cap: ${data.market_cap:,.2f}
MNAV Multiple (MarketCap / Treasury): {data.mnav_multiple:.2f}x

Filings Processed: {data.filings_processed}

Generated automatically by MNAV Analysis Tool.
"""

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = SENDER_EMAIL
        msg["To"] = request.email

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(MAILJET_USER, MAILJET_PASS)
            server.sendmail(SENDER_EMAIL, request.email, msg.as_string())

        return {"message": f"Email sent successfully to {request.email}"}
        
    except Exception as e:
        print(f"[ERROR] Email sending failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

@app.get("/api/status/{ticker}")
async def get_ticker_status(ticker: str):
    """Get current status and data for a ticker"""
    ticker = ticker.upper()
    
    company_data = get_company_data(ticker)
    if not company_data:
        return {"initialized": False, "ticker": ticker}
    
    total_shares, last_updated = company_data
    filings_count = get_filings_count(ticker)
    last_filing = get_last_processed_filing(ticker)
    
    return {
        "initialized": True,
        "ticker": ticker,
        "total_diluted_shares": total_shares,
        "last_updated": str(last_updated),
        "filings_processed": filings_count,
        "last_filing_accession": last_filing
    }

@app.get("/")
async def root():
    """API health check"""
    return {"message": "MNAV Analysis API is running", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)