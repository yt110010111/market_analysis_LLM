from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging
from agent import AnalysisAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Analysis Agent API")

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
        "version": "0.4.0",
        "description": "使用 LLM 判斷資料充足度的智能分析代理",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "analyze": "/analyze (POST) - 統一入口（使用 LLM 判斷）",
        }
    }


@app.get("/health")
async def health_check():
    """健康檢查端點"""
    return {"status": "healthy", "service": "analysis_agent"}


@app.post("/analyze")
async def analyze_query(request: AnalyzeRequest):
    """
    🎯 統一入口：使用 LLM 判斷資料充足度並迭代搜尋
    
    新流程：
    1. 查詢 Neo4j 現有資料
    2. LLM 判斷是否充足撰寫報告
    3. 如果不足：
       - 生成補充搜尋查詢
       - 搜尋 + 爬取 + 萃取 + 存入 Neo4j
       - 重複步驟 2（最多 3 次迭代）
    4. 生成報告
    
    Returns:
        完整的報告資料
    """
    try:
        logger.info(f"📥 收到分析請求: {request.query}")
        logger.info(f"🤖 使用 LLM 判斷資料充足度並迭代搜尋")
        
        # 直接執行迭代式工作流
        workflow_request = {
            "action": "iterative_analysis",
            "query": request.query
        }
        
        final_result = await agent.orchestrate_workflow(workflow_request)
        
        return {
            "status": final_result.get("status", "success"),
            "query": request.query,
            "action": final_result.get("action", "iterative_analysis"),
            "report": final_result.get("report", "無法生成報告"),
            "sources": final_result.get("sources", {}),
            "workflow_steps": final_result.get("workflow_steps"),
            "generated_at": final_result.get("generated_at", "")
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)