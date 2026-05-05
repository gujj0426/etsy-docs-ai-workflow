// popup.js - 插件弹窗逻辑
// 通过本地中转服务器上传（SDK 上传），稳定可靠

const LOCAL_SERVER = 'http://localhost:8765';

// ── 状态存储 ─────────────────────────────────────────
let lastUpload = null;  // {cdnUrl, objectKey, timestamp}

// ── 工具函数 ─────────────────────────────────────────
function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function showStatus(msg, type) {
  const box = document.getElementById('statusBox');
  box.className = `status ${type}`;
  box.innerHTML = `<span class="status-dot"></span>${msg}`;
}

// ── API 调用 ─────────────────────────────────────────
async function apiPost(endpoint, payload) {
  const resp = await fetch(`${LOCAL_SERVER}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return resp.json();
}

// ── 保存配置 ─────────────────────────────────────────
document.getElementById('btnSave').addEventListener('click', async () => {
  showStatus('✅ 配置已保存！', 'ok');
  // 将 record_id 等信息存入 sessionStorage 供 content.js 使用
  const recordId = document.getElementById('recordId').value.trim();
  const style = document.getElementById('styleSelect').value;
  const color = document.getElementById('colorInput').value.trim();
  if (recordId) {
    sessionStorage.setItem('etsy_record_id', recordId);
    sessionStorage.setItem('etsy_style', style);
    sessionStorage.setItem('etsy_color', color);
    showStatus(`✅ 记录信息已保存：${recordId}`, 'ok');
  }
});

// ── 手动上传测试 ─────────────────────────────────────
document.getElementById('testFile').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  const resultBox = document.getElementById('testResult');
  resultBox.textContent = '⏳ 正在上传...';
  resultBox.style.color = '#666';

  try {
    const base64 = await fileToBase64(file);
    const result = await apiPost('/upload', { imageBase64: base64, filename: file.name });
    if (!result.success) throw new Error(result.error || '上传失败');

    lastUpload = { cdnUrl: result.cdnUrl, objectKey: result.objectKey, timestamp: Date.now() };

    // 自动填入 AI 触发卡片的 CDN URL
    document.getElementById('cdnUrlDisplay').textContent = result.cdnUrl;
    document.getElementById('cdnUrlDisplay').href = result.cdnUrl;
    document.getElementById('aiStatus').textContent = '📤 图片已上传，等待填写信息...';
    document.getElementById('aiStatus').style.color = '#666';

    resultBox.innerHTML = `✅ 上传成功！<br>
      <a href="${result.cdnUrl}" target="_blank" style="color:#1a73e8;font-size:11px;word-break:break-all">${result.cdnUrl}</a>`;
    resultBox.style.color = '#1e7e34';
  } catch (err) {
    resultBox.textContent = `❌ ${err.message}`;
    resultBox.style.color = '#c5221f';
  }
});

// ── 写入客户原图 ─────────────────────────────────────
document.getElementById('btnWriteTdx').addEventListener('click', async () => {
  const cdnUrl = lastUpload ? lastUpload.cdnUrl : document.getElementById('cdnUrlDisplay').textContent;
  const recordId = document.getElementById('recordId').value.trim();

  if (!cdnUrl || cdnUrl.startsWith('（等待上传')) {
    document.getElementById('aiStatus').textContent = '❌ 请先上传图片';
    document.getElementById('aiStatus').style.color = '#c5221f';
    return;
  }
  if (!recordId) {
    document.getElementById('aiStatus').textContent = '❌ 请输入记录ID（record_id）';
    document.getElementById('aiStatus').style.color = '#c5221f';
    return;
  }

  const btn = document.getElementById('btnWriteTdx');
  btn.disabled = true;
  btn.textContent = '⏳ 写入中...';
  document.getElementById('aiStatus').textContent = '⏳ 正在写入腾讯文档...';
  document.getElementById('aiStatus').style.color = '#666';

  try {
    const result = await apiPost('/write_tdocs', { record_id: recordId, cdnUrl });
    if (!result.success) throw new Error(result.error || '写入失败');

    document.getElementById('aiStatus').innerHTML =
      `✅ 已写入「客户原图」<br><span style="font-size:10px">imageID: ${result.imageID}</span>`;
    document.getElementById('aiStatus').style.color = '#1e7e34';
  } catch (err) {
    document.getElementById('aiStatus').textContent = `❌ ${err.message}`;
    document.getElementById('aiStatus').style.color = '#c5221f';
  } finally {
    btn.disabled = false;
    btn.textContent = '📤 写入客户原图';
  }
});

// ── 触发 AI 生图 ─────────────────────────────────────
document.getElementById('btnTriggerAi').addEventListener('click', async () => {
  const recordId = document.getElementById('recordId').value.trim();
  const style = document.getElementById('styleSelect').value;
  const color = document.getElementById('colorInput').value.trim();

  if (!recordId) {
    document.getElementById('aiStatus').textContent = '❌ 请输入记录ID（record_id）';
    document.getElementById('aiStatus').style.color = '#c5221f';
    return;
  }

  const btn = document.getElementById('btnTriggerAi');
  btn.disabled = true;
  btn.textContent = '⏳ AI生成中...';
  document.getElementById('aiStatus').textContent = '⏳ 正在生成 AI 图（约 30-60 秒）...';
  document.getElementById('aiStatus').style.color = '#666';

  try {
    const result = await apiPost('/trigger_ai', { record_id: recordId, style, color });
    if (!result.success) throw new Error(result.error || '生成失败');

    document.getElementById('aiStatus').innerHTML =
      `🎉 AI 图生成完成！<br><span style="font-size:10px">已回写到「AI生成粗略图」</span>`;
    document.getElementById('aiStatus').style.color = '#1e7e34';
  } catch (err) {
    document.getElementById('aiStatus').textContent = `❌ ${err.message}`;
    document.getElementById('aiStatus').style.color = '#c5221f';
  } finally {
    btn.disabled = false;
    btn.textContent = '✨ 立即生成 AI 图';
  }
});

// ── 监听来自 content.js 的上传成功消息 ────────────────
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'ETSY_UPLOAD_SUCCESS') {
    lastUpload = { cdnUrl: msg.cdnUrl, objectKey: msg.objectKey, timestamp: Date.now() };
    document.getElementById('cdnUrlDisplay').textContent = msg.cdnUrl;
    document.getElementById('cdnUrlDisplay').href = msg.cdnUrl;
    document.getElementById('aiStatus').textContent = '📤 图片已上传，可填写下方信息触发 AI 生成';
    document.getElementById('aiStatus').style.color = '#1a73e8';
  }
});

// ── 初始化 ──────────────────────────────────────────
(async () => {
  // 尝试从 health 端点检测服务器状态
  try {
    const resp = await fetch(`${LOCAL_SERVER}/health`);
    const data = await resp.json();
    if (data.sdk && data.tdx_configured && data.jimeng_configured) {
      document.getElementById('aiStatus').textContent = '✅ 服务器就绪，所有服务正常';
      document.getElementById('aiStatus').style.color = '#1e7e34';
    } else {
      const issues = [];
      if (!data.sdk) issues.push('COS SDK');
      if (!data.tdx_configured) issues.push('腾讯文档凭证');
      if (!data.jimeng_configured) issues.push('即梦凭证');
      document.getElementById('aiStatus').textContent = `⚠️ 部分服务未就绪: ${issues.join(', ')}`;
      document.getElementById('aiStatus').style.color = '#e67e22';
    }
  } catch {
    document.getElementById('aiStatus').textContent = '⚠️ 服务器未启动，请先运行 cos_proxy_server.py';
    document.getElementById('aiStatus').style.color = '#c5221f';
  }
})();
