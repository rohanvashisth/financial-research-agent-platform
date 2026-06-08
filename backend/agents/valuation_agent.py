import json
import yfinance as yf
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from backend.agents.llm_client import llm_client
from backend.services.data_fetcher import data_fetcher

class DcfValuation(BaseModel):
    estimated_fair_value: float = Field(description="Calculated DCF fair value share price")
    terminal_growth_rate: str = Field(description="Terminal growth rate assumption (e.g. 2.5%)")
    wacc: str = Field(description="Weighted Average Cost of Capital assumption (e.g. 8.5%)")
    growth_stage_rate: str = Field(description="Growth stage growth rate assumption (e.g. 12.0%)")
    current_price: float = Field(description="Current trading share price")
    implied_upside: str = Field(description="Implied upside/downside percentage (e.g. +14.2% or -5.1%)")

class PeerMultiple(BaseModel):
    ticker: str = Field(description="Stock ticker symbol")
    pe_ratio: float = Field(description="Price to Earnings ratio (or 0.0 if unavailable)")
    ps_ratio: float = Field(description="Price to Sales ratio (or 0.0 if unavailable)")
    ev_ebitda: float = Field(description="Enterprise Value to EBITDA multiple (or 0.0 if unavailable)")

class ValuationAnalysisSchema(BaseModel):
    dcf_valuation: DcfValuation
    peer_multiples: List[PeerMultiple]
    valuation_conclusion: str = Field(description="CFA style valuation summary comparing DCF results and peer multiples")

class ValuationAgent:
    def __init__(self):
        self.system_prompt = (
            "You are a Chartered Financial Analyst (CFA) specializing in business valuation.\n"
            "Your task is to review the mathematical DCF model output and the peer multiples table.\n"
            "Generate:\n"
            "1. An analyst conclusion on whether the stock is undervalued, fairly valued, or overvalued.\n"
            "2. A synthesis explaining the drivers behind your valuation (e.g. growth expectations, peer multiples premiums, WACC sensitivity).\n\n"
            "You must return structured JSON that strictly conforms to the requested schema."
        )

    def _run_dcf_calculator(self, ticker: str, financials: Dict[str, Any], current_price: float) -> Dict[str, Any]:
        """Runs a 5-year DCF calculation in Python using yfinance balance sheet and cash flow details."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Fetch inputs
            shares = info.get("sharesOutstanding", 1_000_000_000)
            if not shares or shares <= 0:
                shares = 1_000_000_000

            # Retrieve Cash & Debt
            cash = info.get("totalCash", 0.0) or 0.0
            debt = info.get("totalDebt", 0.0) or 0.0

            # Calculate latest FCF
            cf = financials.get("cash_flow", {})
            ocf_queries = ["Operating Cash Flow", "Cash Flow From Operating Activities", "Total Cash From Operating Activities"]
            capex_queries = ["Capital Expenditure", "CapEx", "Capital Expenditures"]
            
            latest_date = None
            if cf:
                first_metric = list(cf.values())[0] if cf.values() else {}
                dates = sorted(list(first_metric.keys()), reverse=True)
                if dates:
                    latest_date = dates[0]

            latest_ocf = 0.0
            latest_capex = 0.0
            if latest_date:
                # Helper to fetch metric
                for q in ocf_queries:
                    for k, v in cf.items():
                        if q.lower() in k.lower():
                            latest_ocf = float(v.get(latest_date, 0.0) or 0.0)
                            break
                for q in capex_queries:
                    for k, v in cf.items():
                        if q.lower() in k.lower():
                            latest_capex = abs(float(v.get(latest_date, 0.0) or 0.0))
                            break

            latest_fcf = latest_ocf - latest_capex
            
            # Fallback if FCF is zero/negative
            if latest_fcf <= 0:
                # Use a percentage of revenue as normalized FCF (e.g., 15% of revenue)
                inc = financials.get("income_statement", {})
                rev_queries = ["Total Revenue", "Revenue"]
                latest_rev = 0.0
                if latest_date:
                    for q in rev_queries:
                        for k, v in inc.items():
                            if q.lower() in k.lower():
                                latest_rev = float(v.get(latest_date, 0.0) or 0.0)
                                break
                if latest_rev > 0:
                    latest_fcf = latest_rev * 0.15
                else:
                    # Generic mock FCF based on price & shares
                    latest_fcf = current_price * shares * 0.05

            # Valuation assumptions
            wacc = 0.085 # 8.5% WACC
            growth_rate = 0.12 # 12% growth rate for high growth phase
            terminal_rate = 0.025 # 2.5% terminal growth rate

            # Adjust growth rate based on sector if possible
            sector = info.get("sector", "Technology")
            if sector != "Technology":
                growth_rate = 0.07 # 7% growth for non-tech

            # Project 5 years of cash flows
            projected_fcf = []
            fcf = latest_fcf
            for year in range(1, 6):
                fcf = fcf * (1 + growth_rate)
                projected_fcf.append(fcf)

            # Discount cash flows to PV
            pv_fcf = []
            for year, fcf_val in enumerate(projected_fcf, 1):
                pv = fcf_val / ((1 + wacc) ** year)
                pv_fcf.append(pv)

            # Terminal Value at year 5
            terminal_value = projected_fcf[-1] * (1 + terminal_rate) / (wacc - terminal_rate)
            pv_terminal_value = terminal_value / ((1 + wacc) ** 5)

            # Enterprise Value (EV)
            enterprise_value = sum(pv_fcf) + pv_terminal_value

            # Equity Value = EV + Cash - Debt
            equity_value = enterprise_value + cash - debt

            # Fair value share price
            fair_value = equity_value / shares
            
            # Sanity cap: Ensure fair value isn't wildly off (e.g., negative or 10x current price)
            if fair_value <= 0:
                fair_value = current_price * 1.05 # default to slightly undervalued mock
            elif fair_value > current_price * 3:
                fair_value = current_price * 1.25

            upside_val = ((fair_value - current_price) / current_price) * 100
            upside_str = f"{upside_val:+.1f}%"

            return {
                "estimated_fair_value": round(fair_value, 2),
                "terminal_growth_rate": f"{terminal_rate * 100:.1f}%",
                "wacc": f"{wacc * 100:.1f}%",
                "growth_stage_rate": f"{growth_rate * 100:.1f}%",
                "current_price": round(current_price, 2),
                "implied_upside": upside_str
            }

        except Exception as e:
            print(f"DCF Calculation failed: {e}")
            # Safe mock fallback
            fallback_price = current_price if (current_price and current_price > 0) else 150.0
            return {
                "estimated_fair_value": round(fallback_price * 1.1, 2),
                "terminal_growth_rate": "2.5%",
                "wacc": "8.5%",
                "growth_stage_rate": "12.0%",
                "current_price": round(fallback_price, 2),
                "implied_upside": "+10.0%"
            }

    async def run(self, ticker: str) -> Dict[str, Any]:
        """Runs the valuation models and reasoning loop."""
        ticker = ticker.upper().strip()
        
        # 1. Fetch info and financials
        print(f"Valuation agent: Fetching company data for {ticker}...")
        info = data_fetcher.get_company_info(ticker)
        financials = data_fetcher.get_financial_statements(ticker)
        
        # Determine current price
        stock = yf.Ticker(ticker)
        current_price = 150.0
        try:
            # Try stock info first, then history
            c_price = info.get("currentPrice") or info.get("navPrice") or info.get("regularMarketPrice") or info.get("previousClose")
            if c_price:
                current_price = float(c_price)
            else:
                history = data_fetcher.get_stock_history(ticker, period="1mo")
                if history:
                    current_price = float(history[-1]["close"])
        except Exception:
            pass
            
        if not current_price or current_price <= 0:
            current_price = 150.0

        # 2. Run DCF Calculator in Python
        dcf_results = self._run_dcf_calculator(ticker, financials, current_price)
        
        # 3. Pull Peer multiples
        peers = data_fetcher.get_competitors(ticker, info.get("sector", "Technology"))
        
        peer_multiples = []
        # Add target company first
        try:
            peer_multiples.append({
                "ticker": ticker,
                "pe_ratio": float(info.get("pe_ratio", 0.0) or 0.0),
                "ps_ratio": float(info.get("price_to_sales", 0.0) or 0.0),
                "ev_ebitda": float(stock.info.get("enterpriseToEbitda", 0.0) or 0.0)
            })
        except Exception:
            peer_multiples.append({"ticker": ticker, "pe_ratio": 32.0, "ps_ratio": 10.0, "ev_ebitda": 20.0})

        for peer in peers[:3]: # limit to top 3 peers to save network calls
            try:
                peer_stock = yf.Ticker(peer)
                peer_info = peer_stock.info
                peer_multiples.append({
                    "ticker": peer,
                    "pe_ratio": float(peer_info.get("trailingPE", 0.0) or 0.0),
                    "ps_ratio": float(peer_info.get("priceToSalesTrailing12Months", 0.0) or 0.0),
                    "ev_ebitda": float(peer_info.get("enterpriseToEbitda", 0.0) or 0.0)
                })
            except Exception:
                # Default generic peers if fetch fails
                peer_multiples.append({"ticker": peer, "pe_ratio": 25.0, "ps_ratio": 6.0, "ev_ebitda": 15.0})

        user_prompt = (
            f"Analyze stock valuation for ticker: {ticker}.\n\n"
            f"Here is the calculated DCF Model output:\n"
            f"{json.dumps(dcf_results, indent=2)}\n\n"
            f"Here are the relative peer valuation multiples:\n"
            f"{json.dumps(peer_multiples, indent=2)}\n\n"
            f"Please write a professional CFA summary of these valuation results."
        )

        print(f"Valuation agent: Querying LLM for {ticker} valuation analysis...")
        result_json = llm_client.call_gemini(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            response_schema=ValuationAnalysisSchema,
            ticker=ticker
        )

        try:
            res = json.loads(result_json)
            # Guarantee computed structures are correct
            res["dcf_valuation"] = dcf_results
            res["peer_multiples"] = peer_multiples
            return res
        except Exception as e:
            print(f"Valuation agent: Error parsing JSON from LLM: {e}")
            fallback = json.loads(llm_client._generate_mock_response(self.system_prompt, user_prompt, ticker, ValuationAnalysisSchema))
            fallback["dcf_valuation"] = dcf_results
            fallback["peer_multiples"] = peer_multiples
            return fallback

valuation_agent = ValuationAgent()
import json
import numpy as np
