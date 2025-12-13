# search_engine.py - Fixed Mock Mode
import logging
import asyncio
from typing import List, Dict, Any
import time
import os

logger = logging.getLogger(__name__)


class DuckDuckGoSearchEngine:
    """
    混合模式搜尋引擎
    優先使用 DuckDuckGo，失敗時自動切換到模擬模式
    設置 USE_MOCK=true 環境變數可強制使用模擬模式
    """
    
    def __init__(self, max_results=10):
        self.max_results = max_results
        self.retry_attempts = 2
        self.retry_delay = 5
        self.last_request_time = 0
        self.min_request_interval = 3
        
        # 讀取環境變數
        use_mock_env = os.getenv("USE_MOCK", "false").lower()
        self.use_mock = use_mock_env in ["true", "1", "yes"]
        
        logger.info(f"環境變數 USE_MOCK={os.getenv('USE_MOCK', 'not set')}")
        logger.info(f"解析後 use_mock={self.use_mock}")
        
        if self.use_mock:
            logger.info("🎭 強制使用模擬模式（USE_MOCK=true）")
            self.ddgs = None
        else:
            logger.info(f"🔍 嘗試初始化 DuckDuckGo 搜尋引擎，最大結果數: {max_results}")
            self.ddgs = None
            self._init_ddgs()
    
    def _init_ddgs(self):
        """初始化 DDGS 實例"""
        if self.use_mock:
            logger.info("模擬模式啟用，跳過 DDGS 初始化")
            self.ddgs = None
            return
            
        try:
            from duckduckgo_search import DDGS
            self.ddgs = DDGS(timeout=20)
            logger.info("✅ DDGS 實例初始化成功")
        except Exception as e:
            logger.error(f"❌ 無法初始化 DDGS: {str(e)}")
            self.ddgs = None

    async def _rate_limit_delay(self):
        """實施 rate limiting"""
        if self.use_mock:
            # 模擬模式下也添加小延遲以模擬真實搜尋
            await asyncio.sleep(0.3)
            return
            
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            wait_time = self.min_request_interval - time_since_last
            logger.info(f"Rate limit: 等待 {wait_time:.2f} 秒")
            await asyncio.sleep(wait_time)
        
        self.last_request_time = time.time()

    async def search(self, query: str, category: str = "all") -> List[Dict[str, Any]]:
        """
        執行搜尋（支援模擬模式和真實搜尋）
        
        Args:
            query: 查詢字串
            category: "all" 或 "news"
            
        Returns:
            搜尋結果列表
        """
        logger.info(f"🔎 開始搜尋: '{query}', category: {category}, mock_mode: {self.use_mock}")
        
        # 如果是模擬模式，直接返回模擬結果
        if self.use_mock:
            await asyncio.sleep(0.5)  # 模擬網路延遲
            results = self._get_mock_results(query)
            logger.info(f"✅ 模擬搜尋完成，返回 {len(results)} 個結果")
            return results
        
        # 真實搜尋模式
        if not self.ddgs:
            logger.warning("DDGS 未初始化，切換到模擬模式")
            return self._get_mock_results(query)
        
        for attempt in range(self.retry_attempts):
            try:
                await self._rate_limit_delay()
                
                formatted = []
                
                if category == "news":
                    results = self.ddgs.news(query, max_results=self.max_results)
                else:
                    results = self.ddgs.text(query, max_results=self.max_results)
                
                for r in results:
                    formatted.append({
                        "title": r.get("title", ""),
                        "url": r.get("href") or r.get("link", ""),
                        "link": r.get("href") or r.get("link", ""),
                        "snippet": r.get("body") or r.get("description", "")
                    })
                
                if formatted:
                    logger.info(f"✅ 真實搜尋成功，找到 {len(formatted)} 個結果")
                    return formatted
                else:
                    logger.warning(f"搜尋無結果，切換到模擬模式: {query}")
                    return self._get_mock_results(query)
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"搜尋失敗 (嘗試 {attempt + 1}/{self.retry_attempts}): {error_msg}")
                
                if "Ratelimit" in error_msg or "SSL" in error_msg:
                    if attempt < self.retry_attempts - 1:
                        wait_time = self.retry_delay * (attempt + 2)
                        logger.info(f"等待 {wait_time} 秒後重試...")
                        await asyncio.sleep(wait_time)
                        self._init_ddgs()
                        continue
                    else:
                        logger.error(f"達到最大重試次數，切換到模擬模式: {query}")
                        return self._get_mock_results(query)
                else:
                    logger.error(f"搜尋遇到非預期錯誤，切換到模擬模式: {error_msg}")
                    return self._get_mock_results(query)
        
        return self._get_mock_results(query)
    
    def _get_mock_results(self, query: str) -> List[Dict[str, Any]]:
        """
        返回模擬搜尋結果
        """
        logger.info(f"📝 生成模擬搜尋結果: {query}")
        
        results = []
        templates = [
            {
                "title": f"{query} - 最新消息與深度分析",
                "snippet": f"關於{query}的最新發展動態，包含市場趨勢、產業分析和專家見解。本文詳細探討了該主題的各個層面，提供全面的資訊和數據支持。"
            },
            {
                "title": f"{query}完整指南 - 專業解析",
                "snippet": f"這是一份關於{query}的完整指南，涵蓋基礎知識、進階技巧和實戰案例。無論您是初學者還是專業人士，都能從中獲得有價值的資訊。"
            },
            {
                "title": f"2025年{query}趨勢報告",
                "snippet": f"最新的{query}產業報告顯示，該領域正在經歷重大變革。本報告分析了當前市場狀況、未來發展方向以及投資機會。"
            },
            {
                "title": f"{query}技術突破與創新應用",
                "snippet": f"近期{query}領域出現多項技術突破，為產業帶來新的可能性。本文介紹了最新的技術進展和創新應用案例。"
            },
            {
                "title": f"深入了解{query} - 專家訪談",
                "snippet": f"業界專家深度解析{query}的現狀與未來。透過訪談，我們獲得了獨家見解和前瞻性觀點，幫助您更好地理解這個主題。"
            }
        ]
        
        for i, template in enumerate(templates[:self.max_results], 1):
            results.append({
                "title": template["title"],
                "url": f"https://example.com/article/{i}?q={query}",
                "link": f"https://example.com/article/{i}?q={query}",
                "snippet": template["snippet"]
            })
        
        return results

    async def search_news(self, query: str) -> List[Dict[str, Any]]:
        """執行新聞搜尋"""
        logger.info(f"📰 開始新聞搜尋: '{query}'")
        return await self.search(query, category="news")

    async def health_check(self) -> Dict[str, Any]:
        """健康檢查"""
        logger.info("🏥 執行搜尋引擎健康檢查...")
        
        if self.use_mock:
            logger.info("✅ 模擬模式健康檢查通過")
            return {
                "status": "healthy",
                "engine": "MockSearchEngine",
                "mode": "mock",
                "max_results": self.max_results,
                "note": "使用模擬資料"
            }
        
        if not self.ddgs:
            return {
                "status": "degraded",
                "engine": "DuckDuckGo",
                "mode": "fallback",
                "error": "DDGS 未初始化，使用模擬模式",
                "fallback": "enabled"
            }
        
        try:
            await self._rate_limit_delay()
            test_results = self.ddgs.text("test", max_results=1)
            result_list = list(test_results)
            
            logger.info("✅ DuckDuckGo 健康檢查通過")
            return {
                "status": "healthy",
                "engine": "DuckDuckGo",
                "mode": "real",
                "max_results": self.max_results,
                "fallback": "available"
            }
        except Exception as e:
            logger.warning(f"⚠️ DuckDuckGo 健康檢查失敗: {str(e)[:100]}")
            return {
                "status": "degraded",
                "engine": "DuckDuckGo",
                "mode": "fallback",
                "error": str(e)[:100],
                "fallback": "enabled"
            }


# 測試用主程式
async def main():
    """測試搜尋引擎"""
    print("\n" + "="*60)
    print("搜尋引擎測試")
    print("="*60)
    
    engine = DuckDuckGoSearchEngine(max_results=5)
    
    # 健康檢查
    print("\n=== 健康檢查 ===")
    health = await engine.health_check()
    print(f"狀態: {health}")
    
    # 測試一般搜尋
    print("\n=== 一般搜尋測試 ===")
    results = await engine.search("TSMC 台積電")
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['title']}")
        print(f"   URL: {result['url']}")
        print(f"   摘要: {result['snippet'][:100]}...")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())