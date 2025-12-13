import React, { useState } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  const [userInput, setUserInput] = useState('');
  const [showReport, setShowReport] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [reportTitle, setReportTitle] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!userInput.trim()) {
      alert('請輸入查詢內容');
      return;
    }

    setIsLoading(true);
    setReportTitle(userInput);

    try {
      // 發送請求到 web_search_agent
      await axios.post('/api/search', {
        query: userInput
      });

      // 顯示報告頁面（即使沒有回傳資料）
      setTimeout(() => {
        setShowReport(true);
        setIsLoading(false);
      }, 1000);

    } catch (error) {
      console.error('Error:', error);
      setIsLoading(false);
      alert('發送請求時發生錯誤，請稍後再試');
    }
  };

  const handleClose = () => {
    setShowReport(false);
    setUserInput('');
  };

  return (
    <div className="app">
      {/* 主頁面 */}
      <div className="main-container">
        <div className="content-wrapper">
          <h1 className="title">Research Assistant</h1>
          <p className="subtitle">輸入您想要查詢的資訊，AI 將為您生成詳細報告</p>
          
          <form onSubmit={handleSubmit} className="search-form">
            <input
              type="text"
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              placeholder="例如：人工智慧的最新發展趨勢"
              className="search-input"
              disabled={isLoading}
            />
            <button 
              type="submit" 
              className="submit-button"
              disabled={isLoading}
            >
              {isLoading ? (
                <span className="loading-spinner"></span>
              ) : (
                '生成報告'
              )}
            </button>
          </form>
        </div>
      </div>

      {/* 報告頁面 */}
      <div className={`report-panel ${showReport ? 'show' : ''}`}>
        <div className="report-header">
          <h2>{reportTitle} 報告</h2>
          <button className="close-button" onClick={handleClose}>
            ✕
          </button>
        </div>
        
        <div className="report-content">
          {/* 示意圖片 */}
          <div className="report-image">
            <img 
              src="https://images.unsplash.com/photo-1677442136019-21780ecad995?w=800&h=400&fit=crop" 
              alt="AI Generated" 
            />
          </div>

          {/* 文字內容 */}
          <div className="report-section">
            <h3>摘要</h3>
            <p>
              這是一個示範報告頁面。當您的 agent 完成後，這裡將顯示實際的分析結果。
              目前您的查詢已經成功發送到 web_search_agent 進行處理。
            </p>
          </div>

          <div className="report-section">
            <h3>關鍵發現</h3>
            <p>
              • 您的查詢內容：{reportTitle}<br/>
              • 系統已接收並處理您的請求<br/>
              • 後續可以在這裡展示更詳細的分析結果
            </p>
          </div>

          <div className="report-section">
            <h3>詳細分析</h3>
            <p>
              當 analysis_agent 和 data_extraction_agent 完成後，
              這裡可以顯示更深入的分析內容、圖表、統計數據等資訊。
            </p>
          </div>

          <div className="report-image">
            <img 
              src="https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=800&h=400&fit=crop" 
              alt="Data Analysis" 
            />
          </div>

          <div className="report-section">
            <h3>結論</h3>
            <p>
              報告的內容將根據您的查詢動態生成。目前這是一個示範頁面，
              展示了報告的基本結構，包含標題、圖片和可滾動的文字段落。
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;