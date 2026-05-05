# Etsy Open API v3 官方文档（中文译版）

> 原文来源：https://developers.etsy.com/documentation/  
> 整理时间：2026-04-01  
> 适用版本：Etsy Open API v3

---

## 目录

1. [API 概述](#1-api-概述)
2. [快速入门](#2-快速入门)
3. [认证与授权（OAuth 2.0）](#3-认证与授权oauth-20)
4. [请求规范](#4-请求规范)
5. [速率限制](#5-速率限制)
6. [权限范围（Scopes）完整列表](#6-权限范围scopes完整列表)
7. [主要接口端点速查](#7-主要接口端点速查)
8. [常用调用示例（Python）](#8-常用调用示例python)
9. [错误处理](#9-错误处理)
10. [重要注意事项](#10-重要注意事项)

---

## 1. API 概述

Etsy Open API v3 是一套 **REST 风格** 的官方接口，允许开发者通过程序访问 Etsy 平台的核心数据与功能，包括：

- 商品 Listing 的创建、读取、修改和删除
- 店铺信息查询与管理
- 订单查询与履行
- 收款与支付记录查询
- 买家信息访问（需授权）

### API 基础地址

```
https://api.etsy.com/v3/
```

或等效地址：

```
https://openapi.etsy.com/v3/
```

两个域名完全等效，可以互换使用。**所有请求必须使用 HTTPS。**

---

## 2. 快速入门

### 第一步：注册应用，获取 API Key

1. 访问 [Etsy 开发者后台](https://www.etsy.com/developers/your-apps)
2. 点击 **"Register a new app"** 创建应用
3. 填写应用名称、描述、用途等信息
4. 提交后，在应用管理页面获取两个关键凭证：
   - **API Key（Keystring）**：应用的唯一标识符
   - **Shared Secret**：与 API Key 配套的密钥

> ⚠️ API Key 需要通过 Etsy 审核后方可正常使用。

---

### 第二步：验证 API Key 是否有效

无需 OAuth，直接用 API Key 发一个 ping 请求：

**请求（GET）：**
```
GET https://api.etsy.com/v3/application/openapi-ping
```

**请求头：**
```
x-api-key: 你的API_Key
```

**成功响应（JSON）：**
```json
{
  "application_id": 1234
}
```

如果收到这个响应，说明你的 API Key 有效，可以开始调用公开接口了。

---

### 第三步：调用公开接口（无需登录授权）

公开接口（Public Endpoints）只需要 API Key，不需要用户授权，例如：

- 搜索商品 Listing
- 查看店铺公开信息
- 查看某个 Listing 的详细信息

**示例：查询某个 Listing**

```
GET https://api.etsy.com/v3/application/listings/{listing_id}
```

请求头加上 `x-api-key: 你的API_Key` 即可。

---

### 第四步：OAuth 授权（访问私有数据）

如果需要读取/修改自己的订单、库存、店铺设置等私有数据，则需要完成 OAuth 2.0 授权流程（详见第 3 章）。

---

## 3. 认证与授权（OAuth 2.0）

Etsy API v3 使用标准的 **OAuth 2.0 授权码模式**，并强制要求使用 **PKCE（Proof Key for Code Exchange）** 增强安全性。

### 完整授权流程（共 3 步）

---

#### 步骤 1：引导用户授权，获取授权码

将用户重定向到以下 URL（GET 请求）：

```
https://www.etsy.com/oauth/connect
```

**必须携带的 URL 参数：**

| 参数名 | 示例值 | 说明 |
|--------|--------|------|
| `response_type` | `code` | 固定值，不可修改 |
| `client_id` | `你的API_Key` | 你的 API Key |
| `redirect_uri` | `https://你的网站/callback` | 授权成功后跳转的地址（需与后台注册一致） |
| `scope` | `listings_r%20transactions_r` | 请求的权限，URL编码，多个权限用空格分隔 |
| `state` | `随机字符串` | 防 CSRF 攻击用，每次请求必须不同 |
| `code_challenge` | `PKCE生成的挑战码` | 由代码验证器派生 |
| `code_challenge_method` | `S256` | 固定值 |

**完整示例 URL：**
```
https://www.etsy.com/oauth/connect?response_type=code&client_id=your_api_key&redirect_uri=https://example.com/callback&scope=listings_r%20transactions_r&state=random_state_string&code_challenge=your_challenge&code_challenge_method=S256
```

用户同意后，Etsy 会跳转到你的 `redirect_uri`，并附带 `code` 参数：

```
https://example.com/callback?code=授权码&state=your_state
```

> ⚠️ **重要**：务必验证返回的 `state` 与你发送的完全一致，否则拒绝处理，防止 CSRF 攻击。

---

#### 步骤 2：用授权码换取 Access Token

向以下端点发起 **POST** 请求：

```
POST https://api.etsy.com/v3/public/oauth/token
```

**请求体（application/x-www-form-urlencoded）：**

| 参数名 | 值 |
|--------|-----|
| `grant_type` | `authorization_code` |
| `client_id` | 你的 API Key |
| `redirect_uri` | 与步骤 1 完全一致 |
| `code` | 步骤 1 获得的授权码 |
| `code_verifier` | 生成 `code_challenge` 时使用的原始验证器字符串 |

**成功响应（JSON）：**
```json
{
  "access_token": "12345678.abcdefghij...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "12345678.xxxxxx..."
}
```

| 字段 | 说明 |
|------|------|
| `access_token` | 调用 API 用的令牌，**有效期 1 小时（3600 秒）** |
| `refresh_token` | 刷新令牌，用于无需用户重新授权地获取新 access_token |
| `expires_in` | access_token 的有效秒数 |

> 💡 `access_token` 的前缀数字就是用户的 Etsy 用户 ID，例如 `12345678.xxx` 中 `12345678` 是用户 ID。

---

#### 步骤 3：调用需要授权的 API

在请求头中同时携带 API Key 和 Access Token：

```http
x-api-key: 你的API_Key
Authorization: Bearer 12345678.abcdefghij...
```

---

### 刷新 Access Token

Access Token 1小时后过期，用 Refresh Token 获取新的 Token（无需用户重新授权）：

```
POST https://api.etsy.com/v3/public/oauth/token
```

**参数：**
```
grant_type=refresh_token
client_id=你的API_Key
refresh_token=你的refresh_token
```

---

### PKCE 生成方法（Python 示例）

```python
import hashlib
import base64
import os

# 1. 生成代码验证器（43-128位随机字符串）
code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('utf-8')

# 2. 生成代码挑战（SHA256哈希后Base64编码）
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode('utf-8')).digest()
).rstrip(b'=').decode('utf-8')

print(f"code_verifier: {code_verifier}")
print(f"code_challenge: {code_challenge}")
```

---

## 4. 请求规范

### 请求头

| 请求头 | 示例 | 说明 |
|--------|------|------|
| `x-api-key` | `你的API_Key` | **必须**，所有请求都要带 |
| `Authorization` | `Bearer access_token` | 需要用户授权的接口必须带 |
| `Content-Type` | `application/json` | POST/PUT 请求时必须指定 |

### 编码规范

- 所有网络通信使用 **UTF-8 编码**
- 表单提交时需在 Content-Type 中声明字符集：  
  `application/x-www-form-urlencoded; charset=utf-8`

### 完整请求示例（curl）

```bash
# 公开接口（只需 API Key）
curl -X GET "https://api.etsy.com/v3/application/listings/12345" \
  -H "x-api-key: 你的API_Key"

# 私有接口（需要 OAuth 授权）
curl -X GET "https://api.etsy.com/v3/application/shops/my_shop/transactions" \
  -H "x-api-key: 你的API_Key" \
  -H "Authorization: Bearer 你的access_token"
```

---

## 5. 速率限制

Etsy API 有请求频率限制，超出后会返回 `429 Too Many Requests`。

**建议处理方式：**
- 在代码中捕获 429 响应，等待后重试（建议退避策略：1秒 → 2秒 → 4秒）
- 避免在循环中密集请求，每次请求间加适当延时（`time.sleep(0.1)`）
- 批量操作优先使用支持列表的接口（如 `getListings` 一次获取多个）

> 💡 具体限额数值 Etsy 未公开披露，建议保守估计，每秒不超过 10 次请求。

---

## 6. 权限范围（Scopes）完整列表

申请 OAuth 授权时，需要在 `scope` 参数中声明所需权限。权限需用空格分隔，并进行 URL 编码。

| Scope | 中文说明 |
|-------|---------|
| `address_r` | 读取用户收货地址 |
| `address_w` | 更新和删除用户收货地址 |
| `billing_r` | 读取账单和支付记录 |
| `cart_r` | 读取购物车内容 |
| `cart_w` | 添加/移除购物车商品 |
| `email_r` | 读取用户邮箱信息 |
| `favorites_r` | 查看用户收藏的商品和店铺 |
| `favorites_w` | 添加/移除收藏 |
| `feedback_r` | 查看用户反馈详情 |
| `listings_d` | **删除**用户的 Listing |
| `listings_r` | **读取**非公开 Listing（下架、过期等） |
| `listings_w` | **创建和编辑** Listing |
| `profile_r` | 读取用户私人资料 |
| `profile_w` | 更新用户私人资料 |
| `recommend_r` | 查看推荐商品 |
| `recommend_w` | 移除推荐商品 |
| `shops_r` | 查看店铺信息（包括未公开信息） |
| `shops_w` | 更新店铺描述、消息和分类 |
| `transactions_r` | **读取**购买和销售订单数据 |
| `transactions_w` | **更新**销售数据 |

**推荐组合（Etsy卖家日常运营）：**
```
listings_r listings_w transactions_r shops_r shops_w
```

URL 编码写法：
```
listings_r%20listings_w%20transactions_r%20shops_r%20shops_w
```

---

## 7. 主要接口端点速查

### 7.1 Listing（商品）接口

| 方法 | 接口路径 | 说明 | 是否需要认证 |
|------|---------|------|------------|
| GET | `/application/listings/{listing_id}` | 查询单个 Listing | 否 |
| GET | `/application/listings/active` | 获取所有在售 Listing | 否 |
| GET | `/application/shops/{shop_id}/listings` | 获取店铺所有 Listing | 否 |
| GET | `/application/shops/{shop_id}/listings/active` | 获取店铺在售 Listing | 否 |
| POST | `/application/shops/{shop_id}/listings` | 创建新 Listing | 是（`listings_w`）|
| PUT | `/application/shops/{shop_id}/listings/{listing_id}` | 更新 Listing | 是（`listings_w`）|
| DELETE | `/application/shops/{shop_id}/listings/{listing_id}` | 删除 Listing | 是（`listings_d`）|

---

### 7.2 Shop（店铺）接口

| 方法 | 接口路径 | 说明 | 是否需要认证 |
|------|---------|------|------------|
| GET | `/application/shops/{shop_id}` | 查询店铺信息 | 否 |
| GET | `/application/users/{user_id}/shops` | 获取用户店铺列表 | 是（`shops_r`）|
| PUT | `/application/shops/{shop_id}` | 更新店铺信息 | 是（`shops_w`）|

---

### 7.3 Transaction（订单）接口

| 方法 | 接口路径 | 说明 | 是否需要认证 |
|------|---------|------|------------|
| GET | `/application/shops/{shop_id}/transactions` | 获取店铺所有订单 | 是（`transactions_r`）|
| GET | `/application/shops/{shop_id}/transactions/{transaction_id}` | 查询单个订单 | 是（`transactions_r`）|
| GET | `/application/shops/{shop_id}/receipts` | 获取收据列表 | 是（`transactions_r`）|
| GET | `/application/shops/{shop_id}/receipts/{receipt_id}` | 查询单个收据 | 是（`transactions_r`）|

---

### 7.4 User（用户）接口

| 方法 | 接口路径 | 说明 | 是否需要认证 |
|------|---------|------|------------|
| GET | `/application/users/{user_id}` | 获取用户信息 | 是（`profile_r`）|

---

### 7.5 其他常用接口

| 方法 | 接口路径 | 说明 | 是否需要认证 |
|------|---------|------|------------|
| GET | `/application/openapi-ping` | 验证 API Key 是否有效 | 否 |
| POST | `/public/oauth/token` | 获取/刷新 Access Token | 否 |

---

## 8. 常用调用示例（Python）

### 安装依赖

```bash
pip install requests
```

---

### 示例 1：验证 API Key（无需授权）

```python
import requests

API_KEY = "你的API_Key"

response = requests.get(
    "https://api.etsy.com/v3/application/openapi-ping",
    headers={"x-api-key": API_KEY}
)

print(response.json())  # 输出: {"application_id": 1234}
```

---

### 示例 2：查询店铺信息（无需授权）

```python
import requests

API_KEY = "你的API_Key"
SHOP_ID = "你的店铺名或ID"  # 例如 "MyEtsyShop"

response = requests.get(
    f"https://api.etsy.com/v3/application/shops/{SHOP_ID}",
    headers={"x-api-key": API_KEY}
)

if response.status_code == 200:
    shop = response.json()
    print(f"店铺名：{shop['shop_name']}")
    print(f"总销量：{shop['transaction_sold_count']}")
    print(f"粉丝数：{shop['num_favorers']}")
else:
    print(f"请求失败：{response.status_code}", response.text)
```

---

### 示例 3：查询店铺在售 Listing 列表（无需授权）

```python
import requests

API_KEY = "你的API_Key"
SHOP_ID = "你的店铺名或ID"

response = requests.get(
    f"https://api.etsy.com/v3/application/shops/{SHOP_ID}/listings/active",
    headers={"x-api-key": API_KEY},
    params={
        "limit": 25,      # 每页最多25条（最大100）
        "offset": 0       # 分页偏移
    }
)

if response.status_code == 200:
    data = response.json()
    print(f"共 {data['count']} 个在售商品")
    for item in data['results']:
        print(f"- [{item['listing_id']}] {item['title'][:50]}... 价格: ${item['price']['amount'] / item['price']['divisor']:.2f}")
else:
    print(f"失败：{response.status_code}")
```

---

### 示例 4：查询订单列表（需要 OAuth 授权）

```python
import requests

API_KEY = "你的API_Key"
ACCESS_TOKEN = "你的access_token"  # 通过 OAuth 流程获取
SHOP_ID = "你的店铺名或ID"

headers = {
    "x-api-key": API_KEY,
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

response = requests.get(
    f"https://api.etsy.com/v3/application/shops/{SHOP_ID}/transactions",
    headers=headers,
    params={"limit": 25, "offset": 0}
)

if response.status_code == 200:
    data = response.json()
    for order in data['results']:
        print(f"订单 {order['transaction_id']}: {order['title']}")
        print(f"  买家ID: {order['buyer_user_id']}")
        print(f"  金额: ${order['price']['amount'] / order['price']['divisor']:.2f}")
        print(f"  时间: {order['create_timestamp']}")
```

---

### 示例 5：搜索某关键词的商品（用于市场调研）

```python
import requests

API_KEY = "你的API_Key"

# 注意：搜索接口通过 findAllListingsActive 端点
response = requests.get(
    "https://openapi.etsy.com/v3/application/listings/active",
    headers={"x-api-key": API_KEY},
    params={
        "keywords": "personalized tie clip",  # 搜索关键词
        "limit": 25,
        "sort_on": "score",       # 相关度排序
        "min_price": 15,
        "max_price": 50
    }
)

if response.status_code == 200:
    data = response.json()
    for item in data['results']:
        price = item['price']['amount'] / item['price']['divisor']
        print(f"标题: {item['title'][:60]}")
        print(f"价格: ${price:.2f} | 收藏: {item['num_favorers']}")
        print(f"链接: {item['url']}")
        print("---")
```

---

## 9. 错误处理

| HTTP 状态码 | 含义 | 处理建议 |
|------------|------|---------|
| `200 OK` | 请求成功 | 正常处理响应数据 |
| `400 Bad Request` | 请求参数有误 | 检查参数格式和必填字段 |
| `401 Unauthorized` | 未授权 | 检查 API Key 或 Access Token |
| `403 Forbidden` | 无权访问 | 检查是否申请了对应的 Scope 权限 |
| `404 Not Found` | 资源不存在 | 检查 listing_id / shop_id 是否正确 |
| `429 Too Many Requests` | 请求过于频繁 | 暂停请求，等待后重试 |
| `500 Internal Server Error` | Etsy 服务器错误 | 稍后重试 |

**Python 通用错误处理示例：**

```python
import requests
import time

def safe_request(url, headers, params=None, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            wait_time = 2 ** attempt  # 指数退避：1s, 2s, 4s
            print(f"请求限频，等待 {wait_time} 秒后重试...")
            time.sleep(wait_time)
        else:
            print(f"请求失败 [{response.status_code}]: {response.text}")
            return None
    return None
```

---

## 10. 重要注意事项

### 合规要求

1. **必须标注免责声明**：在任何使用了 Etsy API 数据的页面或应用中，必须显著标注：
   > "Etsy 是 Etsy, Inc. 的商标。本应用使用 Etsy API，但未经 Etsy, Inc. 认可或认证。"

2. **禁止屏幕抓取**：不允许使用爬虫、Playwright 等方式绕过 API 抓取 Etsy 数据。

3. **数据不得再分发**：API 获取的数据只能用于申请时说明的用途，不能转售或对外开放。

---

### 账号休眠规则

> 应用在 **6 个月内无任何成功 API 请求**，会被标记为「休眠」状态，之后将无法继续使用。

建议定期发一次 ping 请求保持活跃。

---

### 访问类型区别

| 类型 | 说明 | 适合谁 |
|------|------|--------|
| **个人访问** | 默认授权，读写最多 5 个店铺 | Etsy 卖家管理自己店铺 |
| **商业访问** | 需额外申请，可为任意卖家服务 | SaaS 工具、第三方服务商 |

---

### 个人卖家推荐使用流程

```
1. 用 API Key 直接调用公开接口（搜索、查看竞品 Listing）
         ↓
2. 完成 OAuth 授权，获取自己店铺的 Access Token
         ↓
3. 用 Access Token 查询自己的订单、库存、店铺数据
         ↓
4. 定期用 Refresh Token 刷新 Access Token（无需重复授权）
```

---

## 参考链接

| 资源 | 链接 |
|------|------|
| 官方开发者文档首页 | https://developers.etsy.com/documentation/ |
| OAuth 认证详情 | https://developers.etsy.com/documentation/essentials/authentication |
| 快速入门教程 | https://developers.etsy.com/documentation/tutorials/quickstart |
| API Reference（接口列表） | https://developers.etsy.com/documentation/reference/ |
| 开发者后台（管理 App） | https://www.etsy.com/developers/your-apps |

---

*文档版本：2026-04-01 | 基于 Etsy Open API v3 官方文档整理*
