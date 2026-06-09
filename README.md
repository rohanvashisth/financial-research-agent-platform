# AI-Powered Financial Research Agent Platform

An enterprise-grade, multi-agent financial research and equity analysis platform. The system leverages **FastAPI** on the backend to orchestrate specialized worker agents and broker live telemetry via **WebSockets** to a **React (TypeScript + Tailwind CSS)** dashboard. 

The platform fetches raw XBRL financial filings directly from the **SEC EDGAR API** (prioritizing official 10-K/10-Q statements over third-party APIs), processes vector embeddings via a semantic RAG pipeline, runs a dynamic WACC-based Discounted Cash Flow (DCF) model, and generates publication-ready research briefings.

---

## 🌟 Core Features

1. **Multi-Agent Orchestration Workflow**: Coordinates 5 specialized AI agents (Filing, Metrics, News, Valuation, and Report) sequentially to build comprehensive research memos.
2. **SEC EDGAR Direct Ingestion**: Extracts raw XBRL facts straight from SEC EDGAR. Resolves historical accounting tag shifts (e.g., ASC 606 shifts post-2018) using a priority-reverse merging strategy, cleans date series via period-duration filtering, and uses gross profit-operating expense proxies for missing metrics.
3. **Interactive SEC RAG Chat Pipeline**: Semantic chunking and vector storage of filings to answer questions grounded with citations and clickable SEC filing URLs.
4. **Premium Glassmorphic Dashboard**: Built with React, TypeScript, and Tailwind CSS. Includes real-time WebSocket log streaming, stock charting, and professional-standard accounting tables (right-aligned numbers, indented child metrics, double-underline net totals).
5. **Dual-Profile Runtime Modes**:
   - **Local Mode (Default)**: Runs out-of-the-box using SQLite, a pure-Python vector database, and local `asyncio.Queue` event-brokering.
   - **Production Mode**: Connects to **PostgreSQL (pgvector)** and **Apache Kafka** for cloud deployments.
6. **Model Context Protocol (MCP) Integration**: Exposes SEC ingestion, search, and ratio analysis tools to MCP-compatible LLM desktop clients (e.g., Claude Desktop).
7. **Git Auto-Commit Daemon**: Runs a background watchdog loop (`autocommit.py`) that stages, commits, and pushes file changes to the remote GitHub repository every 10 seconds.

---

## 📁 Repository Structure

```
├── backend/
│   ├── agents/                 # Multi-agent definitions & workflow state machine
│   │   ├── filing_agent.py     # Extracts business units, risks, and guidance
│   │   ├── metrics_agent.py    # Calculates growth and health ratios
│   │   ├── news_agent.py       # Sentiment analyst and news summarizer
│   │   ├── valuation_agent.py  # Runs WACC-based 5-year DCF & peer multiples
│   │   ├── report_agent.py     # Synthesizes markdown research memos
│   │   ├── workflow.py         # Sequential state machine runner
│   │   └── llm_client.py       # Gemini API client with smart local mock fallbacks
│   ├── services/               # System abstraction layer files
│   │   ├── data_fetcher.py     # Direct SEC XBRL parser & yfinance fallback
│   │   ├── vector_store.py     # Resolves SQLite / pgvector search profiles
│   │   └── event_broker.py     # Resolves In-Memory / Kafka messaging profiles
│   ├── main.py                 # FastAPI endpoints & WebSocket router
│   ├── mcp_server.py           # Model Context Protocol server exposing tools
│   ├── config.py               # Env configuration & path resolver
│   └── requirements.txt        # Python dependency manifest
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # Main React application & table formatter
│   │   ├── index.css           # Tailwind injections & scrollbar classes
│   │   └── main.tsx            # App entrypoint
│   ├── tailwind.config.js      # CSS configuration
│   ├── package.json            # Node.js project manifest
│   └── vite.config.ts          # Vite compilation config
├── data/                       # Local SQLite storage and compiled reports
├── docker-compose.yml          # Container configuration for Postgres & Kafka
├── autocommit.py               # Repository auto-commit background daemon
└── .env                        # Local environment parameters
```

---

## ⚙️ Quick Start Guide (Local Mode)

Local mode runs instantly using SQLite and local queues without needing Docker.

### 1. Set Up Environment Variables
Create a `.env` file in the root directory:
```env
RUN_MODE=local
GEMINI_API_KEY=your_gemini_api_key_here
SEC_USER_AGENT=YourName contact@email.com
```

### 2. Launch the Backend Server
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate

# Install dependencies and start server
pip install -r backend/requirements.txt
$env:PYTHONPATH="."       # Linux/macOS: export PYTHONPATH=.
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
*API docs will be available at `http://localhost:8000/docs`.*

### 3. Launch the Frontend Dashboard
In a separate terminal window:
```bash
cd frontend
npm install
npm run dev
```
*Open `http://localhost:5173/` in your browser to interact with the platform.*

---

## 🐳 Docker Deployment (Production Mode)

Production mode activates PostgreSQL with `pgvector` and an Apache Kafka message broker.

1. **Spin Up Containers**:
   ```bash
   docker-compose up -d
   ```
2. **Switch Execution Profile**:
   Set `RUN_MODE=production` in your `.env` along with the corresponding `POSTGRES_*` and `KAFKA_*` endpoints, then restart the backend service.

---

## 🔌 Model Context Protocol (MCP) Setup

You can expose the agent's financial research tools directly to desktop applications like **Claude Desktop**. 

Add the following to your Claude Desktop configuration file (e.g., `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "financial-research": {
      "command": "python",
      "args": [
        "c:/Rohan/Projects/Financial Research Agent Platform/backend/mcp_server.py"
      ],
      "env": {
        "PYTHONPATH": "c:/Rohan/Projects/Financial Research Agent Platform",
        "GEMINI_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

---

## 🤖 Auto-Commit Watchdog

To maintain active sync of modifications during work, run the autocommit daemon in the background:
```bash
python autocommit.py
```
This script runs a lightweight loop that automatically stages, commits, and pushes any local changes to your git remote origin every 10 seconds.
