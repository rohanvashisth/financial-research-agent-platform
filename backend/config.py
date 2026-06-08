import os
from pathlib import Path
from dotenv import load_dotenv

# Find the workspace root directory and load the environment variables from .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

class Settings:
    RUN_MODE: str = os.getenv("RUN_MODE", "local").lower()
    
    # LLM Settings
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    # SEC EDGAR Settings
    SEC_USER_AGENT: str = os.getenv("SEC_USER_AGENT", "FinancialResearchAgent/1.0 (researcher@example.com)")
    
    # Postgres Database Settings
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    # Handle potentially empty password
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgrespassword")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "financial_research")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", 5432))
    
    # Kafka Settings
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    
    # Server configuration
    PORT: int = int(os.getenv("PORT", 8000))
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    
    # Storage Directory (Local data folder for SQLite, downloaded SEC files, etc.)
    DATA_DIR: Path = BASE_DIR / "data"
    
    def __init__(self):
        # Create directories if they do not exist
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        (self.DATA_DIR / "filings").mkdir(parents=True, exist_ok=True)
        (self.DATA_DIR / "reports").mkdir(parents=True, exist_ok=True)

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        
    @property
    def sqlite_db_path(self) -> str:
        return str(self.DATA_DIR / "financial_research.db")

settings = Settings()
