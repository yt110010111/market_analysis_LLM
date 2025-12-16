import os

# ============ Ollama 配置 ============
OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://ollama:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "llama3.2:3b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.3"))

# ============ 迭代控制 ============
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "3"))  # 最多迭代次數
URLS_PER_ITERATION = int(os.getenv("URLS_PER_ITERATION", "5"))  # 每次迭代爬取的 URL 數量

# ============ 充足度判斷閾值 ============
MIN_ENTITIES_FALLBACK = int(os.getenv("MIN_ENTITIES_FALLBACK", "5"))  # 降級方案的最小實體數
MIN_RELATIONSHIPS_FALLBACK = int(os.getenv("MIN_RELATIONSHIPS_FALLBACK", "3"))  # 降級方案的最小關係數
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.7"))  # LLM 判斷的最低信心度

# ============ 服務端點 ============
WEB_SCRAPING_URL = os.getenv("WEB_SCRAPING_AGENT_URL", "http://web_scraping_agent:8003")
DATA_EXTRACTION_URL = os.getenv("DATA_EXTRACTION_AGENT_URL", "http://data_extraction_agent:8004")

# ============ Neo4j 配置 ============
NEO4J_URL = os.getenv("NEO4J_URL", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

# ============ 日誌配置 ============
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")