import yfinance as yf
import feedparser
from functools import lru_cache

@lru_cache(maxsize=32)
def fetch_market_data(symbol: str) -> str:
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d")
        if data.empty:
            return f"Could not find market data for symbol: {symbol}"
            
        last_price = data['Close'].iloc[-1]
        return f"Current price of {symbol} is: ${last_price:,.2f}"
    except Exception as e:
        return f"Failed to fetch market data: {e}"

def intelligence_agent(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Fetches real-time market data (stocks/crypto) or breaking news headlines.
    """
    action = parameters.get("action", "market").lower()
    
    if action == "market":
        symbol = parameters.get("symbol", "")
        if not symbol:
            return "Must specify a ticker symbol (e.g., AAPL for Apple, BTC-USD for Bitcoin)."
            
        return fetch_market_data(symbol)
            
    elif action == "news":
        topic = parameters.get("topic", "world").lower()
                                     
        url = "https://news.google.com/rss"
        if topic and topic != "world":
            url = f"https://news.google.com/rss/search?q={topic}"
            
        try:
            feed = feedparser.parse(url)
            if not feed.entries:
                return f"No news found for topic: {topic}"
                
            headlines = []
            for i, entry in enumerate(feed.entries[:5]):
                headlines.append(f"{i+1}. {entry.title}")
                
            return f"Top 5 news headlines for '{topic}':\n" + "\n".join(headlines)
        except Exception as e:
            return f"Failed to fetch news: {e}"
            
    else:
        return f"Unknown intelligence action: {action}"
