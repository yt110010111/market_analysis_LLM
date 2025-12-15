## Overview

This project implements an **agentic, multi-stage LLM system** designed for end-to-end information discovery, analysis, and knowledge structuring. The architecture follows a **Controller–Worker Agentic Orchestration Pattern**, where a central analysis agent coordinates multiple specialized agents to execute complex tasks in a deterministic and scalable pipeline.

User queries are processed through a structured workflow that includes web search, content scraping, semantic analysis, data extraction, and graph-based reasoning. Large Language Models are served via Ollama, while Neo4j is used to persist extracted knowledge and relationships, enabling iterative reasoning and retrieval-augmented generation (Graph-RAG).

By decomposing responsibilities across domain-specific agents, the system improves reliability, observability, and extensibility, making it suitable for research, market analysis, and complex knowledge-intensive applications.

## Services
All services were composed in different container

### ollama
LLM 推理服務，負責模型載入與文字生成。支援 NVIDIA GPU 加速。

### backend
neo4j
graph database服務，用於儲存與查詢結構化知識（Graph / RAG）。提供連線介面。
'''
http://140.113.73.25:7474/browser/
account:neo4j
password:password123
'''

### web_search_agent
對外查詢入口服務，負責搜尋請求、Query Expansion，並協調 Analysis Agent。

### analysis_agent
核心分析代理，負責推理流程控制，整合搜尋結果、Neo4j 圖資料查詢，並調用爬蟲與資料擷取等下游 agents。

### web_scraping_agent
網頁爬取服務，負責抓取與清洗網頁內容，提供原始文本給分析與資料擷取流程。

### data_extraction_agent
資料擷取服務，使用 LLM 從文件中萃取結構化資訊，並透過限制文件數量、長度與並行度以提升效能與穩定性。

### frontend:
'''
http://localhost:3000/
http://140.113.73.25:3000
'''
前端介面（Vite / React），提供使用者操作入口，透過 HTTP 呼叫 `web_search_agent` 與後端 agent 系統互動。




### agent logs
docker compose up agent_name
docker compose exec agent_name bash
docker-compose logs -f container



### 申請tavily API key
https://app.tavily.com/home
docker-compose.yml:
environment替換:
'''
-TAVILY_API_KEY
'''
