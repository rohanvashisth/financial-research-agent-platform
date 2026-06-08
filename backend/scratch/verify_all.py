import asyncio
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.data_fetcher import data_fetcher
from backend.services.vector_store import vector_store
from backend.agents.workflow import workflow

async def run_checks():
    print("==================================================")
    print("RUNNING DIAGNOSTIC AND FUNCTIONAL TESTS...")
    print("==================================================")
    
    # 1. Test yfinance and SEC mappings
    print("\n--- 1. Testing Data Fetcher ---")
    cik = data_fetcher.get_cik("MSFT")
    print(f"Ticker CIK Resolution: MSFT -> CIK {cik}")
    if cik == "0000789019":
        print("[OK] Ticker CIK mapping successful.")
    else:
        print("[FAIL] Ticker CIK mapping failed or using unexpected value.")

    print("\nFetching Microsoft metadata...")
    info = data_fetcher.get_company_info("MSFT")
    print(f"Company Name: {info.get('name')}")
    print(f"Sector: {info.get('sector')}")
    print(f"Market Cap: {info.get('market_cap'):,}")
    if info.get('name') and "Microsoft" in info.get('name'):
        print("[OK] Yahoo Finance metadata fetch successful.")
    else:
        print("[FAIL] Metadata fetch failed.")

    # 2. Test Vector Store & RAG
    print("\n--- 2. Testing SQLite Vector Store ---")
    print("Ingesting mock chunks...")
    mock_chunks = data_fetcher._generate_mock_filing_chunks("MSFT", "10-K")
    await vector_store.save_chunks(mock_chunks)
    
    print("Querying vector store for risk factors...")
    results = await vector_store.similarity_search("MSFT", "What are the competition risks?", limit=2)
    print(f"Returned {len(results)} search results.")
    for idx, r in enumerate(results):
        print(f"Result {idx+1} [{r['section']}] (Score: {r['score']:.4f}):")
        print(f"  Content: {r['content'][:120]}...")
        
    if len(results) > 0:
        print("[OK] Vector store similarity search and indexing successful.")
    else:
        print("[FAIL] Similarity search failed.")

    # 3. Test Agent Workflow Pipeline
    print("\n--- 3. Testing Agent Workflow Sequence ---")
    print("Executing research workflow for MSFT (mock flow)...")
    
    log_stages = []
    async def log_callback(payload):
        log_stages.append(payload['stage'])
        print(f"  [STREAM LOG] {payload['stage'].upper()}: {payload['message']}")

    res = await workflow.execute_research("MSFT", on_progress=log_callback)
    
    print("\nWorkflow Execution Summary:")
    print(f"Status: {res.get('status')}")
    print(f"Duration: {res.get('duration_seconds')} seconds")
    print(f"Log stages captured: {', '.join(log_stages)}")
    
    if res.get('status') == 'success' and 'report' in res:
        print("[OK] Multi-agent workflow execution successful.")
        print(f"Report length: {len(res['report'])} characters.")
    else:
        print("[FAIL] Workflow execution failed.")
        
    print("\n==================================================")
    print("DIAGNOSTICS COMPLETED.")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_checks())
