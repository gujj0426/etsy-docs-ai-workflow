#!/usr/bin/env python3
"""
Google OAuth 授权脚本 - 获取 Refresh Token
纯标准库实现，无需安装任何第三方依赖

用法：
  python3 get_refresh_token.py
  （双击 .command 文件直接运行）
"""

import json
import urllib.parse
import urllib.request
import http.server
import webbrowser
import threading
import sys
import os

# ─────────────────────────────────────────────
# 读取凭据
# ─────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(SCRIPT_DIR, "google_credentials.json")
TOKEN_OUTPUT_PATH = os.path.join(SCRIPT_DIR, "google_tokens.json")

with open(CREDENTIALS_PATH) as f:
    creds = json.load(f)

client_id     = creds["web"]["client_id"]
client_secret = creds["web"]["client_secret"]
redirect_uri  = "http://localhost:8080"

# ─────────────────────────────────────────────
# OAuth 参数
# ─────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.install",
]

auth_url = (
    "https://accounts.google.com/o/oauth2/auth?"
    + urllib.parse.urlencode({
        "client_id":     client_id,
        "redirect_uri":  redirect_uri,
        "scope":         " ".join(SCOPES),
        "response_type": "code",
        "access_type":  "offline",
        "prompt":        "consent",
    })
)

# ─────────────────────────────────────────────
# 本地回调服务器
# ─────────────────────────────────────────────
auth_code    = None
server_ready = threading.Event()

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        if "code=" in self.path:
            parsed  = urllib.parse.urlparse(self.path)
            params  = urllib.parse.parse_qs(parsed.query)
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<html><body>"
                "<h2>✅ 授权成功！可以关闭此窗口了。</h2>"
                "<p>请回到终端窗口查看 Refresh Token。</p>"
                "<script>window.close()</script>"
                "</body></html>".encode()
            )
            server_ready.set()
        elif "error=" in self.path:
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<html><body><h2>❌ 授权被拒绝</h2>"
                "<p>请回到终端窗口重试。</p>"
                "<script>window.close()</script>"
                "</body></html>".encode()
            )
            server_ready.set()
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing code parameter")

    def log_message(self, *args):
        pass  # 静默日志

def run_server():
    server = http.server.HTTPServer(("localhost", 8080), Handler)
    server.handle_request()
    server.server_close()

# ─────────────────────────────────────────────
# 启动服务器 + 打开浏览器
# ─────────────────────────────────────────────
server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

print("=" * 50)
print("  Google Drive OAuth 授权")
print("=" * 50)
print()
print("  1. 浏览器将自动打开（若未打开，请手动访问下方链接）")
print()
print("  " + auth_url)
print()
print("  2. 登录 Google 账号，点击「允许授权」")
print("  3. 等待页面提示「授权成功」后，切换回本窗口")
print()
webbrowser.open(auth_url)

# ─────────────────────────────────────────────
# 等待授权回调
# ─────────────────────────────────────────────
print("  ⏳ 等待授权回调...")
server_ready.wait(timeout=180)

if not auth_code:
    print()
    print("❌ 授权超时（3分钟），请重试")
    sys.exit(1)

print("  ✅ 收到授权码，正在换取 Token...")

# ─────────────────────────────────────────────
# 用 urllib 换 Token（无第三方依赖）
# ─────────────────────────────────────────────
token_data = urllib.parse.urlencode({
    "code":          auth_code,
    "client_id":     client_id,
    "client_secret": client_secret,
    "redirect_uri":  redirect_uri,
    "grant_type":    "authorization_code",
}).encode("utf-8")

req = urllib.request.Request(
    "https://oauth2.googleapis.com/token",
    data=token_data,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    method="POST"
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        tokens = json.loads(resp.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    err_body = e.read().decode("utf-8")
    print(f"❌ 获取 Token 失败（HTTP {e.code}）：{err_body}")
    sys.exit(1)

refresh_token = tokens.get("refresh_token")
access_token = tokens.get("access_token")

if not refresh_token:
    print("❌ 未收到 refresh_token")
    print(f"   收到内容：{json.dumps(tokens, indent=2)}")
    print()
    print("💡 提示：若之前已授权过，请到以下地址撤销授权后重试：")
    print("   https://myaccount.google.com/permissions")
    sys.exit(1)

# ─────────────────────────────────────────────
# 保存 Token
# ─────────────────────────────────────────────
token_json = {
    "client_id":     client_id,
    "client_secret": client_secret,
    "refresh_token": refresh_token,
    "access_token":  access_token,
}

with open(TOKEN_OUTPUT_PATH, "w") as f:
    json.dump(token_json, f, indent=2)

# ─────────────────────────────────────────────
# 完成输出
# ─────────────────────────────────────────────
print()
print("=" * 50)
print("  ✅ 授权成功！")
print("=" * 50)
print()
print(f"📁 文件已保存：{TOKEN_OUTPUT_PATH}")
print()
print("【请复制以下三个值，配置到腾讯云 SCF 环境变量】")
print("-" * 50)
print(f"GOOGLE_CLIENT_ID     = {client_id}")
print(f"GOOGLE_CLIENT_SECRET = {client_secret}")
print(f"GOOGLE_REFRESH_TOKEN = {refresh_token}")
print("-" * 50)
print()
print("✅ 全部完成！可以关闭本窗口。")
