# agents/web_search_agent/app.py
import logging
import asyncio
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
import requests

from search_engine import DuckDuckGoSearchEngine
from query_expander import OllamaQueryExpander

from fastapi.middleware.cors import CORSMiddleware


# ----------------------
# Logging
# ----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("web_search_agent")

# ----------------------
# FastAPI app
# ----------------------
app = FastAPI(title="Web Search Agent", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------
# Constants / singletons
# ----------------------
OLLAMA_HOST = "http://ollama:11434"
SEARCH_MAX_RESULTS = 10

search_engine = DuckDuckGoSearchEngine(max_results=SEARCH_MAX_RESULTS)
query_expander = OllamaQueryExpander(ollama_host=OLLAMA_HOST, model="llama3.2:3b")

# ----------------------
# Pydantic models
# ----------------------
class SearchResponse(BaseModel):
    status: str
    original_query: str
    expanded_queries: List[str]
    total_queries: int
    results: List[Dict[str, Any]]
    total_results: int
    execution_time: float
    timestamp: str

# ----------------------
# Health check endpoint
# ----------------------
@app.get("/health")
async def health():
    logger.info("Received /health")
    results = {"agent": "healthy"}
    try:
        ollama_status = await query_expander.health_check()
        results["ollama"] = ollama_status
        logger.info(f"Ollama health: {ollama_status}")
    except Exception as e:
        results["ollama"] = {"status": "unhealthy", "error": str(e)}
        logger.error(f"Ollama health check error: {e}")

    try:
        search_status = await search_engine.health_check()
        results["search_engine"] = search_status
        logger.info(f"Search engine health: {search_status}")
    except Exception as e:
        results["search_engine"] = {"status": "unhealthy", "error": str(e)}
        logger.error(f"Search engine health check error: {e}")

    return results

# ----------------------
# Web search endpoint
# ----------------------
@app.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., description="User query string"),
    expand: bool = Query(True, description="Whether to expand query using Ollama"),
    max_results: Optional[int] = Query(None, description="Limit results (overrides default)")
):
    logger.info(f"Received search request: q='{q}', expand={expand}, max_results={max_results}")
    try:
        if max_results:
            search_engine.max_results = max_results

        start_time = asyncio.get_event_loop().time()

        expanded_queries = []
        if expand:
            expanded_queries = await query_expander.expand(q)
            logger.info(f"Expanded queries: {expanded_queries}")
        all_queries = [q] + expanded_queries

        all_results = []
        seen_urls = set()
        for query in all_queries:
            results = await search_engine.search(query)
            logger.info(f"Results for '{query}': {len(results)} items")
            for r in results:
                url = r.get("url") or r.get("href") or ""
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)
            if len(all_results) >= search_engine.max_results:
                break

        final = all_results[:search_engine.max_results]
        execution_time = asyncio.get_event_loop().time() - start_time
        logger.info(f"Search completed: total_results={len(final)}, execution_time={execution_time:.3f}s")

        return {
            "status": "success",
            "original_query": q,
            "expanded_queries": expanded_queries,
            "total_queries": len(all_queries),
            "results": final,
            "total_results": len(final),
            "execution_time": execution_time,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.exception("Search endpoint error")
        raise HTTPException(status_code=500, detail=str(e))

# ----------------------
# News search endpoint
# ----------------------
@app.get("/search/news")
async def search_news(
    q: str = Query(..., description="User query string"),
    max_results: Optional[int] = Query(None, description="Limit results")
):
    logger.info(f"Received news search request: q='{q}', max_results={max_results}")
    try:
        if max_results:
            search_engine.max_results = max_results
        results = await search_engine.search_news(q)
        logger.info(f"News search results: {len(results)} items")
        return {"status": "success", "query": q, "total_results": len(results), "results": results}
    except Exception as e:
        logger.exception("search_news error")
        raise HTTPException(status_code=500, detail=str(e))

# ----------------------
# Ollama direct endpoint for frontend testing
# ----------------------
@app.post("/ask")
async def ask(request: Request):
    """
    Simple endpoint to test Ollama directly
    """
    body = await request.json()
    prompt = body.get("prompt", "")
    logger.info(f"Received /ask prompt: {prompt}")

    data = {"model": "llama3.2:3b", "prompt": prompt}
    try:
        resp = requests.post(f"{OLLAMA_HOST}/api/generate", json=data, stream=True)
        full_text = ""
        for line in resp.iter_lines():
            if line:
                import json
                part = json.loads(line.decode("utf-8"))
                full_text += part.get("response", "")
        logger.info(f"Ollama /ask response: {full_text}")
        return {"response": full_text}
    except Exception as e:
        logger.exception("Error calling Ollama in /ask")
        return {"response": "", "error": str(e)}
