import requests
import functools

@functools.lru_cache(maxsize=1000)
def get_cik_for_ticker(ticker):
    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {
        "User-Agent": "MNAV-Script/1.0 lucasrosenberg@gmail.com"
    }
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    mapping = resp.json()
    for entry in mapping.values():
        if entry['ticker'].lower() == ticker.lower():
            return str(entry['cik_str']).zfill(10)
    raise ValueError(f"CIK not found for ticker {ticker}")
