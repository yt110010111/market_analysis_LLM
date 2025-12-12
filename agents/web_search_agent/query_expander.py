"""
Query Expander 使用 Ollama 進行查詢擴展
包含：查詢改寫、同義詞擴展、相關主題生成
"""
import logging
import json
import aiohttp
from typing import List, Dict, Any
import asyncio

logger = logging.getLogger(__name__)


class OllamaQueryExpander:
    """
    使用 Ollama 本地 LLM 進行查詢擴展
    主要功能：
    1. 查詢改寫（不同表達方式）
    2. 同義詞擴展
    3. 相關主題生成
    """
    
    def __init__(self, ollama_host: str = "http://ollama:11434", model: str = "llama3.2:latest"):
        """
        初始化 Query Expander
        
        Args:
            ollama_host: Ollama 服務地址
            model: 使用的模型名稱（建議使用輕量級模型如 llama3.2:3b）
        """
        self.ollama_host = ollama_host
        self.model = model
        self.api_url = f"{ollama_host}/api/generate"
        logger.info(f"初始化 Query Expander - Host: {ollama_host}, Model: {model}")
        
    async def expand(self, query: str, num_expansions: int = 3) -> List[str]:
        """
        擴展查詢
        
        Args:
            query: 原始查詢
            num_expansions: 生成的擴展查詢數量
            
        Returns:
            擴展後的查詢列表
        """
        logger.info(f"開始擴展查詢: '{query}', 目標數量: {num_expansions}")
        
        prompt = self._build_expansion_prompt(query, num_expansions)
        
        try:
            expanded = await self._call_ollama(prompt)
            queries = self._parse_expansion_result(expanded, num_expansions)
            
            logger.info(f"查詢擴展完成，生成 {len(queries)} 個擴展查詢")
            for i, q in enumerate(queries, 1):
                logger.debug(f"  擴展 {i}: {q}")
                
            return queries
            
        except Exception as e:
            logger.error(f"查詢擴展失敗: {str(e)}", exc_info=True)
            return []
            
    def _build_expansion_prompt(self, query: str, num_expansions: int) -> str:
        """
        建立擴展查詢的 prompt
        
        Args:
            query: 原始查詢
            num_expansions: 需要的擴展數量
            
        Returns:
            完整的 prompt
        """
        prompt = f"""你是一個專業的搜尋查詢優化專家。請針對以下查詢生成 {num_expansions} 個不同的搜尋查詢變體。

原始查詢: {query}

要求:
1. 生成的查詢應該與原始查詢語意相關
2. 使用不同的關鍵字和表達方式
3. 包含同義詞和相關詞彙
4. 適合用於搜尋引擎
5. 每個查詢應該簡短精確（5-10個字）

請直接輸出 {num_expansions} 個查詢，每行一個，不要編號或其他格式。範例：

台積電最新財報
TSMC財務報告
台積電營收數據
"""
        return prompt
        
    async def _call_ollama(self, prompt: str) -> str:
        """
        呼叫 Ollama API
        
        Args:
            prompt: 輸入 prompt
            
        Returns:
            模型回應
        """
        logger.debug(f"呼叫 Ollama API: {self.api_url}")
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "max_tokens": 200
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        text = result.get("response", "")
                        logger.debug(f"Ollama 回應長度: {len(text)} 字元")
                        return text
                    else:
                        error_text = await response.text()
                        logger.error(f"Ollama API 錯誤 {response.status}: {error_text}")
                        raise Exception(f"Ollama API error: {response.status}")
                        
        except asyncio.TimeoutError:
            logger.error("Ollama API 呼叫超時")
            raise Exception("Ollama API timeout")
        except Exception as e:
            logger.error(f"呼叫 Ollama 時發生錯誤: {str(e)}")
            raise
            
    def _parse_expansion_result(self, text: str, num_expansions: int) -> List[str]:
        """
        解析擴展結果
        
        Args:
            text: 模型輸出文字
            num_expansions: 期望的擴展數量
            
        Returns:
            擴展查詢列表
        """
        logger.debug("開始解析擴展結果")
        
        # 按行分割
        lines = text.strip().split('\n')
        
        # 清理每一行
        queries = []
        for line in lines:
            # 移除編號、空白、特殊字元
            cleaned = line.strip()
            # 移除常見的編號格式
            cleaned = cleaned.lstrip('0123456789.、-* ')
            
            if cleaned and len(cleaned) > 2:
                queries.append(cleaned)
                
        # 限制數量
        queries = queries[:num_expansions]
        
        logger.debug(f"解析完成，找到 {len(queries)} 個有效查詢")
        return queries
        
    async def health_check(self, retries: int = 5, delay: int = 3) -> Dict[str, Any]:
        logger.info("執行 Ollama 健康檢查...")
        for attempt in range(1, retries + 1):
            try:
                test_prompt = "Say 'OK' if you can respond."
                response = await self._call_ollama(test_prompt)
                if response:
                    logger.info("Ollama 健康檢查通過")
                    return {"status": "healthy", "model": self.model}
            except Exception as e:
                logger.warning(f"Attempt {attempt} failed: {str(e)}")
                await asyncio.sleep(delay)
        return {"status": "unhealthy", "model": self.model, "error": "Cannot connect to Ollama after retries"}



# 測試用主程式
async def main():
    """測試 Query Expander"""
    expander = OllamaQueryExpander(
        ollama_host="http://localhost:11434",
        model="llama3.2:3b"
    )
    
    # 健康檢查
    print("\n=== 健康檢查 ===")
    health = await expander.health_check()
    print(health)
    
    # 測試查詢擴展
    print("\n=== 查詢擴展測試 ===")
    test_queries = [
        "台積電最新財報",
        "電動車市場趨勢",
        "人工智慧發展現況"
    ]
    
    for query in test_queries:
        print(f"\n原始查詢: {query}")
        expanded = await expander.expand(query, num_expansions=3)
        for i, exp in enumerate(expanded, 1):
            print(f"  擴展 {i}: {exp}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())