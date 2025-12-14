#agents/analysis_agent/app.py 
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import logging
from agent import AnalysisAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Analysis Agent API")

agent = AnalysisAgent()


class SearchResultsRequest(BaseModel):
    query: str
    results: List[Dict[str, Any]]


class AnalysisResponse(BaseModel):
    action: str
    query: str
    details: Dict[str, Any]


@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {"status": "healthy", "service": "analysis_agent"}


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_search_results(request: SearchResultsRequest):
    """
    分析搜尋結果並決定下一步行動
    
    - 如果資料充足：返回 action="generate_report"
    - 如果資料不足：返回 action="scrape_and_extract"
    """
    try:
        logger.info(f"Received analysis request for query: {request.query}")
        
        search_results = {
            "query": request.query,
            "results": request.results
        }
        
        # 分析搜尋結果
        analysis_result = agent.analyze_search_results(search_results)
        
        return {
            "action": analysis_result["action"],
            "query": analysis_result["query"],
            "details": analysis_result
        }
        
    except Exception as e:
        logger.error(f"Error in analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/orchestrate")
async def orchestrate_workflow(request: Dict[str, Any]):
    """
    執行完整的工作流編排
    
    根據分析結果，執行相應的工作流：
    - generate_report: 直接生成報告
    - scrape_and_extract: 執行爬蟲 -> 萃取 -> 儲存 -> 生成報告
    """
    try:
        logger.info(f"Orchestrating workflow for action: {request.get('action')}")
        
        result = await agent.orchestrate_workflow(request)
        
        return result
        
    except Exception as e:
        logger.error(f"Error in orchestration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/check-coverage")
async def check_database_coverage(request: Dict[str, Any]):
    """
    單獨檢查資料庫覆蓋度（用於測試）
    """
    try:
        query = request.get("query", "")
        results = request.get("results", [])
        
        coverage = agent._check_database_coverage(query, results)
        
        return coverage
        
    except Exception as e:
        logger.error(f"Error checking coverage: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """根端點"""
    return {
        "service": "analysis_agent",
        "version": "0.1.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "analyze": "/analyze (POST)",
            "orchestrate": "/orchestrate (POST)",
            "check_coverage": "/check-coverage (POST)"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)