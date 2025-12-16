import logging
from typing import Dict, Any, List
import requests
import json
from report_generator import ReportGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnalysisAgent:
    """
    分析代理：使用 LLM 判斷資料充足度並協調工作流
    """
    
    def __init__(self):
        self.report_generator = ReportGenerator()
        self.web_scraping_url = "http://web_scraping_agent:8003"
        self.data_extraction_url = "http://data_extraction_agent:8004"
        self.ollama_endpoint = "http://ollama:11434"
        self.model_name = "llama3.2:3b"
        self.max_iterations = 3  # 最多迭代 3 次
    
    def _query_ollama(self, prompt: str, temperature: float = 0.3) -> str:
        """
        呼叫 Ollama API
        """
        try:
            response = requests.post(
                f"{self.ollama_endpoint}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "temperature": temperature,
                    "stream": False
                },
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except Exception as e:
            logger.error(f"❌ Ollama 呼叫失敗: {e}")
            raise
    
    def _check_data_sufficiency_with_llm(
        self, 
        query: str, 
        entities: List[Dict], 
        relationships: List[Dict],
        iteration: int = 0
    ) -> Dict[str, Any]:
        """
        使用 LLM 判斷資料是否充足以撰寫報告
        
        Returns:
            {
                "is_sufficient": bool,
                "reason": str,
                "missing_aspects": List[str],
                "confidence": float
            }
        """
        # 構建實體摘要
        entity_summary = self._summarize_entities(entities)
        relationship_summary = self._summarize_relationships(relationships)
        
        prompt = f"""你是一個專業的市場分析助理。請判斷以下資料是否足以撰寫一份完整的市場分析報告。

查詢主題: {query}

目前收集的資料:
- 實體數量: {len(entities)}
- 關係數量: {len(relationships)}
- 迭代次數: {iteration + 1}/{self.max_iterations}

實體摘要:
{entity_summary}

關係摘要:
{relationship_summary}

請評估:
1. 資料是否涵蓋主題的核心面向？
2. 是否有足夠的細節支撐分析？
3. 關係是否足以建立因果或關聯分析？
4. 還缺少哪些重要資訊？

請以 JSON 格式回應（只回傳 JSON，不要其他文字）:
{{
    "is_sufficient": true/false,
    "confidence": 0.0-1.0,
    "reason": "簡短說明",
    "missing_aspects": ["缺少的面向1", "缺少的面向2"],
    "coverage_score": 0-100
}}"""

        try:
            llm_response = self._query_ollama(prompt, temperature=0.3)
            
            # 嘗試解析 JSON
            # 移除可能的 markdown 標記
            llm_response = llm_response.replace("```json", "").replace("```", "").strip()
            
            result = json.loads(llm_response)
            
            logger.info(f"🤖 LLM 判斷結果:")

            logger.info(f"   原因: {result.get('reason', 'N/A')}")
            if result.get('missing_aspects'):
                logger.info(f"   缺少面向: {', '.join(result.get('missing_aspects', []))}")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ LLM 回應解析失敗: {e}")
            logger.warning(f"   原始回應: {llm_response[:200]}")
            
            # 降級處理：使用簡單規則
            return self._fallback_sufficiency_check(entities, relationships)
        except Exception as e:
            logger.error(f"❌ LLM 判斷失敗: {e}")
            return self._fallback_sufficiency_check(entities, relationships)
    
    def _fallback_sufficiency_check(
        self, 
        entities: List[Dict], 
        relationships: List[Dict]
    ) -> Dict[str, Any]:
        """
        降級方案：使用簡單規則判斷
        """
        entity_count = len(entities)
        rel_count = len(relationships)
        
        # 簡單規則：至少 5 個實體和 3 個關係
        is_sufficient = entity_count >= 5 and rel_count >= 3
        coverage_score = min(100, (entity_count * 10 + rel_count * 15))
        
        return {
            "is_sufficient": is_sufficient,
            "confidence": 0.6,
            "reason": f"基於規則判斷：{entity_count} 實體, {rel_count} 關係",
            "missing_aspects": ["需要更多資料"] if not is_sufficient else [],
            "coverage_score": coverage_score
        }
    
    def _summarize_entities(self, entities: List[Dict]) -> str:
        """
        摘要實體資訊
        """
        if not entities:
            return "無實體資料"
        
        # 統計實體類型
        type_counts = {}
        for entity in entities[:20]:  # 只看前 20 個
            entity_type = entity.get("type", "Unknown")
            type_counts[entity_type] = type_counts.get(entity_type, 0) + 1
        
        summary_lines = [f"- {type_}: {count} 個" for type_, count in type_counts.items()]
        
        # 列出一些實體名稱
        sample_names = [e.get("name", "N/A") for e in entities[:5]]
        summary_lines.append(f"範例: {', '.join(sample_names)}")
        
        return "\n".join(summary_lines)
    
    def _summarize_relationships(self, relationships: List[Dict]) -> str:
        """
        摘要關係資訊
        """
        if not relationships:
            return "無關係資料"
        
        # 統計關係類型
        type_counts = {}
        for rel in relationships[:20]:  # 只看前 20 個
            rel_type = rel.get("type", "Unknown")
            type_counts[rel_type] = type_counts.get(rel_type, 0) + 1
        
        summary_lines = [f"- {type_}: {count} 個" for type_, count in type_counts.items()]
        
        return "\n".join(summary_lines)
    
    def _generate_search_queries(self, query: str, missing_aspects: List[str]) -> List[str]:
        """
        根據缺少的面向生成新的搜尋查詢
        """
        if not missing_aspects:
            return [query]
        
        prompt = f"""基於以下資訊，生成 2-3 個更具體的搜尋查詢來補充缺少的資訊。

原始查詢: {query}
缺少的面向: {', '.join(missing_aspects)}

請生成能夠找到這些缺少資訊的搜尋查詢。
格式: 每行一個查詢，不要編號或其他標記。
範例:
台灣 AI 產業 供應鏈
台灣 AI 晶片 市場規模
台灣 AI 新創公司"""

        try:
            llm_response = self._query_ollama(prompt, temperature=0.7)
            queries = [q.strip() for q in llm_response.split("\n") if q.strip()]
            queries = queries[:3]  # 最多 3 個
            
            logger.info(f"🔍 生成新搜尋查詢: {queries}")
            return queries
            
        except Exception as e:
            logger.warning(f"⚠️ 生成搜尋查詢失敗: {e}")
            return [query]
    
    async def orchestrate_workflow(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        迭代式工作流：不斷搜尋直到資料充足
        
        流程:
        1. 檢查現有資料
        2. LLM 判斷是否充足
        3. 如果不足 → 搜尋 + 爬取 + 萃取 → 回到步驟 2
        4. 如果充足或達到最大迭代次數 → 生成報告
        """
        query = request.get("query")
        action = request.get("action")
        
        logger.info(f"🎬 開始執行迭代式工作流: {query}")
        
        all_scraped_results = []
        iteration = 0
        
        try:
            while iteration < self.max_iterations:
                logger.info(f"\n{'='*60}")
                logger.info(f"📍 迭代 {iteration + 1}/{self.max_iterations}")
                logger.info(f"{'='*60}")
                
                # ============ 步驟 1: 查詢現有資料 ============
                logger.info(f"🔍 步驟 1: 查詢 Neo4j 現有資料")
                neo4j_data = self.report_generator._query_neo4j_knowledge(query)
                entities = neo4j_data.get("entities", [])
                relationships = neo4j_data.get("relationships", [])
                
                logger.info(f"📊 當前資料: {len(entities)} 實體, {len(relationships)} 關係")
                
                # ============ 步驟 2: LLM 判斷充足度 ============
                logger.info(f"🤖 步驟 2: LLM 判斷資料充足度")
                sufficiency = self._check_data_sufficiency_with_llm(
                    query, entities, relationships, iteration
                )
                
                # ============ 步驟 3: 決定是否繼續 ============
                if sufficiency.get("is_sufficient", False):
                    logger.info(f"✅ LLM 判斷資料充足，開始生成報告")
                    break
                
                if iteration >= self.max_iterations - 1:
                    logger.info(f"⚠️ 已達最大迭代次數，強制生成報告")
                    break
                
                # ============ 步驟 4: 生成新搜尋查詢 ============
                logger.info(f"📝 步驟 3: 生成補充搜尋查詢")
                missing_aspects = sufficiency.get("missing_aspects", [])
                search_queries = self._generate_search_queries(query, missing_aspects)
                
                # ============ 步驟 5: 搜尋 + 爬取 ============
                logger.info(f"🔍 步驟 4: 執行搜尋和爬取")
                for search_query in search_queries:
                    logger.info(f"   搜尋: {search_query}")
                    scraped_data = await self._search_and_scrape(search_query)
                    
                    if scraped_data.get("results"):
                        all_scraped_results.extend(scraped_data.get("results", []))
                        
                        # ============ 步驟 6: 萃取並存入 Neo4j ============
                        logger.info(f"   🔬 萃取資料並存入 Neo4j")
                        await self._extract_data(query, scraped_data)
                
                iteration += 1
            
            # ============ 最終步驟: 生成報告 ============
            logger.info(f"\n{'='*60}")
            logger.info(f"📝 最終步驟: 生成報告")
            logger.info(f"{'='*60}")
            
            # 重新查詢最終資料
            final_neo4j_data = self.report_generator._query_neo4j_knowledge(query)
            final_entities = final_neo4j_data.get("entities", [])
            final_relationships = final_neo4j_data.get("relationships", [])
            
            logger.info(f"📊 最終資料: {len(final_entities)} 實體, {len(final_relationships)} 關係")
            
            report_data = self.report_generator.generate_report_from_extraction(
                query=query,
                entities=final_entities,
                relationships=final_relationships,
                search_results=all_scraped_results
            )
            
            logger.info(f"✅ 報告生成完成")
            
            return {
                "status": "success",
                "action": action,
                "report": report_data["report"],
                "query": query,
                "sources": report_data["sources"],
                "workflow_steps": {
                    "iterations": iteration + 1,
                    "total_scraped_urls": len(all_scraped_results),
                    "final_entities": len(final_entities),
                    "final_relationships": len(final_relationships),
                    "sufficiency_score": sufficiency.get("coverage_score", 0)
                },
                "generated_at": report_data["generated_at"]
            }
            
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
        使用 Tavily 搜尋並爬取網頁
        """
        try:
            response = requests.post(
                f"{self.web_scraping_url}/scrape",
                json={
                    "urls": [],
                    "query": query,
                    "dynamic_search": True
                },
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"   ✅ 爬取完成: {result.get('successful', 0)} 個成功")
            return result
            
        except Exception as e:
            logger.error(f"   ❌ 搜尋爬取失敗: {e}")
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
            
            stats = result.get("statistics", {})
            entity_count = stats.get("total_entities", 0)
            rel_count = stats.get("total_relationships", 0)
            logger.info(f"   ✅ 萃取成功: {entity_count} 個實體, {rel_count} 個關係")
            
            return result
            
        except Exception as e:
            logger.error(f"   ❌ 資料萃取失敗: {e}")
            return {
                "entities": [],
                "relationships": [],
                "statistics": {"total_entities": 0, "total_relationships": 0},
                "error": str(e)
            }