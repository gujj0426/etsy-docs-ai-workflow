// content.js - 注入到 docs.qq.com
// 拦截图片上传，通过本地服务器中转上传到 COS

(function () {
  'use strict';

  const LOCAL_SERVER = 'http://localhost:8765';
  const TARGET_FIELD_NAME = '客户原图';
  const STATUS_MS = 4000;

  // ─── Toast ────────────────────────────────────────────────────
  let toastEl = null;
  function showToast(message, type = 'info') {
    if (!toastEl) {
      toastEl = document.createElement('div');
      toastEl.id = 'etsy-cos-toast';
      Object.assign(toastEl.style, {
        position: 'fixed', top: '20px', left: '50%', transform: 'translateX(-50%)',
        zIndex: 999999, padding: '10px 20px', borderRadius: '8px',
        fontSize: '14px', fontFamily: 'sans-serif', maxWidth: '400px',
        textAlign: 'center', boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
        transition: 'opacity 0.3s ease', pointerEvents: 'none',
        color: '#fff', background: '#333',
      });
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = message;
    toastEl.style.background = type === 'success' ? '#27ae60' :
      type === 'error' ? '#e74c3c' : '#2c3e50';
    toastEl.style.opacity = '1';
    clearTimeout(toastEl._timer);
    toastEl._timer = setTimeout(() => { toastEl.style.opacity = '0'; }, STATUS_MS);
  }

  // ─── 文件读取 ─────────────────────────────────────────────────
  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  // ─── 通过本地服务器上传 ───────────────────────────────────────
  async function uploadViaServer(imageBase64, filename) {
    const response = await fetch(`${LOCAL_SERVER}/upload`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ imageBase64, filename }),
    });
    const result = await response.json();
    if (!result.success) throw new Error(result.error || '上传失败');
    return result;
  }

  // ─── 拦截 input[type=file] ────────────────────────────────────
  const seenInputs = new WeakSet();
  const observer = new MutationObserver(() => {
    document.querySelectorAll('input[type="file"]').forEach(input => {
      if (!seenInputs.has(input)) {
        seenInputs.add(input);
        input.addEventListener('change', async () => {
          for (const file of input.files || []) {
            if (!file.type.startsWith('image/')) continue;
            showToast('正在上传图片到 COS...', 'info');
            try {
              const base64 = await fileToBase64(file);
              const result = await uploadViaServer(base64, file.name);
              showToast(`✅ COS 上传成功: ${result.cdnUrl.split('/').pop()}`, 'success');
            } catch (err) {
              showToast(`❌ ${err.message}`, 'error');
            }
            // 通知 popup 上传成功（自动显示 CDN URL）
            try {
              chrome.runtime.sendMessage({
                type: 'ETSY_UPLOAD_SUCCESS',
                cdnUrl: result.cdnUrl,
                objectKey: result.objectKey,
              });
            } catch (_) {}
          }
        }, true);
      }
    });
  });
  observer.observe(document.body || document.documentElement, { childList: true, subtree: true });

  console.log('[Etsy COS 插件] 已加载，等待上传...');
})();
