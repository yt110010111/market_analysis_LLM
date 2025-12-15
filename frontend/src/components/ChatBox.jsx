import React, { useState } from "react";
import axios from "axios";

export default function ChatBox() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);

  const sendMessage = async () => {
    if (!input) return;
    setMessages([...messages, { sender: "user", text: input }]);

    try {
      // 使用 docker-compose service name 呼叫 analysis_agent
      const res = await axios.post(`/api/analyze`,{ query: input });

      // 取 report 與 workflow_steps 展示
      const report = res.data.report || "No report";
      const workflow = res.data.workflow_steps
        ? JSON.stringify(res.data.workflow_steps, null, 2)
        : "";

      const reply = workflow ? `${report}\n\nWorkflow Steps:\n${workflow}` : report;

      setMessages((prev) => [...prev, { sender: "bot", text: reply }]);
    } catch (err) {
      console.error(err);
      setMessages((prev) => [...prev, { sender: "bot", text: "Error generating report" }]);
    }

    setInput("");
  };

  return (
    <div>
      <div style={{ border: "1px solid gray", padding: "10px", height: "300px", overflowY: "scroll" }}>
        {messages.map((m, i) => (
          <div key={i} style={{ textAlign: m.sender === "user" ? "right" : "left" }}>
            <b>{m.sender}:</b> {m.text}
          </div>
        ))}
      </div>
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        style={{ width: "80%" }}
      />
      <button onClick={sendMessage} style={{ width: "18%" }}>Send</button>
    </div>
  );
}
