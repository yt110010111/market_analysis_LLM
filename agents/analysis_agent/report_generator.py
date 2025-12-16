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
        
        # 🔧 可配置的查詢限制
        self.max_entities_per_keyword = int(os.getenv("MAX_ENTITIES_PER_KEYWORD", "50"))  # 提高到 50
        self.max_total_entities = int(os.getenv("MAX_TOTAL_ENTITIES", "100"))  # 提高到 100
        self.max_relationships = int(os.getenv("MAX_RELATIONSHIPS", "100"))  # 提高到 100
    
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
        🔧 優化：從 Neo4j 查詢與 query 相關的知識圖譜，移除不必要的限制
        
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
            entity_names_set = set()  # 用於去重
            relationships = []
            
            with driver.session() as session:
                # 🔧 查詢 1: 直接匹配的實體（提高限制）
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
                        LIMIT $limit
                    """, keyword=keyword, limit=self.max_entities_per_keyword)
                    
                    for record in result:
                        name = record["name"]
                        if name not in entity_names_set:
                            entity_names_set.add(name)
                            entities.append({
                                "name": name,
                                "type": record["type"],
                                "description": record["description"],
                                "source_url": record["source_url"]
                            })
                
                # 🔧 查詢 2: 通過 Query 節點找到的實體（提高限制）
                for keyword in keywords:
                    result = session.run("""
                        MATCH (q:Query)-[:FOUND]->(e:Entity)
                        WHERE q.text CONTAINS $keyword
                        RETURN DISTINCT e.name as name,
                               e.type as type,
                               e.description as description,
                               e.source_url as source_url
                        LIMIT $limit
                    """, keyword=keyword, limit=self.max_entities_per_keyword)
                    
                    for record in result:
                        name = record["name"]
                        if name not in entity_names_set:
                            entity_names_set.add(name)
                            entities.append({
                                "name": name,
                                "type": record["type"],
                                "description": record["description"],
                                "source_url": record["source_url"]
                            })
                
                # 🔧 截斷到最大實體數
                if len(entities) > self.max_total_entities:
                    logger.info(f"      ⚠️ 實體數量超過限制，截斷至 {self.max_total_entities}")
                    entities = entities[:self.max_total_entities]
                
                # 🔧 查詢 3: 找出實體之間的關係（使用所有實體，不限制為 20）
                if entities:
                    entity_names = list(entity_names_set)
                    
                    # 分批查詢以避免查詢過大
                    batch_size = 50
                    for i in range(0, len(entity_names), batch_size):
                        batch = entity_names[i:i+batch_size]
                        
                        result = session.run("""
                            MATCH (e1:Entity)-[r:RELATES_TO]->(e2:Entity)
                            WHERE e1.name IN $names AND e2.name IN $names
                            RETURN e1.name as source,
                                   e2.name as target,
                                   r.type as relation_type,
                                   r.description as description
                            LIMIT $limit
                        """, names=batch, limit=self.max_relationships)
                        
                        for record in result:
                            relationships.append({
                                "source": record["source"],
                                "target": record["target"],
                                "relation": record["relation_type"],
                                "description": record["description"]
                            })
                        
                        # 如果已經達到最大關係數，停止查詢
                        if len(relationships) >= self.max_relationships:
                            logger.info(f"      ⚠️ 關係數量達到限制 {self.max_relationships}")
                            break
            
            driver.close()
            
            logger.info(f"      ✅ Neo4j 查詢完成: {len(entities)} 實體, {len(relationships)} 關係")
            
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
        stopwords = {'的', '是', '和', '與', '或', '在', '了', '有', '為', '等', 
                     'the', 'is', 'and', 'or', 'in', 'at', 'to', 'a', 'an'}
        
        # 分割並過濾
        words = query.split()
        keywords = [w for w in words if w.lower() not in stopwords and len(w) > 1]
        
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
        🔧 優化：整合來自不同來源的資料，不再限制數量
        """
        integrated = {
            "query": query,
            "search_results": search_results[:10] if search_results else [],  # 稍微提高搜尋結果
            "neo4j_entities": neo4j_data.get("entities", []),  # 🔧 不限制
            "neo4j_relationships": neo4j_data.get("relationships", []),  # 🔧 不限制
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
        🔧 優化：構建用於生成報告的 prompt，顯示更多實體和關係
        """
        # 準備實體資訊（顯示更多）
        entities_info = ""
        entities = sources.get("neo4j_entities", [])
        if entities:
            entities_info = f"知識庫中的相關實體 (共 {len(entities)} 個):\n"
            # 🔧 顯示更多實體（最多 30 個）
            for i, entity in enumerate(entities[:30], 1):
                entities_info += f"{i}. {entity['name']} ({entity['type']})"
                if entity.get('description'):
                    entities_info += f": {entity.get('description', '')[:150]}"
                entities_info += "\n"
            
            if len(entities) > 30:
                entities_info += f"... 以及其他 {len(entities) - 30} 個實體\n"
        
        # 準備關係資訊（顯示更多）
        relationships_info = ""
        relationships = sources.get("neo4j_relationships", [])
        if relationships:
            relationships_info = f"\n實體之間的關係 (共 {len(relationships)} 個):\n"
            # 🔧 顯示更多關係（最多 20 個）
            for i, rel in enumerate(relationships[:20], 1):
                relationships_info += f"{i}. {rel['source']} --[{rel['relation']}]--> {rel['target']}"
                if rel.get('description'):
                    relationships_info += f" ({rel['description'][:100]})"
                relationships_info += "\n"
            
            if len(relationships) > 20:
                relationships_info += f"... 以及其他 {len(relationships) - 20} 個關係\n"
        
        # 準備搜尋結果
        search_info = ""
        search_results = sources.get("search_results", [])
        if search_results:
            search_info = "\n最新搜尋結果:\n"
            for i, result in enumerate(search_results[:5], 1):
                search_info += f"{i}. {result.get('title', 'N/A')}\n"
                search_info += f"   摘要: {result.get('snippet', 'N/A')[:200]}\n"
        
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
- 充分利用提供的所有 {len(entities)} 個實體和 {len(relationships)} 個關係
- 基於提供的資料
- 客觀且有依據
- 結構清晰
- 使用專業語言

報告：
"""
        
        return prompt
    
    def generate_report_from_extraction(
        self,
        query: str,
        entities: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        search_results: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        🔧 優化：直接使用萃取的實體和關係生成報告，不限制數量
        避免萃取完成後立即查詢 Neo4j 的時間差問題
        """
        logger.info(f"📝 使用萃取結果生成報告: {query}")
        logger.info(f"   📊 實體: {len(entities)}, 關係: {len(relationships)}")
        
        # 構建資料源（🔧 不限制數量）
        sources = {
            "query": query,
            "search_results": search_results[:10] if search_results else [],
            "neo4j_entities": entities,  # 🔧 使用所有實體
            "neo4j_relationships": relationships  # 🔧 使用所有關係
        }
        
        # 生成報告
        logger.info(f"   🤖 呼叫 Ollama 生成報告...")
        report = self._generate_report_with_llm(query, sources)
        
        result = {
            "query": query,
            "report": report,
            "sources": {
                "search_results_count": len(search_results) if search_results else 0,
                "neo4j_entities": len(entities),
                "neo4j_relationships": len(relationships)
            },
            "generated_at": datetime.utcnow().isoformat() + "Z"
        }
        
        logger.info(f"   ✅ 報告生成完成，長度: {len(report)} 字元")
        
        return result
    
    def _call_ollama(self, prompt: str, max_tokens: int = 3000) -> str:
        """
        🔧 優化：增加 max_tokens 以支援更長的報告
        """
        try:
            response = requests.post(
                f"{self.ollama_endpoint}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": max_tokens,  # 🔧 提高到 3000
                        "top_p": 0.9
                    }
                },
                timeout=120  # 🔧 增加超時時間到 2 分鐘
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
            report += f"## 相關實體 (共 {len(entities)} 個)\n\n"
            for entity in entities[:10]:
                report += f"- **{entity['name']}** ({entity['type']})\n"
                if entity.get('description'):
                    report += f"  {entity['description'][:100]}...\n"
            if len(entities) > 10:
                report += f"\n... 以及其他 {len(entities) - 10} 個實體\n"
            report += "\n"
        
        # 關係摘要
        relationships = sources.get("neo4j_relationships", [])
        if relationships:
            report += f"## 實體關係 (共 {len(relationships)} 個)\n\n"
            for rel in relationships[:10]:
                report += f"- {rel['source']} → {rel['relation']} → {rel['target']}\n"
            if len(relationships) > 10:
                report += f"\n... 以及其他 {len(relationships) - 10} 個關係\n"
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