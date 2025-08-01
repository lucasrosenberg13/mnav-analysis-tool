import os
import psycopg2
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
import openai

# Import utilities
from ticker_utils import get_cik_for_ticker
from gpt_extractor import extract_crypto_and_shares_with_gpt

# Simple 8-K finder function
def get_latest_8k_url(cik: str) -> Optional[Tuple[str, str, str]]:
    """Get the latest 8-K filing URL with Item 8.01"""
    SEC_API_BASE = "https://data.sec.gov"
    SEC_DOC_BASE = "https://www.sec.gov"
    
    padded_cik = str(cik).zfill(10)
    submissions_url = f"{SEC_API_BASE}/submissions/CIK{padded_cik}.json"
    
    try:
        resp = requests.get(submissions_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        accession_numbers = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])
        filing_dates = filings.get("filingDate", [])
        
        for form, acc, doc, date in zip(forms, accession_numbers, primary_docs, filing_dates):
            if form == "8-K":
                acc_nodash = acc.replace("-", "")
                filing_url = f"{SEC_DOC_BASE}/Archives/edgar/data/{int(cik)}/{acc_nodash}/{doc}"
                return filing_url, acc, date
        
        return None
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch filings for CIK {cik}: {e}")
        return None

app = FastAPI(title="MNAV Analysis API", version="2.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
SMTP_SERVER = "in-v3.mailjet.com"
SMTP_PORT = 587
MAILJET_USER = os.getenv("MAILJET_USER", "ad6944548828bc7ffc0582ffbb09fcb6")
MAILJET_PASS = os.getenv("MAILJET_PASS", "10a20df16440c695fbd8108d958dba80")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "Jsorkin123@gmail.com")

# OpenAI setup - handled in gpt_extractor.py

# PostgreSQL setup
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = f"postgresql://{os.getenv('PGUSER')}:{os.getenv('PGPASSWORD')}@{os.getenv('PGHOST')}:{os.getenv('PGPORT')}/{os.getenv('PGDATABASE')}"

# Ticker configuration - easily expandable for any crypto
TICKER_CONFIG = {
    'SBET': {
        'name': 'Sharplink Gaming',
        'crypto': 'ETH',
        'crypto_name': 'Ethereum',
        'coingecko_id': 'ethereum'
    },
    'MSTR': {
        'name': 'MicroStrategy', 
        'crypto': 'BTC',
        'crypto_name': 'Bitcoin',
        'coingecko_id': 'bitcoin'
    },
    'UPXI': {
        'name': 'UPEXI INC', 
        'crypto': 'SOL',
        'crypto_name': 'Solana',
        'coingecko_id': 'solana'
    },
    # Easy to add more:
    # 'EXAMPLE_SOL': {
    #     'name': 'Example Solana Company',
    #     'crypto': 'SOL',
    #     'crypto_name': 'Solana',
    #     'coingecko_id': 'solana'
    # },
    # 'EXAMPLE_DOGE': {
    #     'name': 'Example Dogecoin Company',
    #     'crypto': 'DOGE',
    #     'crypto_name': 'Dogecoin',
    #     'coingecko_id': 'dogecoin'
    # }
}

HEADERS = {"User-Agent": "MNAV-Script/2.0 lucasrosenberg@gmail.com"}

@contextmanager
def get_db_connection():
    """Database connection context manager"""
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

def init_database():
    """Initialize database tables with schema migration"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Create filings_processed table (old schema first)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS filings_processed (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(10) NOT NULL,
                accession_number VARCHAR(50) NOT NULL,
                filing_date DATE NOT NULL,
                filing_url TEXT NOT NULL,
                shares_added INTEGER DEFAULT 0,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, accession_number)
            )
        ''')
        
        # Add crypto_holdings column to filings_processed if it doesn't exist
        try:
            cursor.execute('''
                ALTER TABLE filings_processed 
                ADD COLUMN IF NOT EXISTS crypto_holdings INTEGER DEFAULT 0
            ''')
            print("[INFO] Added crypto_holdings column to filings_processed")
        except Exception as e:
            print(f"[INFO] Filings table migration: {e}")
        
        # Create company_data table (old schema first)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS company_data (
                ticker VARCHAR(10) PRIMARY KEY,
                total_diluted_shares BIGINT NOT NULL,
                base_shares BIGINT DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Add total_crypto_holdings column to company_data if it doesn't exist
        try:
            cursor.execute('''
                ALTER TABLE company_data 
                ADD COLUMN IF NOT EXISTS total_crypto_holdings INTEGER DEFAULT 0
            ''')
            print("[INFO] Added total_crypto_holdings column to company_data")
        except Exception as e:
            print(f"[INFO] Company data migration: {e}")
        
        # Fix base_shares column if it exists but has NULL values
        try:
            cursor.execute('''
                UPDATE company_data 
                SET base_shares = total_diluted_shares 
                WHERE base_shares IS NULL
            ''')
            cursor.execute('''
                ALTER TABLE company_data 
                ALTER COLUMN base_shares SET NOT NULL
            ''')
            print("[INFO] Fixed base_shares column")
        except Exception as e:
            print(f"[INFO] Base shares fix: {e}")
        
        conn.commit()
        print("[INFO] Database schema fully updated")

# Pydantic models
class MNAVResponse(BaseModel):
    ticker: str
    crypto_type: str
    crypto_price: float
    stock_price: float
    crypto_holdings: int
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
    initial_crypto_holdings: Optional[int] = 0

# Price fetching functions
def get_crypto_price(crypto_symbol: str) -> float:
    """Fetch crypto price from CoinGecko"""
    ticker_config = next((config for config in TICKER_CONFIG.values() 
                         if config['crypto'] == crypto_symbol.upper()), None)
    
    if not ticker_config:
        raise HTTPException(status_code=400, detail=f"Unsupported crypto: {crypto_symbol}")
    
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": ticker_config['coingecko_id'], "vs_currencies": "usd"}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()[ticker_config['coingecko_id']]["usd"]
    except Exception as e:
        print(f"[ERROR] CoinGecko API failed for {crypto_symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch {crypto_symbol} price")

def get_stock_price(ticker: str) -> float:
    """Fetch stock price from Finnhub"""
    FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "d23d8ipr01qgiro36h70d23d8ipr01qgiro36h7g")
    try:
        import urllib.request
        import urllib.parse
        import json
        
        params = urllib.parse.urlencode({
            'symbol': ticker,
            'token': FINNHUB_API_KEY
        })
        url = f"https://finnhub.io/api/v1/quote?{params}"
        
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            price = data['c']
            if not price:
                raise Exception("Price not found in Finnhub response")
            return float(price)
    except Exception as e:
        print(f"[ERROR] Finnhub fetch failed for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch {ticker} stock price")

# Database functions
def get_company_data(ticker: str) -> Optional[Tuple[int, int, str]]:
    """Get company data"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT total_diluted_shares, total_crypto_holdings, last_updated FROM company_data WHERE ticker = %s',
            (ticker,)
        )
        result = cursor.fetchone()
        return result if result else None

def update_company_data(ticker: str, total_shares: int, total_crypto: int = None):
    """Update company data"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if total_crypto is not None:
            cursor.execute('''
                INSERT INTO company_data (ticker, total_diluted_shares, base_shares, total_crypto_holdings, last_updated)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (ticker) 
                DO UPDATE SET 
                    total_diluted_shares = EXCLUDED.total_diluted_shares,
                    total_crypto_holdings = EXCLUDED.total_crypto_holdings,
                    last_updated = CURRENT_TIMESTAMP
            ''', (ticker, total_shares, total_shares, total_crypto))
        else:
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
    """Get last processed filing"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT accession_number FROM filings_processed WHERE ticker = %s ORDER BY filing_date DESC LIMIT 1',
            (ticker,)
        )
        result = cursor.fetchone()
        return result[0] if result else None

def add_processed_filing(ticker: str, accession_number: str, filing_date: str, 
                        filing_url: str, shares_added: int, crypto_holdings: int):
    """Add processed filing"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO filings_processed 
            (ticker, accession_number, filing_date, filing_url, shares_added, crypto_holdings)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, accession_number) DO NOTHING
        ''', (ticker, accession_number, filing_date, filing_url, shares_added, crypto_holdings))
        conn.commit()

def get_filings_count(ticker: str) -> int:
    """Get number of processed filings"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM filings_processed WHERE ticker = %s', (ticker,))
        result = cursor.fetchone()
        return result[0] if result else 0

def check_and_process_new_filings(ticker: str) -> Tuple[int, int]:
    """Main filing processing function using GPT extractor"""
    print(f"[INFO] Processing filings for {ticker}")
    
    company_data = get_company_data(ticker)
    if not company_data:
        raise HTTPException(
            status_code=404, 
            detail=f"No data found for {ticker}. Please initialize first."
        )
    
    current_total_shares, current_crypto_holdings, last_updated = company_data
    last_processed_accession = get_last_processed_filing(ticker)
    
    print(f"[INFO] Current: {current_total_shares:,} shares, {current_crypto_holdings:,} crypto, last filing: {last_processed_accession}")
    
    cik = get_cik_for_ticker(ticker)
    filing_info = get_latest_8k_url(cik)
    
    if not filing_info:
        print(f"[INFO] No recent 8-K filings found for {ticker}")
        return current_crypto_holdings, current_total_shares
    
    filing_url, accession_number, filing_date = filing_info
    print(f"[INFO] Latest 8-K: {accession_number} from {filing_date}")
    
    if accession_number == last_processed_accession:
        print(f"[INFO] Filing already processed")
        return current_crypto_holdings, current_total_shares
    
    print(f"[INFO] Processing new filing: {accession_number}")
    
    # Get crypto info for this ticker
    config = TICKER_CONFIG.get(ticker.upper())
    crypto_symbol = config['crypto']
    crypto_name = config['crypto_name']
    
    # Use the crypto-specific GPT extractor
    try:
        shares_sold, new_crypto_holdings = extract_crypto_and_shares_with_gpt(
            filing_url, crypto_symbol, crypto_name
        )
        print(f"[DEBUG] GPT Extracted - Shares: {shares_sold}, {crypto_symbol}: {new_crypto_holdings}")
    except Exception as e:
        print(f"[ERROR] GPT extraction failed: {e}")
        return current_crypto_holdings, current_total_shares
    
    if new_crypto_holdings is not None:
        current_crypto_holdings = new_crypto_holdings
        print(f"[INFO] Updated crypto holdings: {current_crypto_holdings:,}")
    
    if shares_sold is not None:
        current_total_shares += shares_sold
        print(f"[INFO] Added {shares_sold:,} shares. Total now: {current_total_shares:,}")
    
    update_company_data(ticker, current_total_shares, current_crypto_holdings)
    add_processed_filing(ticker, accession_number, filing_date, filing_url, 
                        shares_sold or 0, new_crypto_holdings or 0)
    
    print(f"[INFO] Complete: {current_crypto_holdings:,} crypto, {current_total_shares:,} shares")
    
    return current_crypto_holdings, current_total_shares

# API Routes
@app.on_event("startup")
async def startup_event():
    """Initialize database"""
    try:
        init_database()
        print("[INFO] Database initialized")
    except Exception as e:
        print(f"[ERROR] Database initialization failed: {e}")

@app.post("/api/initialize/{ticker}")
async def initialize_ticker(ticker: str, request: InitializeRequest):
    """Initialize a ticker"""
    ticker = ticker.upper()
    
    if ticker not in TICKER_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unsupported ticker: {ticker}")
    
    try:
        get_cik_for_ticker(ticker)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found")
    
    update_company_data(ticker, request.total_diluted_shares_outstanding, request.initial_crypto_holdings)
    
    config = TICKER_CONFIG[ticker]
    return {
        "message": f"Initialized {ticker} with {request.total_diluted_shares_outstanding:,} shares and {request.initial_crypto_holdings:,} {config['crypto']}",
        "ticker": ticker,
        "crypto_type": config['crypto']
    }

@app.get("/api/analyze/{ticker}", response_model=MNAVResponse)
async def analyze_ticker(ticker: str):
    """Analyze a ticker"""
    ticker = ticker.upper()
    
    if ticker not in TICKER_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unsupported ticker: {ticker}")
    
    try:
        config = TICKER_CONFIG[ticker]
        
        crypto_holdings, diluted_shares = check_and_process_new_filings(ticker)
        
        crypto_price = get_crypto_price(config['crypto'])
        stock_price = get_stock_price(ticker)
        
        treasury_value = crypto_holdings * crypto_price
        mnav_per_share = treasury_value / diluted_shares if diluted_shares > 0 else 0
        market_cap = stock_price * diluted_shares if diluted_shares > 0 else 0
        mnav_multiple = market_cap / treasury_value if treasury_value > 0 else 0
        
        filings_count = get_filings_count(ticker)
        
        return MNAVResponse(
            ticker=ticker,
            crypto_type=config['crypto'],
            crypto_price=crypto_price,
            stock_price=stock_price,
            crypto_holdings=crypto_holdings,
            diluted_shares=diluted_shares,
            treasury_value=treasury_value,
            mnav_per_share=mnav_per_share,
            market_cap=market_cap,
            mnav_multiple=mnav_multiple,
            last_updated=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            filings_processed=filings_count
        )
        
    except Exception as e:
        print(f"[ERROR] Analysis failed for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/email")
async def send_email_report(request: EmailRequest):
    """Send email report"""
    try:
        data = request.mnav_data
        
        subject = f"{data.ticker} MNAV Report"
        body = f"""
✅ {data.ticker} MNAV REPORT
Generated at: {data.last_updated}

{data.crypto_type} Price: ${data.crypto_price:,.2f}
{data.ticker} Stock Price: ${data.stock_price:,.2f}

Aggregate {data.crypto_type} Holdings: {data.crypto_holdings:,} {data.crypto_type}
Diluted Shares Outstanding: {data.diluted_shares:,}

Treasury Value: ${data.treasury_value:,.2f}
MNAV per Share: ${data.mnav_per_share:,.2f}
Market Cap: ${data.market_cap:,.2f}
MNAV Multiple: {data.mnav_multiple:.2f}x

Filings Processed: {data.filings_processed}

Generated by MNAV Analysis Tool.
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
        print(f"[ERROR] Email failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

@app.get("/api/status/{ticker}")
async def get_ticker_status(ticker: str):
    """Get ticker status"""
    ticker = ticker.upper()
    
    if ticker not in TICKER_CONFIG:
        return {"initialized": False, "ticker": ticker, "error": "Unsupported ticker"}
    
    company_data = get_company_data(ticker)
    if not company_data:
        return {"initialized": False, "ticker": ticker}
    
    total_shares, total_crypto, last_updated = company_data
    filings_count = get_filings_count(ticker)
    last_filing = get_last_processed_filing(ticker)
    
    return {
        "initialized": True,
        "ticker": ticker,
        "crypto_type": TICKER_CONFIG[ticker]['crypto'],
        "total_diluted_shares": total_shares,
        "total_crypto_holdings": total_crypto,
        "last_updated": str(last_updated),
        "filings_processed": filings_count,
        "last_filing_accession": last_filing
    }

@app.get("/")
async def root():
    """Health check"""
    return {
        "message": "MNAV Analysis API v2.0 - GPT Powered", 
        "version": "2.0.0",
        "supported_tickers": list(TICKER_CONFIG.keys())
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)