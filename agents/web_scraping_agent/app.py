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
    
    Returns:
        爬取結果
    """
    try:
        logger.info(f"📥 收到爬取請求: {len(request.urls)} 個 URL")
        
        if not request.urls:
            raise HTTPException(status_code=400, detail="URL list is empty")
        
        # 限制一次最多爬取 10 個 URL
        if len(request.urls) > 10:
            logger.warning(f"⚠️ URL 數量過多，限制為前 10 個")
            request.urls = request.urls[:10]
        
        # 執行爬取
        results = await agent.scrape_urls(request.urls, request.query)
        
        # 可選：儲存為 JSON（在生產環境可能要改為資料庫）
        # agent.save_results_to_json(results, f"scraping_{results['timestamp']}.json")
        
        return results
        
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