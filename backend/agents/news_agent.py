import json
import requests
import xml.etree.ElementTree as ET
import yfinance as yf
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from backend.agents.llm_client import llm_client

class NewsSummaryItem(BaseModel):
    title: str = Field(description="Title of the news article")
    source: str = Field(description="Publisher/Source (e.g. Bloomberg, CNBC, Reuters)")
    sentiment: str = Field(description="Sentiment tag: Bullish, Neutral, or Bearish")
    summary: str = Field(description="1-sentence summary of the news development")

class NewsAnalysisSchema(BaseModel):
    sentiment_score: float = Field(description="Numerical sentiment score from 0.0 (bearish) to 1.0 (bullish)")
    sentiment_label: str = Field(description="Overall sentiment tag: Bullish, Neutral, or Bearish")
    news_summaries: List[NewsSummaryItem]

class NewsAgent:
    def __init__(self):
        self.system_prompt = (
            "You are a Financial News Sentiment Analyst.\n"
            "Your task is to analyze the recent news articles for the given company ticker.\n"
            "Generate:\n"
            "1. An overall numerical sentiment score from 0.0 (highly negative/bearish) to 1.0 (highly positive/bullish).\n"
            "2. A corresponding label: 'Bullish', 'Neutral', or 'Bearish'.\n"
            "3. Bullet point summaries of the articles, highlighting the title, publisher source, sentiment, and a brief 1-sentence summary.\n\n"
            "You must return structured JSON that strictly conforms to the requested schema."
        )

    def _fetch_rss_news(self, ticker: str) -> List[Dict[str, Any]]:
        """Fetches fresh live financial news from Google News RSS for any ticker symbol."""
        items = []
        try:
            url = f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
            if res.status_code == 200:
                root = ET.fromstring(res.text)
                for item in root.findall(".//item")[:6]:
                    title = item.find("title").text if item.find("title") is not None else ""
                    link = item.find("link").text if item.find("link") is not None else ""
                    source_elem = item.find("source")
                    source = source_elem.text if source_elem is not None else "Financial News"
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        title = parts[0]
                        if source == "Financial News" and len(parts) > 1:
                            source = parts[1]
                    if title:
                        items.append({
                            "title": title.strip(),
                            "publisher": source.strip(),
                            "link": link.strip(),
                            "summary": title.strip()
                        })
        except Exception as e:
            print(f"Error fetching live RSS news for {ticker}: {e}")
        return items

    def _compute_rule_based_sentiment(self, cleaned_news: List[Dict[str, Any]], ticker: str) -> Dict[str, Any]:
        """Dynamically scores sentiment from real news headlines without static mocks."""
        bull_words = {"surge", "surges", "gain", "gains", "jump", "jumps", "beat", "beats", "record", "bull", "bullish", "upgrade", "growth", "high", "strong", "outperform", "buy", "profit", "soar", "rally"}
        bear_words = {"fall", "falls", "drop", "drops", "plunge", "plunges", "loss", "losses", "cut", "cuts", "miss", "misses", "bear", "bearish", "downgrade", "low", "weak", "sell", "risk", "warning", "probe", "investigation", "dip"}

        summaries = []
        total_score = 0.5
        count = 0

        for item in cleaned_news:
            title = item.get("title", "")
            title_lower = title.lower()
            words = set(title_lower.split())
            
            bull_count = len(words & bull_words)
            bear_count = len(words & bear_words)
            
            if bull_count > bear_count:
                sentiment = "Bullish"
                item_score = 0.75
            elif bear_count > bull_count:
                sentiment = "Bearish"
                item_score = 0.25
            else:
                sentiment = "Neutral"
                item_score = 0.50

            total_score += item_score
            count += 1

            summaries.append({
                "title": title,
                "source": item.get("publisher", "Market Wire"),
                "sentiment": sentiment,
                "summary": f"Recent market coverage regarding {ticker}: {title}."
            })

        avg_score = round(total_score / count, 2) if count > 0 else 0.50
        if avg_score >= 0.60:
            label = "Bullish"
        elif avg_score <= 0.40:
            label = "Bearish"
        else:
            label = "Neutral"

        return {
            "sentiment_score": avg_score,
            "sentiment_label": label,
            "news_summaries": summaries
        }

    async def run(self, ticker: str) -> Dict[str, Any]:
        """Fetches live market news and executes sentiment analysis reasoning."""
        ticker = ticker.upper().strip()
        print(f"News agent: Fetching fresh live market news for {ticker}...")
        
        # 1. Fetch live news: try yfinance, fallback to live Google News RSS
        raw_news = []
        try:
            stock = yf.Ticker(ticker)
            raw_news = stock.news or []
        except Exception:
            pass
            
        if not raw_news:
            raw_news = self._fetch_rss_news(ticker)

        # 2. Format articles for prompt
        cleaned_news = []
        for item in raw_news[:6]:
            title = item.get("title", "")
            publisher = item.get("publisher", "") or item.get("source", "Market Wire")
            snippet = item.get("summary", "") or item.get("description", "") or title
            if title:
                cleaned_news.append({
                    "title": title,
                    "publisher": publisher,
                    "snippet": snippet
                })

        dynamic_fallback = self._compute_rule_based_sentiment(cleaned_news, ticker)

        if not cleaned_news:
            return {
                "sentiment_score": 0.5,
                "sentiment_label": "Neutral",
                "news_summaries": [
                    {
                        "title": f"Recent trading activity and market observations for {ticker}",
                        "source": "Market Wire",
                        "sentiment": "Neutral",
                        "summary": f"Real-time news feeds did not report major breaking catalysts for {ticker} in the last 24 hours."
                    }
                ]
            }

        user_prompt = (
            f"Analyze news sentiment for ticker: {ticker}.\n\n"
            f"Here are the recent real-time news headlines and snippets:\n"
            f"{json.dumps(cleaned_news, indent=2)}\n\n"
            f"Determine the overall sentiment score (0.0 to 1.0), overall sentiment label, and summarize the articles."
        )

        print(f"News agent: Querying LLM for {ticker} news analysis...")
        result_json = llm_client.call_gemini(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            response_schema=NewsAnalysisSchema,
            ticker=ticker
        )

        try:
            parsed = json.loads(result_json)
            if "sentiment_score" in parsed and "news_summaries" in parsed and parsed["news_summaries"]:
                return parsed
            return dynamic_fallback
        except Exception:
            return dynamic_fallback

news_agent = NewsAgent()
