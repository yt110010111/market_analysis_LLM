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
            "report": "...",  # 關鍵！必須包含報告內容
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
                    "report": report_data["report"],  # 這裡！
                    "query": query,
                    "sources": report_data["sources"],
                    "generated_at": report_data["generated_at"]
                }
                
            elif action == "scrape_and_extract":
                # 執行完整流程：爬蟲 -> 萃取 -> 儲存 -> 生成報告
                urls = request.get("urls_to_scrape", [])
                
                # 步驟 1: 爬取網頁
                logger.info(f"   📡 步驟 1: 爬取 {len(urls)} 個網頁")
                scraped_data = await self._scrape_urls(urls)
                
                # 步驟 2: 萃取結構化資料
                logger.info(f"   🔬 步驟 2: 萃取結構化資料")
                extracted_data = await self._extract_data(query, scraped_data)
                
                # 步驟 3: 生成報告（萃取 agent 已經儲存到 Neo4j）
                logger.info(f"   📝 步驟 3: 生成最終報告")
                search_results = request.get("search_results", [])
                report_data = self.report_generator.generate_comprehensive_report(
                    query=query,
                    search_results=search_results,
                    use_neo4j=True
                )
                
                logger.info(f"✅ 完整工作流執行完成")
                return {
                    "status": "success",
                    "action": "scrape_and_extract",
                    "report": report_data["report"],  # 這裡！
                    "query": query,
                    "sources": report_data["sources"],
                    "workflow_steps": {
                        "scraped_urls": len(scraped_data),
                        "extracted_entities": extracted_data.get("entity_count", 0)
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
    
    async def _scrape_urls(self, urls: List[str]) -> List[Dict[str, Any]]:
        """呼叫 web_scraping_agent 爬取網頁"""
        try:
            response = requests.post(
                f"{self.web_scraping_url}/scrape",
                json={"urls": urls},
                timeout=60
            )
            response.raise_for_status()
            return response.json().get("results", [])
        except Exception as e:
            logger.error(f"   ❌ 爬蟲失敗: {e}")
            return []
    
    async def _extract_data(self, query: str, scraped_data: List[Dict]) -> Dict[str, Any]:
        """呼叫 data_extraction_agent 萃取並儲存資料"""
        try:
            response = requests.post(
                f"{self.data_extraction_url}/extract",
                json={
                    "query": query,
                    "documents": scraped_data
                },
                timeout=120
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"   ❌ 資料萃取失敗: {e}")
            return {"entity_count": 0, "error": str(e)}