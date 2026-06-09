import React, { useState, useEffect, useRef } from 'react';
import { 
  Search, 
  Cpu, 
  FileText, 
  MessageSquare, 
  TrendingUp, 
  DollarSign, 
  AlertCircle, 
  Database, 
  Share2, 
  CheckCircle2, 
  ChevronRight,
  RefreshCw,
  Info
} from 'lucide-react';
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  Tooltip, 
  ResponsiveContainer 
} from 'recharts';
import ReactMarkdown from 'react-markdown';

interface TickerInfo {
  ticker: string;
  name: string;
  sector: string;
  industry: string;
  summary: string;
  employees: number | string;
  website: string;
  market_cap: number;
  pe_ratio: number | string;
  forward_pe: number | string;
  price_to_sales: number | string;
  dividend_yield: number;
  logo_url: string;
}

interface PricePoint {
  date: string;
  close: number;
  open: number;
  high: number;
  low: number;
  volume: number;
}

interface LogEntry {
  timestamp: string;
  stage: string;
  message: string;
  status: string;
}

interface ChatMessage {
  sender: 'user' | 'bot';
  text: string;
  sources?: Array<{ section: string; url: string; date: string }>;
}

export default function App() {
  // Search state
  const [ticker, setTicker] = useState('MSFT');
  const [searchInput, setSearchInput] = useState('MSFT');
  
  // Data states
  const [tickerInfo, setTickerInfo] = useState<TickerInfo | null>(null);
  const [priceHistory, setPriceHistory] = useState<PricePoint[]>([]);
  const [reportMarkdown, setReportMarkdown] = useState('');
  const [agentOutputs, setAgentOutputs] = useState<any>(null);
  const [financials, setFinancials] = useState<any>(null);
  const [financialSubTab, setFinancialSubTab] = useState<'ratios' | 'income' | 'balance' | 'cash'>('ratios');
  
  // UI states
  const [activeTab, setActiveTab] = useState<'memo' | 'chat' | 'pipeline' | 'financials' | 'valuation' | 'news'>('memo');
  const [loading, setLoading] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [wsError, setWsError] = useState<string | null>(null);
  
  // Pipeline Stepper states
  const [pipelineStages, setPipelineStages] = useState({
    init: 'idle',      // idle, running, completed, failed
    filing: 'idle',
    metrics: 'idle',
    news: 'idle',
    valuation: 'idle',
    report: 'idle'
  });

  // RAG Chat states
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    { 
      sender: 'bot', 
      text: "Hello! I am the SEC Filing RAG assistant. Ask me anything about this company's latest 10-K or 10-Q filings, and I will answer with grounded citations." 
    }
  ]);
  const [chatLoading, setChatLoading] = useState(false);

  // References
  const terminalEndRef = useRef<HTMLDivElement>(null);
  const socketRef = useRef<WebSocket | null>(null);

  // Fetch ticker metadata and chart history on mount / search
  const fetchTickerData = async (symbol: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/ticker/${symbol}`);
      if (!res.ok) throw new Error("Ticker not found");
      const data = await res.json();
      setTickerInfo(data.info);
      setPriceHistory(data.history);
      setFinancials(data.financials);
      return data.info;
    } catch (e) {
      console.error("Error fetching ticker metadata:", e);
      return null;
    }
  };

  // Attempt to load existing report from cache
  const loadExistingReport = async (symbol: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/reports/${symbol}`);
      if (res.ok) {
        const data = await res.json();
        setReportMarkdown(data.report);
        setAgentOutputs(data.agent_outputs);
        // Set steps to completed
        setPipelineStages({
          init: 'completed',
          filing: 'completed',
          metrics: 'completed',
          news: 'completed',
          valuation: 'completed',
          report: 'completed'
        });
        return true;
      }
    } catch (e) {
      console.log("No existing report cached.");
    }
    return false;
  };

  // Run the multi-agent research workflow via WebSocket
  const startResearchWorkflow = (symbol: string) => {
    if (socketRef.current) {
      socketRef.current.close();
    }

    setLoading(true);
    setLogs([]);
    setReportMarkdown('');
    setAgentOutputs(null);
    setWsError(null);
    setActiveTab('pipeline');
    
    // Reset steps
    setPipelineStages({
      init: 'running',
      filing: 'idle',
      metrics: 'idle',
      news: 'idle',
      valuation: 'idle',
      report: 'idle'
    });

    const wsUrl = `ws://localhost:8000/ws/research/${symbol}`;
    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    socket.onopen = () => {
      setWsConnected(true);
      setWsError(null);
    };

    socket.onmessage = (event) => {
      try {
        const log = JSON.parse(event.data);
        
        // Append log to console
        setLogs(prev => [...prev, {
          timestamp: log.timestamp,
          stage: log.stage,
          message: log.message,
          status: log.status
        }]);

        // Update pipeline steps
        if (log.stage === 'finished') {
          setPipelineStages({
            init: 'completed',
            filing: 'completed',
            metrics: 'completed',
            news: 'completed',
            valuation: 'completed',
            report: 'completed'
          });
          if (log.data && log.data.report) {
            setReportMarkdown(log.data.report);
            setAgentOutputs(log.data.agent_outputs);
          }
          setLoading(false);
          setActiveTab('memo');
          socket.close();
        } else if (log.stage === 'error') {
          setPipelineStages(prev => ({ ...prev, [log.data?.stage || 'init']: 'failed' }));
          setWsError(log.message);
          setLoading(false);
          socket.close();
        } else {
          // General step transitions
          setPipelineStages(prev => {
            const copy = { ...prev } as any;
            if (log.status === 'running') {
              copy[log.stage] = 'running';
            } else if (log.status === 'completed') {
              copy[log.stage] = 'completed';
            }
            return copy;
          });
        }
      } catch (err) {
        console.error("Error parsing WebSocket log message:", err);
      }
    };

    socket.onclose = () => {
      setWsConnected(false);
      setLoading(false);
    };

    socket.onerror = (err) => {
      console.error("WebSocket error:", err);
      setWsError("Failed to connect to backend event stream.");
      setLoading(false);
    };
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchInput) return;
    const cleanSymbol = searchInput.toUpperCase().trim();
    setTicker(cleanSymbol);
    
    // 1. Fetch metadata
    await fetchTickerData(cleanSymbol);
    
    // 2. Check if report already exists, if so load it
    const exists = await loadExistingReport(cleanSymbol);
    if (!exists) {
      // 3. Otherwise run pipeline
      startResearchWorkflow(cleanSymbol);
    }
  };

  const handleForceResearch = () => {
    startResearchWorkflow(ticker);
  };

  // RAG Chat Submission
  const handleSendChatMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || chatLoading) return;

    const userMsg = chatInput;
    setChatInput('');
    setChatMessages(prev => [...prev, { sender: 'user', text: userMsg }]);
    setChatLoading(true);

    try {
      const res = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, query: userMsg })
      });
      if (!res.ok) throw new Error("Chat request failed");
      const data = await res.json();
      
      setChatMessages(prev => [...prev, { 
        sender: 'bot', 
        text: data.answer, 
        sources: data.sources 
      }]);
    } catch (err) {
      console.error(err);
      setChatMessages(prev => [...prev, { 
        sender: 'bot', 
        text: "Sorry, I encountered an error searching the filings." 
      }]);
    } finally {
      setChatLoading(false);
    }
  };

  // Scroll terminal to bottom
  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // Load initial ticker MSFT on mount
  useEffect(() => {
    const init = async () => {
      await fetchTickerData('MSFT');
      await loadExistingReport('MSFT');
    };
    init();
    
    return () => {
      if (socketRef.current) socketRef.current.close();
    };
  }, []);

  const formatNumber = (num: number) => {
    if (!num) return 'N/A';
    if (num >= 1e12) return `$${(num / 1e12).toFixed(2)}T`;
    if (num >= 1e9) return `$${(num / 1e9).toFixed(2)}B`;
    if (num >= 1e6) return `$${(num / 1e6).toFixed(2)}M`;
    return `$${num.toLocaleString()}`;
  };

  const getStepColor = (status: string) => {
    if (status === 'running') return 'text-secondary border-secondary bg-secondary/10';
    if (status === 'completed') return 'text-primary border-primary bg-primary/10';
    if (status === 'failed') return 'text-red-500 border-red-500 bg-red-500/10';
    return 'text-gray-500 border-border bg-card';
  };

  const getMetricStyle = (metric: string) => {
    const finalTotals = [
      'net income',
      'total liabilities & equity',
      'free cash flow'
    ];

    const subtotals = [
      'total revenue',
      'gross profit',
      'operating expenses',
      'operating income',
      'total current assets',
      'total assets',
      'total current liabilities',
      'total liabilities',
      'stockholders equity',
      'operating cash flow',
      'investing cash flow',
      'financing cash flow',
      'net change in cash'
    ];

    const indented = [
      'cost of revenue',
      'research & development',
      'sg&a',
      'interest expense',
      'tax expense',
      'cash & cash equivalents',
      'short-term investments',
      'accounts receivable',
      'inventory',
      'pp&e net',
      'goodwill & intangibles',
      'accounts payable',
      'short-term debt',
      'long-term debt',
      'retained earnings',
      'net income (cash flow)',
      'depreciation & amortization',
      'share-based compensation',
      'capital expenditures'
    ];

    const lower = metric.toLowerCase().trim();

    if (finalTotals.includes(lower)) {
      return {
        rowClass: "border-t border-border/60 hover:bg-card/50 text-white font-bold bg-white/5",
        metricClass: "p-3 pl-4 text-white font-bold border-b-4 border-double border-primary/50",
        cellClass: "p-3 text-white font-bold font-mono border-b-4 border-double border-primary/50"
      };
    }

    if (subtotals.includes(lower)) {
      return {
        rowClass: "border-t border-b border-border/80 hover:bg-card/45 text-white font-semibold bg-white/2",
        metricClass: "p-3 pl-4 text-white font-semibold",
        cellClass: "p-3 text-white font-semibold font-mono"
      };
    }

    if (indented.includes(lower)) {
      return {
        rowClass: "border-b border-border/20 hover:bg-card/30 text-gray-400",
        metricClass: "p-3 pl-8 text-gray-400 font-normal italic",
        cellClass: "p-3 text-gray-400 font-normal font-mono"
      };
    }

    return {
      rowClass: "border-b border-border/40 hover:bg-card/40 text-gray-300",
      metricClass: "p-3 pl-4 text-gray-300 font-medium",
      cellClass: "p-3 text-gray-300 font-mono"
    };
  };

  const renderFinancialTable = (type: 'income' | 'balance' | 'cash') => {
    if (!financials) {
      return (
        <div className="text-gray-500 text-center py-10 italic">
          No financial statement data loaded. Enter a ticker to fetch statements.
        </div>
      );
    }

    let annualData: any = {};
    let quarterlyData: any = {};
    let title = "";

    if (type === 'income') {
      annualData = financials.income_statement || {};
      quarterlyData = financials.quarterly_income_statement || {};
      title = "Income Statement";
    } else if (type === 'balance') {
      annualData = financials.balance_sheet || {};
      quarterlyData = financials.quarterly_balance_sheet || {};
      title = "Balance Sheet";
    } else {
      annualData = financials.cash_flow || {};
      quarterlyData = financials.quarterly_cash_flow || {};
      title = "Cash Flow Statement";
    }

    const metrics = Object.keys(annualData);
    if (metrics.length === 0) {
      return (
        <div className="text-gray-500 text-center py-10 italic">
          No statement data available for this ticker.
        </div>
      );
    }

    const firstMetric = metrics[0];
    const annualDates = Object.keys(annualData[firstMetric] || {}).sort((a, b) => b.localeCompare(a));
    const quarterlyDates = Object.keys(quarterlyData[firstMetric] || {}).sort((a, b) => b.localeCompare(a)).slice(0, 3);

    const latestAnnualDate = annualDates[0];
    const columns: { date: string; type: string }[] = [];
    if (latestAnnualDate) columns.push({ date: latestAnnualDate, type: 'Annual (LTM)' });
    
    // Last 3 Quarters
    quarterlyDates.forEach((qDate, idx) => {
      columns.push({ date: qDate, type: `Quarter ${idx + 1}` });
    });

    const formatAmount = (val: any) => {
      if (val === undefined || val === null || isNaN(val)) return '-';
      if (Math.abs(val) >= 1e9) {
        return `${(val / 1e9).toFixed(2)}B`;
      } else if (Math.abs(val) >= 1e6) {
        return `${(val / 1e6).toFixed(1)}M`;
      }
      return val.toLocaleString();
    };

    return (
      <div className="bg-card rounded-xl border border-border overflow-hidden flex-1 flex flex-col">
        <div className="p-4 border-b border-border bg-card/60 flex items-center justify-between">
          <h4 className="text-xs font-bold text-white uppercase tracking-wider">{title}</h4>
          <span className="text-[10px] text-gray-400">Values in Millions/Billions</span>
        </div>
        <div className="overflow-x-auto overflow-y-auto max-h-[400px]">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-border bg-card/20 text-gray-500 font-semibold sticky top-0 bg-card z-10">
                <th className="p-3 pl-4">Financial Metric</th>
                {columns.map((col, idx) => (
                  <th key={idx} className="p-3 text-right pr-6">
                    <div>{col.date}</div>
                    <div className="text-[9px] text-primary font-normal">{col.type}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metrics.map((metric, idx) => {
                if (metric.toLowerCase() === 'ticker' || metric.toLowerCase() === 'cik') return null;
                const style = getMetricStyle(metric);
                return (
                  <tr key={idx} className={style.rowClass}>
                    <td className={style.metricClass}>{metric}</td>
                    {columns.map((col, cIdx) => {
                      const val = col.type.startsWith('Annual')
                        ? annualData[metric]?.[col.date]
                        : quarterlyData[metric]?.[col.date];
                      return (
                        <td key={cIdx} className={`p-3 text-right pr-6 ${style.cellClass}`}>
                          {formatAmount(val)}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-background text-gray-100 flex flex-col font-sans">
      
      {/* Top Navbar */}
      <header className="border-b border-border glass px-6 py-4 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center space-x-3">
          <div className="bg-primary/20 p-2 rounded-lg border border-primary/30">
            <Cpu className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight bg-gradient-to-r from-white via-gray-200 to-gray-400 bg-clip-text text-transparent">
              Financial Research Agent Platform
            </h1>
            <p className="text-xs text-gray-400">Multi-Agent Equity Briefings & SEC RAG</p>
          </div>
        </div>

        {/* Search form */}
        <form onSubmit={handleSearch} className="flex items-center space-x-2 max-w-md w-full mx-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 h-4.5 w-4.5 text-gray-400" />
            <input
              type="text"
              placeholder="Enter stock ticker (e.g. MSFT, AAPL, TSLA)..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="bg-card/80 border border-border rounded-lg pl-10 pr-4 py-2 w-full text-sm focus:outline-none focus:border-secondary focus:ring-1 focus:ring-secondary transition-all"
            />
          </div>
          <button 
            type="submit" 
            disabled={loading}
            className="bg-primary hover:bg-primary/80 disabled:opacity-50 text-black font-semibold text-sm px-4 py-2 rounded-lg transition-all flex items-center space-x-1 cursor-pointer"
          >
            {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <span>Analyze</span>}
          </button>
        </form>

        {/* Status Indicators */}
        <div className="flex items-center space-x-4 text-xs">
          <div className="flex items-center space-x-1.5">
            <Database className="h-4 w-4 text-gray-400" />
            <span className="text-gray-400">Mode:</span>
            <span className="font-semibold text-emerald-400 border border-emerald-400/20 px-2 py-0.5 rounded-full bg-emerald-400/10 uppercase tracking-wider text-[10px]">
              Local/Lite
            </span>
          </div>
          <div className="flex items-center space-x-1.5">
            <div className={`h-2.5 w-2.5 rounded-full ${wsConnected ? 'bg-secondary animate-pulse' : 'bg-gray-500'}`} />
            <span className="text-gray-400">{wsConnected ? 'Live Connection' : 'Idle'}</span>
          </div>
        </div>
      </header>

      {/* Main Workspace Layout */}
      <main className="flex-1 p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 max-w-[1600px] w-full mx-auto">
        
        {/* Left Column (Metadata & Stock Chart) - 4 Cols */}
        <section className="lg:col-span-4 flex flex-col space-y-6">
          
          {/* Metadata Card */}
          {tickerInfo ? (
            <div className="glass rounded-xl p-5 flex flex-col space-y-4 relative overflow-hidden">
              <div className="absolute right-0 top-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl" />
              <div className="flex items-start justify-between">
                <div className="flex items-center space-x-3">
                  {tickerInfo.logo_url ? (
                    <img 
                      src={tickerInfo.logo_url} 
                      alt={tickerInfo.name} 
                      className="w-10 h-10 rounded-lg bg-white p-1 border border-border"
                      onError={(e) => { (e.target as any).style.display = 'none'; }}
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-lg bg-card border border-border flex items-center justify-center font-bold text-primary text-sm">
                      {tickerInfo.ticker}
                    </div>
                  )}
                  <div>
                    <h2 className="text-base font-bold text-white flex items-center space-x-1.5">
                      <span>{tickerInfo.name}</span>
                      <span className="text-xs text-primary bg-primary/10 border border-primary/20 px-2 py-0.25 rounded-md font-mono">
                        {tickerInfo.ticker}
                      </span>
                    </h2>
                    <p className="text-xs text-gray-400">{tickerInfo.sector} • {tickerInfo.industry}</p>
                  </div>
                </div>
              </div>

              {/* Price & Valuation Grid */}
              <div className="grid grid-cols-2 gap-4 border-t border-border pt-4">
                <div>
                  <p className="text-[10px] uppercase text-gray-500 tracking-wider">Market Capitalization</p>
                  <p className="text-sm font-semibold text-white mt-0.5">{formatNumber(tickerInfo.market_cap)}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase text-gray-500 tracking-wider">Trailing PE Ratio</p>
                  <p className="text-sm font-semibold text-white mt-0.5">{tickerInfo.pe_ratio}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase text-gray-500 tracking-wider">Price to Sales (LTM)</p>
                  <p className="text-sm font-semibold text-white mt-0.5">{tickerInfo.price_to_sales}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase text-gray-500 tracking-wider">Dividend Yield</p>
                  <p className="text-sm font-semibold text-white mt-0.5">{(tickerInfo.dividend_yield * 100).toFixed(2)}%</p>
                </div>
              </div>

              <div className="border-t border-border pt-3">
                <p className="text-[10px] uppercase text-gray-500 tracking-wider mb-1">Company Description</p>
                <p className="text-xs text-gray-400 leading-relaxed line-clamp-3">
                  {tickerInfo.summary}
                </p>
              </div>
            </div>
          ) : (
            <div className="glass rounded-xl p-6 flex flex-col items-center justify-center h-48 text-gray-500 text-sm">
              <Info className="h-8 w-8 text-gray-600 mb-2 animate-bounce" />
              <span>Enter a ticker symbol to load metadata</span>
            </div>
          )}

          {/* Price Chart Card */}
          {priceHistory.length > 0 && (
            <div className="glass rounded-xl p-5 flex flex-col space-y-4 flex-1">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center space-x-1.5">
                    <TrendingUp className="h-4.5 w-4.5 text-primary" />
                    <span>Historical Trading History</span>
                  </h3>
                  <p className="text-[10px] text-gray-400">1 Year Daily Close Prices ($)</p>
                </div>
                {priceHistory.length > 0 && (
                  <span className="text-xs font-mono font-semibold text-primary">
                    LTM Close: ${priceHistory[priceHistory.length - 1].close.toFixed(2)}
                  </span>
                )}
              </div>

              {/* Chart container */}
              <div className="h-60 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={priceHistory} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorClose" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <XAxis 
                      dataKey="date" 
                      stroke="#4b5563" 
                      tick={{ fill: '#9ca3af', fontSize: 9 }}
                      tickFormatter={(tick) => tick.substring(2, 7)}
                    />
                    <YAxis 
                      stroke="#4b5563" 
                      tick={{ fill: '#9ca3af', fontSize: 9 }} 
                      domain={['auto', 'auto']}
                    />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#11131c', border: '1px solid #1f2231', borderRadius: '8px' }}
                      labelStyle={{ color: '#9ca3af', fontSize: '10px' }}
                      itemStyle={{ color: '#10b981', fontSize: '11px', fontWeight: 'bold' }}
                    />
                    <Area type="monotone" dataKey="close" stroke="#10b981" strokeWidth={1.5} fillOpacity={1} fill="url(#colorClose)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              {/* Actions panel */}
              <div className="border-t border-border pt-4 flex items-center justify-between">
                <span className="text-[10px] text-gray-500">Live data sourced via Yahoo Finance API</span>
                <button
                  onClick={handleForceResearch}
                  disabled={loading}
                  className="text-xs border border-border hover:bg-card px-3 py-1.5 rounded-lg flex items-center space-x-1.5 cursor-pointer text-gray-300 font-semibold"
                >
                  <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
                  <span>Force Re-Run agents</span>
                </button>
              </div>
            </div>
          )}
        </section>

        {/* Right Column (Tabs Container) - 8 Cols */}
        <section className="lg:col-span-8 flex flex-col glass rounded-xl overflow-hidden min-h-[600px] border border-border">
          
          {/* Tabs header */}
          <div className="flex border-b border-border bg-card/40 overflow-x-auto">
            <button
              onClick={() => setActiveTab('memo')}
              className={`px-5 py-3.5 text-xs font-semibold flex items-center space-x-2 border-b-2 transition-all cursor-pointer ${
                activeTab === 'memo' ? 'text-primary border-primary bg-background/30' : 'text-gray-400 border-transparent hover:text-white'
              }`}
            >
              <FileText className="h-4 w-4" />
              <span>Research Brief</span>
            </button>
            <button
              onClick={() => setActiveTab('pipeline')}
              className={`px-5 py-3.5 text-xs font-semibold flex items-center space-x-2 border-b-2 transition-all cursor-pointer ${
                activeTab === 'pipeline' ? 'text-primary border-primary bg-background/30' : 'text-gray-400 border-transparent hover:text-white'
              }`}
            >
              <Cpu className="h-4 w-4" />
              <span>Agent Workflow</span>
            </button>
            <button
              onClick={() => setActiveTab('chat')}
              className={`px-5 py-3.5 text-xs font-semibold flex items-center space-x-2 border-b-2 transition-all cursor-pointer ${
                activeTab === 'chat' ? 'text-primary border-primary bg-background/30' : 'text-gray-400 border-transparent hover:text-white'
              }`}
            >
              <MessageSquare className="h-4 w-4" />
              <span>SEC RAG Chat</span>
            </button>
            <button
              onClick={() => setActiveTab('financials')}
              className={`px-5 py-3.5 text-xs font-semibold flex items-center space-x-2 border-b-2 transition-all cursor-pointer ${
                activeTab === 'financials' ? 'text-primary border-primary bg-background/30' : 'text-gray-400 border-transparent hover:text-white'
              }`}
            >
              <TrendingUp className="h-4 w-4" />
              <span>Financial Health</span>
            </button>
            <button
              onClick={() => setActiveTab('valuation')}
              className={`px-5 py-3.5 text-xs font-semibold flex items-center space-x-2 border-b-2 transition-all cursor-pointer ${
                activeTab === 'valuation' ? 'text-primary border-primary bg-background/30' : 'text-gray-400 border-transparent hover:text-white'
              }`}
            >
              <DollarSign className="h-4 w-4" />
              <span>Valuation & Peers</span>
            </button>
            <button
              onClick={() => setActiveTab('news')}
              className={`px-5 py-3.5 text-xs font-semibold flex items-center space-x-2 border-b-2 transition-all cursor-pointer ${
                activeTab === 'news' ? 'text-primary border-primary bg-background/30' : 'text-gray-400 border-transparent hover:text-white'
              }`}
            >
              <Share2 className="h-4 w-4" />
              <span>Sentiment Feed</span>
            </button>
          </div>

          {/* Tabs body */}
          <div className="flex-1 p-6 overflow-y-auto bg-card/10 flex flex-col">
            
            {/* Tab 1: Markdown Report */}
            {activeTab === 'memo' && (
              <div className="prose prose-invert max-w-none text-xs leading-relaxed space-y-4 select-text">
                {reportMarkdown ? (
                  <div className="markdown-body text-gray-300">
                    <ReactMarkdown>{reportMarkdown}</ReactMarkdown>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
                    <FileText className="h-12 w-12 text-gray-600" />
                    <div>
                      <h4 className="text-sm font-bold text-white">No research report active.</h4>
                      <p className="text-xs text-gray-500 mt-1 max-w-sm">
                        Please type a ticker symbol at the top and hit "Analyze" to run the multi-agent workflow.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Tab 2: Agent execution stream logs */}
            {activeTab === 'pipeline' && (
              <div className="flex-1 flex flex-col space-y-6">
                
                {/* Visual Pipeline Stepper */}
                <div className="grid grid-cols-6 gap-2 bg-card/60 p-4 rounded-xl border border-border">
                  {[
                    { key: 'init', name: 'Start' },
                    { key: 'filing', name: 'Filing RAG' },
                    { key: 'metrics', name: 'Financials' },
                    { key: 'news', name: 'Sentiment' },
                    { key: 'valuation', name: 'Valuation' },
                    { key: 'report', name: 'Synthesis' }
                  ].map((step, idx) => {
                    const status = (pipelineStages as any)[step.key];
                    return (
                      <div key={step.key} className="flex flex-col items-center text-center space-y-2 relative">
                        <div className={`w-8 h-8 rounded-full border flex items-center justify-center font-bold text-xs ${getStepColor(status)} transition-all`}>
                          {status === 'completed' ? <CheckCircle2 className="h-5 w-5 text-primary" /> : idx + 1}
                        </div>
                        <span className="text-[10px] font-semibold text-gray-300">{step.name}</span>
                        {idx < 5 && (
                          <div className="hidden sm:block absolute top-4 left-[65%] right-[-35%] h-[1px] bg-border z-0" />
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Live Console Terminal */}
                <div className="flex-1 bg-black/80 rounded-xl p-4 border border-border font-mono text-xs flex flex-col min-h-[350px] relative">
                  
                  {/* Terminal Header */}
                  <div className="flex items-center justify-between border-b border-border/40 pb-2 mb-3">
                    <div className="flex items-center space-x-1.5">
                      <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
                      <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/80" />
                      <div className="w-2.5 h-2.5 rounded-full bg-green-500/80" />
                      <span className="text-gray-500 ml-2 text-[10px]">agent_workflow_stream.log</span>
                    </div>
                    {loading && (
                      <div className="flex items-center space-x-1">
                        <RefreshCw className="h-3 w-3 text-secondary animate-spin" />
                        <span className="text-secondary text-[10px]">Streaming...</span>
                      </div>
                    )}
                  </div>

                  {/* Terminal Logs Container */}
                  <div className="flex-1 overflow-y-auto space-y-2 max-h-[350px] pr-2">
                    {logs.length === 0 ? (
                      <div className="text-gray-600 italic py-10 text-center">
                        Terminal idle. Start research pipeline to stream agent reasoning steps...
                      </div>
                    ) : (
                      logs.map((log, index) => {
                        let color = 'text-gray-400';
                        if (log.status === 'completed') color = 'text-primary';
                        if (log.status === 'failed') color = 'text-red-400 font-bold';
                        if (log.stage === 'finished') color = 'text-yellow-400 font-bold';
                        
                        return (
                          <div key={index} className="flex items-start space-x-2">
                            <span className="text-gray-600 font-semibold shrink-0">[{log.timestamp}]</span>
                            <span className="text-secondary shrink-0 font-bold">[{log.stage.toUpperCase()}]</span>
                            <span className={`${color} leading-relaxed`}>{log.message}</span>
                          </div>
                        );
                      })
                    )}
                    <div ref={terminalEndRef} />
                  </div>

                  {/* Errors and Warnings */}
                  {wsError && (
                    <div className="bg-red-950/40 border border-red-500/30 text-red-300 p-3 rounded-lg flex items-center space-x-2 mt-4 font-sans">
                      <AlertCircle className="h-5 w-5 text-red-400 shrink-0" />
                      <span>{wsError}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Tab 3: SEC RAG Chat */}
            {activeTab === 'chat' && (
              <div className="flex-1 flex flex-col space-y-4">
                
                {/* Instructions banner */}
                <div className="bg-card/40 p-4 rounded-xl border border-border flex items-start space-x-3 text-xs leading-relaxed text-gray-400">
                  <Database className="h-5 w-5 text-primary shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-white">Interactive SEC Ingestion RAG Pipeline</span>
                    <p className="mt-1">
                      Enter any question below regarding {ticker}'s corporate filings. The pipeline runs a local semantic similarity search against the embedded sections of the latest 10-K, fetches relevant context, and reasons over it.
                    </p>
                  </div>
                </div>

                {/* Chat Message thread */}
                <div className="flex-1 overflow-y-auto space-y-4 border border-border/40 rounded-xl p-4 min-h-[300px] max-h-[400px] bg-black/20 flex flex-col">
                  {chatMessages.map((msg, index) => (
                    <div 
                      key={index}
                      className={`flex flex-col max-w-[85%] rounded-xl p-3 text-xs leading-relaxed ${
                        msg.sender === 'user' 
                          ? 'bg-secondary/20 text-white border border-secondary/30 self-end'
                          : 'bg-card text-gray-300 border border-border self-start'
                      }`}
                    >
                      <span className="font-semibold text-[10px] uppercase text-gray-500 mb-1">
                        {msg.sender === 'user' ? 'You' : 'SEC RAG Agent'}
                      </span>
                      <p className="whitespace-pre-line">{msg.text}</p>
                      
                      {/* Citing Sources */}
                      {msg.sources && msg.sources.length > 0 && (
                        <div className="border-t border-border/50 pt-2 mt-2 flex flex-col space-y-1">
                          <span className="text-[10px] font-bold text-primary flex items-center space-x-1">
                            <Info className="h-3 w-3" />
                            <span>Grounded Citations:</span>
                          </span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {msg.sources.map((src, sIdx) => (
                              <a 
                                key={sIdx}
                                href={src.url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-[9px] bg-border hover:bg-card border border-border px-2 py-0.5 rounded text-gray-400 hover:text-white transition-all font-mono"
                              >
                                {src.section} ({src.date})
                              </a>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                  {chatLoading && (
                    <div className="bg-card text-gray-400 border border-border rounded-xl p-3 text-xs self-start max-w-[80%] flex items-center space-x-2">
                      <RefreshCw className="h-4 w-4 animate-spin text-primary" />
                      <span>Retrieving filings and drafting source-grounded response...</span>
                    </div>
                  )}
                </div>

                {/* Chat Input form */}
                <form onSubmit={handleSendChatMessage} className="flex space-x-2">
                  <input
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    placeholder={`Ask about ${ticker}'s risks, business segments, AI plans...`}
                    className="flex-1 bg-card border border-border rounded-lg px-4 py-2.5 text-xs focus:outline-none focus:border-secondary transition-all"
                  />
                  <button 
                    type="submit"
                    disabled={chatLoading}
                    className="bg-secondary hover:bg-secondary/80 disabled:opacity-50 text-white font-semibold text-xs px-5 py-2.5 rounded-lg transition-all flex items-center space-x-1.5 cursor-pointer"
                  >
                    <span>Ask RAG</span>
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </form>
              </div>
            )}

            {/* Tab 4: Financial Metrics */}
            {activeTab === 'financials' && (
              <div className="flex-1 flex flex-col space-y-6">
                {/* Financial Sub-navigation */}
                <div className="flex items-center space-x-2 border-b border-border/40 pb-2">
                  <button
                    onClick={() => setFinancialSubTab('ratios')}
                    className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                      financialSubTab === 'ratios' ? 'bg-primary text-black' : 'bg-card text-gray-400 border border-border hover:text-white'
                    }`}
                  >
                    Summary & Ratios
                  </button>
                  <button
                    onClick={() => setFinancialSubTab('income')}
                    className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                      financialSubTab === 'income' ? 'bg-primary text-black' : 'bg-card text-gray-400 border border-border hover:text-white'
                    }`}
                  >
                    Income Statement
                  </button>
                  <button
                    onClick={() => setFinancialSubTab('balance')}
                    className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                      financialSubTab === 'balance' ? 'bg-primary text-black' : 'bg-card text-gray-400 border border-border hover:text-white'
                    }`}
                  >
                    Balance Sheet
                  </button>
                  <button
                    onClick={() => setFinancialSubTab('cash')}
                    className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                      financialSubTab === 'cash' ? 'bg-primary text-black' : 'bg-card text-gray-400 border border-border hover:text-white'
                    }`}
                  >
                    Cash Flow
                  </button>
                </div>

                {/* Subtab 1: Ratios Summary (requires agent workflow output) */}
                {financialSubTab === 'ratios' && (
                  <>
                    {agentOutputs?.metrics_agent ? (
                      <div className="space-y-6">
                        {/* Ratio Card Deck */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                          {[
                            { label: 'YoY Growth', val: agentOutputs.metrics_agent.metrics_summary?.revenue_growth_yoy || 'N/A', desc: 'Revenue growth rate' },
                            { label: 'Gross Margin', val: agentOutputs.metrics_agent.metrics_summary?.gross_margin || 'N/A', desc: 'Cost optimization margin' },
                            { label: 'Operating Margin', val: agentOutputs.metrics_agent.metrics_summary?.operating_margin || 'N/A', desc: 'Operating efficiency ratio' },
                            { label: 'Debt to Equity', val: agentOutputs.metrics_agent.metrics_summary?.debt_to_equity || 'N/A', desc: 'Solvency risk multiple' }
                          ].map((card, idx) => (
                            <div key={idx} className="bg-card p-4 rounded-xl border border-border flex flex-col space-y-1">
                              <span className="text-[10px] uppercase text-gray-500 tracking-wider font-semibold">{card.label}</span>
                              <span className="text-lg font-bold text-white">{card.val}</span>
                              <span className="text-[9px] text-gray-400">{card.desc}</span>
                            </div>
                          ))}
                        </div>

                        {/* Trend Commentary */}
                        <div className="bg-card/40 border border-border p-5 rounded-xl space-y-3">
                          <h4 className="text-sm font-bold text-white flex items-center space-x-1.5">
                            <TrendingUp className="h-4.5 w-4.5 text-primary" />
                            <span>Trend & Profitability Analysis</span>
                          </h4>
                          <p className="text-xs text-gray-300 leading-relaxed">
                            {agentOutputs.metrics_agent?.trend_analysis}
                          </p>
                        </div>

                        {/* Risk Signals */}
                        <div className="bg-red-950/20 border border-red-500/20 p-5 rounded-xl space-y-3">
                          <h4 className="text-sm font-bold text-red-400 flex items-center space-x-1.5">
                            <AlertCircle className="h-4.5 w-4.5 text-red-400" />
                            <span>Financial Risk Signals</span>
                          </h4>
                          <p className="text-xs text-red-200 leading-relaxed">
                            {agentOutputs.metrics_agent?.risk_signals}
                          </p>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center py-20 text-center text-gray-500 space-y-4">
                        <TrendingUp className="h-12 w-12 text-gray-600 animate-pulse" />
                        <div>
                          <h4 className="text-sm font-bold text-white">Ratios require analysis</h4>
                          <p className="text-xs text-gray-500 mt-1 max-w-sm">
                            Run the research workflow by clicking "Analyze" to trigger the metrics reasoning agent and calculate trend details.
                          </p>
                        </div>
                      </div>
                    )}
                  </>
                )}

                {/* Subtab 2: Income Statement */}
                {financialSubTab === 'income' && renderFinancialTable('income')}

                {/* Subtab 3: Balance Sheet */}
                {financialSubTab === 'balance' && renderFinancialTable('balance')}

                {/* Subtab 4: Cash Flow */}
                {financialSubTab === 'cash' && renderFinancialTable('cash')}
              </div>
            )}

            {/* Tab 5: DCF & Peers */}
            {activeTab === 'valuation' && (
              <div className="flex-1 flex flex-col space-y-6">
                {agentOutputs?.valuation_agent ? (
                  <div className="space-y-6">
                    
                    {/* DCF Assumptions Summary */}
                    <div className="glass p-5 rounded-xl border border-border grid grid-cols-2 md:grid-cols-3 gap-6 relative">
                      <div className="absolute right-0 top-0 w-20 h-20 bg-secondary/5 rounded-full blur-xl" />
                      <div>
                        <span className="text-[10px] uppercase text-gray-500 tracking-wider">Estimated Fair Value</span>
                        <p className="text-xl font-bold text-primary mt-1">
                          ${agentOutputs.valuation_agent.dcf_valuation?.estimated_fair_value?.toFixed(2) || '0.00'}
                        </p>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase text-gray-500 tracking-wider">Implied Upside</span>
                        <p className="text-xl font-bold text-primary mt-1">
                          {agentOutputs.valuation_agent.dcf_valuation?.implied_upside || 'N/A'}
                        </p>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase text-gray-500 tracking-wider">Trading Price</span>
                        <p className="text-xl font-bold text-gray-400 mt-1">
                          ${agentOutputs.valuation_agent.dcf_valuation?.current_price?.toFixed(2) || '0.00'}
                        </p>
                      </div>
                      <div className="border-t border-border pt-4">
                        <span className="text-[9px] uppercase text-gray-500">WACC (Discount Rate)</span>
                        <p className="text-xs font-semibold text-white mt-0.5">{agentOutputs.valuation_agent.dcf_valuation?.wacc || 'N/A'}</p>
                      </div>
                      <div className="border-t border-border pt-4">
                        <span className="text-[9px] uppercase text-gray-500">Stage 1 Growth Rate</span>
                        <p className="text-xs font-semibold text-white mt-0.5">{agentOutputs.valuation_agent.dcf_valuation?.growth_stage_rate || 'N/A'}</p>
                      </div>
                      <div className="border-t border-border pt-4">
                        <span className="text-[9px] uppercase text-gray-500">Terminal Growth Rate</span>
                        <p className="text-xs font-semibold text-white mt-0.5">{agentOutputs.valuation_agent.dcf_valuation?.terminal_growth_rate || 'N/A'}</p>
                      </div>
                    </div>

                    {/* Competitor Multiples Comparison */}
                    <div className="bg-card rounded-xl border border-border overflow-hidden">
                      <div className="p-4 border-b border-border bg-card/60 flex items-center justify-between">
                        <h4 className="text-xs font-bold text-white uppercase tracking-wider">Peer Valuation Ratios</h4>
                        <span className="text-[10px] text-gray-400">LTM Multiples</span>
                      </div>
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="border-b border-border bg-card/20 text-gray-500 font-semibold">
                            <th className="p-3">Ticker</th>
                            <th className="p-3">P/E Ratio</th>
                            <th className="p-3">P/S Ratio</th>
                            <th className="p-3">EV / EBITDA</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(agentOutputs.valuation_agent.peer_multiples || []).map((peer: any, idx: number) => (
                            <tr 
                              key={idx} 
                              className={`border-b border-border/40 hover:bg-card/40 ${
                                peer.ticker === ticker ? 'bg-primary/5 font-semibold text-primary' : 'text-gray-300'
                              }`}
                            >
                              <td className="p-3 font-mono">{peer.ticker}</td>
                              <td className="p-3">{peer.pe_ratio ? peer.pe_ratio.toFixed(1) : 'N/A'}</td>
                              <td className="p-3">{peer.ps_ratio ? peer.ps_ratio.toFixed(1) : 'N/A'}</td>
                              <td className="p-3">{peer.ev_ebitda ? peer.ev_ebitda.toFixed(1) : 'N/A'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Valuation conclusion */}
                    <div className="bg-card/40 border border-border p-5 rounded-xl space-y-3">
                      <h4 className="text-sm font-bold text-white flex items-center space-x-1.5">
                        <Info className="h-4.5 w-4.5 text-primary" />
                        <span>Valuation Analyst Conclusion</span>
                      </h4>
                      <p className="text-xs text-gray-300 leading-relaxed">
                        {agentOutputs.valuation_agent?.valuation_conclusion}
                      </p>
                    </div>

                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-20 text-center text-gray-500 space-y-4">
                    <DollarSign className="h-12 w-12 text-gray-600 animate-pulse" />
                    <span>Run the research workflow to trigger DCF calculations and peer comparison tables.</span>
                  </div>
                )}
              </div>
            )}

            {/* Tab 6: Sentiment & News */}
            {activeTab === 'news' && (
              <div className="flex-1 flex flex-col space-y-6">
                {agentOutputs?.news_agent ? (
                  <div className="space-y-6">
                    
                    {/* Sentiment meter */}
                    <div className="glass p-5 rounded-xl border border-border flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                      <div>
                        <h4 className="text-sm font-bold text-white">Sentiment Dashboard</h4>
                        <p className="text-xs text-gray-400 mt-1">Aggregated sentiment score from news articles</p>
                      </div>
                      <div className="flex items-center space-x-4">
                        <div className="text-right">
                          <span className="text-[10px] uppercase text-gray-500 tracking-wider">Sentiment Index</span>
                          <p className="text-base font-bold text-white">
                            {agentOutputs.news_agent.sentiment_score !== undefined && agentOutputs.news_agent.sentiment_score !== null
                              ? agentOutputs.news_agent.sentiment_score.toFixed(2)
                              : '0.00'}
                          </p>
                        </div>
                        <span className={`px-4 py-1.5 rounded-full text-xs font-bold ${
                          agentOutputs.news_agent?.sentiment_label === 'Bullish' 
                            ? 'bg-primary/10 text-primary border border-primary/20'
                            : agentOutputs.news_agent?.sentiment_label === 'Bearish'
                            ? 'bg-red-500/10 text-red-500 border border-red-500/20'
                            : 'bg-gray-500/10 text-gray-400 border border-gray-500/20'
                        }`}>
                          {agentOutputs.news_agent?.sentiment_label || 'Neutral'}
                        </span>
                      </div>
                    </div>

                    {/* News items list */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {(agentOutputs.news_agent.news_summaries || []).map((news: any, idx: number) => {
                        let badgeColor = 'bg-gray-500/10 text-gray-400 border-gray-500/20';
                        if (news.sentiment === 'Bullish') badgeColor = 'bg-primary/10 text-primary border-primary/20';
                        if (news.sentiment === 'Bearish') badgeColor = 'bg-red-500/10 text-red-500 border-red-500/20';
                        
                        return (
                          <div key={idx} className="bg-card border border-border p-4 rounded-xl flex flex-col justify-between space-y-3 hover:border-border/80 transition-all">
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="text-[10px] text-gray-500 font-semibold">{news.source}</span>
                                <span className={`text-[9px] border px-2 py-0.25 rounded-md font-semibold ${badgeColor}`}>
                                  {news.sentiment}
                                </span>
                              </div>
                              <h5 className="text-xs font-bold text-white leading-snug hover:text-secondary transition-all cursor-pointer">
                                {news.title}
                              </h5>
                            </div>
                            <p className="text-xs text-gray-400 leading-normal">
                              {news.summary}
                            </p>
                          </div>
                        );
                      })}
                    </div>

                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-20 text-center text-gray-500 space-y-4">
                    <Share2 className="h-12 w-12 text-gray-600 animate-pulse" />
                    <span>Run the research workflow to extract and analyze market news headlines.</span>
                  </div>
                )}
              </div>
            )}

          </div>

        </section>

      </main>

      {/* Footer */}
      <footer className="border-t border-border/80 py-4 px-6 text-center text-[10px] text-gray-500 bg-card/10">
        AI-Powered Financial Research Agent Platform • Created in Planning Mode • Python 3.14 + React TS + WebSockets • Free data via yfinance & SEC EDGAR
      </footer>

    </div>
  );
}
