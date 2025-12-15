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

    setIsLoading(true);
    setReportTitle(userInput);
    setError('');
    setReportContent('');

    try {
      // 步驟 1: 發送搜尋請求
      console.log('步驟 1: 發送搜尋請求...');
      const searchResponse = await axios.post('/api/analyze', {
        query: userInput
      });

      console.log('搜尋結果:', searchResponse.data);

      // 步驟 2: 分析搜尋結果
      console.log('步驟 2: 分析搜尋結果...');
      const analysisResponse = await axios.post('/api/analyze', {
        query: userInput,
        results: searchResponse.data.results || []
      });

      console.log('分析結果:', analysisResponse.data);

      // 步驟 3: 執行工作流並生成報告
      console.log('步驟 3: 生成報告...');
      const orchestrateResponse = await axios.post('/api/orchestrate', {
        action: analysisResponse.data.action,
        query: userInput,
        search_results: searchResponse.data.results || [],
        urls_to_scrape: analysisResponse.data.details?.urls_to_scrape || []
      });

      console.log('報告結果:', orchestrateResponse.data);

      // 檢查是否有報告內容
      if (orchestrateResponse.data.report) {
        setReportContent(orchestrateResponse.data.report);
        setReportSources(orchestrateResponse.data.sources);
        setShowReport(true);
      } else {
        throw new Error('服務器未返回報告內容');
      }

    } catch (error) {
      console.error('錯誤:', error);
      setError(error.response?.data?.detail || error.message || '發生未知錯誤');
      
      // 顯示錯誤報告
      setReportContent(`# 生成報告時發生錯誤\n\n${error.message}\n\n請稍後再試或聯繫管理員。`);
      setShowReport(true);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    setShowReport(false);
    setUserInput('');
    setReportContent('');
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
              disabled={isLoading}
            >
              {isLoading ? (
                <>
                  <span className="loading-spinner"></span>
                  <span>生成中...</span>
                </>
              ) : (
                <>
                  <span> 生成報告</span>
                </>
              )}
            </button>
          </form>

          {error && (
            <div className="error-message">
               錯誤：{error}
            </div>
          )}
        </div>
      </div>

      {/* 報告頁面 */}
      <div className={`report-panel ${showReport ? 'show' : ''}`}>
        <div className="report-header">
          <h2>{reportTitle}</h2>
          <button className="close-button" onClick={handleClose}>
            ✕
          </button>
        </div>
        
        <div className="report-content">
          {reportContent ? (
            <>
              {/* Markdown 渲染 */}
              <div className="markdown-content">
                <ReactMarkdown>{reportContent}</ReactMarkdown>
              </div>

              {/* 來源資訊 */}
              {reportSources && (
                <div className="report-section sources-section">
                  <h3> 資料來源統計</h3>
                  <ul>
                    <li>搜尋結果: {reportSources.search_results_count} 條</li>
                    <li>知識庫實體: {reportSources.neo4j_entities} 個</li>
                    <li>實體關係: {reportSources.neo4j_relationships} 個</li>
                  </ul>
                </div>
              )}
            </>
          ) : (
            <div className="loading-placeholder">
              <div className="loading-spinner"></div>
              <p> 正在生成精彩報告...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;