import re
import requests
import smtplib
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
# test
from sec_edgar import get_latest_8k_url, download_filing_text
from ticker_utils import get_cik_for_ticker
import argparse

# Mailjet SMTP settings
SMTP_SERVER = "in-v3.mailjet.com"
SMTP_PORT = 587
MAILJET_USER = "ad6944548828bc7ffc0582ffbb09fcb6"
MAILJET_PASS = "10a20df16440c695fbd8108d958dba80"
SENDER_EMAIL = "Jsorkin123@gmail.com"
RECEIVER_EMAIL = "Jsorkin123@gmail.com"

# -----------------------------
# PDF text extraction
# -----------------------------

# -----------------------------
# Extract ETH holdings & diluted shares
# -----------------------------
def extract_total_eth_holdings(text):
    if text.lstrip().lower().startswith("<html") or text.lstrip().startswith("<?xml"):
        soup = BeautifulSoup(text, "html.parser")
        candidates = []
        for tag in soup.find_all(string=True):
            if "eth" in tag.lower():
                patterns = [
                    r'ETH Holdings (?:were|rose to|Increase to|totaled|:)?\s*([\d,]+)',
                    r'aggregate ETH Holdings (?:were|was|totaled)?\s*([\d,]+)',
                    r'holdings rose to\s*([\d,]+)\s*ETH',
                    r'holdings.*?([\d,]+)\s*ETH',
                    r'ETH Holdings.*?([\d,]+)'
                ]
                for pat in patterns:
                    match = re.search(pat, tag, re.IGNORECASE)
                    if match:
                        n = match.group(1)
                        n_clean = n.replace(",", "").strip()
                        if n_clean and n_clean.isdigit():
                            val = int(n_clean)
                            if 1000 < val < 2_000_000:
                                candidates.append(val)
                nums = re.findall(r"[\d,]+", tag)
                for n in nums:
                    n_clean = n.replace(",", "").strip()
                    if not n_clean or not n_clean.isdigit():
                        continue
                    val = int(n_clean)
                    if 1000 < val < 2_000_000:
                        candidates.append(val)
        if candidates:
            return max(candidates)
    patterns = [
        r'ETH Holdings (?:were|rose to|Increase to|totaled|:)?\s*([\d,]+)',
        r'aggregate ETH Holdings (?:were|was|totaled)?\s*([\d,]+)',
        r'holdings rose to\s*([\d,]+)\s*ETH',
        r'holdings.*?([\d,]+)\s*ETH',
        r'ETH Holdings.*?([\d,]+)'
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            n = match.group(1)
            n_clean = n.replace(",", "").strip()
            if n_clean and n_clean.isdigit():
                return int(n_clean)
    return None

def extract_diluted_shares_anywhere(text):
    # Not robust yet – placeholder for future logic
    if text.lstrip().lower().startswith("<html") or text.lstrip().startswith("<?xml"):
        soup = BeautifulSoup(text, "html.parser")
        candidates = []
        for tag in soup.find_all(string=True):
            if "diluted" in tag.lower() or "shares" in tag.lower():
                nums = re.findall(r"[\d,]{6,}", tag)
                for n in nums:
                    n_clean = n.replace(",", "").strip()
                    if not n_clean or not n_clean.isdigit():
                        continue
                    val = int(n_clean)
                    if 50_000_000 <= val <= 200_000_000:
                        candidates.append(val)
        if candidates:
            return max(candidates)
    patterns = [
        r'Assumed Diluted Shares Outstanding.*?([\d,]{6,})',
        r'fully diluted.*?([\d,]{6,})',
        r'shares outstanding.*?([\d,]{6,})'
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = int(m.group(1).replace(",", ""))
            if 50_000_000 <= val <= 200_000_000:
                return val
    all_nums = [int(n.replace(",", "")) for n in re.findall(r"\d{1,3}(?:,\d{3})+", text)]
    plausible = [n for n in all_nums if 50_000_000 <= n <= 200_000_000]
    if plausible:
        return max(plausible)
    return None

# -----------------------------
# BTC holdings & Common ATM shares extraction for MSTR

def extract_btc_and_shares(text):
    import re
    from bs4 import BeautifulSoup
    btc_holdings = None
    shares_sold = None

    def norm(s):
        return re.sub(r'[^a-z0-9]', '', s.strip().lower())

    if text.lstrip().lower().startswith("<html") or text.lstrip().startswith("<?xml"):
        soup = BeautifulSoup(text, "html.parser")
        # --- Find the anchor node for 'Item 8.01 Other Events.' ---
        anchor = None
        # Search for the anchor by block tag, joining all text (handles split/formatting)
        for tag in soup.find_all(['p', 'div', 'span']):
            full_text = tag.get_text(separator=' ', strip=True).lower().replace('\xa0', ' ')
            norm_text = re.sub(r'\s+', ' ', full_text)
            if 'item 8.01 other events' in norm_text:
                anchor = tag
                print(f"[DEBUG] Found anchor for 'Item 8.01 Other Events.': {anchor}")
                break
        if not anchor:
            print("[DEBUG] Could not find 'Item 8.01 Other Events.' anchor; skipping targeted extraction.")
            return btc_holdings, shares_sold
        # --- Collect tables after anchor, before next 'Item' section ---
        tables_to_check = []
        node = anchor
        while node is not None:
            node = node.find_next_sibling()
            if node is None:
                break
            # Stop at next major 'Item' section
            if node.get_text(strip=True).lower().startswith("item ") and "other events" not in node.get_text(strip=True).lower():
                print(f"[DEBUG] Stopping at section: {node.get_text(strip=True)[:40]}")
                break
            if node.name == "table":
                tables_to_check.append(node)
        print(f"[DEBUG] Found {len(tables_to_check)} tables after 'Item 8.01 Other Events.'")
        for table in tables_to_check:
            rows = table.find_all("tr")
            # --- Build composite headers from first 2-3 rows ---
            header_matrix = []
            for row in rows[:3]:
                cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
                header_matrix.append(cells)
            if not header_matrix:
                continue
            max_cols = max(len(row) for row in header_matrix)
            composite_headers = []
            for col in range(max_cols):
                col_header = " ".join(header_matrix[row][col] if col < len(header_matrix[row]) else "" for row in range(len(header_matrix)))
                composite_headers.append(norm(col_header))
            print(f"[DEBUG] Composite headers: {composite_headers}")
            # Map normalized composite headers to column indices
            header_map = {h: idx for idx, h in enumerate(composite_headers)}
            # --- Extract BTC Holdings ---
            btc_col = None
            for h, idx in header_map.items():
                if "aggregatebtcholdings" in h:
                    btc_col = idx
                    print(f"[DEBUG] Found BTC Holdings column at idx {btc_col}: {h}")
                    break
            if btc_col is not None:
                # Find first plausible data row (skip header rows)
                for row in rows[3:]:
                    cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
                    if not cells or len(cells) <= btc_col:
                        continue
                    btc_candidate = cells[btc_col]
                    m = re.search(r"([\d,]+)", btc_candidate)
                    if m and btc_candidate.strip():
                        btc_holdings = int(m.group(1).replace(",", ""))
                        print(f"[DEBUG] Extracted Aggregate BTC Holdings: {btc_holdings}")
                        break
            # --- Extract Shares Sold (legacy logic, if needed) ---
            shares_col = None
            for h, idx in header_map.items():
                if "sharessold" in h:
                    shares_col = idx
                    print(f"[DEBUG] Found Shares Sold column at idx {shares_col}: {h}")
                    break
            if shares_col is not None:
                for row in rows[3:]:
                    cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
                    if not cells or len(cells) <= shares_col:
                        continue
                    # Optional: add a more robust row match if needed
                    share_candidate = cells[shares_col]
                    m = re.search(r"([\d,]+)", share_candidate)
                    if m and share_candidate.strip():
                        shares_sold = int(m.group(1).replace(",", ""))
                        print(f"[DEBUG] Extracted Shares Sold: {shares_sold}")
                        break
            if btc_holdings is not None or shares_sold is not None:
                return btc_holdings, shares_sold
        # Fallback to old logic if not found
        if btc_holdings is None or shares_sold is None:
            print("[DEBUG] Fallback extraction triggered")
    return btc_holdings, shares_sold

# -----------------------------
# Fetch live ETH price
# -----------------------------
def get_eth_price_usd():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": "ethereum", "vs_currencies": "usd"}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()["ethereum"]["usd"]
    except Exception as e:
        print(f"[WARN] CoinGecko API failed: {e}")
        return None

# -----------------------------
# Fetch SBET stock price via TradingView
# -----------------------------
def get_sbet_stock_price_tradingview():
    try:
        url = "https://www.tradingview.com/symbols/NASDAQ-SBET/"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        match = re.search(r'"regularMarketPrice":\s*([\d.]+)', resp.text)
        if match:
            return float(match.group(1))
        alt_match = re.search(r'"price":\s*([\d.]+)', resp.text)
        if alt_match:
            return float(alt_match.group(1))
    except Exception as e:
        print(f"[WARN] TradingView fetch failed: {e}")
        return None

# -----------------------------
# Metric calculators
# -----------------------------
def calc_treasury_value(eth_count, eth_price):
    return eth_count * eth_price

def calc_mnav_per_share(treasury_value, diluted_shares):
    return treasury_value / diluted_shares

def calc_market_cap(stock_price, diluted_shares):
    return stock_price * diluted_shares

def calc_mnav_multiple(market_cap, treasury_value):
    return market_cap / treasury_value

# -----------------------------
# Email sender via Mailjet
# -----------------------------
def send_email_report(mnav_per_share, treasury_value, market_cap, mnav_multiple, eth_price, stock_price):
    subject = "SBET MNAV Report"
    body = f"""
✅ SBET MNAV REPORT

ETH Price: ${eth_price:,.2f}
SBET Stock Price: ${stock_price:,.2f}

Treasury Value: ${treasury_value:,.2f}
MNAV per Share: ${mnav_per_share:,.2f}
Market Cap: ${market_cap:,.2f}
MNAV Multiple (MarketCap / Treasury): {mnav_multiple:.2f}x

Generated automatically by your MNAV script.
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(MAILJET_USER, MAILJET_PASS)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print(f"[INFO] ✅ Email sent successfully to {RECEIVER_EMAIL}")
    except Exception as e:
        print(f"[WARN] Failed to send email: {e}")

# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated SEC 8-K/ETH extraction for any ticker")
    parser.add_argument("--ticker", type=str, help="Stock ticker symbol (e.g., SBET, MSFT, AAPL)")
    args = parser.parse_args()
    ticker = args.ticker.upper() if args.ticker else input("Enter ticker symbol: ").strip().upper()
    cik = get_cik_for_ticker(ticker)

    print(f"[INFO] Fetching latest 8-K for {ticker} (CIK: {cik}) from SEC EDGAR...")
    sec_url = get_latest_8k_url(cik)
    text = None
    if sec_url:
        print(f"[INFO] Latest 8-K URL: {sec_url}")
        text = download_filing_text(sec_url)
    if not text:
        raise RuntimeError("Failed to fetch or parse latest 8-K from SEC EDGAR.")

    print("\n[DEBUG] First 400 chars of filing text:\n", text[:400], "\n")

    from sec_edgar import extract_eth_and_shares

    # Use new robust extraction from 8-K for both ETH and shares sold
    extracted_eth, shares_sold = extract_eth_and_shares(text)
    extracted_shares = extract_diluted_shares_anywhere(text)

    total_eth = extracted_eth if extracted_eth else 0

    if shares_sold:
        diluted_shares = shares_sold
        print(f"[INFO] Shares sold from ATM Facility (8-K) → Shares: {diluted_shares:,}")
    else:
        diluted_shares = extracted_shares if extracted_shares else 0
        if extracted_shares:
            print(f"[INFO] Extracted diluted shares from filing → Shares: {extracted_shares:,}")
        else:
            print("[WARN] Could not determine diluted shares outstanding.")

    if extracted_eth:
        print(f"[INFO] Extracted ETH from filing → ETH: {extracted_eth:,}")

    eth_price = get_eth_price_usd() or float(input("Enter ETH price manually: "))

    def get_stock_price_tradingview(ticker):
        try:
            url = f"https://www.tradingview.com/symbols/NASDAQ-{ticker}/"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            match = re.search(r'"regularMarketPrice":\s*([\d.]+)', resp.text)
            if match:
                return float(match.group(1))
            alt_match = re.search(r'"price":\s*([\d.]+)', resp.text)
            if alt_match:
                return float(alt_match.group(1))
        except Exception as e:
            print(f"[WARN] TradingView fetch failed: {e}")
            return None
    stock_price = get_stock_price_tradingview(ticker) or float(input(f"Enter {ticker} stock price manually: "))

    treasury_value = calc_treasury_value(total_eth, eth_price)
    mnav_per_share = calc_mnav_per_share(treasury_value, diluted_shares) if diluted_shares else 0
    market_cap = calc_market_cap(stock_price, diluted_shares) if diluted_shares else 0
    mnav_multiple = calc_mnav_multiple(market_cap, treasury_value) if treasury_value else 0

    print("\n[DEBUG] Final Values Used:")
    print(f"  ETH Holdings: {total_eth:,} ETH")
    print(f"  ETH Price: ${eth_price:,.2f}")
    print(f"  {ticker} Stock Price: ${stock_price:,.2f}")
    print(f"  Diluted Shares: {diluted_shares:,}")

    print("\n✅ MNAV METRICS:")
    print(f"  Treasury Value: ${treasury_value:,.2f}")
    print(f"  MNAV per Share: ${mnav_per_share:,.2f}")
    print(f"  Market Cap: ${market_cap:,.2f}")
    print(f"  MNAV Multiple: {mnav_multiple:.2f}x")

    # Send email after printing
    # send_email_report(mnav_per_share, treasury_value, market_cap, mnav_multiple, eth_price, stock_price)

