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
ANALYSIS_AGENT_URL = "http://analysis_agent:8002"  # 新增
SEARCH_MAX_RESULTS = 10

search_engine = DuckDuckGoSearchEngine(max_results=SEARCH_MAX_RESULTS)
query_expander = OllamaQueryExpander(ollama_host=OLLAMA_HOST, model="llama3.2:3b")

# ----------------------
# Pydantic models
# ----------------------
class SearchRequest(BaseModel):
    query: str

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
# POST endpoint for frontend (主要入口)
# ----------------------
@app.post("/search")
async def search_post(request: SearchRequest):
    """
    前端的主要入口：執行搜尋後自動呼叫 analysis_agent
    """
    logger.info(f"📥 收到前端搜尋請求: query='{request.query}'")
    try:
        start_time = asyncio.get_event_loop().time()

        # ========== 步驟 1: 查詢擴展 ==========
        logger.info(f"📝 開始查詢擴展...")
        expanded_queries = await query_expander.expand(request.query)
        logger.info(f"✅ 查詢擴展完成: {expanded_queries}")
        
        all_queries = [request.query] + expanded_queries
        logger.info(f"🔍 將執行 {len(all_queries)} 個查詢: {all_queries}")

        # ========== 步驟 2: 執行搜尋 ==========
        all_results = []
        seen_urls = set()
        for idx, query in enumerate(all_queries):
            if idx > 0:
                await asyncio.sleep(1.5)
            
            results = await search_engine.search(query)
            logger.info(f"Results for '{query}': {len(results)} items")
            for r in results:
                url = r.get("url") or r.get("href") or ""
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)
            if len(all_results) >= search_engine.max_results:
                break

        final_results = all_results[:search_engine.max_results]
        search_execution_time = asyncio.get_event_loop().time() - start_time
        logger.info(f"✅ 搜尋完成: total_results={len(final_results)}, time={search_execution_time:.3f}s")

        # 準備搜尋結果
        search_data = {
            "status": "success",
            "original_query": request.query,
            "expanded_queries": expanded_queries,
            "total_queries": len(all_queries),
            "results": final_results,
            "total_results": len(final_results),
            "execution_time": search_execution_time,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        }

        # ========== 步驟 3: 呼叫 Analysis Agent ==========
        logger.info(f"🧠 呼叫 Analysis Agent 進行分析...")
        try:
            analysis_response = requests.post(
                f"{ANALYSIS_AGENT_URL}/analyze",
                json={
                    "query": request.query,
                    "results": final_results
                },
                timeout=30
            )
            
            if analysis_response.ok:
                analysis_data = analysis_response.json()
                logger.info(f"✅ Analysis 完成: action={analysis_data.get('action')}")
                
                # ========== 步驟 4: 根據分析結果執行工作流 ==========
                orchestrate_response = requests.post(
                    f"{ANALYSIS_AGENT_URL}/orchestrate",
                    json=analysis_data.get("details"),
                    timeout=60
                )
                
                if orchestrate_response.ok:
                    orchestrate_data = orchestrate_response.json()
                    logger.info(f"✅ Orchestration 完成: {orchestrate_data.get('action')}")
                    
                    # 返回完整結果
                    return {
                        "status": "success",
                        "search_results": search_data,
                        "analysis": analysis_data,
                        "final_result": orchestrate_data
                    }
                else:
                    logger.error(f"❌ Orchestration 失敗: {orchestrate_response.text}")
                    # 即使編排失敗，也返回搜尋和分析結果
                    return {
                        "status": "partial_success",
                        "search_results": search_data,
                        "analysis": analysis_data,
                        "error": "Orchestration failed"
                    }
            else:
                logger.error(f"❌ Analysis 失敗: {analysis_response.text}")
                # 如果分析失敗，至少返回搜尋結果
                return {
                    "status": "partial_success",
                    "search_results": search_data,
                    "error": "Analysis failed"
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 呼叫 Analysis Agent 錯誤: {e}")
            # 如果 analysis_agent 不可用，返回搜尋結果
            return {
                "status": "partial_success",
                "search_results": search_data,
                "error": f"Analysis agent unavailable: {str(e)}"
            }

    except Exception as e:
        logger.exception("POST /search endpoint error")
        raise HTTPException(status_code=500, detail=str(e))

# ----------------------
# Web search endpoint (GET - 保留原有功能，用於獨立測試)
# ----------------------
@app.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., description="User query string"),
    expand: bool = Query(True, description="Whether to expand query using Ollama"),
    max_results: Optional[int] = Query(None, description="Limit results (overrides default)")
):
    """
    GET endpoint - 只執行搜尋，不呼叫其他 agent（用於測試）
    """
    logger.info(f"Received GET /search request: q='{q}', expand={expand}, max_results={max_results}")
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
        for idx, query in enumerate(all_queries):
            if idx > 0:
                await asyncio.sleep(1.5)
                
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
        logger.exception("GET /search endpoint error")
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