import json
from typing import Dict, Any
from backend.agents.llm_client import llm_client

class ReportAgent:
    def __init__(self):
        self.system_prompt = (
            "You are a Lead Equity Research Analyst at a premier investment bank.\n"
            "Your task is to synthesize the individual analysis reports from your team (Filing, Metrics, News, Valuation) "
            "into a cohesive, professional, markdown investment memo.\n\n"
            "The report MUST include the following sections:\n"
            "1. **Header Block**: Company name, ticker, trading price, estimated fair value, recommendation (Buy/Hold/Sell), and implied upside.\n"
            "2. **Executive Summary & Investment Thesis**: The core investment argument, key drivers, and long-term outlook.\n"
            "3. **Business Segment Review**: Table or list of business units, revenue shares, and descriptive summaries.\n"
            "4. **Financial Analysis**: Summary of growth trends, profitability margins, debt levels, and cash flow dynamics.\n"
            "5. **News Catalyst & Sentiment Review**: News summaries, overall sentiment index, and market indicators.\n"
            "6. **Valuation & DCF Modeling**: Detailed DCF model assumptions (WACC, terminal growth, growth rate) and a comparison table of peer multiples.\n"
            "7. **Key Investment Risks**: Key risks extracted from filings and their impact on operations.\n"
            "8. **Source Citations**: Formal bibliography of the SEC filings referenced, citing sections and accession numbers.\n\n"
            "Ensure the markdown uses clean headings, tables, blockquotes, and highlights. "
            "Write in a formal, analytical, Wall Street analyst tone. Avoid generic statements; refer directly to the metrics and risks provided."
        )

    async def run(self, ticker: str, agent_outputs: Dict[str, Any]) -> str:
        """Synthesizes the final markdown research memo from prior agent results."""
        ticker = ticker.upper().strip()
        
        # Structure the prompt data
        prompt_data = {
            "filing_agent": agent_outputs.get("filing_agent", {}),
            "metrics_agent": agent_outputs.get("metrics_agent", {}),
            "news_agent": agent_outputs.get("news_agent", {}),
            "valuation_agent": agent_outputs.get("valuation_agent", {})
        }
        
        user_prompt = (
            f"Generate a comprehensive investment research brief for: {ticker}.\n\n"
            f"Here are the inputs from the specialized agents:\n"
            f"{json.dumps(prompt_data, indent=2)}\n\n"
            f"Synthesize this information into a beautifully structured Markdown report."
        )

        print(f"Report agent: Synthesizing final analyst memo for {ticker}...")
        report_markdown = llm_client.call_gemini(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            ticker=ticker
        )
        
        # Save the report to local files for caching/cashing in
        from backend.config import settings
        report_path = settings.DATA_DIR / "reports" / f"{ticker}_report.md"
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_markdown)
            print(f"Saved completed report for {ticker} to {report_path}")
        except Exception as e:
            print(f"Failed to cache report: {e}")

        return report_markdown

report_agent = ReportAgent()
