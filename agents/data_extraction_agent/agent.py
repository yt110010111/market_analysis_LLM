import os
import json
import logging
from typing import Dict, List, Any
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataExtractionAgent:
    """
    資料萃取代理：使用 Ollama 分析爬取的內容，提取關鍵資訊和關聯
    """
    
    def __init__(self):
        self.ollama_endpoint = os.getenv("OLLAMA_ENDPOINT", "http://ollama:11434")
        self.model_name = os.getenv("MODEL_NAME", "llama3.2:3b")
        
    def extract_and_analyze(self, scraped_data: Dict[str, Any], query: str = "") -> Dict[str, Any]:
        """
        分析爬取的資料，提取關鍵資訊和實體關聯
        
        Args:
            scraped_data: web_scraping_agent 的輸出
            query: 原始查詢
            
        Returns:
            提取的實體、關係和摘要
        """
        logger.info(f"🔬 開始分析 {len(scraped_data.get('results', []))} 個文檔")
        
        results = scraped_data.get('results', [])
        if not results:
            logger.warning("⚠️ 沒有可分析的資料")
            return {
                "query": query,
                "entities": [],
                "relationships": [],
                "summary": "無資料可分析",
                "status": "no_data"
            }
        
        # 分析每個文檔
        all_entities = []
        all_relationships = []
        document_summaries = []
        
        for idx, doc in enumerate(results):
            if not doc.get("success"):
                continue
                
            logger.info(f"📄 分析文檔 {idx+1}/{len(results)}: {doc.get('title', 'Untitled')}")
            
            # 提取實體和關係
            extraction = self._extract_entities_and_relationships(doc, query)
            
            all_entities.extend(extraction.get("entities", []))
            all_relationships.extend(extraction.get("relationships", []))
            document_summaries.append({
                "url": doc.get("url"),
                "title": doc.get("title"),
                "summary": extraction.get("summary", "")
            })
        
        # 去重實體（基於名稱）
        unique_entities = self._deduplicate_entities(all_entities)
        
        # 生成整體摘要
        overall_summary = self._generate_overall_summary(document_summaries, query)
        
        logger.info(f"✅ 分析完成: 實體 {len(unique_entities)} 個, 關係 {len(all_relationships)} 個")
        
        return {
            "query": query,
            "total_documents": len(results),
            "entities": unique_entities,
            "relationships": all_relationships,
            "document_summaries": document_summaries,
            "overall_summary": overall_summary,
            "status": "success"
        }
    
    def _extract_entities_and_relationships(self, doc: Dict[str, Any], query: str) -> Dict[str, Any]:
        """
        從單個文檔中提取實體和關係
        """
        content = doc.get("full_text", "") or doc.get("content", "")
        title = doc.get("title", "")
        
        # 截斷過長的內容
        if len(content) > 3000:
            content = content[:3000]
        
        prompt = f"""分析以下文本，提取關鍵實體和它們之間的關係。

查詢主題: {query}
文檔標題: {title}

文檔內容:
{content}

請以 JSON 格式輸出，包含：
1. entities: 實體列表，每個實體包含 name (名稱), type (類型: 人物/組織/產品/概念/地點), description (簡短描述)
2. relationships: 關係列表，每個關係包含 source (來源實體), target (目標實體), relation (關係類型), description (描述)
3. summary: 這篇文檔的簡短摘要（2-3句話）

只返回 JSON，不要其他文字：
{{
  "entities": [
    {{"name": "實體名稱", "type": "類型", "description": "描述"}}
  ],
  "relationships": [
    {{"source": "來源", "target": "目標", "relation": "關係", "description": "描述"}}
  ],
  "summary": "摘要文字"
}}
"""
        
        try:
            response = self._call_ollama(prompt)
            
            # 解析 JSON
            # 清理可能的 markdown 代碼塊
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            extracted = json.loads(response)
            
            # 為實體添加來源
            for entity in extracted.get("entities", []):
                entity["source_url"] = doc.get("url")
                entity["source_title"] = title
            
            return extracted
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 解析失敗: {e}")
            logger.debug(f"原始回應: {response[:500]}")
            
            # 返回空結果
            return {
                "entities": [],
                "relationships": [],
                "summary": "無法解析文檔內容"
            }
        except Exception as e:
            logger.error(f"❌ 提取失敗: {e}")
            return {
                "entities": [],
                "relationships": [],
                "summary": "提取過程發生錯誤"
            }
    
    def _deduplicate_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        去除重複的實體（基於名稱）
        """
        seen = {}
        for entity in entities:
            name = entity.get("name", "").lower()
            if name and name not in seen:
                seen[name] = entity
            elif name:
                # 合併來源資訊
                if "sources" not in seen[name]:
                    seen[name]["sources"] = [seen[name].get("source_url")]
                if entity.get("source_url") not in seen[name]["sources"]:
                    seen[name]["sources"].append(entity.get("source_url"))
        
        return list(seen.values())
    
    def _generate_overall_summary(self, document_summaries: List[Dict[str, Any]], query: str) -> str:
        """
        生成所有文檔的整體摘要
        """
        if not document_summaries:
            return "無可用資料"
        
        summaries_text = "\n\n".join([
            f"來源 {idx+1} ({doc['title']}): {doc['summary']}"
            for idx, doc in enumerate(document_summaries)
        ])
        
        prompt = f"""基於以下多個來源的摘要，生成一個整合性的總結，回答查詢主題。

查詢主題: {query}

各來源摘要:
{summaries_text}

請提供一個清晰、連貫的總結（3-5 句話），整合所有來源的關鍵資訊：
"""
        
        try:
            overall_summary = self._call_ollama(prompt)
            return overall_summary.strip()
        except Exception as e:
            logger.error(f"❌ 生成總結失敗: {e}")
            return "無法生成整體摘要"
    
    def _call_ollama(self, prompt: str, max_tokens: int = 2000) -> str:
        """
        呼叫 Ollama API
        """
        try:
            response = requests.post(
                f"{self.ollama_endpoint}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,  # 較低的溫度以獲得更一致的輸出
                        "num_predict": max_tokens
                    }
                },
                timeout=60
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            logger.error(f"❌ Ollama 呼叫失敗: {e}")
            raise