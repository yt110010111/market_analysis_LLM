import os
import json
import logging
from typing import Dict, List, Any
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnalysisAgent:
    """
    分析代理：決定是否需要額外資料收集或直接生成報告
    """
    
    def __init__(self):
        self.ollama_endpoint = os.getenv("OLLAMA_ENDPOINT", "http://ollama:11434")
        self.model_name = os.getenv("MODEL_NAME", "llama3.2:3b")
        self.neo4j_url = os.getenv("NEO4J_URL", "http://neo4j:7474")
        self.web_scraping_agent_url = os.getenv("WEB_SCRAPING_AGENT_URL", "http://web_scraping_agent:8002")
        self.data_extraction_agent_url = os.getenv("DATA_EXTRACTION_AGENT_URL", "http://data_extraction_agent:8003")
        
    def analyze_search_results(self, search_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析搜尋結果，決定下一步行動
        
        Args:
            search_results: web_search_agent 的結果
            
        Returns:
            決策結果，包含 action 和相關資料
        """
        query = search_results.get("query", "")
        results = search_results.get("results", [])
        
        logger.info(f"Analyzing search results for query: {query}")
        
        # 步驟 1: 檢查資料庫中的相關資料
        db_coverage = self._check_database_coverage(query, results)
        
        # 步驟 2: 根據資料庫覆蓋度決定行動
        if db_coverage["sufficient"]:
            logger.info("Database coverage sufficient, generating report")
            return {
                "action": "generate_report",
                "query": query,
                "search_results": results,
                "db_data": db_coverage["data"]
            }
        else:
            logger.info("Database coverage insufficient, initiating web scraping")
            return {
                "action": "scrape_and_extract",
                "query": query,
                "search_results": results,
                "missing_topics": db_coverage["missing_topics"],
                "urls_to_scrape": self._identify_scraping_targets(results)
            }
    
    def _check_database_coverage(self, query: str, search_results: List[Dict]) -> Dict[str, Any]:
        """
        使用 RAG 檢查資料庫中是否有足夠的相關資料
        
        這裡使用簡單的關鍵詞匹配和計數邏輯
        實際應該查詢 Neo4j 並使用向量相似度
        """
        try:
            # TODO: 實作真正的 Neo4j 查詢
            # 目前使用簡化邏輯：如果搜尋結果少於3個，認為不足
            
            prompt = f"""分析以下搜尋結果，判斷是否需要更多資料來回答問題。

問題: {query}

搜尋結果數量: {len(search_results)}
搜尋結果摘要: {json.dumps([r.get('title', '') for r in search_results[:5]], ensure_ascii=False)}

請回答：
1. 這些資料是否足夠回答問題？(是/否)
2. 如果不足，缺少哪些主題？

請以 JSON 格式回答：
{{"sufficient": true/false, "missing_topics": ["topic1", "topic2"]}}
"""
            
            response = self._call_ollama(prompt)
            
            # 解析 LLM 回應
            try:
                decision = json.loads(response)
            except json.JSONDecodeError:
                # 如果解析失敗，使用簡單規則
                decision = {
                    "sufficient": len(search_results) >= 3,
                    "missing_topics": []
                }
            
            return {
                "sufficient": decision.get("sufficient", False),
                "missing_topics": decision.get("missing_topics", []),
                "data": search_results if decision.get("sufficient") else []
            }
            
        except Exception as e:
            logger.error(f"Error checking database coverage: {e}")
            # 發生錯誤時，假設需要更多資料
            return {
                "sufficient": False,
                "missing_topics": ["general"],
                "data": []
            }
    
    def _identify_scraping_targets(self, search_results: List[Dict]) -> List[str]:
        """
        從搜尋結果中識別需要爬取的 URL
        """
        urls = []
        for result in search_results[:5]:  # 只取前5個結果
            url = result.get("url")
            if url and url.startswith("http"):
                urls.append(url)
        return urls
    
    def _call_ollama(self, prompt: str) -> str:
        """
        呼叫 Ollama API
        """
        try:
            response = requests.post(
                f"{self.ollama_endpoint}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            raise
    
    async def orchestrate_workflow(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        根據分析結果編排後續工作流
        """
        action = analysis_result.get("action")
        
        if action == "generate_report":
            return await self._generate_report(analysis_result)
        elif action == "scrape_and_extract":
            return await self._scrape_and_extract_workflow(analysis_result)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _generate_report(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        直接生成報告（資料充足時）
        """
        query = data.get("query")
        search_results = data.get("search_results", [])
        
        prompt = f"""基於以下資料，生成一份詳細報告回答這個問題：

問題: {query}

資料來源:
{json.dumps(search_results, ensure_ascii=False, indent=2)}

請生成一份結構化的報告，包含：
1. 摘要
2. 主要發現
3. 詳細分析
4. 結論
"""
        
        report = self._call_ollama(prompt)
        
        return {
            "status": "completed",
            "action": "report_generated",
            "query": query,
            "report": report,
            "sources": [r.get("url") for r in search_results]
        }
    
    async def _scrape_and_extract_workflow(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        執行爬蟲和資料萃取工作流
        """
        urls = data.get("urls_to_scrape", [])
        query = data.get("query")
        
        logger.info(f"Initiating scraping for {len(urls)} URLs")
        
        # 步驟 1: 呼叫 web_scraping_agent
        try:
            scraping_response = requests.post(
                f"{self.web_scraping_agent_url}/scrape",
                json={"urls": urls, "query": query},
                timeout=60
            )
            scraping_response.raise_for_status()
            scraped_data = scraping_response.json()
            logger.info(f"✅ Scraping completed: {scraped_data.get('successful', 0)} successful")
        except Exception as e:
            logger.error(f"Error calling web_scraping_agent: {e}")
            scraped_data = {"error": str(e), "results": []}
        
        # 步驟 2: 呼叫 data_extraction_agent 分析關聯
        try:
            extraction_response = requests.post(
                f"{self.data_extraction_agent_url}/extract",
                json={"data": scraped_data, "query": query},
                timeout=90
            )
            extraction_response.raise_for_status()
            extracted_data = extraction_response.json()
            logger.info(f"✅ Extraction completed: {len(extracted_data.get('entities', []))} entities")
        except Exception as e:
            logger.error(f"Error calling data_extraction_agent: {e}")
            extracted_data = {"error": str(e), "entities": [], "relationships": []}
        
        # 步驟 3: 儲存到 Neo4j
        neo4j_result = self._store_to_neo4j(extracted_data, query)
        
        # 步驟 4: 生成最終報告
        report = self._generate_final_report(query, scraped_data, extracted_data)
        
        return {
            "status": "completed",
            "action": "data_collected_and_stored",
            "query": query,
            "scraped_urls": urls,
            "scraping_stats": {
                "successful": scraped_data.get("successful", 0),
                "failed": scraped_data.get("failed", 0)
            },
            "extraction_stats": {
                "entities": len(extracted_data.get("entities", [])),
                "relationships": len(extracted_data.get("relationships", []))
            },
            "neo4j_stored": neo4j_result.get("success", False),
            "report": report
        }
    
    def _store_to_neo4j(self, extracted_data: Dict[str, Any], query: str) -> Dict[str, Any]:
        """
        將提取的實體和關係儲存到 Neo4j
        """
        try:
            from neo4j import GraphDatabase
            
            neo4j_uri = os.getenv("NEO4J_URL", "bolt://neo4j:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "password123")
            
            driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
            
            with driver.session() as session:
                # 創建查詢節點
                session.run(
                    "MERGE (q:Query {text: $query_text, timestamp: datetime()}) RETURN q",
                    query_text=query
                )
                
                # 創建實體節點
                entities = extracted_data.get("entities", [])
                for entity in entities:
                    session.run(
                        """
                        MERGE (e:Entity {name: $name})
                        SET e.type = $type, 
                            e.description = $description,
                            e.source_url = $source_url,
                            e.updated_at = datetime()
                        WITH e
                        MATCH (q:Query {text: $query_text})
                        MERGE (q)-[:FOUND]->(e)
                        """,
                        name=entity.get("name"),
                        type=entity.get("type"),
                        description=entity.get("description"),
                        source_url=entity.get("source_url"),
                        query_text=query
                    )
                
                # 創建關係
                relationships = extracted_data.get("relationships", [])
                for rel in relationships:
                    session.run(
                        """
                        MATCH (source:Entity {name: $source})
                        MATCH (target:Entity {name: $target})
                        MERGE (source)-[r:RELATES_TO {type: $relation}]->(target)
                        SET r.description = $description,
                            r.updated_at = datetime()
                        """,
                        source=rel.get("source"),
                        target=rel.get("target"),
                        relation=rel.get("relation"),
                        description=rel.get("description")
                    )
            
            driver.close()
            
            logger.info(f"✅ 儲存到 Neo4j: {len(entities)} 實體, {len(relationships)} 關係")
            
            return {
                "success": True,
                "entities_stored": len(entities),
                "relationships_stored": len(relationships)
            }
            
        except Exception as e:
            logger.error(f"❌ Neo4j 儲存失敗: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _generate_final_report(self, query: str, scraped_data: Dict, extracted_data: Dict) -> str:
        """
        基於爬取和萃取的資料生成最終報告
        """
        summary = extracted_data.get("overall_summary", "")
        entities = extracted_data.get("entities", [])
        
        prompt = f"""基於以下資訊，生成一份關於「{query}」的詳細研究報告。

整體摘要:
{summary}

發現的關鍵實體:
{', '.join([e.get('name', '') for e in entities[:10]])}

請生成一份結構化報告，包含：
1. 執行摘要（2-3 段）
2. 主要發現
3. 詳細分析
4. 結論和建議

報告：
"""
        
        try:
            report = self._call_ollama(prompt)
            return report
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return f"基於收集的資料，關於{query}的主要發現如下：\n\n{summary}"