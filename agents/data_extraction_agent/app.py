from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import logging
from agent import DataExtractionAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Data Extraction Agent API")

agent = DataExtractionAgent()


class ExtractionRequest(BaseModel):
    data: Dict[str, Any]  # 來自 web_scraping_agent 的輸出
    query: str = ""


@app.get("/")
async def root():
    """根端點"""
    return {
        "service": "data_extraction_agent",
        "version": "0.1.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "extract": "/extract (POST)"
        }
    }


@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {
        "status": "healthy",
        "service": "data_extraction_agent",
        "model": agent.model_name,
        "ollama_endpoint": agent.ollama_endpoint
    }


@app.post("/extract")
async def extract_data(request: ExtractionRequest):
    """
    從爬取的資料中提取實體、關係和摘要
    
    Args:
        data: web_scraping_agent 的輸出
        query: 原始查詢
        
    Returns:
        提取的實體、關係和摘要
    """
    try:
        logger.info(f"📥 收到資料萃取請求: query='{request.query}'")
        
        # 執行提取和分析
        result = agent.extract_and_analyze(request.data, request.query)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ 萃取錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    import sys
    
    # 確保程式持續運行
    try:
        uvicorn.run(
            app, 
            host="0.0.0.0", 
            port=8004,
            log_level="info"
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)