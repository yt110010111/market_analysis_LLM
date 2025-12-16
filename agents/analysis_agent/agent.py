# agents/analysis_agent/agent.py
import logging
from typing import Dict, Any, List
import requests
from report_generator import ReportGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnalysisAgent:
    """
    分析代理：分析搜尋結果並協調工作流
    """
    
    def __init__(self):
        self.report_generator = ReportGenerator()
        self.web_scraping_url = "http://web_scraping_agent:8003"
        self.data_extraction_url = "http://data_extraction_agent:8004"
    
    def analyze_search_results(self, search_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析搜尋結果並決定下一步行動
        
        策略：
        1. 檢查資料庫中是否已有足夠資料
        2. 如果有 -> 直接生成報告
        3. 如果沒有 -> 執行爬蟲和萃取流程
        """
        query = search_results.get("query", "")
        results = search_results.get("results", [])
        
        logger.info(f"🔍 分析搜尋結果: {query}")
        logger.info(f"   找到 {len(results)} 個搜尋結果")
        
        # 檢查資料庫覆蓋度
        coverage = self._check_database_coverage(query, results)
        
        if coverage["has_sufficient_data"]:
            logger.info("   ✅ 資料庫資料充足，直接生成報告")
            return {
                "action": "generate_report",
                "query": query,
                "reason": "資料庫中已有足夠的相關資料",
                "coverage": coverage,
                "search_results": results
            }
        else:
            logger.info("   ⚠️ 資料庫資料不足，需要爬取網頁")
            return {
                "action": "scrape_and_extract",
                "query": query,
                "reason": "需要從網頁爬取更多資料",
                "coverage": coverage,
                "urls_to_scrape": [r.get("url") for r in results[:5]],  # 限制 5 個
                "search_results": results
            }
    
    def _check_database_coverage(self, query: str, results: List[Dict]) -> Dict[str, Any]:
        """
        檢查 Neo4j 資料庫中是否有足夠的相關資料
        """
        try:
            # 使用 report_generator 的 Neo4j 查詢方法
            neo4j_data = self.report_generator._query_neo4j_knowledge(query)
            
            entity_count = neo4j_data.get("entity_count", 0)
            relationship_count = neo4j_data.get("relationship_count", 0)
            
            # 判斷標準：至少 3 個實體或 2 個關係
            has_sufficient_data = entity_count >= 3 or relationship_count >= 2
            
            return {
                "has_sufficient_data": has_sufficient_data,
                "entity_count": entity_count,
                "relationship_count": relationship_count,
                "threshold": {"min_entities": 3, "min_relationships": 2}
            }
            
        except Exception as e:
            logger.warning(f"   ⚠️ 檢查資料庫覆蓋度失敗: {e}")
            # 如果檢查失敗，預設為需要爬取
            return {
                "has_sufficient_data": False,
                "entity_count": 0,
                "relationship_count": 0,
                "error": str(e)
            }
    
    async def orchestrate_workflow(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        根據 action 執行相應的工作流
        
        返回格式：
        {
            "status": "success",
            "report": "...",
            "query": "...",
            "sources": {...}
        }
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
                
                # ✅ 關鍵修改：直接使用萃取結果，不再查詢 Neo4j
                entities = extracted_data.get("entities", [])
                relationships = extracted_data.get("relationships", [])
                
                logger.info(f"   📝 步驟 3: 使用萃取結果生成報告")
                logger.info(f"   📊 使用 {len(entities)} 個實體和 {len(relationships)} 個關係")
                
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
    
    async def _search_and_scrape(self, query: str) -> Dict[str, Any]:
        """
        🆕 使用 Tavily 搜尋並爬取網頁（一次完成）
        
        這個方法會：
        1. 調用 web_scraping_agent
        2. 傳入 query 和 dynamic_search=True
        3. web_scraping_agent 會自動用 Tavily 搜尋並爬取
        
        返回格式：
        {
            "query": str,
            "total_urls": int,
            "successful": int,
            "failed": int,
            "results": [...]
        }
        """
        try:
            response = requests.post(
                f"{self.web_scraping_url}/scrape",
                json={
                    "urls": [],  # 空列表，讓它自己用 Tavily 搜尋
                    "query": query,
                    "dynamic_search": True  # 啟用 Tavily
                },
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"   ✅ 搜尋並爬取完成: {result.get('successful', 0)} 個成功")
            return result
            
        except Exception as e:
            logger.error(f"   ❌ 搜尋並爬取失敗: {e}")
            return {"results": []}
    
    async def _extract_data(self, query: str, scraped_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        呼叫 data_extraction_agent 萃取並儲存資料
        """
        try:
            response = requests.post(
                f"{self.data_extraction_url}/extract",
                json={
                    "data": scraped_data,
                    "query": query
                },
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            
            # 記錄成功訊息
            stats = result.get("statistics", {})
            entity_count = stats.get("total_entities", 0)
            rel_count = stats.get("total_relationships", 0)
            logger.info(f"   ✅ 萃取成功: {entity_count} 個實體, {rel_count} 個關係")
            
            # ✅ 檢查 Neo4j 存儲狀態
            storage_status = result.get("neo4j_storage", {})
            if storage_status.get("status") == "error":
                logger.warning(f"   ⚠️ Neo4j 存儲失敗: {storage_status.get('error')}")
            elif storage_status.get("status") == "success":
                logger.info(f"   ✅ Neo4j 存儲成功: {storage_status.get('entities_stored')} 實體, {storage_status.get('relationships_stored')} 關係")
            
            return result
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"   ❌ 資料萃取失敗: {e.response.status_code} - {e.response.text}")
            # ✅ 返回空結果而不是拋出異常
            return {
                "entities": [],
                "relationships": [],
                "statistics": {"total_entities": 0, "total_relationships": 0},
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"   ❌ 資料萃取失敗: {e}")
            # ✅ 返回空結果而不是拋出異常
            return {
                "entities": [],
                "relationships": [],
                "statistics": {"total_entities": 0, "total_relationships": 0},
                "error": str(e)
            }