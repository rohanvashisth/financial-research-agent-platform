from typing import Dict, Any, List
from pydantic import BaseModel, Field
from backend.agents.llm_client import llm_client
from backend.services.vector_store import vector_store
from backend.services.data_fetcher import data_fetcher

class BusinessSegment(BaseModel):
    name: str = Field(description="Name of the business segment")
    share: str = Field(description="Approximate revenue share of the segment (e.g. 35% or N/A)")
    description: str = Field(description="Brief description of segment operations")

class KeyRisk(BaseModel):
    risk: str = Field(description="Description of the risk factor")
    mitigation: str = Field(description="Management's mitigation strategy or description of impacts")

class Citation(BaseModel):
    document: str = Field(description="Document name (e.g., 2025 10-K)")
    section: str = Field(description="Section name (e.g., Item 1A: Risk Factors)")
    context: str = Field(description="The context of the citation")

class FilingAnalysisSchema(BaseModel):
    business_segments: List[BusinessSegment]
    key_risks: List[KeyRisk]
    management_outlook: str
    sources_cited: List[Citation]

class FilingAgent:
    def __init__(self):
        self.system_prompt = (
            "You are a Senior Equity Research Analyst specializing in SEC filing analysis.\n"
            "Your task is to analyze the company's SEC filings (10-K or 10-Q) using the provided RAG context.\n"
            "Extract the following information:\n"
            "1. Major business segments (product/service lines) and their approximate revenue shares.\n"
            "2. Critical operational, financial, and regulatory risk factors mentioned.\n"
            "3. Management's outlook, future strategy, and guidance commentary.\n"
            "4. Detailed sources cited (document title, item number, exact context).\n\n"
            "You must return structured JSON that strictly conforms to the requested schema."
        )

    async def run(self, ticker: str) -> Dict[str, Any]:
        """Runs the SEC RAG and reasoning process for the filing agent."""
        ticker = ticker.upper().strip()
        
        # 1. Ensure filing data is ingested in the vector store
        # First check if we have chunks in the vector store
        chunks = await vector_store.similarity_search(ticker, "risks segments outlook", limit=1)
        if not chunks:
            # Not ingested yet, download and ingest
            print(f"Filing agent: Ingesting filings for {ticker}...")
            raw_chunks = data_fetcher.get_sec_rag_chunks(ticker, "10-K")
            await vector_store.save_chunks(raw_chunks)
            
        # 2. Query vector store for relevant chunks
        queries = [
            "What are the major business segments and revenue drivers?",
            "What are the biggest risk factors and challenges listed?",
            "What is the management discussion, outlook, and future guidance?"
        ]
        
        context_blocks = []
        for q in queries:
            results = await vector_store.similarity_search(ticker, q, limit=3)
            for res in results:
                context_blocks.append(
                    f"[{res['section']} ({res['date']})]\nUrl: {res['url']}\nContent: {res['content']}"
                )
        
        rag_context = "\n\n---\n\n".join(context_blocks)
        
        # 3. Invoke LLM with RAG context
        user_prompt = (
            f"Analyze SEC filings for ticker: {ticker}.\n\n"
            f"Here is the RAG Context retrieved from the SEC filings:\n"
            f"{rag_context}\n\n"
            f"Extract the business segments, risks, outlook, and cite specific pages/items."
        )
        
        print(f"Filing agent: Querying LLM for {ticker} filing analysis...")
        result_json = llm_client.call_gemini(
            system_prompt=self.system_prompt,
            user_prompt=user_prompt,
            response_schema=FilingAnalysisSchema,
            ticker=ticker
        )
        
        try:
            return json.loads(result_json)
        except Exception as e:
            print(f"Filing agent: Error parsing JSON from LLM: {e}")
            # Try to return raw string wrapped in a dict or default mock
            return json.loads(llm_client._generate_mock_response(self.system_prompt, user_prompt, ticker, FilingAnalysisSchema))

filing_agent = FilingAgent()
import json
