#agents/web_scraping_agent/app.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import logging
from agent import WebScrapingAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Web Scraping Agent API")

agent = WebScrapingAgent()


class ScrapeRequest(BaseModel):
    urls: List[str]
    query: str = ""
    dynamic_search: bool = True  # 預設啟用動態搜尋


class ScrapeResponse(BaseModel):
    query: str
    total_urls: int
    successful: int
    failed: int
    results: List[Dict[str, Any]]
    timestamp: str


@app.get("/")
async def root():
    """根端點"""
    return {
        "service": "web_scraping_agent",
        "version": "0.1.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "scrape": "/scrape (POST)"
        }
    }


@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {
        "status": "healthy",
        "service": "web_scraping_agent",
        "timeout": agent.timeout,
        "max_retries": agent.max_retries
    }


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_urls(request: ScrapeRequest):
    """
    爬取指定的 URL 列表
    
    Args:
        urls: 要爬取的 URL 列表
        query: 相關的查詢（可選）
        dynamic_search: 是否使用 Tavily 動態搜尋更多 URL（預設 True）
    
    Returns:
        爬取結果
    """
    try:
        logger.info(f"📥 收到爬取請求: {len(request.urls)} 個 URL, query='{request.query}', dynamic_search={request.dynamic_search}")
        
        # 如果既沒有 URL 也沒有 query，無法處理
        if not request.urls and not request.query:
            raise HTTPException(
                status_code=400, 
                detail="需要提供 URLs 或 query（啟用 dynamic_search 時）"
            )
        
        # 使用提供的 URL 或空列表
        urls = request.urls if request.urls else []
        
        # 執行爬取（可能包含動態搜尋）
        results = await agent.scrape_urls(
            urls, 
            request.query, 
            dynamic_search=request.dynamic_search
        )
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 爬取錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scrape/single")
async def scrape_single_url(url: str, query: str = ""):
    """
    爬取單個 URL（便捷端點）
    """
    try:
        logger.info(f"📥 收到單一 URL 爬取請求: {url}")
        
        results = await agent.scrape_urls([url], query)
        
        if results["successful"] > 0:
            return results["results"][0]
        else:
            raise HTTPException(status_code=500, detail="Scraping failed")
            
    except Exception as e:
        logger.error(f"❌ 爬取錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)