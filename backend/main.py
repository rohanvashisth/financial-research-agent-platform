import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from backend.config import settings
from backend.services.data_fetcher import data_fetcher
from backend.services.vector_store import vector_store
from backend.services.event_broker import event_broker
from backend.agents.workflow import workflow
from backend.agents.llm_client import llm_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    print("Starting Financial Research Agent Platform backend...")
    
    # Start Event Broker
    await event_broker.start()
    
    # Initialize pgvector database in Production Mode
    if settings.RUN_MODE == "production":
        await vector_store.initialize_postgres()
        
    yield
    
    # Shutdown actions
    print("Shutting down Financial Research Agent Platform backend...")
    await event_broker.stop()

app = FastAPI(
    title="AI-Powered Financial Research Agent Platform",
    description="An agentic equity research platform that fetches data, reasons over SEC filings, and drafts investment memos.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for the frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    ticker: str
    query: str

class ResearchTriggerRequest(BaseModel):
    ticker: str

@app.get("/")
def read_root():
    return {
        "status": "online",
        "mode": settings.RUN_MODE,
        "llm_configured": bool(settings.GEMINI_API_KEY)
    }

@app.get("/api/ticker/{symbol}")
def get_ticker_data(symbol: str):
    """Fetches company metadata and stock history for charting."""
    symbol = symbol.upper().strip()
    info = data_fetcher.get_company_info(symbol)
    history = data_fetcher.get_stock_history(symbol, period="1y")
    financials = data_fetcher.get_financial_statements(symbol)
    return {
        "info": info,
        "history": history,
        "financials": financials
    }

@app.get("/api/reports/{symbol}")
def get_report(symbol: str):
    """Fetches cached research results and report markdown if generated."""
    symbol = symbol.upper().strip()
    result_cache = settings.DATA_DIR / "reports" / f"{symbol}_results.json"
    
    if not result_cache.exists():
        raise HTTPException(status_code=404, detail=f"No research report found for ticker {symbol}. Please run research first.")
        
    try:
        with open(result_cache, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read report data: {str(e)}")

@app.post("/api/research/{symbol}")
async def trigger_research(symbol: str):
    """Triggers a background research task without waiting for the WebSocket."""
    symbol = symbol.upper().strip()
    
    # Run in background
    asyncio.create_task(workflow.execute_research(symbol))
    return {
        "status": "queued",
        "message": f"Research job for {symbol} has been queued.",
        "ticker": symbol
    }

@app.post("/api/chat")
async def chat_with_sec_filings(req: ChatRequest):
    """RAG Chat: Queries SEC filings for specific ticker and returns source-grounded answer."""
    ticker = req.ticker.upper().strip()
    query = req.query.strip()
    
    # 1. Ingest if missing
    chunks = await vector_store.similarity_search(ticker, "business segment risk", limit=1)
    if not chunks:
        # Ingest
        raw_chunks = data_fetcher.get_sec_rag_chunks(ticker, "10-K")
        await vector_store.save_chunks(raw_chunks)
        
    # 2. Similarity search
    matched_chunks = await vector_store.similarity_search(ticker, query, limit=4)
    
    if not matched_chunks:
        return {
            "answer": f"I was unable to find any relevant information regarding '{query}' in the SEC filings of {ticker}.",
            "sources": []
        }
        
    # 3. Build RAG prompt
    context_str = ""
    sources = []
    for idx, chunk in enumerate(matched_chunks):
        context_str += f"Context Block {idx+1} [{chunk['section']}]:\n{chunk['content']}\n\n"
        sources.append({
            "section": chunk["section"],
            "url": chunk["url"],
            "date": chunk["date"]
        })
        
    system_prompt = (
        "You are an expert financial researcher answering questions about corporate SEC filings.\n"
        "Answer the user's question using ONLY the provided filing context blocks. Be precise and cite the source.\n"
        "If the answer cannot be determined from the context, state that the context does not contain the answer, "
        "but provide a helpful general answer based on what you know. Keep your answer grounded and factual."
    )
    
    user_prompt = (
        f"Question: {query}\n\n"
        f"SEC Filing Context:\n"
        f"{context_str}\n\n"
        f"Answer the question clearly and reference the sections."
    )
    
    answer_text = llm_client.call_gemini(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        ticker=ticker
    )
    
    return {
        "answer": answer_text,
        "sources": sources
    }

@app.websocket("/ws/research/{symbol}")
async def websocket_research(websocket: WebSocket, symbol: str):
    """WebSocket route streaming real-time log steps of the agent workflow execution."""
    symbol = symbol.upper().strip()
    await websocket.accept()
    print(f"WebSocket connected for ticker research stream: {symbol}")
    
    # Keep track of the active connection
    try:
        async def on_progress_callback(log_payload: Dict[str, Any]):
            # Send log through the socket as JSON string
            try:
                await websocket.send_text(json.dumps(log_payload, default=str))
            except Exception as e:
                print(f"WS send failed: {e}")
                # Raise error to trigger outer disconnect block if socket died
                raise e

        # Execute research workflow and stream progress
        # Run inside a try-except to catch socket breaks
        await workflow.execute_research(symbol, on_progress=on_progress_callback)
        
    except WebSocketDisconnect:
        print(f"WebSocket client disconnected for symbol {symbol}")
    except Exception as e:
        print(f"WebSocket connection closed due to error: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass

import json
