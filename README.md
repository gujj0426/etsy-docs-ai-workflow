# Etsy 运营 / AI 工作流

腾讯文档智能表格 → 客户原图 → [腾讯云 SCF] → 火山即梦图生图 → 回写「AI生成粗略图」。

## 目录说明

| 路径 | 说明 |
|------|------|
| `ai_workflow/` | SCF 生产脚本、`pack_and_deploy_scf.py` 部署、`scf_pipeline.py` 主流程 |
| `browser_extension/` | `docs.qq.com` 配套浏览器扩展（本地 COS 代理上传） |
| `config/` | **仅存本地**：复制 `tdocs_openapi_v2.example.json` → `tdocs_openapi_v2.json`（勿提交） |

## 环境变量（云函数 / 本地）

**腾讯云（部署脚本、COS、运维脚本）**

- `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`  
  （亦可使用别名 `TENCENT_SECRET_ID` / `TENCENT_SECRET_KEY`，COS 相关也可用 `COS_SECRET_ID` / `COS_SECRET_KEY`。）

**云函数 `etsy-ai-workflow` 运行时**

- `OA2_ACCESS_TOKEN`、`OA2_CLIENT_ID`、`OA2_OPEN_ID`
- `OA2_STORAGE_FILE_ID`（可选）
- `JIMENG_AK`、`JIMENG_SK`

详见 `ai_workflow/pack_and_deploy_scf.py` 内注释。

## 部署到 SCF

```bash
cd ai_workflow
export TENCENTCLOUD_SECRET_ID="..."
export TENCENTCLOUD_SECRET_KEY="..."
python3 pack_and_deploy_scf.py
```

## 推送到 GitHub（GitHub CLI）

已安装 `gh` 后，在本仓库根目录执行：

```bash
./scripts/gh_first_push.sh              # 默认创建公开仓库 etsy-docs-ai-workflow 并推送
./scripts/gh_first_push.sh 你的仓库名
GITHUB_REPO_VISIBILITY=private ./scripts/gh_first_push.sh 私有仓库名
```

首次运行若未登录，脚本会启动浏览器 OAuth（`gh auth login --web`）。

## 许可证

内部运营项目；第三方 SDK 遵循各自许可证。
