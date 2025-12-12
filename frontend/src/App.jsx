import { useState } from "react";

function App() {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    setLoading(true);
    setResponse(null);

    try {
      const res = await fetch(`http://web_search_agent:8001/search?q=${encodeURIComponent(query)}&expand=true`);

      const data = await res.json();
      setResponse(data);
    } catch (err) {
      setResponse({ error: err.toString() });
    }

    setLoading(false);
  };

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      <h2>Web Search Agent Test UI</h2>

      <input
        style={{ width: "60%", padding: "8px" }}
        placeholder="輸入 query，例如：NVIDIA stock news"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />

      <button onClick={handleSearch} style={{ marginLeft: 10, padding: "8px 16px" }}>
        Search
      </button>

      {loading && <p>搜尋中...</p>}
      {response && (
        <pre style={{ background: "#eee", marginTop: 20, padding: 10 }}>
          {JSON.stringify(response, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default App;
