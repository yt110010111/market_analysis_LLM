#agents/web_scraping_agent/agent.py
import os
import logging
import asyncio
from typing import List, Dict, Any
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
import json
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebScrapingAgent:
    """
    網頁爬蟲代理：爬取指定 URL 的內容
    支援動態搜尋（使用 Tavily）來獲取更多相關 URL
    """
    
    def __init__(self):
        self.timeout = int(os.getenv("SCRAPING_TIMEOUT", "30"))
        self.max_retries = int(os.getenv("SCRAPING_MAX_RETRIES", "3"))
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        self.tavily_api_key = os.getenv("TAVILY_API_KEY", "")
        
    async def scrape_urls(self, urls: List[str], query: str = "", dynamic_search: bool = False) -> Dict[str, Any]:
        """
        爬取多個 URL 的內容
        
        Args:
            urls: 要爬取的 URL 列表
            query: 相關的查詢（用於上下文）
            dynamic_search: 是否使用 Tavily 動態搜尋更多 URL
            
        Returns:
            爬取結果的字典
        """
        logger.info(f"🕷️ 開始爬取 {len(urls)} 個 URL")
        
        # 如果啟用動態搜尋且有 query，使用 Tavily 獲取更多 URL
        if dynamic_search and query and self.tavily_api_key:
            logger.info(f"🔍 使用 Tavily 動態搜尋: {query}")
            additional_urls = self._search_with_tavily(query, max_results=5)
            if additional_urls:
                logger.info(f"✅ Tavily 找到 {len(additional_urls)} 個額外 URL")
                urls = list(set(urls + additional_urls))  # 合併並去重
            else:
                logger.warning("⚠️ Tavily 搜尋未返回結果")
        
        results = []
        successful = 0
        failed = 0
        
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            tasks = [self._scrape_single_url(client, url, idx) for idx, url in enumerate(urls)]
            scrape_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in scrape_results:
            if isinstance(result, Exception):
                logger.error(f"❌ 爬取失敗: {result}")
                failed += 1
            elif result and result.get("success"):
                results.append(result)
                successful += 1
            else:
                failed += 1
        
        logger.info(f"✅ 爬取完成: 成功 {successful}, 失敗 {failed}")
        
        return {
            "query": query,
            "total_urls": len(urls),
            "successful": successful,
            "failed": failed,
            "results": results,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def _search_with_tavily(self, query: str, max_results: int = 5) -> List[str]:
        """
        使用 Tavily API 搜尋相關 URL
        """
        try:
            response = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.tavily_api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "advanced",
                    "include_raw_content": False
                },
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            urls = [result.get("url") for result in results if result.get("url")]
            logger.info(f"📋 Tavily 返回 {len(urls)} 個 URL")
            
            return urls
            
        except Exception as e:
            logger.error(f"❌ Tavily 搜尋失敗: {e}")
            return []
    
    async def _scrape_single_url(self, client: httpx.AsyncClient, url: str, idx: int) -> Dict[str, Any]:
        """
        爬取單個 URL
        """
        logger.info(f"📄 [{idx+1}] 爬取: {url}")
        
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        }
        
        for attempt in range(self.max_retries):
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                # 解析 HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 提取標題
                title = soup.find('title')
                title_text = title.get_text().strip() if title else ""
                
                # 提取主要內容
                content = self._extract_main_content(soup)
                
                # 提取 meta 描述
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                description = meta_desc.get('content', '') if meta_desc else ""
                
                # 提取所有段落文字
                paragraphs = soup.find_all(['p', 'article', 'section'])
                text_content = '\n\n'.join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
                
                # 截斷過長的內容（保留前 5000 字元）
                if len(text_content) > 5000:
                    text_content = text_content[:5000] + "..."
                
                logger.info(f"✅ [{idx+1}] 成功: {url} (長度: {len(text_content)} 字元)")
                
                return {
                    "success": True,
                    "url": url,
                    "title": title_text,
                    "description": description,
                    "content": content,
                    "full_text": text_content,
                    "content_length": len(text_content),
                    "scraped_at": datetime.utcnow().isoformat() + "Z"
                }
                
            except httpx.HTTPStatusError as e:
                logger.warning(f"⚠️ [{idx+1}] HTTP 錯誤 (嘗試 {attempt+1}/{self.max_retries}): {e.response.status_code}")
                if attempt == self.max_retries - 1:
                    return {
                        "success": False,
                        "url": url,
                        "error": f"HTTP {e.response.status_code}",
                        "error_type": "http_error"
                    }
                await asyncio.sleep(1)
                
            except httpx.TimeoutException:
                logger.warning(f"⏱️ [{idx+1}] 超時 (嘗試 {attempt+1}/{self.max_retries})")
                if attempt == self.max_retries - 1:
                    return {
                        "success": False,
                        "url": url,
                        "error": "Request timeout",
                        "error_type": "timeout"
                    }
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ [{idx+1}] 錯誤: {str(e)}")
                return {
                    "success": False,
                    "url": url,
                    "error": str(e),
                    "error_type": "unknown"
                }
    
    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """
        提取網頁的主要內容
        嘗試找到 main, article 或其他主要內容標籤
        """
        # 優先尋找這些標籤
        main_tags = ['main', 'article', '[role="main"]', '.content', '#content']
        
        for tag in main_tags:
            if tag.startswith('.') or tag.startswith('#') or tag.startswith('['):
                # CSS 選擇器
                element = soup.select_one(tag)
            else:
                element = soup.find(tag)
            
            if element:
                text = element.get_text(separator='\n', strip=True)
                if len(text) > 100:  # 確保有足夠的內容
                    return text[:3000]  # 限制長度
        
        # 如果找不到主要內容，返回 body 的文字
        body = soup.find('body')
        if body:
            # 移除 script 和 style 標籤
            for script in body(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            return body.get_text(separator='\n', strip=True)[:3000]
        
        return ""
    
    def save_results_to_json(self, results: Dict[str, Any], output_path: str = "scraping_results.json"):
        """
        將爬取結果儲存為 JSON 檔案
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 結果已儲存至: {output_path}")
            return True
        except Exception as e:
            logger.error(f"❌ 儲存失敗: {e}")
            return False