import os
import re
import requests
from bs4 import BeautifulSoup
from openai import OpenAI


api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable is not set")

client = OpenAI(api_key-api_key)

HEADERS = {"User-Agent": "SBET-MNAV-Script/1.0 lucasrosenberg@gmail.com"}


def get_visible_text(soup):
    for elem in soup(['script', 'style']):
        elem.decompose()
    text = soup.get_text(separator=' ')
    return ' '.join(text.split())


def extract_section(text, start_header="Item 8.01 Other Items"):
    pattern = re.compile(
        rf"({re.escape(start_header)})(.*?)(?=Item\\s+\\d+\\.\\d+|SIGNATURE|$)",
        re.IGNORECASE | re.DOTALL
    )
    match = pattern.search(text)
    if match:
        return match.group(2).strip()
    return text


def extract_crypto_and_shares_with_gpt(sec_url, crypto_symbol="ETH", crypto_name="Ethereum"):
    """
    Downloads an SEC 8-K filing, extracts the relevant section, and uses GPT to extract shares and crypto holdings.
    
    Args:
        sec_url: URL to the SEC filing
        crypto_symbol: The crypto symbol to look for (ETH, BTC, SOL, etc.)
        crypto_name: Full name of the cryptocurrency (Ethereum, Bitcoin, Solana, etc.)
    
    Returns: (shares: int or None, crypto_holdings: int or None)
    """
    response = requests.get(sec_url, headers=HEADERS)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    filing_text = get_visible_text(soup)
    relevant_text = extract_section(filing_text)

    prompt = (
        "You are an expert financial analyst. I will provide you with a section of an SEC filing. "
        "Please extract the following two pieces of information from the document:\n\n"
        f"1. The number of Common ATM shares sold (if available).\n"
        f"2. The aggregate {crypto_name} ({crypto_symbol}) holdings reported by the company (if available).\n\n"
        "Please provide your answer in the following format:\n\n"
        "Common ATM shares sold: [number or 'Not found']\n"
        f"Aggregate {crypto_symbol} holdings: [amount or 'Not found']\n\n"
        "If either value is not explicitly stated in the document, say 'Not found' for that item. Only use information found in the provided text.\n\n"
        "Here is the relevant section of the SEC filing:\n\n"
        f"{relevant_text[:12000]}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        content = response.choices[0].message.content.strip()
        print(f"[DEBUG] GPT Response: {content}")
    except Exception as e:
        print(f"[ERROR] OpenAI API call failed: {e}")
        return None, None

    # Parse GPT output
    shares = None
    crypto_holdings = None
    shares_match = re.search(r"Common ATM shares sold:\s*([\d,]+|Not found)", content, re.IGNORECASE)
    crypto_match = re.search(rf"Aggregate {crypto_symbol} holdings:\s*([\d,]+|Not found)", content, re.IGNORECASE)
    
    if shares_match:
        val = shares_match.group(1).replace(",", "").strip()
        if val.lower() != "not found" and val.isdigit():
            shares = int(val)
    if crypto_match:
        val = crypto_match.group(1).replace(",", "").strip()
        if val.lower() != "not found" and val.isdigit():
            crypto_holdings = int(val)
    
    return shares, crypto_holdings

# Keep the old function for backward compatibility
def extract_eth_and_shares_with_gpt(sec_url):
    """
    Legacy function for ETH extraction - calls the new generic function
    """
    return extract_crypto_and_shares_with_gpt(sec_url, "ETH", "Ethereum")