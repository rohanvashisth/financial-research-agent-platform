import json
import yfinance as yf
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from backend.agents.llm_client import llm_client

class NewsSummaryItem(BaseModel):
    title: str = Field(description="Title of the news article")
    source: str = Field(description="Publisher/Source (e.g. Bloomberg, CNBC)")
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

    async def run(self, ticker: str) -> Dict[str, Any]:
        """Fetches yfinance news and runs sentiment analysis reasoning."""
        ticker = ticker.upper().strip()
        
        # 1. Fetch news from yfinance
        print(f"News agent: Fetching news for {ticker}...")
        raw_news = []
        try:
            stock = yf.Ticker(ticker)
            raw_news = stock.news
        except Exception as e:
            print(f"News agent error fetching yfinance news: {e}")
            
        if not raw_news:
            # Generate mock news if none available
            raw_news = [
                {"title": f"{ticker} expands core cloud services and AI pipelines", "publisher": "Reuters", "link": "https://example.com/news1"},
                {"title": f"Regulators scrutinize recent acquisitions by {ticker}", "publisher": "Bloomberg", "link": "https://example.com/news2"},
                {"title": f"Analysts highlight margin strength for {ticker}", "publisher": "CNBC", "link": "https://example.com/news3"}
            ]

        # 2. Extract relevant details for the LLM prompt
        cleaned_news = []
        for item in raw_news[:6]:  # Limit to top 6 news stories
            title = item.get("title", "")
            publisher = item.get("publisher", "")
            # Some news feeds have summary/description, some don't
            snippet = item.get("summary", "") or item.get("description", "") or "No snippet available."
            
            cleaned_news.append({
                "title": title,
                "publisher": publisher,
                "snippet": snippet
            })

        user_prompt = (
            f"Analyze news sentiment for ticker: {ticker}.\n\n"
            f"Here are the recent news headlines and snippets:\n"
            f"{json.dumps(cleaned_news, indent=2)}\n\n"
            f"Determine the overall sentiment score, overall sentiment label, and summarize the articles."
        )

        print(f"News agent: Querying LLM for {ticker} news analysis...")
        result_json = llm_client.call_gemini(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            response_schema=NewsAnalysisSchema,
            ticker=ticker
        )

        try:
            return json.loads(result_json)
        except Exception as e:
            print(f"News agent: Error parsing JSON from LLM: {e}")
            return json.loads(llm_client._generate_mock_response(self.system_prompt, user_prompt, ticker, NewsAnalysisSchema))

news_agent = NewsAgent()
