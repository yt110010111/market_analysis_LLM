#agents/analysis_agent/report_generator.py
import os
import json
import logging
from typing import Dict, List, Any
import requests
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    報告生成器：從 Neo4j 查詢相關實體並生成詳細報告
    """
    
    def __init__(self):
        self.ollama_endpoint = os.getenv("OLLAMA_ENDPOINT", "http://ollama:11434")
        self.model_name = os.getenv("MODEL_NAME", "llama3.2:3b")
        self.neo4j_url = os.getenv("NEO4J_URL", "bolt://neo4j:7687")
        self.neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD", "password123")
    
    def generate_comprehensive_report(
        self, 
        query: str, 
        search_results: List[Dict[str, Any]] = None,
        use_neo4j: bool = True
    ) -> Dict[str, Any]:
        """
        生成綜合報告
        
        Args:
            query: 使用者查詢
            search_results: 搜尋結果（可選）
            use_neo4j: 是否從 Neo4j 查詢額外資料
            
        Returns:
            包含報告和統計資訊的字典
        """
        logger.info(f"📝 開始生成報告: {query}")
        
        # 步驟 1: 從 Neo4j 獲取相關實體和關係
        neo4j_data = {}
        if use_neo4j:
            logger.info(f"   🔍 從 Neo4j 查詢相關資料...")
            neo4j_data = self._query_neo4j_knowledge(query)
            logger.info(f"   ✅ 找到 {neo4j_data.get('entity_count', 0)} 個實體, {neo4j_data.get('relationship_count', 0)} 個關係")
        
        # 步驟 2: 整合所有資料來源
        all_sources = self._integrate_data_sources(query, search_results, neo4j_data)
        
        # 步驟 3: 生成報告
        logger.info(f"   🤖 呼叫 Ollama 生成報告...")
        report = self._generate_report_with_llm(query, all_sources)
        
        # 步驟 4: 返回結果
        result = {
            "query": query,
            "report": report,
            "sources": {
                "search_results_count": len(search_results) if search_results else 0,
                "neo4j_entities": neo4j_data.get("entity_count", 0),
                "neo4j_relationships": neo4j_data.get("relationship_count", 0)
            },
            "generated_at": datetime.utcnow().isoformat() + "Z"
        }
        
        logger.info(f"   ✅ 報告生成完成，長度: {len(report)} 字元")
        
        return result
    
    def _query_neo4j_knowledge(self, query: str) -> Dict[str, Any]:
        """
        從 Neo4j 查詢與 query 相關的知識圖譜
        
        Returns:
            包含實體、關係和統計資訊的字典
        """
        try:
            from neo4j import GraphDatabase
            
            driver = GraphDatabase.driver(
                self.neo4j_url,
                auth=(self.neo4j_user, self.neo4j_password)
            )
            
            # 提取查詢關鍵詞
            keywords = self._extract_keywords(query)
            logger.info(f"      查詢關鍵詞: {keywords}")
            
            entities = []
            relationships = []
            
            with driver.session() as session:
                # 查詢 1: 直接匹配的實體
                for keyword in keywords:
                    result = session.run("""
                        MATCH (e:Entity)
                        WHERE e.name CONTAINS $keyword 
                           OR e.description CONTAINS $keyword
                           OR e.type CONTAINS $keyword
                        RETURN DISTINCT e.name as name, 
                               e.type as type,
                               e.description as description,
                               e.source_url as source_url
                        LIMIT 10
                    """, keyword=keyword)
                    
                    for record in result:
                        entity = {
                            "name": record["name"],
                            "type": record["type"],
                            "description": record["description"],
                            "source_url": record["source_url"]
                        }
                        if entity not in entities:
                            entities.append(entity)
                
                # 查詢 2: 通過 Query 節點找到的實體
                for keyword in keywords:
                    result = session.run("""
                        MATCH (q:Query)-[:FOUND]->(e:Entity)
                        WHERE q.text CONTAINS $keyword
                        RETURN DISTINCT e.name as name,
                               e.type as type,
                               e.description as description,
                               e.source_url as source_url
                        LIMIT 10
                    """, keyword=keyword)
                    
                    for record in result:
                        entity = {
                            "name": record["name"],
                            "type": record["type"],
                            "description": record["description"],
                            "source_url": record["source_url"]
                        }
                        if entity not in entities:
                            entities.append(entity)
                
                # 查詢 3: 找出實體之間的關係
                if entities:
                    entity_names = [e["name"] for e in entities[:20]]  # 限制數量
                    
                    result = session.run("""
                        MATCH (e1:Entity)-[r:RELATES_TO]->(e2:Entity)
                        WHERE e1.name IN $names AND e2.name IN $names
                        RETURN e1.name as source,
                               e2.name as target,
                               r.type as relation_type,
                               r.description as description
                        LIMIT 20
                    """, names=entity_names)
                    
                    for record in result:
                        relationships.append({
                            "source": record["source"],
                            "target": record["target"],
                            "relation": record["relation_type"],
                            "description": record["description"]
                        })
            
            driver.close()
            
            logger.info(f"      ✅ Neo4j 查詢完成")
            
            return {
                "entities": entities,
                "relationships": relationships,
                "entity_count": len(entities),
                "relationship_count": len(relationships),
                "keywords_used": keywords
            }
            
        except Exception as e:
            logger.warning(f"      ⚠️ Neo4j 查詢失敗: {e}")
            return {
                "entities": [],
                "relationships": [],
                "entity_count": 0,
                "relationship_count": 0,
                "error": str(e)
            }
    
    def _extract_keywords(self, query: str) -> List[str]:
        """
        從查詢中提取關鍵詞
        """
        # 簡單的關鍵詞提取（可以改進為使用 NLP）
        # 移除常見停用詞
        stopwords = {'的', '是', '和', '與', '或', '在', '了', '有', '為', '等'}
        
        # 分割並過濾
        words = query.split()
        keywords = [w for w in words if w not in stopwords and len(w) > 1]
        
        # 如果沒有關鍵詞，使用整個查詢
        if not keywords:
            keywords = [query]
        
        return keywords[:5]  # 最多 5 個關鍵詞
    
    def _integrate_data_sources(
        self, 
        query: str,
        search_results: List[Dict[str, Any]],
        neo4j_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        整合來自不同來源的資料
        """
        integrated = {
            "query": query,
            "search_results": search_results[:5] if search_results else [],  # 限制數量
            "neo4j_entities": neo4j_data.get("entities", [])[:10],  # 最多 10 個實體
            "neo4j_relationships": neo4j_data.get("relationships", [])[:10],  # 最多 10 個關係
        }
        
        return integrated
    
    def _generate_report_with_llm(self, query: str, sources: Dict[str, Any]) -> str:
        """
        使用 LLM 生成詳細報告
        """
        # 構建 prompt
        prompt = self._build_report_prompt(query, sources)
        
        # 呼叫 Ollama
        try:
            report = self._call_ollama(prompt)
            return report
        except Exception as e:
            logger.error(f"   ❌ LLM 生成報告失敗: {e}")
            # 返回備用報告
            return self._generate_fallback_report(query, sources)
    
    def _build_report_prompt(self, query: str, sources: Dict[str, Any]) -> str:
        """
        構建用於生成報告的 prompt
        """
        # 準備實體資訊
        entities_info = ""
        if sources.get("neo4j_entities"):
            entities_info = "知識庫中的相關實體:\n"
            for i, entity in enumerate(sources["neo4j_entities"][:10], 1):
                entities_info += f"{i}. {entity['name']} ({entity['type']}): {entity.get('description', 'N/A')[:100]}\n"
        
        # 準備關係資訊
        relationships_info = ""
        if sources.get("neo4j_relationships"):
            relationships_info = "\n實體之間的關係:\n"
            for i, rel in enumerate(sources["neo4j_relationships"][:5], 1):
                relationships_info += f"{i}. {rel['source']} --[{rel['relation']}]--> {rel['target']}\n"
        
        # 準備搜尋結果
        search_info = ""
        if sources.get("search_results"):
            search_info = "\n最新搜尋結果:\n"
            for i, result in enumerate(sources["search_results"][:3], 1):
                search_info += f"{i}. {result.get('title', 'N/A')}\n"
                search_info += f"   摘要: {result.get('snippet', 'N/A')[:150]}\n"
        
        # 構建完整 prompt
        prompt = f"""你是一位專業的研究員。請基於以下資訊，用繁體中文(zh-tw)撰寫一份關於「{query}」的詳細研究報告。

{entities_info}
{relationships_info}
{search_info}

請撰寫一份結構完整的研究報告，包含以下部分：

1. **執行摘要** (2-3 段)
   - 簡要概述主題
   - 突出最重要的發現

2. **背景資訊**
   - 相關背景和上下文
   - 主要參與者或實體

3. **主要發現** (3-5 點)
   - 基於資料的關鍵洞察
   - 重要趨勢或模式

4. **詳細分析** (2-3 段)
   - 深入分析實體之間的關係
   - 解釋重要性和影響

5. **結論與總結**
   - 總結關鍵要點
   - 明確的回覆使用者所的問題

請確保報告：
- 基於提供的資料
- 客觀且有依據
- 結構清晰
- 使用專業語言

報告：
"""
        
        return prompt
    
    def _call_ollama(self, prompt: str, max_tokens: int = 2000) -> str:
        """
        呼叫 Ollama API 生成文本
        """
        try:
            response = requests.post(
                f"{self.ollama_endpoint}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,  # 中等創造性
                        "num_predict": max_tokens,
                        "top_p": 0.9
                    }
                },
                timeout=60  # 增加超時時間
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            logger.error(f"   ❌ Ollama API 錯誤: {e}")
            raise
    
    def _generate_fallback_report(self, query: str, sources: Dict[str, Any]) -> str:
        """
        當 LLM 失敗時，生成簡單的備用報告
        """
        report = f"# {query} - 研究報告\n\n"
        report += f"生成時間: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
        
        # 實體摘要
        entities = sources.get("neo4j_entities", [])
        if entities:
            report += "## 相關實體\n\n"
            for entity in entities[:5]:
                report += f"- **{entity['name']}** ({entity['type']})\n"
                if entity.get('description'):
                    report += f"  {entity['description'][:100]}...\n"
            report += "\n"
        
        # 關係摘要
        relationships = sources.get("neo4j_relationships", [])
        if relationships:
            report += "## 實體關係\n\n"
            for rel in relationships[:5]:
                report += f"- {rel['source']} → {rel['relation']} → {rel['target']}\n"
            report += "\n"
        
        # 搜尋結果
        search_results = sources.get("search_results", [])
        if search_results:
            report += "## 相關資料來源\n\n"
            for i, result in enumerate(search_results[:5], 1):
                report += f"{i}. [{result.get('title', 'N/A')}]({result.get('url', '#')})\n"
            report += "\n"
        
        report += "## 結論\n\n"
        report += f"基於現有資料，找到 {len(entities)} 個相關實體和 {len(relationships)} 個關係。"
        report += "建議進行進一步研究以獲得更深入的洞察。\n"
        
        return report