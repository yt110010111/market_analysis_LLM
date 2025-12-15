# agents/analysis_agent/app.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import logging
from agent import AnalysisAgent
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Analysis Agent API")

# ⭐ 添加 CORS 中間件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = AnalysisAgent()


class AnalyzeRequest(BaseModel):
    """前端統一入口的請求格式"""
    query: str


class AnalyzeResponse(BaseModel):
    """統一回應格式"""
    status: str
    query: str
    action: str
    report: str
    sources: Dict[str, Any]
    workflow_steps: Optional[Dict[str, Any]] = None
    generated_at: str


@app.get("/")
async def root():
    """根端點"""
    return {
        "service": "analysis_agent",
        "version": "0.2.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "analyze": "/analyze (POST) - 統一入口",
            "orchestrate": "/orchestrate (POST) - 內部使用",
        }
    }


@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {"status": "healthy", "service": "analysis_agent"}


@app.post("/analyze")
async def analyze_query(request: AnalyzeRequest):
    """
    🎯 統一入口：前端只需要調用這個端點
    
    流程：
    1. 使用 Tavily 搜尋相關資料
    2. 分析資料庫覆蓋度
    3. 根據覆蓋度決定：
       - 直接生成報告 (Neo4j 資料充足)
       - 爬蟲 + 萃取 + 生成報告 (資料不足)
    
    Returns:
        完整的報告資料
    """
    try:
        logger.info(f"📥 收到統一分析請求: {request.query}")
        
        # ============ 步驟 1: 使用 Tavily 搜尋 ============
        logger.info(f"🔍 步驟 1/3: 使用 Tavily 搜尋")
        search_results = await _search_with_tavily(request.query)
        
        if not search_results:
            logger.warning("⚠️ Tavily 搜尋無結果，使用空結果繼續")
            search_results = []
        
        logger.info(f"✅ 找到 {len(search_results)} 個搜尋結果")
        
        # ============ 步驟 2: 分析資料庫覆蓋度 ============
        logger.info(f"📊 步驟 2/3: 分析資料庫覆蓋度")
        analysis_result = agent.analyze_search_results({
            "query": request.query,
            "results": search_results
        })
        
        logger.info(f"📋 分析結果: {analysis_result['action']}")
        
        # ============ 步驟 3: 執行工作流 ============
        logger.info(f"🎬 步驟 3/3: 執行工作流")
        final_result = await agent.orchestrate_workflow(analysis_result)
        
        # ============ 返回統一格式 ============
        return {
            "status": final_result.get("status", "success"),
            "query": request.query,
            "action": final_result.get("action", "unknown"),
            "report": final_result.get("report", "無法生成報告"),
            "sources": final_result.get("sources", {}),
            "workflow_steps": final_result.get("workflow_steps"),
            "generated_at": final_result.get("generated_at", ""),
            
            # 額外資訊（供前端使用）
            "search_results": {
                "total_results": len(search_results),
                "results": search_results[:5]  # 只返回前 5 個
            }
        }
        
    except Exception as e:
        logger.error(f"❌ 分析失敗: {e}", exc_info=True)
        return {
            "status": "error",
            "query": request.query,
            "action": "error",
            "report": f"# 分析失敗\n\n抱歉，處理您的請求時發生錯誤：{str(e)}",
            "sources": {},
            "generated_at": "",
            "error": str(e)
        }


async def _search_with_tavily(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    使用 Tavily API 搜尋
    
    注意：這裡我們直接在 analysis_agent 調用 Tavily，
    而不是通過 web_scraping_agent（避免多餘的 HTTP 調用）
    """
    try:
        # 使用 web_scraping_agent 的 Tavily 功能
        response = requests.post(
            f"{agent.web_scraping_url}/scrape",
            json={
                "urls": [],  # 空列表
                "query": query,
                "dynamic_search": True  # 啟用 Tavily
            },
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        results = data.get("results", [])
        
        # 轉換為統一格式
        formatted_results = []
        for result in results:
            if result.get("success"):
                formatted_results.append({
                    "url": result.get("url"),
                    "title": result.get("title", ""),
                    "description": result.get("description", ""),
                    "content": result.get("content", "")
                })
        
        logger.info(f"✅ Tavily 返回 {len(formatted_results)} 個結果")
        return formatted_results
        
    except Exception as e:
        logger.error(f"❌ Tavily 搜尋失敗: {e}")
        return []


@app.post("/orchestrate")
async def orchestrate_workflow(request: Dict[str, Any]):
    """
    執行完整的工作流編排（內部使用）
    
    根據分析結果執行相應的工作流:
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)