import asyncio
import time
import json
from typing import Dict, Any, Callable, Awaitable, Optional
from backend.services.event_broker import event_broker
from backend.agents.filing_agent import filing_agent
from backend.agents.metrics_agent import metrics_agent
from backend.agents.news_agent import news_agent
from backend.agents.valuation_agent import valuation_agent
from backend.agents.report_agent import report_agent
from backend.config import settings

class ResearchWorkflow:
    def __init__(self):
        self._running_jobs = set()

    async def execute_research(
        self, 
        ticker: str, 
        on_progress: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    ) -> Dict[str, Any]:
        """Runs the entire multi-agent financial research pipeline sequentially."""
        ticker = ticker.upper().strip()
        job_id = f"job_{ticker}_{int(time.time())}"
        
        if ticker in self._running_jobs:
            print(f"Job for {ticker} is already running.")
            return {"status": "already_running", "ticker": ticker}
            
        self._running_jobs.add(ticker)
        
        async def send_log(stage: str, message: str, status: str = "running", data: Any = None):
            """Helper to send progress update logs."""
            log_payload = {
                "job_id": job_id,
                "ticker": ticker,
                "stage": stage,
                "message": message,
                "status": status,
                "timestamp": time.strftime("%H:%M:%S"),
                "data": data
            }
            # 1. Trigger WebSocket callback
            if on_progress:
                try:
                    await on_progress(log_payload)
                except Exception as e:
                    print(f"Error sending progress WebSocket log: {e}")
            
            # 2. Log internally
            print(f"[{ticker}] [{stage.upper()}] - {message}")

        # Start timer
        start_time = time.time()
        agent_outputs = {}

        try:
            # 1. Publish Event research.requested
            await event_broker.publish("research.requested", {
                "job_id": job_id,
                "ticker": ticker,
                "timestamp": time.time()
            })
            
            await send_log("init", "Initializing AI-Powered Financial Research Agent Platform...", "running")
            await asyncio.sleep(0.5)

            # Step 1: Filing Agent (SEC EDGAR RAG)
            await send_log("filing", "Filing Agent: Fetching SEC filings and initializing RAG database...", "running")
            # In local mode, we might wait a tiny bit to make logs readable and look premium
            await asyncio.sleep(1.0)
            filing_data = await filing_agent.run(ticker)
            agent_outputs["filing_agent"] = filing_data
            await send_log(
                "filing", 
                f"Filing Agent: Completed. Extracted {len(filing_data.get('business_segments', []))} business segments and {len(filing_data.get('key_risks', []))} risk factors.", 
                "completed",
                data=filing_data
            )
            await asyncio.sleep(0.8)

            # Step 2: Financial Metrics Agent (yfinance + Python ratios)
            await send_log("metrics", "Metrics Agent: Querying income, balance, and cash flow statements...", "running")
            await asyncio.sleep(1.0)
            metrics_data = await metrics_agent.run(ticker)
            agent_outputs["metrics_agent"] = metrics_data
            await send_log(
                "metrics", 
                f"Metrics Agent: Completed. Calculated growth ratios ({metrics_data.get('metrics_summary', {}).get('revenue_growth_yoy', 'N/A')} YoY) and operating margins.", 
                "completed",
                data=metrics_data
            )
            await asyncio.sleep(0.8)

            # Step 3: News Agent (Sentiment analysis)
            await send_log("news", "News Agent: Pulling recent market articles and calculating sentiment score...", "running")
            await asyncio.sleep(1.0)
            news_data = await news_agent.run(ticker)
            agent_outputs["news_agent"] = news_data
            await send_log(
                "news", 
                f"News Agent: Completed. Detected {news_data.get('sentiment_label', 'Neutral')} sentiment score: {news_data.get('sentiment_score', 0.5)}.", 
                "completed",
                data=news_data
            )
            await asyncio.sleep(0.8)

            # Step 4: Valuation Agent (DCF + Peer Multiples)
            await send_log("valuation", "Valuation Agent: Running dynamic 5-year DCF model and fetching peer valuations...", "running")
            await asyncio.sleep(1.0)
            valuation_data = await valuation_agent.run(ticker)
            agent_outputs["valuation_agent"] = valuation_data
            await send_log(
                "valuation", 
                f"Valuation Agent: Completed. Estimated Fair Value: ${valuation_data.get('dcf_valuation', {}).get('estimated_fair_value', 0.0):.2f} (Upside: {valuation_data.get('dcf_valuation', {}).get('implied_upside', 'N/A')}).", 
                "completed",
                data=valuation_data
            )
            await asyncio.sleep(0.8)

            # Step 5: Report Agent (Synthesis)
            await send_log("report", "Report Agent: Synthesizing individual agent memos into final markdown research briefing...", "running")
            await asyncio.sleep(1.2)
            report_markdown = await report_agent.run(ticker, agent_outputs)
            agent_outputs["report"] = report_markdown
            await send_log("report", "Report Agent: Completed final synthesis.", "completed")
            await asyncio.sleep(0.5)

            # Complete Job
            duration = round(time.time() - start_time, 2)
            final_payload = {
                "status": "success",
                "ticker": ticker,
                "duration_seconds": duration,
                "report": report_markdown,
                "agent_outputs": agent_outputs
            }
            
            # Save final results locally to cache
            result_cache = settings.DATA_DIR / "reports" / f"{ticker}_results.json"
            with open(result_cache, "w", encoding="utf-8") as f:
                json.dump(final_payload, f, default=str)
                
            await send_log("finished", f"Workflow Finished. Total time: {duration} seconds. Document published.", "finished", data=final_payload)
            
            # Publish Event research.completed
            await event_broker.publish("research.completed", {
                "job_id": job_id,
                "ticker": ticker,
                "timestamp": time.time(),
                "duration": duration,
                "status": "success"
            })
            
            return final_payload

        except Exception as e:
            import traceback
            error_msg = f"Workflow Error: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            await send_log("error", f"Critical Workflow failure: {str(e)}", "failed")
            
            error_payload = {
                "status": "failed",
                "ticker": ticker,
                "error": str(e)
            }
            
            # Publish Event research.completed (failed)
            await event_broker.publish("research.completed", {
                "job_id": job_id,
                "ticker": ticker,
                "timestamp": time.time(),
                "status": "failed",
                "error": str(e)
            })
            
            return error_payload
            
        finally:
            self._running_jobs.remove(ticker)

workflow = ResearchWorkflow()
