#agents/data_extraction_agent/agent.py
import os
import json
import logging
import re
from typing import Dict, List, Any, Set, Tuple
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataExtractionAgent:
    """
    GPU 加速超強版 - 最大化實體和關聯提取：
    
    核心策略：
    1. 多輪提取 - 用不同角度提取同一文檔（3輪）
    2. 大文本分塊 - 將長文檔切分成多個塊，每塊獨立提取
    3. 關係挖掘增強 - 專門的關係提取輪次
    4. 實體擴展 - 基於已提取實體進行二次擴展
    5. 交叉驗證 - 多個文檔間的實體交叉引用
    6. 深度上下文 - 為每個實體提取豐富的上下文
    """

    def __init__(self):
        self.ollama_endpoint = os.getenv("OLLAMA_ENDPOINT", "http://ollama:11434")
        self.model_name = os.getenv("MODEL_NAME", "llama3.2:3b")
        self.max_docs = int(os.getenv("MAX_DOCS", "10"))  # 增加到 10 個文檔
        self.chunk_size = int(os.getenv("CHUNK_SIZE", "4000"))  # 每個塊 4000 字符
        self.max_chunks_per_doc = int(os.getenv("MAX_CHUNKS_PER_DOC", "5"))  # 每個文檔最多 5 個塊
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", "60"))
        self.max_workers = int(os.getenv("MAX_WORKERS", "5"))  # GPU 支持更多並行
        
        # 多輪提取配置
        self.enable_multi_pass = True  # 啟用多輪提取
        self.enable_relationship_mining = True  # 啟用深度關係挖掘
        self.enable_entity_expansion = True  # 啟用實體擴展
        
        # 實體類型（更細緻的分類）
        self.entity_types = {
            "organization": ["公司", "組織", "機構", "團隊", "部門", "子公司"],
            "person": ["創始人", "CEO", "高管", "董事", "員工", "顧問"],
            "product": ["產品", "服務", "平台", "應用", "解決方案"],
            "technology": ["技術", "算法", "框架", "工具", "協議", "標準"],
            "competitor": ["競爭對手", "替代品", "同業"],
            "partner": ["合作夥伴", "供應商", "客戶", "戰略聯盟"],
            "investor": ["投資者", "創投", "天使投資人", "私募基金"],
            "event": ["融資", "收購", "上市", "發布", "獎項", "里程碑"],
            "metric": ["營收", "用戶數", "市值", "估值", "增長率", "市場份額"],
            "location": ["總部", "辦公室", "市場", "地區"],
            "concept": ["策略", "願景", "使命", "價值主張", "商業模式"]
        }
        
        # 關係類型（更豐富的關係）
        self.relationship_types = [
            "創立", "領導", "任職於", "投資", "被投資", 
            "收購", "被收購", "合作", "競爭", "供應",
            "使用", "開發", "發布", "支持", "集成",
            "擁有", "隸屬於", "位於", "服務於", "影響",
            "衍生自", "基於", "優於", "劣於", "相似於"
        ]

    def extract_and_analyze(self, scraped_data: Dict[str, Any], query: str) -> Dict[str, Any]:
        results = scraped_data.get("results", [])
        if not results:
            return {"query": query, "status": "no_data", "entities": [], "summary": "無可分析資料"}

        logger.info(f"🚀 GPU 加速模式：開始深度處理 {len(results)} 份文件，目標主題: {query}")

        # ========== 階段 1：多輪並行提取 ==========
        all_entities = []
        all_relationships = []
        document_summaries = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有文檔處理任務
            futures = [
                executor.submit(self._deep_process_document, doc, query, idx)
                for idx, doc in enumerate(results[:self.max_docs], start=1)
            ]
            
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=180)  # 每個文檔最多 3 分鐘
                    if result:
                        all_entities.extend(result["entities"])
                        all_relationships.extend(result["relationships"])
                        document_summaries.append(result["summary_info"])
                        logger.info(f"✅ 文檔處理完成: {len(result['entities'])} 實體, {len(result['relationships'])} 關係")
                except Exception as e:
                    logger.warning(f"⚠️ 文檔處理失敗: {e}")

        if not all_entities:
            return {
                "query": query,
                "status": "empty",
                "entities": [],
                "relationships": [],
                "summary": "未能提取出資訊"
            }

        logger.info(f"📊 階段 1 完成: {len(all_entities)} 個原始實體, {len(all_relationships)} 個關係")

        # ========== 階段 2：實體去重與合併 ==========
        unique_entities = self._advanced_deduplicate_entities(all_entities, query)
        logger.info(f"📊 去重後: {len(unique_entities)} 個獨特實體")

        # ========== 階段 3：實體擴展（基於已有實體挖掘更多關聯）==========
        if self.enable_entity_expansion and len(unique_entities) > 5:
            expanded_entities = self._expand_entities(unique_entities, all_entities, query)
            unique_entities.extend(expanded_entities)
            unique_entities = self._advanced_deduplicate_entities(unique_entities, query)
            logger.info(f"📊 擴展後: {len(unique_entities)} 個實體")

        # ========== 階段 4：關係去重與推斷 ==========
        unique_relationships = self._advanced_deduplicate_relationships(all_relationships)
        
        # 推斷隱含關係（基於已有實體和關係）
        inferred_relationships = self._infer_relationships(unique_entities, unique_relationships)
        unique_relationships.extend(inferred_relationships)
        unique_relationships = self._advanced_deduplicate_relationships(unique_relationships)
        
        logger.info(f"📊 關係處理完成: {len(unique_relationships)} 個獨特關係")

        # ========== 階段 5：生成整體摘要 ==========
        overall_summary = self._generate_comprehensive_summary(
            unique_entities, 
            unique_relationships, 
            document_summaries, 
            query
        )

        # ========== 階段 6：實體排序與評分 ==========
        scored_entities = self._score_and_rank_entities(unique_entities, unique_relationships, query)

        logger.info(f"🎉 最終結果：{len(scored_entities)} 個實體，{len(unique_relationships)} 個關係")

        return {
            "query": query,
            "entities": scored_entities,
            "relationships": unique_relationships,
            "document_summaries": document_summaries,
            "overall_summary": overall_summary,
            "status": "success",
            "statistics": {
                "total_entities": len(scored_entities),
                "total_relationships": len(unique_relationships),
                "documents_processed": len(document_summaries),
                "entity_types": self._count_entity_types(scored_entities),
                "relationship_types": self._count_relationship_types(unique_relationships)
            }
        }

    # =========================
    # 深度文檔處理
    # =========================

    def _deep_process_document(self, doc: Dict[str, Any], query: str, idx: int) -> Dict[str, Any]:
        """深度處理單個文檔（多輪、多塊）"""
        text = doc.get("full_text") or doc.get("content", "")
        title = doc.get("title", "")
        url = doc.get("url", "")
        
        if not text:
            return None
        
        logger.info(f"📄 開始處理文檔 {idx}: {title[:50]}...")
        
        # 清理文本
        cleaned_text = self._smart_clean_text(text)
        
        # 將文本切分成多個塊
        chunks = self._split_into_chunks(cleaned_text, self.chunk_size, overlap=500)
        chunks = chunks[:self.max_chunks_per_doc]
        
        logger.info(f"   切分為 {len(chunks)} 個塊")
        
        all_entities = []
        all_relationships = []
        
        # ===== 第 1 輪：基礎實體提取 =====
        for chunk_idx, chunk in enumerate(chunks, start=1):
            extraction = self._extract_entities_basic(chunk, title, url, query, chunk_idx)
            if extraction:
                all_entities.extend(extraction.get("entities", []))
                all_relationships.extend(extraction.get("relationships", []))
        
        logger.info(f"   第 1 輪完成: {len(all_entities)} 實體")
        
        # ===== 第 2 輪：深度關係挖掘 =====
        if self.enable_relationship_mining and len(all_entities) > 3:
            for chunk_idx, chunk in enumerate(chunks[:3], start=1):  # 只對前 3 個塊做深度挖掘
                deep_relationships = self._extract_relationships_deep(
                    chunk, title, url, query, all_entities
                )
                if deep_relationships:
                    all_relationships.extend(deep_relationships)
        
        logger.info(f"   第 2 輪完成: {len(all_relationships)} 關係")
        
        # ===== 第 3 輪：上下文增強 =====
        if len(all_entities) > 0:
            enhanced_entities = self._enhance_entity_context(
                all_entities, cleaned_text, title, url
            )
            all_entities = enhanced_entities
        
        logger.info(f"   第 3 輪完成: 實體上下文已增強")
        
        # 生成文檔摘要
        summary = self._generate_document_summary(all_entities, all_relationships, title, query)
        
        return {
            "entities": all_entities,
            "relationships": all_relationships,
            "summary_info": {
                "url": url,
                "title": title,
                "summary": summary,
                "entity_count": len(all_entities),
                "relationship_count": len(all_relationships)
            }
        }

    # =========================
    # 文本處理
    # =========================

    def _smart_clean_text(self, text: str) -> str:
        """智能清理文本"""
        if not text:
            return ""
        
        # 移除常見的網頁噪音
        noise_patterns = [
            r'cookie\s+policy.*?(?:\n|$)',
            r'privacy\s+policy.*?(?:\n|$)',
            r'terms\s+of\s+service.*?(?:\n|$)',
            r'subscribe.*?newsletter.*?(?:\n|$)',
            r'related\s+articles.*?(?:\n|$)',
        ]
        
        for pattern in noise_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # 保留有意義的段落（至少 50 字符）
        paragraphs = [p.strip() for p in text.split('\n') if len(p.strip()) > 50]
        
        return '\n\n'.join(paragraphs)

    def _split_into_chunks(self, text: str, chunk_size: int, overlap: int = 0) -> List[str]:
        """將文本切分成重疊的塊"""
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            
            # 嘗試在句子邊界切分
            if end < len(text):
                last_period = chunk.rfind('.')
                last_newline = chunk.rfind('\n')
                split_point = max(last_period, last_newline)
                
                if split_point > chunk_size * 0.7:  # 至少保留 70%
                    chunk = chunk[:split_point + 1]
                    end = start + split_point + 1
            
            chunks.append(chunk)
            start = end - overlap  # 重疊部分
        
        return chunks

    # =========================
    # LLM 提取（多種策略）
    # =========================

    def _extract_entities_basic(self, text: str, title: str, url: str, query: str, chunk_idx: int) -> Dict[str, Any]:
        """基礎實體提取（廣泛且全面）"""
        
        prompt = f"""你是知識圖譜構建專家。請從文本中提取與「{query}」相關的**所有**實體和關係。

【核心任務】
1. 提取盡可能多的實體（目標：15-30 個）
2. 為每個實體提供詳細描述
3. 識別實體間的各種關係
4. 不要遺漏任何重要資訊

【實體類型】（請盡量涵蓋）
- 公司/組織：相關公司、子公司、部門、機構
- 人物：創始人、高管、董事、重要員工
- 產品/服務：主要產品、服務、平台
- 技術：使用的技術、技術棧、算法、工具
- 競爭對手：直接競爭者、間接競爭者、潛在威脅
- 合作夥伴：戰略合作、供應商、客戶
- 投資者：投資機構、創投、天使投資人
- 事件：融資、收購、發布、里程碑
- 指標：營收、用戶數、市值、增長數據
- 地點：總部、辦公室、市場區域
- 概念：策略、願景、商業模式

【關係類型】（請盡量識別）
創立、領導、投資、收購、合作、競爭、使用、開發、發布、位於、服務於等

【文檔資訊】
標題：{title}
區塊：{chunk_idx}

【文本內容】
{text[:3500]}

【輸出格式】
必須返回有效的 JSON：
{{
  "entities": [
    {{
      "name": "實體名稱",
      "type": "實體類型（從上述類型中選擇）",
      "description": "詳細描述（50-100字），說明該實體的背景、作用、與主題的關聯",
      "importance": "high/medium/low（重要性評估）"
    }}
  ],
  "relationships": [
    {{
      "source": "源實體名稱",
      "target": "目標實體名稱",
      "relation": "關係類型",
      "description": "關係的詳細描述",
      "strength": "strong/medium/weak（關係強度）"
    }}
  ]
}}

【範例】
如果主題是 "Tesla"：
{{
  "entities": [
    {{"name": "Tesla", "type": "公司/組織", "description": "美國電動車製造商，由 Elon Musk 領導，專注於電動車和清潔能源", "importance": "high"}},
    {{"name": "Elon Musk", "type": "人物", "description": "Tesla CEO，企業家，同時領導 SpaceX 和 X（前 Twitter）", "importance": "high"}},
    {{"name": "Model 3", "type": "產品/服務", "description": "Tesla 暢銷電動車型，面向大眾市場", "importance": "medium"}},
    {{"name": "BYD", "type": "競爭對手", "description": "中國電動車製造商，全球銷量領先", "importance": "medium"}},
    {{"name": "Gigafactory", "type": "地點", "description": "Tesla 在全球的超級工廠，用於大規模生產", "importance": "medium"}}
  ],
  "relationships": [
    {{"source": "Elon Musk", "target": "Tesla", "relation": "領導", "description": "擔任 CEO 並推動公司戰略", "strength": "strong"}},
    {{"source": "Tesla", "target": "BYD", "relation": "競爭", "description": "在電動車市場直接競爭", "strength": "strong"}},
    {{"source": "Tesla", "target": "Model 3", "relation": "開發", "description": "Tesla 開發並生產 Model 3", "strength": "strong"}}
  ]
}}

現在請開始提取，記住要**全面且詳細**，不要遺漏任何相關實體："""

        response = self._call_ollama(prompt, temperature=0.1)
        return self._parse_json_response(response, title, url)

    def _extract_relationships_deep(self, text: str, title: str, url: str, query: str, existing_entities: List[Dict]) -> List[Dict]:
        """深度關係挖掘（專注於關係）"""
        
        # 提取已有實體名稱
        entity_names = [e["name"] for e in existing_entities[:20]]  # 最多使用 20 個
        
        prompt = f"""你是關係挖掘專家。請分析文本，找出以下實體之間的**所有可能關係**。

【已知實體】
{', '.join(entity_names)}

【文本內容】
{text[:3000]}

【任務】
1. 找出已知實體之間的關係
2. 找出已知實體與文本中其他實體的關係
3. 識別隱含的、間接的關係
4. 每個關係都要有詳細描述

【關係類型】
創立、領導、投資、收購、合作、競爭、使用、開發、發布、支持、影響、基於、優於、服務於等

【輸出格式】
{{
  "relationships": [
    {{
      "source": "實體A",
      "target": "實體B",
      "relation": "關係類型",
      "description": "詳細描述這個關係，包括時間、方式、影響等",
      "strength": "strong/medium/weak",
      "evidence": "文本中支持這個關係的具體證據"
    }}
  ]
}}

請盡可能多地提取關係（目標：10-20 個關係）："""

        response = self._call_ollama(prompt, temperature=0.1)
        parsed = self._parse_json_response(response, title, url)
        return parsed.get("relationships", []) if parsed else []

    def _enhance_entity_context(self, entities: List[Dict], full_text: str, title: str, url: str) -> List[Dict]:
        """增強實體上下文（為重要實體添加更多資訊）"""
        
        # 挑選最重要的實體進行增強
        important_entities = [e for e in entities if e.get("importance") == "high"][:10]
        
        if not important_entities:
            return entities
        
        entity_names = [e["name"] for e in important_entities]
        
        prompt = f"""請為以下實體提供更豐富的上下文資訊。

【實體列表】
{', '.join(entity_names)}

【文檔】
{title}
{full_text[:4000]}

【任務】
為每個實體提供：
1. 詳細的背景資訊
2. 在文檔中的角色
3. 與主題的關聯
4. 相關的數據或事實

【輸出格式】
{{
  "enhanced_entities": [
    {{
      "name": "實體名稱",
      "extended_description": "豐富的描述（100-200字）",
      "key_facts": ["事實1", "事實2", "事實3"],
      "mentions": 3
    }}
  ]
}}

請提供詳細資訊："""

        response = self._call_ollama(prompt, temperature=0.2)
        parsed = self._parse_json_response(response, title, url)
        
        if parsed and "enhanced_entities" in parsed:
            # 合併增強資訊
            enhanced_map = {e["name"]: e for e in parsed["enhanced_entities"]}
            
            for entity in entities:
                if entity["name"] in enhanced_map:
                    enhanced = enhanced_map[entity["name"]]
                    entity["description"] = enhanced.get("extended_description", entity.get("description", ""))
                    entity["key_facts"] = enhanced.get("key_facts", [])
                    entity["mentions"] = enhanced.get("mentions", 1)
        
        return entities

    # =========================
    # 實體擴展與推斷
    # =========================

    def _expand_entities(self, unique_entities: List[Dict], all_entities: List[Dict], query: str) -> List[Dict]:
        """基於已有實體，挖掘更多關聯實體"""
        
        # 選擇最重要的實體作為種子
        seed_entities = [e for e in unique_entities if e.get("importance") == "high"][:5]
        
        if not seed_entities:
            return []
        
        seed_names = [e["name"] for e in seed_entities]
        
        prompt = f"""基於以下核心實體，請推斷和列出**相關但尚未提及**的重要實體。

【核心實體】
{', '.join(seed_names)}

【主題】
{query}

【任務】
推斷可能相關但文檔中未明確提到的實體，例如：
- 相關的競爭對手
- 關鍵的合作夥伴
- 重要的技術或工具
- 潛在的投資者
- 相關的市場或行業

【輸出格式】
{{
  "inferred_entities": [
    {{
      "name": "推斷的實體名稱",
      "type": "實體類型",
      "description": "為什麼這個實體可能相關",
      "confidence": "high/medium/low",
      "reasoning": "推斷依據"
    }}
  ]
}}

請列出 5-10 個可能相關的實體："""

        response = self._call_ollama(prompt, temperature=0.3)
        parsed = self._parse_json_response(response, "", "")
        
        if parsed and "inferred_entities" in parsed:
            inferred = parsed["inferred_entities"]
            # 只保留高置信度的推斷實體
            return [e for e in inferred if e.get("confidence") in ["high", "medium"]]
        
        return []

    def _infer_relationships(self, entities: List[Dict], relationships: List[Dict]) -> List[Dict]:
        """基於已有實體和關係，推斷隱含關係"""
        
        if len(entities) < 5 or len(relationships) < 3:
            return []
        
        entity_names = [e["name"] for e in entities[:15]]
        existing_rels = [(r["source"], r["target"], r["relation"]) for r in relationships[:10]]
        
        prompt = f"""基於以下實體和已知關係，請推斷可能存在的**隱含關係**。

【實體】
{', '.join(entity_names)}

【已知關係】
{json.dumps(existing_rels[:10], ensure_ascii=False)}

【任務】
推斷邏輯上合理但未明確提及的關係，例如：
- 如果 A 領導 B，B 開發 C，則 A 可能影響 C
- 如果 X 投資 Y，Y 競爭 Z，則 X 可能關注 Z
- 傳遞性關係、隱含的合作或競爭關係

【輸出格式】
{{
  "inferred_relationships": [
    {{
      "source": "實體A",
      "target": "實體B",
      "relation": "推斷的關係類型",
      "description": "推斷依據和邏輯",
      "confidence": "high/medium/low",
      "inferred": true
    }}
  ]
}}

請列出 3-8 個合理的推斷關係："""

        response = self._call_ollama(prompt, temperature=0.3)
        parsed = self._parse_json_response(response, "", "")
        
        if parsed and "inferred_relationships" in parsed:
            inferred = parsed["inferred_relationships"]
            # 只保留中高置信度的推斷關係
            return [r for r in inferred if r.get("confidence") in ["high", "medium"]]
        
        return []

    # =========================
    # LLM 調用
    # =========================

    def _call_ollama(self, prompt: str, temperature: float = 0.1) -> str:
        """調用 Ollama（針對 GPU 優化）"""
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
                "num_predict": 3000,  # GPU 支持更長輸出
                "top_p": 0.9,
                "top_k": 40,
                "repeat_penalty": 1.1
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
        except Exception as e:
            logger.error(f"❌ Ollama 調用失敗: {e}")
            return None

    def _parse_json_response(self, text: str, source_title: str, source_url: str) -> Dict[str, Any]:
        """解析 JSON 回應"""
        if not text:
            return None
        
        try:
            # 清理 Markdown 標記
            text = re.sub(r'```(json)?\s*', '', text)
            
            # 提取 JSON
            match = re.search(r'\{.*\}', text, re.DOTALL)
            json_str = match.group(0) if match else text
            
            parsed = json.loads(json_str)
            
            # 補充來源資訊
            for entity in parsed.get("entities", []):
                entity.setdefault("source_title", source_title)
                entity.setdefault("source_url", source_url)
                entity.setdefault("type", "未分類")
                entity.setdefault("description", "")
                entity.setdefault("importance", "medium")
            
            return parsed
            
        except Exception as e:
            logger.warning(f"⚠️ JSON 解析失敗: {e}")
            return None

    # =========================
    # 高級去重與排序
    # =========================

    def _advanced_deduplicate_entities(self, entities: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """高級去重（考慮相似名稱、別名）"""
        if not entities:
            return []
        
        # 構建實體映射
        entity_map = {}
        
        for e in entities:
            name = e.get("name", "").strip()
            if not name or len(name) < 2:
                continue
            
            # 標準化名稱
            normalized = self._normalize_entity_name(name)
            
            if normalized in entity_map:
                # 合併實體資訊（保留更詳細的）
                existing = entity_map[normalized]
                
                # 選擇更好的描述
                if len(e.get("description", "")) > len(existing.get("description", "")):
                    existing["description"] = e["description"]
                
                # 合併來源
                if "sources" not in existing:
                    existing["sources"] = []
                existing["sources"].append({
                    "title": e.get("source_title", ""),
                    "url": e.get("source_url", "")
                })
                
                # 合併關鍵事實
                if "key_facts" in e:
                    if "key_facts" not in existing:
                        existing["key_facts"] = []
                    existing["key_facts"].extend(e["key_facts"])
                
                # 提升重要性
                if e.get("importance") == "high":
                    existing["importance"] = "high"
                
            else:
                # 新實體
                e["normalized_name"] = normalized
                e["sources"] = [{
                    "title": e.get("source_title", ""),
                    "url": e.get("source_url", "")
                }]
                entity_map[normalized] = e
        
        return list(entity_map.values())

    def _normalize_entity_name(self, name: str) -> str:
        """標準化實體名稱"""
        # 移除標點、空格，轉小寫
        normalized = re.sub(r'[^\w\s]', '', name.lower())
        normalized = re.sub(r'\s+', '', normalized)
        
        # 移除常見後綴
        suffixes = ['inc', 'ltd', 'llc', 'corp', 'corporation', 'company', 'co']
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]
        
        return normalized.strip()

    def _advanced_deduplicate_relationships(self, relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """高級去重關係"""
        seen = set()
        unique = []
        
        for r in relationships:
            source = self._normalize_entity_name(r.get("source", ""))
            target = self._normalize_entity_name(r.get("target", ""))
            relation = r.get("relation", "").strip().lower()
            
            # 創建唯一鍵（考慮雙向關係）
            key1 = (source, relation, target)
            key2 = (target, self._reverse_relation(relation), source)
            
            if key1 not in seen and key2 not in seen and source and target:
                seen.add(key1)
                unique.append(r)
        
        return unique

    def _reverse_relation(self, relation: str) -> str:
        """獲取反向關係"""
        reverse_map = {
            "領導": "被領導",
            "投資": "被投資",
            "收購": "被收購",
            "創立": "由創立",
            "使用": "被使用",
            "開發": "被開發"
        }
        return reverse_map.get(relation, relation)

    def _score_and_rank_entities(self, entities: List[Dict], relationships: List[Dict], query: str) -> List[Dict]:
        """為實體評分並排序"""
        
        # 計算每個實體在關係中出現的次數
        entity_mentions = {}
        for r in relationships:
            source = r.get("source", "")
            target = r.get("target", "")
            entity_mentions[source] = entity_mentions.get(source, 0) + 1
            entity_mentions[target] = entity_mentions.get(target, 0) + 1
        
        q_lower = query.lower()
        
        for entity in entities:
            name = entity.get("name", "")
            name_lower = name.lower()
            desc = entity.get("description", "").lower()
            
            score = 0
            
            # 1. 名稱包含查詢詞（高權重）
            if q_lower in name_lower:
                score += 10
            
            # 2. 描述包含查詢詞
            if q_lower in desc:
                score += 5
            
            # 3. 重要性評估
            importance = entity.get("importance", "medium")
            if importance == "high":
                score += 8
            elif importance == "medium":
                score += 4
            
            # 4. 關係豐富度（在關係網中的中心性）
            mention_count = entity_mentions.get(name, 0)
            score += min(mention_count * 2, 10)
            
            # 5. 描述豐富度
            desc_length = len(entity.get("description", ""))
            if desc_length > 100:
                score += 3
            elif desc_length > 50:
                score += 1
            
            # 6. 有關鍵事實
            if entity.get("key_facts"):
                score += len(entity["key_facts"])
            
            # 7. 多來源驗證
            if entity.get("sources"):
                score += min(len(entity["sources"]), 5)
            
            entity["relevance_score"] = score
        
        # 按評分排序
        entities.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        return entities

    # =========================
    # 摘要生成
    # =========================

    def _generate_document_summary(self, entities: List[Dict], relationships: List[Dict], title: str, query: str) -> str:
        """生成單個文檔的摘要"""
        if not entities:
            return f"{title} - 未能提取資訊"
        
        entity_types = {}
        for e in entities:
            etype = e.get("type", "未分類")
            entity_types[etype] = entity_types.get(etype, 0) + 1
        
        type_summary = ", ".join([f"{k}({v}個)" for k, v in sorted(entity_types.items(), key=lambda x: -x[1])[:3]])
        
        return f"{title} - 提取了 {len(entities)} 個實體和 {len(relationships)} 個關係，主要包括：{type_summary}"

    def _generate_comprehensive_summary(self, entities: List[Dict], relationships: List[Dict], 
                                       doc_summaries: List[Dict], query: str) -> str:
        """生成全面的整體摘要"""
        
        prompt = f"""請基於以下資訊，生成一份關於「{query}」的全面分析摘要（200-300字）。

【提取的實體數量】
總計：{len(entities)} 個實體

【主要實體類型分布】
{self._get_entity_type_distribution(entities)}

【關係數量】
總計：{len(relationships)} 個關係

【前 10 個最重要實體】
{self._get_top_entities_summary(entities[:10])}

【文檔來源】
處理了 {len(doc_summaries)} 個來源

【任務】
生成一份簡潔的摘要，包括：
1. {query} 的核心定位和業務
2. 關鍵人物和組織架構
3. 主要產品或服務
4. 重要的合作或競爭關係
5. 值得關注的事件或數據

請用流暢的中文撰寫："""

        response = self._call_ollama(prompt, temperature=0.2)
        
        if response:
            # 嘗試提取文本（可能是 JSON 或純文本）
            try:
                parsed = json.loads(response)
                return parsed.get("summary", response)
            except:
                # 直接返回文本
                return response.strip()
        
        return f"關於 {query} 的資訊已從 {len(doc_summaries)} 個來源提取完成，包含 {len(entities)} 個實體和 {len(relationships)} 個關係。"

    def _get_entity_type_distribution(self, entities: List[Dict]) -> str:
        """獲取實體類型分布"""
        type_count = {}
        for e in entities:
            etype = e.get("type", "未分類")
            type_count[etype] = type_count.get(etype, 0) + 1
        
        return ", ".join([f"{k}: {v}" for k, v in sorted(type_count.items(), key=lambda x: -x[1])[:5]])

    def _get_top_entities_summary(self, entities: List[Dict]) -> str:
        """獲取頂級實體摘要"""
        summaries = []
        for e in entities[:10]:
            name = e.get("name", "")
            etype = e.get("type", "")
            summaries.append(f"- {name} ({etype})")
        return "\n".join(summaries)

    # =========================
    # 統計輔助
    # =========================

    def _count_entity_types(self, entities: List[Dict]) -> Dict[str, int]:
        """統計實體類型"""
        counts = {}
        for e in entities:
            etype = e.get("type", "未分類")
            counts[etype] = counts.get(etype, 0) + 1
        return counts

    def _count_relationship_types(self, relationships: List[Dict]) -> Dict[str, int]:
        """統計關係類型"""
        counts = {}
        for r in relationships:
            rtype = r.get("relation", "未分類")
            counts[rtype] = counts.get(rtype, 0) + 1
        return counts