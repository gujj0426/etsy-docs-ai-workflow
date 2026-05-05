// background.js - Service Worker（Manifest V3）
// 最小化占位：监听安装事件，实际上传由本地服务器 cos_proxy_server.py 处理

chrome.runtime.onInstalled.addListener(() => {
  console.log('[Etsy COS] 插件已安装');
  // 上传功能由 popup.js / content.js 通过 http://localhost:8765 中转
});