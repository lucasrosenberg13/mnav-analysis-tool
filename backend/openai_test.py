import os
from dotenv import load_dotenv
import openai
import requests
from bs4 import BeautifulSoup

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    raise ValueError('Please set the OPENAI_API_KEY environment variable in your .env file.')

# Configure OpenAI client
openai.api_key = api_key

# --- Step 1: Download and extract filing text ---
# SEC_URL = "https://www.sec.gov/Archives/edgar/data/0001050446/000095017025097081/mstr-20250616.htm"
SEC_URL = "https://www.sec.gov/Archives/edgar/data/0001981535/000164117225020521/form8-k.htm"

headers = {"User-Agent": "SBET-MNAV-Script/1.0 lucasrosenberg@gmail.com"}
response = requests.get(SEC_URL, headers=headers)
response.raise_for_status()
soup = BeautifulSoup(response.text, 'html.parser')

# Extract visible text from the filing (may include some extra whitespace)
def get_visible_text(soup):
    # Remove script and style elements
    for elem in soup(['script', 'style']):
        elem.decompose()
    # Get text
    text = soup.get_text(separator=' ')
    # Collapse whitespace
    return ' '.join(text.split())

filing_text = get_visible_text(soup)

import re

# Extract only the text between 'Item 8.01 Other Items' and the next section header or 'SIGNATURE'
def extract_section(text, start_header):
    pattern = re.compile(
        rf"({re.escape(start_header)})(.*?)(?=Item\s+\d+\.\d+|SIGNATURE|$)",
        re.IGNORECASE | re.DOTALL
    )
    match = pattern.search(text)
    if match:
        # Return only the section content, not the header
        return match.group(2).strip()
    return text  # fallback to full text if not found

relevant_text = extract_section(filing_text, "Item 8.01 Other Items")

# --- Step 2: Prepare the prompt ---
prompt = (
    "You are an expert financial analyst. I will provide you with a section of an SEC filing. "
    "Please extract the following two pieces of information from the document:\n\n"
    "1. The number of Common ATM shares sold (if available).\n"
    "2. The aggregate ETH Holding (ETH) reported by the company (if available).\n\n"
    "Please provide your answer in the following format:\n\n"
    "Common ATM shares sold: [number or 'Not found']\n"
    "Aggregate ETH holdings: [amount or 'Not found']\n\n"
    "If either value is not explicitly stated in the document, say 'Not found' for that item. Only use information found in the provided text.\n\n"
    "Here is the relevant section of the SEC filing:\n\n"
    f"{relevant_text[:12000]}"
)

# --- Step 3: Send to OpenAI API ---
print("\n--- Prompt Sent to OpenAI ---\n")
print(prompt)
print("\n--- End of Prompt ---\n")

try:
    response = openai.chat.completions.create(
        model="gpt-4o",  # Use GPT-4o for best results, or fallback to gpt-3.5-turbo
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=300,
        temperature=0
    )
    print("\n--- Extraction Result ---")
    print(response.choices[0].message.content.strip())
except Exception as e:
    print('Error communicating with OpenAI:', e)
