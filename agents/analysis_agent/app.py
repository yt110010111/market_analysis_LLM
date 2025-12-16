# agents/analysis_agent/app.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import logging
from agent import AnalysisAgent

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
        "version": "0.3.0",
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
    
    優化後的流程：
    1. 直接檢查資料庫覆蓋度 ✅
    2. 如果資料充足 → 立即生成報告 ✅
    3. 如果資料不足 → 執行完整工作流:
       a. Tavily 搜尋 + 網頁爬取 (一次)
       b. 資料萃取並存入 Neo4j
       c. 生成報告
    
    Returns:
        完整的報告資料
    """
    try:
        logger.info(f"📥 收到統一分析請求: {request.query}")
        
        # ============ 步驟 1: 檢查資料庫覆蓋度 ============
        logger.info(f"🔍 步驟 1/2: 檢查資料庫覆蓋度")
        coverage = agent._check_database_coverage(request.query, [])
        
        logger.info(f"📊 資料庫狀態: {coverage['entity_count']} 個實體, {coverage['relationship_count']} 個關係")
        
        # ============ 步驟 2: 根據覆蓋度決定行動 ============
        if coverage["has_sufficient_data"]:
            # ✅ 資料充足，直接生成報告
            logger.info("✅ 資料庫資料充足，直接生成報告")
            logger.info(f"📝 步驟 2/2: 生成報告")
            
            report_data = agent.report_generator.generate_comprehensive_report(
                query=request.query,
                search_results=[],
                use_neo4j=True
            )
            
            return {
                "status": "success",
                "query": request.query,
                "action": "generate_report",
                "report": report_data["report"],
                "sources": report_data["sources"],
                "workflow_steps": {
                    "database_entities": coverage["entity_count"],
                    "database_relationships": coverage["relationship_count"],
                    "action": "used_existing_data"
                },
                "generated_at": report_data["generated_at"]
            }
        
        else:
            # ❌ 資料不足，執行完整工作流
            logger.info("⚠️ 資料庫資料不足，執行完整工作流")
            logger.info(f"📝 步驟 2/2: 搜尋 → 爬取 → 萃取 → 生成報告")
            
            # 構建工作流請求
            workflow_request = {
                "action": "scrape_and_extract",
                "query": request.query,
                "reason": "資料庫資料不足",
                "coverage": coverage,
                "urls_to_scrape": [],  # 空列表，讓 workflow 自己用 Tavily 搜尋
                "search_results": []
            }
            
            # 執行工作流
            final_result = await agent.orchestrate_workflow(workflow_request)
            
            return {
                "status": final_result.get("status", "success"),
                "query": request.query,
                "action": final_result.get("action", "scrape_and_extract"),
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


@app.post("/orchestrate")
async def orchestrate_workflow(self, request: Dict[str, Any]) -> Dict[str, Any]:
    """
    根據 action 執行相應的工作流
    """
    action = request.get("action")
    query = request.get("query")
    
    logger.info(f"🎬 開始執行工作流: {action}")
    
    try:
        if action == "generate_report":
            # 直接生成報告
            search_results = request.get("search_results", [])
            report_data = self.report_generator.generate_comprehensive_report(
                query=query,
                search_results=search_results,
                use_neo4j=True
            )
            
            logger.info(f"✅ 報告生成完成")
            return {
                "status": "success",
                "action": "generate_report",
                "report": report_data["report"],
                "query": query,
                "sources": report_data["sources"],
                "generated_at": report_data["generated_at"]
            }
            
        elif action == "scrape_and_extract":
            # 執行完整流程：Tavily 搜尋 + 爬蟲 -> 萃取 -> 儲存 -> 生成報告
            
            # 步驟 1: 使用 Tavily 搜尋並爬取網頁
            logger.info(f"   🔍 步驟 1: 使用 Tavily 搜尋並爬取網頁")
            scraped_data = await self._search_and_scrape(query)
            
            if not scraped_data.get("results"):
                logger.warning("   ⚠️ 未找到任何網頁資料")
                # 即使沒有新資料，也嘗試用資料庫生成報告
                report_data = self.report_generator.generate_comprehensive_report(
                    query=query,
                    search_results=[],
                    use_neo4j=True
                )
                return {
                    "status": "success",
                    "action": "scrape_and_extract",
                    "report": report_data["report"],
                    "query": query,
                    "sources": report_data["sources"],
                    "workflow_steps": {
                        "scraped_urls": 0,
                        "extracted_entities": 0,
                        "note": "未找到新資料，使用現有資料庫生成報告"
                    },
                    "generated_at": report_data["generated_at"]
                }
            
            # 步驟 2: 萃取結構化資料（萃取 agent 會自動存入 Neo4j）
            logger.info(f"   🔬 步驟 2: 萃取結構化資料並存入 Neo4j")
            extracted_data = await self._extract_data(query, scraped_data)
            
            # ✅ 修改：直接使用萃取結果，不再查詢 Neo4j
            # 因為萃取 agent 已經存入 Neo4j，我們直接使用返回的實體和關係
            
            entities = extracted_data.get("entities", [])
            relationships = extracted_data.get("relationships", [])
            
            logger.info(f"   📝 步驟 3: 使用萃取結果生成報告")
            
            # 直接傳遞萃取的實體和關係給報告生成器
            report_data = self.report_generator.generate_report_from_extraction(
                query=query,
                entities=entities,
                relationships=relationships,
                search_results=scraped_data.get("results", [])
            )
            
            logger.info(f"✅ 完整工作流執行完成")
            return {
                "status": "success",
                "action": "scrape_and_extract",
                "report": report_data["report"],
                "query": query,
                "sources": report_data["sources"],
                "workflow_steps": {
                    "scraped_urls": len(scraped_data.get("results", [])),
                    "extracted_entities": len(entities),
                    "extracted_relationships": len(relationships)
                },
                "generated_at": report_data["generated_at"]
            }
        
        else:
            raise ValueError(f"Unknown action: {action}")
            
    except Exception as e:
        logger.error(f"❌ 工作流執行失敗: {e}", exc_info=True)
        return {
            "status": "error",
            "action": action,
            "query": query,
            "error": str(e),
            "report": f"# 報告生成失敗\n\n抱歉，生成報告時發生錯誤：{str(e)}"
        }


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