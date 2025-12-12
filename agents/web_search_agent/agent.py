"""
Web Search Agent
使用 DuckDuckGo 進行網路搜尋，並透過 Ollama 進行查詢擴展
"""
import logging
import asyncio
from typing import List, Dict, Any
from datetime import datetime
from search_engine import DuckDuckGoSearchEngine
from query_expander import OllamaQueryExpander

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WebSearchAgent:
    """
    Web Search Agent 負責：
    1. 接收使用者查詢
    2. 使用 Ollama 進行查詢擴展（同義詞、改寫）
    3. 使用 DuckDuckGo 搜尋相關內容
    4. 回傳結構化搜尋結果
    """
    
    def __init__(self, ollama_host: str = "http://ollama:11434", max_results: int = 10):
        """
        初始化 Web Search Agent
        
        Args:
            ollama_host: Ollama 服務的位址
            max_results: 最大搜尋結果數量
        """
        logger.info(f"初始化 Web Search Agent - Ollama Host: {ollama_host}")
        self.search_engine = DuckDuckGoSearchEngine(max_results=max_results)
        self.query_expander = OllamaQueryExpander(ollama_host=ollama_host)
        self.max_results = max_results
        
    async def search(self, user_prompt: str, expand_query: bool = True) -> Dict[str, Any]:
        """
        執行搜尋任務
        
        Args:
            user_prompt: 使用者輸入的查詢
            expand_query: 是否進行查詢擴展
            
        Returns:
            包含原始查詢、擴展查詢、搜尋結果的字典
        """
        logger.info(f"========== 開始搜尋任務 ==========")
        logger.info(f"原始查詢: {user_prompt}")
        
        start_time = datetime.now()
        
        try:
            # Step 1: 查詢擴展
            expanded_queries = []
            if expand_query:
                logger.info("步驟 1/3: 執行查詢擴展...")
                expanded_queries = await self.query_expander.expand(user_prompt)
                logger.info(f"查詢擴展完成，生成 {len(expanded_queries)} 個擴展查詢")
                for i, query in enumerate(expanded_queries, 1):
                    logger.info(f"  擴展查詢 {i}: {query}")
            else:
                logger.info("步驟 1/3: 跳過查詢擴展")
                
            # Step 2: 合併所有查詢
            all_queries = [user_prompt] + expanded_queries
            logger.info(f"步驟 2/3: 準備搜尋，共 {len(all_queries)} 個查詢")
            
            # Step 3: 執行搜尋
            logger.info("步驟 3/3: 執行網路搜尋...")
            all_results = []
            seen_urls = set()
            
            for i, query in enumerate(all_queries, 1):
                logger.info(f"搜尋查詢 {i}/{len(all_queries)}: {query}")
                results = await self.search_engine.search(query)
                
                # 去重
                unique_results = []
                for result in results:
                    if result['url'] not in seen_urls:
                        seen_urls.add(result['url'])
                        unique_results.append(result)
                        
                logger.info(f"  找到 {len(results)} 個結果，去重後 {len(unique_results)} 個")
                all_results.extend(unique_results)
                
                # 如果已經達到最大結果數，提前結束
                if len(all_results) >= self.max_results:
                    logger.info(f"已達到最大結果數 {self.max_results}，停止搜尋")
                    break
                    
            # 限制最終結果數量
            final_results = all_results[:self.max_results]
            
            # 計算執行時間
            execution_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"========== 搜尋任務完成 ==========")
            logger.info(f"總共找到 {len(final_results)} 個唯一結果")
            logger.info(f"執行時間: {execution_time:.2f} 秒")
            
            return {
                "status": "success",
                "original_query": user_prompt,
                "expanded_queries": expanded_queries,
                "total_queries": len(all_queries),
                "results": final_results,
                "total_results": len(final_results),
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"搜尋過程發生錯誤: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "original_query": user_prompt,
                "timestamp": datetime.now().isoformat()
            }
            
    async def health_check(self) -> Dict[str, Any]:
        """
        健康檢查：測試 Ollama 和搜尋引擎是否正常運作
        
        Returns:
            各組件的健康狀態
        """
        logger.info("執行健康檢查...")
        
        health_status = {
            "agent": "healthy",
            "timestamp": datetime.now().isoformat()
        }
        
        # 檢查 Ollama
        try:
            ollama_status = await self.query_expander.health_check()
            health_status["ollama"] = ollama_status
            logger.info(f"Ollama 狀態: {ollama_status['status']}")
        except Exception as e:
            health_status["ollama"] = {"status": "unhealthy", "error": str(e)}
            logger.error(f"Ollama 健康檢查失敗: {str(e)}")
            
        # 檢查搜尋引擎
        try:
            search_status = await self.search_engine.health_check()
            health_status["search_engine"] = search_status
            logger.info(f"搜尋引擎狀態: {search_status['status']}")
        except Exception as e:
            health_status["search_engine"] = {"status": "unhealthy", "error": str(e)}
            logger.error(f"搜尋引擎健康檢查失敗: {str(e)}")
            
        return health_status


# 測試用主程式
async def main():
    """測試 Web Search Agent"""
    agent = WebSearchAgent(
        ollama_host="http://localhost:11434",
        max_results=5
    )
    
    # 健康檢查
    print("\n=== 健康檢查 ===")
    health = await agent.health_check()
    print(health)
    
    # 執行搜尋
    print("\n=== 執行搜尋 ===")
    result = await agent.search("台積電最新財報")
    print(f"\n找到 {result['total_results']} 個結果")
    for i, item in enumerate(result['results'][:3], 1):
        print(f"\n結果 {i}:")
        print(f"  標題: {item['title']}")
        print(f"  URL: {item['url']}")
        print(f"  摘要: {item['snippet'][:100]}...")


if __name__ == "__main__":
    asyncio.run(main())