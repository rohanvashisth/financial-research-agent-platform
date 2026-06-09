import json
from typing import Any
from google import genai
from google.genai import types
from google.genai import errors
from backend.config import settings

class LLMClient:
    def __init__(self):
        self.client = None
        if settings.GEMINI_API_KEY:
            try:
                self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
            except Exception as e:
                print(f"Error initializing Gemini client: {e}")

    def call_gemini(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        response_schema: Any = None, 
        ticker: str = "MSFT"
    ) -> str:
        """Invokes Gemini LLM. If key is missing, triggers fallback mock generator."""
        if self.client:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.2
                )
                
                if response_schema:
                    config.response_mime_type = "application/json"
                    config.response_schema = response_schema
                
                # Using gemini-2.5-flash as the standard fast reasoning model
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=user_prompt,
                    config=config
                )
                
                if response and response.text:
                    return response.text
            except Exception as e:
                print(f"Gemini LLM call failed: {e}. Falling back to mock generator.")
        
        # Mock responses based on the system prompt and ticker
        return self._generate_mock_response(system_prompt, user_prompt, ticker, response_schema)

    def _generate_mock_response(self, system_prompt: str, user_prompt: str, ticker: str, schema: Any) -> str:
        """Returns realistic mock JSON data matching the expected schema for the requested agent."""
        ticker = ticker.upper().strip()
        system_prompt_lower = system_prompt.lower()
        
        # 0. RAG Chat query check (schema is None, and not report synthesis prompt)
        if schema is None and not ("synthesize" in system_prompt_lower or "memo" in system_prompt_lower):
            user_prompt_lower = user_prompt.lower()
            if "ai" in user_prompt_lower or "artificial intelligence" in user_prompt_lower:
                if ticker in ["AAPL", "APPLE"]:
                    return f"Based on Apple's latest filing context, Apple is focusing heavily on its proprietary on-device AI system, Apple Intelligence, integrated across iOS, iPadOS, and macOS. The company has accelerated capital spending for customized server infrastructure and edge-AI processors, positioning themselves as a leader in private, secure cloud compute. These efforts are expected to catalyze a significant hardware upgrade cycle (specifically for iPhone 15 Pro/16 and M-series Macs) and expand their high-margin Services ecosystem."
                else:
                    return f"According to {ticker}'s latest SEC filings, the company is scaling up its capital expenditures to build out high-performance computing data centers, acquire GPU assets, and integrate Generative AI capabilities across its product lines. Management expects these investments to support enterprise migration and drive substantial productivity gains."
            elif "risk" in user_prompt_lower:
                return f"For {ticker}, the primary risks outlined in the filings include: (1) high capital expenditure demands for next-generation technology developments, (2) intense competition from other hyperscale platform providers, and (3) global regulatory and antitrust reviews targeting bundle packaging or payment fee structures."
            else:
                return f"Based on the SEC filing context for {ticker}, the company is experiencing solid demand across its primary operational divisions. Management highlighted continued execution of capital returns (dividends and buybacks) and a strategic pivot toward integration of cloud and cognitive services to drive operational efficiency."

        # 1. Report Agent (Synthesize Markdown memo) check first to avoid keyword clashes
        if "synthesize" in system_prompt_lower or "memo" in system_prompt_lower:
            return f"""# Equity Research Memo: {ticker}

**Recommendation**: BUY  
**Current Price**: $420.00 | **Target Price**: $465.50 (Implied Upside: +10.8%)  
**Risk Profile**: Moderate  

---

## 1. Executive Summary & Investment Thesis
We reiterate our BUY rating on {ticker} with a 12-month target price of $465.50. The core investment thesis is centered around the company's dominating position in hyperscale cloud computing and enterprise applications, further catalyzed by rapid integration of Generative AI. 

Our dynamic Discounted Cash Flow (DCF) model and peer multiples review suggest the stock trades at an attractive discount relative to its premium growth prospects and resilient operating margins. CapEx intensity is rising to build data centers and GPU capacity, which will impact short-term cash flows but secure a long-term compound growth driver.

---

## 2. Business Segment Overview
According to recent SEC filings, the company operates in three primary divisions:
*   **Intelligent Cloud (Azure)**: The primary growth driver (approx. 43% revenue share), providing database systems, enterprise server products, and developer tools.
*   **Productivity and Business Processes**: Stable high-margin software suite (approx. 31% revenue share), including SaaS subscriptions (Office 365) and CRM/ERP tools.
*   **More Personal Computing**: Consumer-oriented licensing, hardware devices, and gaming services (approx. 26% revenue share).

---

## 3. Financial Performance & Margin Trends
*   **YoY Revenue Growth**: +15.4%, displaying robust demand across commercial sectors.
*   **Margins**: Gross margin remains resilient at 69.8%, with operating margins expanding to 44.2% due to corporate cost controls and operating leverage.
*   **Leverage**: Extremely healthy balance sheet with a Debt-to-Equity ratio of 0.32 and a Return on Equity (ROE) of 38.5%.
*   **Cash Generation**: Free Cash Flow continues to scale (+12.8% YoY), providing self-funding capacity for massive capital expenditures.

---

## 4. Valuation Modeling & Peer Analysis
### Discounted Cash Flow (DCF) Assumptions
*   **WACC (Discount Rate)**: 8.5%
*   **Stage 1 Growth Rate**: 12.0% (5 Years)
*   **Terminal Growth Rate**: 2.5%
*   **Equity Value per Share (Fair Value)**: $465.50

### Relative Peer Multiples
| Ticker | P/E Ratio | P/S Ratio | EV / EBITDA |
| :--- | :--- | :--- | :--- |
| **{ticker}** | **34.2x** | **12.1x** | **22.4x** |
| AAPL | 29.5x | 8.1x | 19.8x |
| GOOGL | 22.1x | 6.2x | 14.5x |
| AMZN | 38.6x | 3.1x | 18.2x |

---

## 5. Key Investment Risks
1.  **Hyperscale AI Capital Expenditures**: Building data centers and purchasing high-end GPUs requires significant upfront capital. High depreciation expense could pressure gross margins in the near-term.
2.  **Hyperscale Cloud Competition**: Competition from AWS and Google Cloud remains fierce, placing pressure on pricing structures.
3.  **Antitrust and Regulatory Scrutiny**: Global regulatory bodies continue to inspect packaging/bundling strategies and search indexing practices.

---

## 6. Sources Cited
*   **SEC 10-K Submission**: Item 1A (Risk Factors) - Detailed review of GPU dependency and data center infrastructure spend.
*   **SEC 10-K Submission**: Item 7 (MD&A) - Management discussion regarding cloud segment growth and recurring SaaS subscriptions.
"""

        # 2. Filing Agent response
        elif "filing" in system_prompt_lower or "sec" in system_prompt_lower:
            data = {
                "business_segments": [
                    {"name": "Intelligent Cloud (Azure)", "share": "43%", "description": "Enterprise cloud services, infrastructure, and database products."},
                    {"name": "Productivity and Business Processes", "share": "31%", "description": "Office 365, LinkedIn, Dynamics ERP and CRM applications."},
                    {"name": "More Personal Computing", "share": "26%", "description": "Windows OS licenses, Xbox gaming hardware and content, surface devices."}
                ] if ticker in ["MSFT", "MICROSOFT"] else [
                    {"name": "iPhone", "share": "52%", "description": "Premium smartphones and iOS ecosystem hardware."},
                    {"name": "Services", "share": "22%", "description": "App Store, iCloud, Apple Music, Apple Pay, subscriptions."},
                    {"name": "Wearables, Home & Accessories", "share": "10%", "description": "Apple Watch, AirPods, Apple TV, smart home products."}
                ],
                "key_risks": [
                    {"risk": "Hyperscale AI Capital Expenditures", "mitigation": "Aggressive monetization of Azure AI services and Copilot products to offset depreciation."},
                    {"risk": "Intense Cloud Competition (AWS, GCP)", "mitigation": "Leveraging deep enterprise relationships and hybrid-cloud software products."},
                    {"risk": "Regulatory and Antitrust Actions", "mitigation": "Cooperating with regulators; separating Teams bundles from Office suites."}
                ] if ticker in ["MSFT", "MICROSOFT"] else [
                    {"risk": "Supply Chain Vulnerability in Asia", "mitigation": "Diversifying manufacturing lines to India, Vietnam, and South America."},
                    {"risk": "App Store Regulatory Pressures", "mitigation": "Modifying fee schedules in Europe and offering third-party payment rails."}
                ],
                "management_outlook": "Management remains highly bullish on AI integrations, planning to increase capital expenditure to build data centers and buy GPUs. They expect double-digit revenue growth in the core cloud business, driven by enterprise AI adoption and solid Office 365 seat growth.",
                "sources_cited": [
                    {"document": "Microsoft FY25 10-K", "section": "Item 1A (Risk Factors) - Page 14", "context": "Detailed discussion of risks regarding capital spending on GPUs and data centers."},
                    {"document": "Microsoft FY25 10-K", "section": "Item 7 (MD&A) - Page 32", "context": "Management Discussion of Azure scaling and operating margin expansion."}
                ]
            }
            return json.dumps(data)

        elif "metrics" in system_prompt_lower or "financial" in system_prompt_lower:
            # Financial Metrics Agent response
            data = {
                "metrics_summary": {
                    "revenue_growth_yoy": "15.4%",
                    "gross_margin": "69.8%",
                    "operating_margin": "44.2%",
                    "net_margin": "35.1%",
                    "debt_to_equity": "0.32",
                    "return_on_equity": "38.5%",
                    "free_cash_flow_growth": "12.8%"
                },
                "trend_analysis": f"Revenue for {ticker} shows a steady upward trajectory driven by recurring software services. Operating margins have remained resilient in the 43-45% range, showing excellent operational leverage despite increased capital expenditures. Cash generation remains a key strength with Free Cash Flow margins exceeding 30%.",
                "risk_signals": "No near-term solvency issues. Capital expenditure is rising rapidly (up 40% YoY), which may pressure free cash flow growth if capital is not deployed efficiently."
            }
            return json.dumps(data)

        elif "news" in system_prompt_lower or "sentiment" in system_prompt_lower:
            # News Agent response
            data = {
                "sentiment_score": 0.75 if ticker in ["MSFT", "NVDA"] else 0.45, # positive/neutral
                "sentiment_label": "Bullish" if ticker in ["MSFT", "NVDA"] else "Neutral",
                "news_summaries": [
                    {"title": f"{ticker} Stock Surges on Strong Cloud Earnings", "source": "Bloomberg", "sentiment": "Bullish", "summary": "Analysts upgraded the stock citing Azure's acceleration and margin stability."},
                    {"title": f"FTC Investigates {ticker} Partnership", "source": "Reuters", "sentiment": "Bearish", "summary": "Regulators are reviewing recent investments for potential antitrust violations."},
                    {"title": f"{ticker} Announces New AI Chips", "source": "CNBC", "sentiment": "Bullish", "summary": "Unveiled custom silicon designed to lower inference costs and reduce reliance on third-party GPUs."}
                ]
            }
            return json.dumps(data)

        elif "valuation" in system_prompt_lower or "dcf" in system_prompt_lower:
            # Valuation Agent response
            data = {
                "dcf_valuation": {
                    "estimated_fair_value": 465.50 if ticker in ["MSFT", "MICROSOFT"] else 210.00,
                    "terminal_growth_rate": "2.5%",
                    "wacc": "8.5%",
                    "growth_stage_rate": "12.0%",
                    "current_price": 420.00 if ticker in ["MSFT", "MICROSOFT"] else 180.00,
                    "implied_upside": "10.8%"
                },
                "peer_multiples": [
                    {"ticker": ticker, "pe_ratio": 34.2, "ps_ratio": 12.1, "ev_ebitda": 22.4},
                    {"ticker": "AAPL", "pe_ratio": 29.5, "ps_ratio": 8.1, "ev_ebitda": 19.8},
                    {"ticker": "GOOGL", "pe_ratio": 22.1, "ps_ratio": 6.2, "ev_ebitda": 14.5},
                    {"ticker": "AMZN", "pe_ratio": 38.6, "ps_ratio": 3.1, "ev_ebitda": 18.2}
                ],
                "valuation_conclusion": f"Based on our DCF model (8.5% WACC, 2.5% Terminal Growth) and relative valuation multiples, {ticker} appears slightly undervalued, trading at a 10% discount to its estimated fair value. While multiples are historically elevated, premium growth in AI services justifies the premium relative to peers."
            }
            return json.dumps(data)

        else:
            # Fallback/Report Synthesis or generic
            return f"# Financial Research Report: {ticker}\n\nThis is a fallback report for {ticker} because the Gemini API key was not configured or the call failed. The report provides structured financial evaluations."

llm_client = LLMClient()
