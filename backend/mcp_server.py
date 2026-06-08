import asyncio
import sys
import json
from typing import Dict, Any, List
from mcp.server import Server
import mcp.types as types
from mcp.server.models import InitializationOptions

# Add parent directory to path to allow absolute imports
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.data_fetcher import data_fetcher
from backend.agents.workflow import workflow
from backend.agents.metrics_agent import metrics_agent
from backend.agents.valuation_agent import valuation_agent
from backend.config import settings

# Initialize MCP Server
server = Server("financial-research-agent-server")

@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """Lists the tools available on this MCP server."""
    return [
        types.Tool(
            name="get_company_filings",
            description="Retrieves a list of recent SEC EDGAR 10-K and 10-Q filings for a ticker symbol (e.g. MSFT, AAPL).",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol (e.g., TSLA)"}
                },
                "required": ["ticker"]
            }
        ),
        types.Tool(
            name="get_financial_metrics",
            description="Extracts key financial statement details and computes YoY growth, margins, and leverage ratios.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol"}
                },
                "required": ["ticker"]
            }
        ),
        types.Tool(
            name="get_stock_price_history",
            description="Returns daily historical closing prices for a ticker over the last year for charting and trends.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol"}
                },
                "required": ["ticker"]
            }
        ),
        types.Tool(
            name="compare_competitors",
            description="Identifies peer competitors and pulls their valuation multiples (P/E, P/S, EV/EBITDA) for comparison.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol"}
                },
                "required": ["ticker"]
            }
        ),
        types.Tool(
            name="generate_research_report",
            description="Runs the multi-agent reasoning workflow (Filing, Metrics, News, Valuation) and generates a complete investment memo in Markdown.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol"}
                },
                "required": ["ticker"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, 
    arguments: Dict[str, Any]
) -> List[types.TextContent]:
    """Executes a tool call requested by the client and returns textual results."""
    ticker = arguments.get("ticker", "").upper().strip()
    if not ticker:
        return [types.TextContent(type="text", text="Error: Ticker symbol is required.")]

    try:
        if name == "get_company_filings":
            filings = data_fetcher.fetch_latest_sec_filings(ticker, filing_type="10-K")
            if not filings:
                return [types.TextContent(type="text", text=f"No 10-K filings found on SEC EDGAR for {ticker}. Check ticker spelling or connection.")]
            res_text = json.dumps(filings[:3], indent=2)
            return [types.TextContent(type="text", text=f"Latest 10-K SEC Filings for {ticker}:\n{res_text}")]

        elif name == "get_financial_metrics":
            financials = data_fetcher.get_financial_statements(ticker)
            ratios = metrics_agent._calculate_financial_ratios(financials)
            res_text = json.dumps({
                "computed_ratios": ratios,
                "note": "Ratios calculated from yfinance financial statements."
            }, indent=2)
            return [types.TextContent(type="text", text=f"Financial Ratios for {ticker}:\n{res_text}")]

        elif name == "get_stock_price_history":
            history = data_fetcher.get_stock_history(ticker, period="1y")
            # Return subset to save token space
            subset = history[-20:] # latest 20 days
            res_text = json.dumps(subset, indent=2)
            return [types.TextContent(type="text", text=f"Last 20 Trading Days for {ticker} (Full 1y available):\n{res_text}")]

        elif name == "compare_competitors":
            info = data_fetcher.get_company_info(ticker)
            peers = data_fetcher.get_competitors(ticker, info.get("sector", "Technology"))
            
            peer_data = []
            for p in [ticker] + peers[:3]:
                p_stock = yf_ticker_safe(p)
                p_info = p_stock.info if p_stock else {}
                peer_data.append({
                    "ticker": p,
                    "name": p_info.get("longName", p),
                    "pe_ratio": p_info.get("trailingPE", "N/A"),
                    "ps_ratio": p_info.get("priceToSalesTrailing12Months", "N/A"),
                    "ev_ebitda": p_info.get("enterpriseToEbitda", "N/A")
                })
            res_text = json.dumps(peer_data, indent=2)
            return [types.TextContent(type="text", text=f"Peer Comparison Table for {ticker}:\n{res_text}")]

        elif name == "generate_research_report":
            # Run the multi-agent workflow synchronously
            print(f"MCP Server: Running multi-agent research workflow for {ticker}...")
            result = await workflow.execute_research(ticker)
            
            if result.get("status") == "success":
                report_md = result.get("report", "")
                return [types.TextContent(type="text", text=report_md)]
            else:
                return [types.TextContent(type="text", text=f"Failed to generate research report for {ticker}. Error: {result.get('error', 'Unknown error')}")]

        else:
            raise ValueError(f"Unknown tool name: {name}")

    except Exception as e:
        import traceback
        err_str = f"Error executing tool '{name}': {str(e)}\n{traceback.format_exc()}"
        return [types.TextContent(type="text", text=err_str)]

def yf_ticker_safe(ticker: str):
    import yfinance as yf
    try:
        return yf.Ticker(ticker)
    except Exception:
        return None

async def run_server():
    """Runs the MCP server over standard input/output streams."""
    import mcp.server.stdio
    print("Starting Model Context Protocol Server over STDIO...", file=sys.stderr)
    
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="financial-research-server",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=types.NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(run_server())
