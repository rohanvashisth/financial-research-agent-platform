import requests
import yfinance as yf
import json
import re
import time
import math
from pathlib import Path
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from backend.config import settings

class DataFetcher:
    def __init__(self):
        self.headers = {
            "User-Agent": settings.SEC_USER_AGENT,
            "Accept-Encoding": "gzip, deflate"
        }
        self.cik_cache_file = settings.DATA_DIR / "cik_map.json"
        self._cik_map = {}
        self._load_cik_map()

    def _load_cik_map(self):
        """Loads ticker-to-CIK mapping from local cache or SEC website."""
        if self.cik_cache_file.exists():
            try:
                with open(self.cik_cache_file, "r") as f:
                    self._cik_map = json.load(f)
                return
            except Exception as e:
                print(f"Error loading CIK map cache: {e}")
        
        fallback_map = {
            "MSFT": "0000789019",
            "AAPL": "0000320193",
            "GOOG": "0001652044",
            "GOOGL": "0001652044",
            "AMZN": "0001018724",
            "TSLA": "0001318605",
            "META": "0001326801",
            "NVDA": "0001045810",
            "NFLX": "0001065280",
            "JPM": "0000019617"
        }

        # Download map from SEC
        try:
            url = "https://www.sec.gov/files/company_tickers.json"
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                sec_data = response.json()
                # Map ticker to CIK
                new_map = {}
                for entry in sec_data.values():
                    ticker = entry["ticker"].upper()
                    cik = entry["cik_str"]
                    new_map[ticker] = f"{cik:010d}"
                
                self._cik_map = new_map
                # Cache it
                with open(self.cik_cache_file, "w") as f:
                    json.dump(self._cik_map, f)
            else:
                print(f"Failed to fetch SEC CIK list: {response.status_code}. Using fallback CIK map.")
                self._cik_map = fallback_map
        except Exception as e:
            print(f"Error downloading CIK map from SEC: {e}. Using fallback CIK map.")
            self._cik_map = fallback_map

    def get_cik(self, ticker: str) -> Optional[str]:
        """Resolves a ticker symbol to a 10-digit SEC CIK."""
        ticker = ticker.upper().strip()
        # Refresh CIK map if ticker is missing
        if ticker not in self._cik_map:
            self._load_cik_map()
        return self._cik_map.get(ticker)

    def get_company_info(self, ticker: str) -> Dict[str, Any]:
        """Fetches metadata about the company from Yahoo Finance."""
        ticker = ticker.upper().strip()
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            return {
                "ticker": ticker,
                "name": info.get("longName", ticker),
                "sector": info.get("sector", "N/A"),
                "industry": info.get("industry", "N/A"),
                "summary": info.get("longBusinessSummary", "N/A"),
                "employees": info.get("fullTimeEmployees", "N/A"),
                "website": info.get("website", "N/A"),
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE", "N/A"),
                "forward_pe": info.get("forwardPE", "N/A"),
                "price_to_sales": info.get("priceToSalesTrailing12Months", "N/A"),
                "dividend_yield": info.get("dividendYield", 0.0),
                "logo_url": f"https://logo.clearbit.com/{info.get('website', '').replace('http://', '').replace('https://', '').split('/')[0]}" if info.get("website") else ""
            }
        except Exception as e:
            print(f"Error fetching yfinance metadata for {ticker}: {e}")
            # Fallback mock data
            return {
                "ticker": ticker,
                "name": f"{ticker} Inc. (Mock)",
                "sector": "Technology",
                "industry": "Software",
                "summary": f"Could not load business summary for {ticker} from Yahoo Finance. This is a fallback mock card.",
                "employees": "N/A",
                "website": "N/A",
                "market_cap": 0,
                "pe_ratio": "N/A",
                "forward_pe": "N/A",
                "price_to_sales": "N/A",
                "dividend_yield": 0.0,
                "logo_url": ""
            }

    def get_stock_history(self, ticker: str, period: str = "1y") -> List[Dict[str, Any]]:
        """Fetches stock price history for charting."""
        ticker = ticker.upper().strip()
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)
            
            data = []
            for date, row in hist.iterrows():
                data.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "close": float(row["Close"]),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "volume": int(row["Volume"])
                })
            return data
        except Exception as e:
            print(f"Error fetching stock history for {ticker}: {e}")
            # Generate mock history for testing
            mock_data = []
            curr_val = 150.0
            for i in range(100):
                date_str = (time.time() - (100 - i) * 86400)
                date_formatted = time.strftime("%Y-%m-%d", time.localtime(date_str))
                curr_val += (time.time() % 10 - 5) / 2
                mock_data.append({
                    "date": date_formatted,
                    "close": curr_val,
                    "open": curr_val - 1.0,
                    "high": curr_val + 2.0,
                    "low": curr_val - 2.0,
                    "volume": 1000000
                })
            return mock_data

    def get_financials_from_sec(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fetches financial statements from SEC EDGAR XBRL company facts."""
        ticker = ticker.upper().strip()
        cik = self.get_cik(ticker)
        if not cik:
            print(f"SEC CIK lookup failed for {ticker}")
            return None
            
        try:
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            response = requests.get(url, headers=self.headers, timeout=15)
            if response.status_code != 200:
                print(f"Failed to fetch SEC Company Facts for {ticker} (CIK {cik}): {response.status_code}")
                return None
                
            data = response.json()
            facts = data.get("facts", {})
            us_gaap = facts.get("us-gaap", {})
            if not us_gaap:
                # Some foreign filers use ifrs-full instead of us-gaap
                us_gaap = facts.get("ifrs-full", {})
                
            if not us_gaap:
                print(f"No XBRL facts found under us-gaap or ifrs-full for {ticker}")
                return None

            # Define mapping of metrics to XBRL tags
            metrics_map = {
                "income_statement": {
                    "Total Revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "RevenuesNetOfInterestExpense", "RevenueFromContractWithCustomerExcludingAssessedTaxAndInterestExpense"],
                    "Cost of Revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices"],
                    "Gross Profit": ["GrossProfit"],
                    "Research & Development": ["ResearchAndDevelopmentExpense"],
                    "SG&A": ["SellingGeneralAndAdministrativeExpense", "SellingAndMarketingExpense", "GeneralAndAdministrativeExpense"],
                    "Operating Expenses": ["OperatingExpenses", "OperatingCostsAndExpenses"],
                    "Operating Income": ["OperatingIncomeLoss"],
                    "Interest Expense": ["InterestExpense", "InterestExpenseDebt"],
                    "Tax Expense": ["IncomeTaxExpenseBenefit", "IncomeTaxExpenseBenefitContinuingOperations"],
                    "Net Income": ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
                    "Basic EPS": ["EarningsPerShareBasic", "EarningsPerShareBasicAndDiluted"],
                    "Diluted EPS": ["EarningsPerShareDiluted"]
                },
                "balance_sheet": {
                    "Cash & Cash Equivalents": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndCashEquivalents", "Cash"],
                    "Short-term Investments": ["ShortTermInvestments", "AvailableForSaleSecuritiesCurrent"],
                    "Accounts Receivable": ["AccountsReceivableNetCurrent", "AccountsReceivableNet"],
                    "Inventory": ["InventoryNet", "Inventories"],
                    "Total Current Assets": ["AssetsCurrent"],
                    "PP&E Net": ["PropertyPlantAndEquipmentNet"],
                    "Goodwill & Intangibles": ["Goodwill", "IntangibleAssetsNetExcludingGoodwill", "GoodwillAndIntangibleAssetsNet"],
                    "Total Assets": ["Assets"],
                    "Accounts Payable": ["AccountsPayableCurrent", "AccountsPayable"],
                    "Short-term Debt": ["DebtCurrent", "ShortTermBorrowings", "LongTermDebtCurrent"],
                    "Total Current Liabilities": ["LiabilitiesCurrent"],
                    "Long-term Debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
                    "Total Liabilities": ["Liabilities"],
                    "Retained Earnings": ["RetainedEarningsAccumulatedDeficit"],
                    "Stockholders Equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
                    "Total Liabilities & Equity": ["LiabilitiesAndStockholdersEquity"]
                },
                "cash_flow": {
                    "Net Income (Cash Flow)": ["NetIncomeLoss"],
                    "Depreciation & Amortization": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"],
                    "Share-based Compensation": ["ShareBasedCompensation"],
                    "Operating Cash Flow": ["NetCashProvidedByUsedInOperatingActivities"],
                    "Capital Expenditures": ["PaymentsToAcquirePropertyPlantAndEquipment", "CapitalExpenditures"],
                    "Investing Cash Flow": ["NetCashProvidedByUsedInInvestingActivities"],
                    "Financing Cash Flow": ["NetCashProvidedByUsedInFinancingActivities"],
                    "Net Change in Cash": ["CashCashEquivalentsRestrictedCashAndCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect", "CashAndCashEquivalentsPeriodIncreaseDecrease"]
                }
            }

            result = {
                "income_statement": {},
                "balance_sheet": {},
                "cash_flow": {},
                "quarterly_income_statement": {},
                "quarterly_balance_sheet": {},
                "quarterly_cash_flow": {}
            }

            # Helper to extract metrics and merge in reverse order (preferred tags take precedence)
            def extract_and_merge(tags: List[str]) -> tuple[dict[str, float], dict[str, float]]:
                annual = {}
                quarterly = {}
                # Loop in reverse order so that preferred tags (which come first in the list) overwrite less preferred tags
                for tag in reversed(tags):
                    if tag in us_gaap:
                        fact_data = us_gaap[tag]
                        units = fact_data.get("units", {})
                        entries = units.get("USD", []) or units.get("shares", []) or list(units.values())[0] if units else []
                        
                        for entry in entries:
                            end_date = entry.get("end")
                            form = entry.get("form")
                            val = entry.get("val")
                            
                            if not end_date or val is None:
                                continue
                            
                            # Standardize dates
                            try:
                                val_float = float(val)
                                if math.isnan(val_float) or math.isinf(val_float):
                                    continue
                            except (ValueError, TypeError):
                                continue
                                
                            fp = entry.get("fp") or ""
                            if form == "10-K" or fp == "FY":
                                annual[end_date] = val_float
                            elif form == "10-Q" or fp.startswith("Q"):
                                quarterly[end_date] = val_float
                                
                return annual, quarterly

            # Populate statements
            for sheet_type, metrics in metrics_map.items():
                for label, tags in metrics.items():
                    annual, quarterly = extract_and_merge(tags)
                    
                    if sheet_type == "income_statement":
                        result["income_statement"][label] = annual
                        result["quarterly_income_statement"][label] = quarterly
                    elif sheet_type == "balance_sheet":
                        result["balance_sheet"][label] = annual
                        result["quarterly_balance_sheet"][label] = quarterly
                    elif sheet_type == "cash_flow":
                        result["cash_flow"][label] = annual
                        result["quarterly_cash_flow"][label] = quarterly

            # Proxy Fallbacks
            for prefix in ["", "quarterly_"]:
                # 1. Operating Income proxy calculation if missing
                inc = result[f"{prefix}income_statement"]
                op_inc = inc.get("Operating Income")
                if not op_inc:
                    gp = inc.get("Gross Profit", {})
                    sga = inc.get("SG&A", {})
                    rd = inc.get("Research & Development", {})
                    all_dates = set(gp.keys()) | set(sga.keys())
                    computed_op = {}
                    for d in all_dates:
                        gp_val = gp.get(d, 0.0)
                        sga_val = sga.get(d, 0.0)
                        rd_val = rd.get(d, 0.0)
                        if gp_val > 0:
                            computed_op[d] = gp_val - sga_val - rd_val
                    inc["Operating Income"] = computed_op
                
                # 2. Free Cash Flow calculation
                cf = result[f"{prefix}cash_flow"]
                ocf = cf.get("Operating Cash Flow", {})
                capex = cf.get("Capital Expenditures", {})
                computed_fcf = {}
                for d in ocf.keys():
                    ocf_val = ocf.get(d, 0.0)
                    capex_val = abs(capex.get(d, 0.0))
                    computed_fcf[d] = ocf_val - capex_val
                cf["Free Cash Flow"] = computed_fcf
            
            # Check if we got any real data
            total_elements = sum(len(sheet) for sheet in result.values())
            if total_elements == 0:
                return None
                
            return result
        except Exception as e:
            print(f"Error fetching SEC Company Facts for {ticker}: {e}")
            return None

    def get_financial_statements(self, ticker: str) -> Dict[str, Any]:
        """Fetches income statement, balance sheet, and cash flow data (both annual and quarterly).
        Prefers SEC EDGAR company facts XBRL data, and falls back to Yahoo Finance if empty/fails."""
        ticker = ticker.upper().strip()
        
        # 1. Try to fetch from SEC EDGAR
        print(f"Data Fetcher: Attempting to pull SEC EDGAR XBRL financials for {ticker}...")
        sec_financials = self.get_financials_from_sec(ticker)
        if sec_financials:
            print(f"Data Fetcher: Successfully retrieved financial statements for {ticker} from SEC EDGAR.")
            return sec_financials
            
        # 2. Fallback to Yahoo Finance
        print(f"Data Fetcher: SEC EDGAR XBRL unavailable for {ticker}. Falling back to Yahoo Finance...")
        try:
            stock = yf.Ticker(ticker)
            
            # Helper to convert DataFrame to clean dictionary
            def df_to_dict(df):
                if df is None or df.empty:
                    return {}
                res = {}
                for idx, row in df.iterrows():
                    metric_name = str(idx)
                    cleaned_row = {}
                    for col, val in row.items():
                        col_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
                        # Check for NaN and Inf values and convert them to None (null in JSON)
                        if val is None or (isinstance(val, float) and math.isnan(val)):
                            cleaned_row[col_str] = None
                        elif isinstance(val, (int, float)):
                            cleaned_row[col_str] = float(val) if not math.isinf(val) else None
                        else:
                            cleaned_row[col_str] = str(val)
                    res[metric_name] = cleaned_row
                return res

            return {
                "income_statement": df_to_dict(stock.financials),
                "balance_sheet": df_to_dict(stock.balance_sheet),
                "cash_flow": df_to_dict(stock.cashflow),
                "quarterly_income_statement": df_to_dict(stock.quarterly_financials),
                "quarterly_balance_sheet": df_to_dict(stock.quarterly_balance_sheet),
                "quarterly_cash_flow": df_to_dict(stock.quarterly_cashflow)
            }
        except Exception as e:
            print(f"Error fetching financial statements for {ticker}: {e}")
            return {
                "income_statement": {},
                "balance_sheet": {},
                "cash_flow": {},
                "quarterly_income_statement": {},
                "quarterly_balance_sheet": {},
                "quarterly_cash_flow": {}
            }

    def get_competitors(self, ticker: str, sector: str = "Technology") -> List[str]:
        """Determines a list of competitor/peer tickers."""
        ticker = ticker.upper().strip()
        
        # Explicit peer map for top tickers
        peer_map = {
            "MSFT": ["AAPL", "GOOGL", "AMZN", "ORCL", "CRM"],
            "AAPL": ["MSFT", "GOOGL", "HPQ", "DELL", "SSNLF"],
            "GOOG": ["MSFT", "AAPL", "META", "AMZN", "NFLX"],
            "GOOGL": ["MSFT", "AAPL", "META", "AMZN", "NFLX"],
            "AMZN": ["WMT", "TGT", "EBAY", "MSFT", "BABA"],
            "TSLA": ["F", "GM", "TM", "RIVN", "LCID", "BYDDY"],
            "META": ["GOOGL", "SNAP", "PINS", "MSFT", "NFLX"],
            "NVDA": ["AMD", "INTC", "QCOM", "AVGO", "TSM"],
            "NFLX": ["DIS", "WBD", "PARA", "AMZN", "AAPL"],
            "JPM": ["BAC", "WFC", "C", "GS", "MS"]
        }
        
        if ticker in peer_map:
            return peer_map[ticker]
            
        # Default peers based on sectors
        sector_peers = {
            "Technology": ["MSFT", "AAPL", "GOOGL", "NVDA", "ORCL"],
            "Financial Services": ["JPM", "BAC", "WFC", "GS", "MS"],
            "Consumer Cyclical": ["AMZN", "TSLA", "HD", "NKE", "MCD"],
            "Healthcare": ["JNJ", "UNH", "LLY", "MRK", "PFE"],
            "Communication Services": ["META", "NFLX", "DIS", "TMUS", "VZ"]
        }
        
        return sector_peers.get(sector, ["SPY", "QQQ", "DIA"])

    def fetch_latest_sec_filings(self, ticker: str, filing_type: str = "10-K") -> List[Dict[str, Any]]:
        """Finds list of recent filings of a type for a ticker."""
        cik = self.get_cik(ticker)
        if not cik:
            print(f"No CIK found for ticker {ticker}")
            return []
            
        try:
            # Get submissions
            url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code != 200:
                print(f"Error fetching SEC submissions for {ticker} (CIK {cik}): {response.status_code}")
                return []
                
            data = response.json()
            recent_filings = data.get("filings", {}).get("recent", {})
            
            filings = []
            if not recent_filings:
                return []
                
            num_filings = len(recent_filings.get("accessionNumber", []))
            for i in range(num_filings):
                f_type = recent_filings["form"][i]
                if filing_type in f_type:
                    acc_num = recent_filings["accessionNumber"][i]
                    acc_num_no_hyphens = acc_num.replace("-", "")
                    doc_name = recent_filings["primaryDocument"][i]
                    filing_date = recent_filings["filingDate"][i]
                    report_date = recent_filings["reportDate"][i]
                    
                    filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_num_no_hyphens}/{doc_name}"
                    
                    filings.append({
                        "ticker": ticker,
                        "cik": cik,
                        "form": f_type,
                        "filing_date": filing_date,
                        "report_date": report_date,
                        "accession_number": acc_num,
                        "document_name": doc_name,
                        "url": filing_url
                    })
                    
            return filings
        except Exception as e:
            print(f"Error fetching SEC filings list for {ticker}: {e}")
            return []

    def download_filing_text(self, url: str) -> str:
        """Downloads filing HTML, strips elements, and returns clean text."""
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            if response.status_code != 200:
                print(f"Failed to download filing from {url}: {response.status_code}")
                return ""
                
            # Parse HTML
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Remove scripts, styles, XML schemas, tables (sometimes tables make text very noisy, but we can leave text)
            for element in soup(["script", "style", "head", "title"]):
                element.decompose()
                
            text = soup.get_text(separator="\n")
            
            # Clean up whitespace
            text = re.sub(r'\n\s*\n', '\n', text)
            text = re.sub(r' +', ' ', text)
            
            return text
        except Exception as e:
            print(f"Error downloading filing content: {e}")
            return ""

    def get_sec_rag_chunks(self, ticker: str, filing_type: str = "10-K") -> List[Dict[str, Any]]:
        """Downloads the latest filing and splits it into semantic chunks."""
        ticker = ticker.upper().strip()
        filing_cache = settings.DATA_DIR / "filings" / f"{ticker}_{filing_type}.json"
        
        # Check cache first
        if filing_cache.exists():
            try:
                with open(filing_cache, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading cached chunks for {ticker}: {e}")

        print(f"Fetching SEC filings for {ticker} from EDGAR...")
        filings = self.fetch_latest_sec_filings(ticker, filing_type)
        
        if not filings:
            # Load mock chunks if network fails
            return self._generate_mock_filing_chunks(ticker, filing_type)
            
        latest_filing = filings[0]
        raw_text = self.download_filing_text(latest_filing["url"])
        
        if not raw_text or len(raw_text) < 1000:
            print("Filing text empty or too short, using mock chunks.")
            return self._generate_mock_filing_chunks(ticker, filing_type)
            
        # Segment into chunks
        chunks = []
        chunk_size = 2500  # Character count
        overlap = 300
        
        # Try to find Risk Factors (Item 1A) and MD&A (Item 7) to tag them specifically
        # Simple regex markers
        risk_match = re.search(r'item\s+1a\.?\s+risk\s+factors', raw_text, re.IGNORECASE)
        mda_match = re.search(r'item\s+7\.?\s+management\'s\s+discussion', raw_text, re.IGNORECASE)
        mda_end = re.search(r'item\s+7a\.?\s+quantitative', raw_text, re.IGNORECASE)
        
        risk_start_idx = risk_match.start() if risk_match else -1
        mda_start_idx = mda_match.start() if mda_match else -1
        mda_end_idx = mda_end.start() if mda_end else -1
        
        # We chunk the whole file but tag the items if they fall inside those indices
        idx = 0
        chunk_id = 0
        total_len = len(raw_text)
        
        # Cap text size to 1,500,000 chars to avoid infinite loops and massive DB size
        max_chars = min(total_len, 1500000)
        
        while idx < max_chars:
            end_idx = min(idx + chunk_size, max_chars)
            chunk_text = raw_text[idx:end_idx].strip()
            
            if len(chunk_text) > 100:
                # Classify section
                section = "General"
                if risk_start_idx != -1 and idx >= risk_start_idx and (mda_start_idx == -1 or idx < mda_start_idx):
                    section = "Item 1A: Risk Factors"
                elif mda_start_idx != -1 and idx >= mda_start_idx and (mda_end_idx == -1 or idx < mda_end_idx):
                    section = "Item 7: MD&A"
                
                chunks.append({
                    "chunk_id": f"{ticker}_{filing_type}_{chunk_id}",
                    "ticker": ticker,
                    "filing_type": filing_type,
                    "date": latest_filing["filing_date"],
                    "url": latest_filing["url"],
                    "section": section,
                    "content": chunk_text
                })
                chunk_id += 1
                
            idx += (chunk_size - overlap)
            
        # Save cache
        try:
            with open(filing_cache, "w", encoding="utf-8") as f:
                json.dump(chunks, f, indent=2)
        except Exception as e:
            print(f"Error caching chunks: {e}")
            
        return chunks

    def _generate_mock_filing_chunks(self, ticker: str, filing_type: str) -> List[Dict[str, Any]]:
        """Provides mock filing details for testing and demo consistency."""
        date_str = "2025-10-31" if filing_type == "10-Q" else "2025-07-28"
        url = "https://www.sec.gov/Archives/edgar/data/0000789019/000078901925000035/msft-20250630.htm"
        
        risk_factors = (
            f"Item 1A. Risk Factors for {ticker}. "
            "Our operations and financial results are subject to various risks and uncertainties. "
            "1. Competition in Cloud Computing and AI: We face intense competition from Amazon Web Services (AWS) "
            "and Google Cloud Platform (GCP). If we fail to innovate in generative AI and cloud infrastructure, our market share may decline. "
            "2. Capital Expenditures and Infrastructure Capacity: Scaling AI services requires significant capital investment in data centers, "
            "GPUs, and energy sourcing. High capex might impact near-term gross margins and cash flow. "
            "3. Cyber Security Threats: Cyberattacks and data breaches could disrupt our services, expose confidential customer data, "
            "damage our brand, and subject us to legal liability. "
            "4. Regulatory and Antitrust Scrutiny: Increased regulation of artificial intelligence, privacy laws (GDPR), "
            "and antitrust investigations into our bundling practices could limit our growth and require changes in our business models."
        )
        
        mda_summary = (
            f"Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations (MD&A). "
            f"For the fiscal period, {ticker} experienced solid revenue growth, driven primarily by our Cloud division. "
            "Server products and cloud services revenue increased, driven by Azure and other cloud services growth. "
            "Commercial cloud gross margin remained strong. Operating expenses increased due to investments in AI, "
            "research and development, and infrastructure. Diluted earnings per share grew YoY. "
            "Azure growth is driven by customer demand for our AI services, migration of workloads to the cloud, and expansion of enterprise agreements. "
            "Capital expenditures were primarily directed towards building global cloud capacity, purchasing server hardware, and acquiring graphics processing units (GPUs)."
        )
        
        segments = (
            f"Item 1. Business Description. {ticker} is organized into three primary operating segments: "
            "1. Productivity and Business Processes: Includes Office Commercial, Office Consumer, LinkedIn, and Dynamics. "
            "2. Intelligent Cloud: Includes Server products and cloud services, including Azure, Windows Server, SQL Server, and Enterprise Services. "
            "3. More Personal Computing: Includes Windows OEM, Devices, Gaming (Xbox services and content), and Search and news advertising. "
            "Our commercial business is transitioning towards subscription services, driving higher recurring revenue."
        )

        chunks = [
            {"chunk_id": f"{ticker}_{filing_type}_0", "ticker": ticker, "filing_type": filing_type, "date": date_str, "url": url, "section": "Item 1: Business Description", "content": segments},
            {"chunk_id": f"{ticker}_{filing_type}_1", "ticker": ticker, "filing_type": filing_type, "date": date_str, "url": url, "section": "Item 1A: Risk Factors", "content": risk_factors},
            {"chunk_id": f"{ticker}_{filing_type}_2", "ticker": ticker, "filing_type": filing_type, "date": date_str, "url": url, "section": "Item 7: MD&A", "content": mda_summary}
        ]
        
        # Write mock cache
        filing_cache = settings.DATA_DIR / "filings" / f"{ticker}_{filing_type}.json"
        try:
            with open(filing_cache, "w", encoding="utf-8") as f:
                json.dump(chunks, f, indent=2)
        except Exception as e:
            print(f"Error caching mock chunks: {e}")
            
        return chunks

data_fetcher = DataFetcher()
