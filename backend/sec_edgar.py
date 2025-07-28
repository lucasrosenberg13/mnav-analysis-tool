import requests
import re
from typing import Optional
from bs4 import BeautifulSoup

SEC_CIK = "1981535"  # Sharplink Gaming (SBET), no leading zeros
SEC_API_BASE = "https://data.sec.gov"
SEC_DOC_BASE = "https://www.sec.gov"
HEADERS = {"User-Agent": "SBET-MNAV-Script/1.0 lucasrosenberg@gmail.com"}


def get_latest_8k_url(cik):
    """
    Fetch the most recent 8-K filing URL for a given CIK from EDGAR that contains 'Item 8.01 Other Events'.
    Iterates through all recent 8-Ks until the section is found.
    Returns the full URL to the primary document (HTML, PDF, or TXT), or None if not found.
    """
    padded_cik = str(cik).zfill(10)
    submissions_url = f"{SEC_API_BASE}/submissions/CIK{padded_cik}.json"
    resp = requests.get(submissions_url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    accession_numbers = filings.get("accessionNumber", [])
    primary_docs = filings.get("primaryDocument", [])
    for form, acc, doc in zip(forms, accession_numbers, primary_docs):
        if form == "8-K":
            acc_nodash = acc.replace("-", "")
            filing_url = f"{SEC_DOC_BASE}/Archives/edgar/data/{int(cik)}/{acc_nodash}/{doc}"
            print(f"[DEBUG] Checking SEC 8-K URL: {filing_url}")
            text = download_filing_text(filing_url)
            if text:
                # Robustly extract all text from HTML/XML if needed
                if text.lstrip().lower().startswith("<html") or text.lstrip().startswith("<?xml"):
                    soup = BeautifulSoup(text, "html.parser")
                    full_text = soup.get_text(separator=" ", strip=True)
                else:
                    full_text = text
                # Normalize whitespace and case
                norm_text = re.sub(r"\s+", " ", full_text).lower()
                # Look for item 8.01 and other events together, allowing for some words in between
                if re.search(r"item\s*8\.01.*other events", norm_text):
                    print(f"[DEBUG] Found 'Item 8.01 Other Events' in: {filing_url}")
                    return filing_url
    print("[DEBUG] No 8-K with 'Item 8.01 Other Events' found in recent filings.")
    return None


def download_filing_text(url: str) -> Optional[str]:
    """
    Download the text of the filing (HTML, TXT, or PDF as bytes).
    If PDF, returns None (let main script handle PDF parsing).
    """
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")
    if "pdf" in content_type:
        # Save PDF to disk for parsing
        with open("latest_sbet_8k.pdf", "wb") as f:
            f.write(resp.content)
        return None
    else:
        return resp.text

def extract_eth_and_shares(text: str):
    """
    Extracts the ETH Holdings and total shares sold from the 8-K filing text.
    Returns (eth_holdings, shares_sold) as integers if found, otherwise None for each value.
    """
    eth_holdings = None
    shares_sold = None
    # ETH Holdings pattern (e.g., 'aggregate ETH Holdings were 280,706')
    eth_match = re.search(r"aggregate ETH Holdings were ([\d,]+)", text, re.IGNORECASE)
    if eth_match:
        eth_holdings = int(eth_match.group(1).replace(",", ""))
    # Shares sold pattern (e.g., 'sold a total of 24,572,195 shares')
    shares_match = re.search(r"sold a total of ([\d,]+) shares", text, re.IGNORECASE)
    if shares_match:
        shares_sold = int(shares_match.group(1).replace(",", ""))
    return eth_holdings, shares_sold
