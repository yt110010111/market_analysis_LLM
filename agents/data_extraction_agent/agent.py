import os
import json
import logging
import re
from typing import Dict, List, Any
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataExtractionAgent:
    """
    極速版本 - 針對慢速 LLM 的激進優化：
    1. 大幅減少文本長度（3000 字符）
    2. 極簡 Prompt（最少 token）
    3. 容錯處理（即使部分失敗也能繼續）
    4. 智能重試機制
    5. 降級策略（LLM 慢時使用規則提取）
    """

    def __init__(self):
        self.ollama_endpoint = os.getenv("OLLAMA_ENDPOINT", "http://ollama:11434")
        self.model_name = os.getenv("MODEL_NAME", "llama3.2:3b")
        self.max_docs = int(os.getenv("MAX_DOCS", "3"))  # 減少到 3 個文檔
        self.max_chars_per_doc = int(os.getenv("MAX_CHARS_PER_DOC", "3000"))  # 大幅減少
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", "30"))  # 降低到 30 秒
        self.max_workers = int(os.getenv("MAX_WORKERS", "2"))  # 減少並行數
        
        # 如果 LLM 超時，使用規則提取
        self.use_fallback = True

    def extract_and_analyze(self, scraped_data: Dict[str, Any], query: str) -> Dict[str, Any]:
        results = scraped_data.get("results", [])
        if not results:
            return {"query": query, "status": "no_data", "entities": [], "summary": "無可分析資料"}

        logger.info(f"🔬 開始處理 {len(results)} 份文件，目標主題: {query}")

        all_entities = []
        all_relationships = []
        document_summaries = []
        
        success_count = 0
        timeout_count = 0

        # 並行處理（減少並行數避免資源競爭）
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_doc = {
                executor.submit(self._process_single_document, doc, query, idx): (doc, idx)
                for idx, doc in enumerate(results[:self.max_docs], start=1)
            }

            for future in as_completed(future_to_doc):
                doc, idx = future_to_doc[future]
                try:
                    result = future.result(timeout=35)  # 每個文檔最多 35 秒
                    
                    if result and result["entities"]:
                        all_entities.extend(result["entities"])
                        all_relationships.extend(result["relationships"])
                        document_summaries.append(result["summary_info"])
                        success_count += 1
                        logger.info(f"✅ 文檔 {idx} 完成: {len(result['entities'])} 個實體")
                    elif result:
                        # LLM 超時，使用 fallback
                        logger.warning(f"⚠️ 文檔 {idx} LLM 超時，使用規則提取")
                        fallback_result = self._fallback_extraction(doc, query, idx)
                        all_entities.extend(fallback_result["entities"])
                        document_summaries.append(fallback_result["summary_info"])
                        timeout_count += 1
                        
                except TimeoutError:
                    logger.error(f"❌ 文檔 {idx} 完全超時")
                    timeout_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ 文檔 {idx} 處理失敗: {e}")
                    timeout_count += 1

        logger.info(f"📊 處理結果: {success_count} 成功, {timeout_count} 超時/失敗")

        # 即使部分失敗，也返回已提取的結果
        if not all_entities:
            # 最後的保底：使用規則提取所有文檔
            logger.warning("⚠️ 所有 LLM 提取失敗，使用規則提取")
            for idx, doc in enumerate(results[:self.max_docs], start=1):
                fallback_result = self._fallback_extraction(doc, query, idx)
                all_entities.extend(fallback_result["entities"])

        if not all_entities:
            return {
                "query": query, 
                "status": "empty", 
                "entities": [], 
                "summary": "處理超時，無法提取資訊"
            }

        # 快速去重
        unique_entities = self._fast_deduplicate_entities(all_entities, query)
        unique_relationships = self._fast_deduplicate_relationships(all_relationships)

        overall_summary = self._generate_fast_summary(document_summaries, query)

        logger.info(f"✅ 最終結果：{len(unique_entities)} 個獨特實體，{len(unique_relationships)} 個關係")

        return {
            "query": query,
            "entities": unique_entities,
            "relationships": unique_relationships,
            "document_summaries": document_summaries,
            "overall_summary": overall_summary,
            "status": "success" if success_count > 0 else "partial",
            "statistics": {
                "total_entities": len(unique_entities),
                "total_relationships": len(unique_relationships),
                "documents_processed": len(document_summaries),
                "success_count": success_count,
                "timeout_count": timeout_count
            }
        }

    def _process_single_document(self, doc: Dict[str, Any], query: str, idx: int) -> Dict[str, Any]:
        """處理單個文檔"""
        text = doc.get("full_text") or doc.get("content", "")
        title = doc.get("title", "")
        url = doc.get("url", "")
        
        # 極簡清理
        cleaned = self._minimal_preprocess(text)
        # 只取前 3000 字符
        sampled = cleaned[:self.max_chars_per_doc]

        if not sampled.strip():
            return None

        # 嘗試 LLM 提取
        try:
            extraction = self._extract_with_llm(sampled, title, url, query)
            
            if not extraction or not extraction.get("entities"):
                # LLM 失敗，使用規則提取
                return self._fallback_extraction(doc, query, idx)
            
            # 寬鬆過濾
            relevant_entities = [
                e for e in extraction.get("entities", []) 
                if self._is_loosely_relevant(e.get("name", ""), e.get("description", ""), e.get("type", ""), query)
            ]

            return {
                "entities": relevant_entities,
                "relationships": extraction.get("relationships", []),
                "summary_info": {
                    "url": url,
                    "title": title,
                    "summary": extraction.get("summary", ""),
                    "entity_count": len(relevant_entities)
                }
            }
        except Exception as e:
            logger.warning(f"LLM 提取異常: {e}，使用規則提取")
            return self._fallback_extraction(doc, query, idx)

    # =========================
    # 極簡文本處理
    # =========================

    def _minimal_preprocess(self, text: str) -> str:
        """極簡清理（最快速度）"""
        if not text:
            return ""
        
        # 只做最基本的清理，不做複雜處理
        lines = [line.strip() for line in text.split("\n") if len(line.strip()) > 20]
        return "\n".join(lines[:100])  # 最多保留 100 行

    def _is_loosely_relevant(self, name: str, desc: str, entity_type: str, query: str) -> bool:
        """寬鬆過濾"""
        if not name or len(name) < 2:
            return False
        
        q_lower = query.lower()
        name_lower = name.lower()
        desc_lower = desc.lower() if desc else ""
        
        # 直接相關
        if q_lower in name_lower or q_lower in desc_lower:
            return True
        
        # 重要類型
        if entity_type in ["公司/組織", "人物", "產品/服務", "競爭對手", "合作夥伴"]:
            return True
        
        # 有描述
        if len(desc_lower) > 10:
            return True
        
        return False

    # =========================
    # 極簡 LLM 調用
    # =========================

    def _extract_with_llm(self, text: str, title: str, url: str, query: str) -> Dict[str, Any]:
        """極簡 Prompt，最小 token 數"""
        # 超短 Prompt
        prompt = f"""提取「{query}」相關實體和關係。

文檔：{title}
{text[:2000]}

JSON格式：
{{"entities":[{{"name":"名稱","type":"類型","description":"說明"}}],"relationships":[{{"source":"A","target":"B","relation":"關係"}}],"summary":"摘要"}}

類型：公司、人物、產品、競爭對手、合作夥伴。"""

        response = self._call_ollama_quick(prompt)
        return self._parse_llm_response(response, query, title, url)

    def _call_ollama_quick(self, prompt: str) -> str:
        """快速 Ollama 調用"""
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0,
                "num_predict": 1000,  # 大幅限制輸出
                "top_k": 10,
                "top_p": 0.5
            }
        }

        try:
            response = requests.post(
                f"{self.ollama_endpoint}/api/generate", 
                json=payload, 
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.Timeout:
            logger.warning(f"⏱️ Ollama 超時（{self.timeout}s）")
            return None
        except Exception as e:
            logger.error(f"❌ Ollama 錯誤: {e}")
            return None

    def _parse_llm_response(self, text: str, query: str, source_title: str, source_url: str) -> Dict[str, Any]:
        """解析 LLM 回應"""
        if not text:
            return None
        
        try:
            text = re.sub(r'```(json)?\s*', '', text)
            match = re.search(r'\{.*\}', text, re.DOTALL)
            json_str = match.group(0) if match else text
            
            parsed = json.loads(json_str)
            
            entities = parsed.get("entities", [])
            for e in entities:
                e["source_title"] = source_title
                e["source_url"] = source_url
                e.setdefault("type", "未分類")
                e.setdefault("description", "")
            
            return {
                "entities": entities,
                "relationships": parsed.get("relationships", []),
                "summary": parsed.get("summary", "")
            }
        except Exception as e:
            logger.warning(f"解析失敗: {e}")
            return None

    # =========================
    # Fallback 規則提取
    # =========================

    def _fallback_extraction(self, doc: Dict[str, Any], query: str, idx: int) -> Dict[str, Any]:
        """
        當 LLM 失敗時的規則提取（保底方案）
        使用簡單的關鍵字和模式匹配
        """
        text = doc.get("full_text") or doc.get("content", "")
        title = doc.get("title", "")
        url = doc.get("url", "")
        
        entities = []
        
        # 規則 1：從標題提取主體
        if title:
            entities.append({
                "name": query.upper(),
                "type": "公司/組織",
                "description": f"來自文檔標題：{title}",
                "source_title": title,
                "source_url": url
            })
        
        # 規則 2：查找大寫詞組（可能是公司名）
        capitalized_words = re.findall(r'\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\b', text[:1000])
        for word in set(capitalized_words[:10]):  # 最多取 10 個
            if len(word) > 2 and word.lower() != query.lower():
                entities.append({
                    "name": word,
                    "type": "公司/組織",
                    "description": f"在文檔中提及",
                    "source_title": title,
                    "source_url": url
                })
        
        # 規則 3：查找常見職位（CEO、CFO 等）
        positions = re.findall(r'(CEO|CFO|CTO|President|Chairman|Director|Founder)', text[:2000], re.IGNORECASE)
        if positions:
            entities.append({
                "name": f"{query} Leadership",
                "type": "人物",
                "description": f"文檔中提到職位：{', '.join(set(positions))}",
                "source_title": title,
                "source_url": url
            })
        
        logger.info(f"🔧 文檔 {idx} 使用規則提取: {len(entities)} 個實體")
        
        return {
            "entities": entities,
            "relationships": [],
            "summary_info": {
                "url": url,
                "title": title,
                "summary": f"規則提取：{title}",
                "entity_count": len(entities)
            }
        }

    # =========================
    # 快速去重
    # =========================

    def _fast_deduplicate_entities(self, entities: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """快速去重"""
        if not entities:
            return []
        
        seen = set()
        unique = []
        
        for e in entities:
            name = e.get("name", "").strip()
            if not name:
                continue
            
            key = re.sub(r'\s+', '', name.lower())
            
            if key not in seen:
                seen.add(key)
                unique.append(e)
        
        # 簡單排序
        q = query.lower()
        unique.sort(key=lambda x: (
            q not in x.get("name", "").lower(),
            x.get("name", "")
        ))
        
        return unique

    def _fast_deduplicate_relationships(self, relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """快速去重關係"""
        seen = set()
        unique = []
        
        for r in relationships:
            key = (
                r.get("source", "").strip().lower(),
                r.get("relation", "").strip().lower(),
                r.get("target", "").strip().lower()
            )
            
            if key not in seen and all(key):
                seen.add(key)
                unique.append(r)
        
        return unique

    def _generate_fast_summary(self, document_summaries: List[Dict[str, Any]], query: str) -> str:
        """快速摘要"""
        if not document_summaries:
            return f"關於 {query} 的資訊提取完成"
        
        titles = [d.get("title", "") for d in document_summaries if d.get("title")]
        
        if titles:
            return f"已從 {len(document_summaries)} 個來源提取關於 {query} 的資訊，包括：{', '.join(titles[:2])} 等。"
        else:
            return f"已從 {len(document_summaries)} 個來源提取關於 {query} 的資訊。"