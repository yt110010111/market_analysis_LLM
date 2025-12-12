import requests
from duckduckgo_search import ddg

# ---- Ollama 測試 ----
OLLAMA_HOST = "http://ollama:11434"
prompt = "寫一句簡短的自我介紹"

resp = requests.post(f"{OLLAMA_HOST}/api/completion", json={"model": "llama3.2:3b", "prompt": prompt})

try:
    data = resp.json()
    text = data.get("choices", [{}])[0].get("text", "")
    print("Ollama 回應:", text)
except Exception:
    # 如果 JSON 解析失敗，直接印 raw text
    print("Ollama 回應 (raw):", resp.text)


# ---- DuckDuckGo 搜尋測試 ----
query = "Python Docker 教學"
results = ddg(query, max_results=3)  # 取前三筆結果

print("\nDuckDuckGo 搜尋結果:")
for idx, r in enumerate(results, 1):
    print(f"{idx}. {r['title']} - {r['href']}")
