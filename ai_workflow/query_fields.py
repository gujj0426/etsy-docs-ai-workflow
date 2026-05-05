import json, urllib.request, urllib.error

cfg = json.load(open('/Users/mac/Desktop/etsy/运营文档/config/tdocs_openapi_v2.json'))
TOKEN   = cfg['access_token']
CLIENT  = cfg['client_id']
OPEN_ID = cfg['open_id']

file_id  = "KFoUkmaZFqLP"
sheet_id = "tbfaTE"

url = f"https://docs.qq.com/openapi/smartbook/v2/files/300000000${file_id}/sheets/{sheet_id}/fields"
headers = {'Access-Token': TOKEN, 'Client-Id': CLIENT, 'Open-Id': OPEN_ID}
req = urllib.request.Request(url, headers=headers, method='GET')
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode('utf-8'))
    print(json.dumps(result, ensure_ascii=False, indent=2)[:5000])
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode()[:500]}")
except Exception as e:
    print(f"错误：{e}")
