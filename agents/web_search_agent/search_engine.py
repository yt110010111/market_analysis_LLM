# search_engine.py
from duckduckgo_search import ddg

class DuckDuckGoSearchEngine:
    def __init__(self, max_results=10):
        self.max_results = max_results

    def search(self, query, category="all"):
        """
        執行 DuckDuckGo 搜尋
        query: 查詢字串
        category: 可選 "all" 或 "news"，用於過濾結果
        """
        if category == "news":
            query = f"{query} site:news"
        # ddg 函數返回 list of dict，每個 dict 有 keys: title, href, body
        results = ddg(query, max_results=self.max_results)
        if not results:
            return []
        # 將結果格式化為簡單字典列表
        formatted = [
            {
                "title": r.get("title", ""),
                "link": r.get("href", ""),
                "snippet": r.get("body", "")
            }
            for r in results
        ]
        return formatted
