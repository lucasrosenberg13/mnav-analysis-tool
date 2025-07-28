# Simple test - save as test_finnhub.py
import urllib.request
import urllib.parse
import json
import time

def get_stock_price(symbol, api_key):
    """Get stock price using only built-in Python libraries"""
    params = urllib.parse.urlencode({
        'symbol': symbol,
        'token': api_key
    })
    
    url = f"https://finnhub.io/api/v1/quote?{params}"
    
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            return {
                'symbol': symbol,
                'price': data['c'],
                'change': data['d'],
                'percent_change': data['dp'],
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            }
    except Exception as e:
        print(f"Error getting {symbol}: {e}")
        return None

# Test it
if __name__ == "__main__":
    # Replace with your actual Finnhub API key
    API_KEY = "d23d8ipr01qgiro36h70d23d8ipr01qgiro36h7g"
    
    symbols = ['MSTR', 'SBET']
    
    print("Testing Finnhub API...")
    for symbol in symbols:
        result = get_stock_price(symbol, API_KEY)
        if result:
            print(f"{symbol}: ${result['price']:.2f} ({result['percent_change']:+.2f}%)")
        else:
            print(f"Failed to get {symbol}")
        
        # Rate limiting - wait 1 second between calls
        time.sleep(1)