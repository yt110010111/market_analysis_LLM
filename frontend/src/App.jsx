import React, { useState } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import './App.css';

function App() {
  const [userInput, setUserInput] = useState('');
  const [showReport, setShowReport] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [reportTitle, setReportTitle] = useState('');
  const [reportContent, setReportContent] = useState('');
  const [reportSources, setReportSources] = useState(null);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!userInput.trim()) {
      alert('請輸入查詢內容');
      return;
    }

    // ✅ 防止重複提交
    if (isLoading) {
      return;
    }

    setIsLoading(true);
    setReportTitle(userInput);
    setError('');
    setReportContent('');
    setShowReport(true); // ✅ 立即顯示報告面板（顯示 loading）

    try {
      // ✅ 只需要一次請求！後端會自動處理整個工作流
      console.log('發送分析請求:', userInput);
      
      const response = await axios.post('/api/analyze', {
        query: userInput
      }, {
        timeout: 180000  // ✅ 設置 3 分鐘超時（因為工作流可能需要時間）
      });

      console.log('收到報告:', response.data);

      // ✅ 檢查是否有報告內容
      if (response.data.report) {
        setReportContent(response.data.report);
        setReportSources(response.data.sources);
      } else {
        throw new Error('服務器未返回報告內容');
      }

    } catch (error) {
      console.error('錯誤:', error);
      
      let errorMessage = '發生未知錯誤';
      
      if (error.code === 'ECONNABORTED') {
        errorMessage = '請求超時，請稍後再試';
      } else if (error.response) {
        errorMessage = error.response.data?.detail || error.response.statusText || '服務器錯誤';
      } else if (error.request) {
        errorMessage = '無法連接到服務器';
      } else {
        errorMessage = error.message;
      }
      
      setError(errorMessage);
      
      // 顯示錯誤報告
      setReportContent(`# 生成報告時發生錯誤\n\n${errorMessage}\n\n請稍後再試或聯繫管理員。`);
      
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    setShowReport(false);
    setUserInput('');
    setReportContent('');
    setReportSources(null);
    setError('');
  };

  return (
    <div className="app">
      {/* 主頁面 */}
      <div className="main-container">
        <div className="content-wrapper">
          <h1 className="title">Research Assistant</h1>
          <p className="subtitle">輸入您想要查詢的資訊，將為您生成詳細報告</p>
          
          <form onSubmit={handleSubmit} className="search-form">
            <input
              type="text"
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              placeholder="例如：SpaceX 的最新發展、人工智慧趨勢分析..."
              className="search-input"
              disabled={isLoading}
            />
            <button 
              type="submit" 
              className="submit-button"
              disabled={isLoading || !userInput.trim()}  // ✅ 空輸入也禁用
            >
              {isLoading ? (
                <>
                  <span className="loading-spinner"></span>
                  <span>生成中...</span>
                </>
              ) : (
                <>
                  <span>🔍 生成報告</span>
                </>
              )}
            </button>
          </form>

          {error && !showReport && (  // ✅ 只在報告面板未顯示時顯示錯誤
            <div className="error-message">
              ⚠️ 錯誤：{error}
            </div>
          )}
        </div>
      </div>

      {/* 報告頁面 */}
      <div className={`report-panel ${showReport ? 'show' : ''}`}>
        <div className="report-header">
          <h2>{reportTitle}</h2>
          <button 
            className="close-button" 
            onClick={handleClose}
            disabled={isLoading}  // ✅ 載入中不允許關閉
          >
            ✕
          </button>
        </div>
        
        <div className="report-content">
          {isLoading ? (
            <div className="loading-placeholder">
              <div className="loading-spinner"></div>
              <p> 正在搜尋並分析資料...</p>
              <p className="loading-hint">檢索網頁中，請稍候</p>
            </div>
          ) : reportContent ? (
            <>
              {/* Markdown 渲染 */}
              <div className="markdown-content">
                <ReactMarkdown>{reportContent}</ReactMarkdown>
              </div>

              {/* 來源資訊 */}
              {reportSources && (
                <div className="report-section sources-section">
                  <h3>📊 資料來源統計</h3>
                  <ul>
                    <li>搜尋結果: {reportSources.search_results_count} 條</li>
                    <li>知識庫實體: {reportSources.neo4j_entities} 個</li>
                    <li>實體關係: {reportSources.neo4j_relationships} 個</li>
                  </ul>
                </div>
              )}

              {/* 顯示錯誤（如果有） */}
              {error && (
                <div className="error-message" style={{ marginTop: '20px' }}>
                  ⚠️ 注意：{error}
                </div>
              )}
            </>
          ) : (
            <div className="error-message">
              ⚠️ 未收到報告內容，請重試
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;