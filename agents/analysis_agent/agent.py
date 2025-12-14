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
        self.neo4j_url = os.getenv("NEO4J_URL", "bolt://neo4j:7687")
        self.neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD", "password123")
        self.web_scraping_agent_url = os.getenv("WEB_SCRAPING_AGENT_URL", "http://web_scraping_agent:8003")
        self.data_extraction_agent_url = os.getenv("DATA_EXTRACTION_AGENT_URL", "http://data_extraction_agent:8004")
        
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
        
        logger.info(f"🧠 開始分析搜尋結果: query='{query}', results_count={len(results)}")
        
        # 步驟 1: 檢查 Neo4j 資料庫中的相關資料
        db_coverage = self._check_database_coverage(query, results)
        
        # 步驟 2: 根據資料庫覆蓋度決定行動
        if db_coverage["sufficient"]:
            logger.info(f"✅ 判斷: 資料充足，直接生成報告")
            logger.info(f"   - 資料庫實體數: {db_coverage.get('db_entities_count', 0)}")
            logger.info(f"   - 搜尋結果數: {len(results)}")
            return {
                "action": "generate_report",
                "query": query,
                "search_results": results,
                "db_data": db_coverage["data"]
            }
        else:
            logger.info(f"❌ 判斷: 資料不足，需要爬蟲收集")
            logger.info(f"   - 資料庫實體數: {db_coverage.get('db_entities_count', 0)}")
            logger.info(f"   - 搜尋結果數: {len(results)}")
            logger.info(f"   - 缺少主題: {db_coverage.get('missing_topics', [])}")
            
            urls_to_scrape = self._identify_scraping_targets(results)
            logger.info(f"   - 識別到 {len(urls_to_scrape)} 個爬取目標")
            
            return {
                "action": "scrape_and_extract",
                "query": query,
                "search_results": results,
                "missing_topics": db_coverage["missing_topics"],
                "urls_to_scrape": urls_to_scrape
            }
    
    def _check_database_coverage(self, query: str, search_results: List[Dict]) -> Dict[str, Any]:
        """
        檢查 Neo4j 資料庫中是否有足夠的相關資料
        
        策略：
        1. 查詢 Neo4j 中相關的實體
        2. 如果資料庫有足夠實體，使用 Ollama 判斷品質
        3. 如果資料庫為空或實體太少，直接判定不足
        """
        logger.info(f"📊 檢查資料庫覆蓋度...")
        
        try:
            # 步驟 1: 查詢 Neo4j 中的相關實體
            db_entities = self._query_neo4j_entities(query)
            db_entities_count = len(db_entities)
            
            logger.info(f"   📁 資料庫中找到 {db_entities_count} 個相關實體")
            
            # 步驟 2: 基本判斷 - 如果資料庫幾乎沒有資料，直接判定不足
            if db_entities_count < 6:
                logger.info(f"   ⚠️ 資料庫實體不足 3 個，判定資料不足")
                return {
                    "sufficient": False,
                    "missing_topics": ["general", query],
                    "data": [],
                    "db_entities_count": db_entities_count,
                    "reason": "資料庫實體數量不足"
                }
            
            # 步驟 3: 如果有一定數量的實體，使用 Ollama 判斷品質
            logger.info(f"   🤖 呼叫 Ollama 評估資料品質...")
            
            prompt = f"""你是一個資料分析專家。請評估以下資料是否足夠回答使用者的問題。

使用者問題: {query}

資料庫中的實體 ({db_entities_count} 個):
{json.dumps(db_entities[:10], ensure_ascii=False, indent=2)}

最新搜尋結果 ({len(search_results)} 個):
{json.dumps([{{
    'title': r.get('title', ''),
    'snippet': r.get('snippet', '')[:100]
}} for r in search_results[:3]], ensure_ascii=False, indent=2)}

評估標準:
1. 資料庫中的實體是否與問題直接相關？
2. 資料是否足夠新？(考慮搜尋結果的日期)
3. 資料是否涵蓋問題的各個主要方面？

請以 JSON 格式回答（只返回 JSON，不要其他文字）:
{{
    "sufficient": true/false,
    "missing_topics": ["缺少的主題1", "缺少的主題2"],
    "reasoning": "判斷理由"
}}
"""
            
            response = self._call_ollama(prompt)
            logger.info(f"   📝 Ollama 原始回應: {response[:200]}...")
            
            # 解析 LLM 回應
            try:
                # 清理回應（移除可能的 markdown）
                clean_response = response.strip()
                if clean_response.startswith("```json"):
                    clean_response = clean_response[7:]
                if clean_response.startswith("```"):
                    clean_response = clean_response[3:]
                if clean_response.endswith("```"):
                    clean_response = clean_response[:-3]
                clean_response = clean_response.strip()
                
                decision = json.loads(clean_response)
                
                logger.info(f"   ✅ Ollama 判斷結果:")
                logger.info(f"      - sufficient: {decision.get('sufficient', False)}")
                logger.info(f"      - reasoning: {decision.get('reasoning', 'N/A')}")
                logger.info(f"      - missing_topics: {decision.get('missing_topics', [])}")
                
            except json.JSONDecodeError as e:
                logger.error(f"   ❌ JSON 解析失敗: {e}")
                logger.error(f"   原始回應: {response}")
                
                # 解析失敗，使用保守策略：假設資料不足
                decision = {
                    "sufficient": False,
                    "missing_topics": [query],
                    "reasoning": "無法解析 LLM 回應，採用保守策略"
                }
            
            return {
                "sufficient": decision.get("sufficient", False),
                "missing_topics": decision.get("missing_topics", []),
                "data": db_entities if decision.get("sufficient") else [],
                "db_entities_count": db_entities_count,
                "reasoning": decision.get("reasoning", ""),
                "llm_response": response[:500]  # 保留前500字元供除錯
            }
            
        except Exception as e:
            logger.error(f"❌ 檢查資料庫覆蓋度時發生錯誤: {e}", exc_info=True)
            
            # 發生錯誤時，假設需要更多資料
            return {
                "sufficient": False,
                "missing_topics": ["general"],
                "data": [],
                "db_entities_count": 0,
                "error": str(e)
            }
    
    def _query_neo4j_entities(self, query: str) -> List[Dict[str, Any]]:
        """
        查詢 Neo4j 中與查詢相關的實體
        """
        try:
            from neo4j import GraphDatabase
            
            driver = GraphDatabase.driver(
                self.neo4j_url,
                auth=(self.neo4j_user, self.neo4j_password)
            )
            
            entities = []
            
            with driver.session() as session:
                # 查詢與 query 相關的實體
                result = session.run("""
                    MATCH (q:Query)-[:FOUND]->(e:Entity)
                    WHERE q.text CONTAINS $query_keyword
                    RETURN e.name as name, e.type as type, 
                           e.description as description,
                           e.source_url as source_url
                    LIMIT 20
                """, query_keyword=query.split()[0])  # 使用查詢的第一個關鍵字
                
                for record in result:
                    entities.append({
                        "name": record["name"],
                        "type": record["type"],
                        "description": record["description"],
                        "source_url": record["source_url"]
                    })
            
            driver.close()
            
            logger.info(f"   🔍 Neo4j 查詢完成，找到 {len(entities)} 個實體")
            
            return entities
            
        except Exception as e:
            logger.warning(f"   ⚠️ Neo4j 查詢失敗: {e}")
            return []
    
    def _identify_scraping_targets(self, search_results: List[Dict]) -> List[str]:
        """
        從搜尋結果中識別需要爬取的 URL
        優先選擇真實可訪問的 URL
        """
        urls = []
        for result in search_results[:10]:
            url = result.get("url")
            # 過濾掉模擬 URL 和無效 URL
            if url and url.startswith("http") and "example.com" not in url:
                urls.append(url)
        
        # 如果沒有找到真實 URL，使用預設的金融資料來源
        if not urls:
            query = search_results[0].get("title", "") if search_results else "stock"
            logger.warning(f"⚠️ 沒有找到真實 URL，使用預設來源")
            
            # 根據查詢添加相關的金融網站
            if any(keyword in query.lower() for keyword in ["stock", "financial", "sofi", "investment"]):
                urls = [
                    "https://finance.yahoo.com",
                    "https://www.marketwatch.com",
                    "https://www.investing.com",
                    "https://seekingalpha.com",
                    "https://www.fool.com"
                ]
        
        logger.info(f"📋 識別到 {len(urls)} 個爬取目標")
        if urls:
            for i, url in enumerate(urls[:3], 1):
                logger.info(f"   {i}. {url}")
        
        return urls[:5]
    
    def _call_ollama(self, prompt: str) -> str:
        """
        呼叫 Ollama API
        """
        try:
            logger.debug(f"🤖 呼叫 Ollama: {prompt[:100]}...")
            
            response = requests.post(
                f"{self.ollama_endpoint}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # 降低溫度以獲得更一致的 JSON
                        "num_predict": 500
                    }
                },
                timeout=100
            )
            response.raise_for_status()
            result = response.json().get("response", "")
            
            logger.debug(f"✅ Ollama 回應長度: {len(result)} 字元")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ollama 呼叫失敗: {e}")
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
        
        logger.info(f"📝 生成報告: {query}")
        
        prompt = f"""基於以下資料，生成一份詳細報告回答這個問題：

問題: {query}

資料來源:
{json.dumps(search_results[:5], ensure_ascii=False, indent=2)}

請生成一份結構化的報告，包含：
1. 摘要（2-3句話）
2. 主要發現（3-5點）
3. 詳細分析（2-3段）
4. 結論

報告：
"""
        
        report = self._call_ollama(prompt)
        
        logger.info(f"✅ 報告生成完成，長度: {len(report)} 字元")
        
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
        
        logger.info(f"🕷️ 開始爬蟲工作流: {len(urls)} 個 URL")
        
        # 步驟 1: 呼叫 web_scraping_agent
        try:
            logger.info(f"   📡 呼叫 web_scraping_agent...")
            scraping_response = requests.post(
                f"{self.web_scraping_agent_url}/scrape",
                json={
                    "urls": urls,
                    "query": query,
                    "dynamic_search": True
                },
                timeout=90
            )
            scraping_response.raise_for_status()
            scraped_data = scraping_response.json()
            logger.info(f"   ✅ 爬蟲完成: {scraped_data.get('successful', 0)} 成功, {scraped_data.get('failed', 0)} 失敗")
        except Exception as e:
            logger.error(f"   ❌ web_scraping_agent 錯誤: {e}")
            scraped_data = {"error": str(e), "results": []}
        
        # 步驟 2: 呼叫 data_extraction_agent
        try:
            logger.info(f"   📡 呼叫 data_extraction_agent...")
            extraction_response = requests.post(
                f"{self.data_extraction_agent_url}/extract",
                json={"data": scraped_data, "query": query},
                timeout=90
            )
            extraction_response.raise_for_status()
            extracted_data = extraction_response.json()
            logger.info(f"   ✅ 萃取完成: {len(extracted_data.get('entities', []))} 實體, {len(extracted_data.get('relationships', []))} 關係")
        except Exception as e:
            logger.error(f"   ❌ data_extraction_agent 錯誤: {e}")
            extracted_data = {"error": str(e), "entities": [], "relationships": []}
        
        # 步驟 3: 儲存到 Neo4j
        logger.info(f"   💾 儲存到 Neo4j...")
        neo4j_result = self._store_to_neo4j(extracted_data, query)
        
        # 步驟 4: 生成最終報告
        logger.info(f"   📝 生成最終報告...")
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
            
            driver = GraphDatabase.driver(
                self.neo4j_url,
                auth=(self.neo4j_user, self.neo4j_password)
            )
            
            with driver.session() as session:
                # 創建查詢節點
                session.run(
                    "MERGE (q:Query {text: $query_text}) SET q.timestamp = datetime() RETURN q",
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
            
            logger.info(f"   ✅ Neo4j 儲存成功: {len(entities)} 實體, {len(relationships)} 關係")
            
            return {
                "success": True,
                "entities_stored": len(entities),
                "relationships_stored": len(relationships)
            }
            
        except Exception as e:
            logger.error(f"   ❌ Neo4j 儲存失敗: {e}")
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