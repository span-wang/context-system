# 小红书备考资料生产工具

一个本地优先的备考资料内容生产工具，支持两种模式：

- 模式 A：连接 RAGFlow 个人知识库，按学科、类目、章节检索资料后生成。
- 模式 B：从本地素材库选择资料，或只填写学科信息直接生成。

当前 MVP 已包含 FastAPI 后端、Next.js 前端、素材库、6 种内容类型、生成历史和内容审查报告。内容审查支持纯大模型、仅依据文档、混合审查三种模式。没有 LLM Key 时会使用本地模板链路跑通流程；后续可接入 Claude/OpenAI 兼容接口。
在 `/settings` 配置 DeepSeek、OpenAI 兼容接口或 Anthropic 后，新建的生成任务会走对应模型；本地模板/本地规则仍可作为无 Key 兜底。
配置页支持把一组 LLM 参数保存成预设，后续可一键切换到生成模型或审查模型。

## 本地启动

### 一键启动

Windows 下直接双击根目录的 `一键启动.bat`。脚本会自动检查依赖、启动后端和前端，并打开浏览器。

停止服务时双击 `一键停止.bat`。

如需使用外部 LLM，可复制 `.env.example` 为 `.env`，填写 `DEEPSEEK_GENERATOR_API_KEY`、`DEEPSEEK_REVIEWER_API_KEY` 或通用的 `DEEPSEEK_API_KEY` 后重新启动。后端会按 `.env.local` > `.env` > `.evn` 的优先级读取本地环境文件；`.evn` 仅用于兼容拼写误差，建议统一使用 `.env`。

高级参数：

```powershell
& .\scripts\start.ps1 -ApiPort 8000 -WebPort 3000
& .\scripts\start.ps1 -NoInstall -NoBrowser
& .\scripts\stop.ps1 -AlsoKnownPorts
```

### 后端

```powershell
cd apps/api
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 前端

```powershell
cd apps/web
npm install
npm run dev
```

打开 http://localhost:3000。

## 主要页面

- `/library`：上传、筛选、预览和管理素材。
- `/generate`：选择模式 A/RAGFlow 或模式 B/直通生成，提交生成任务。
- `/history`：查看生成历史、Markdown 结果和审查报告。
- `/settings`：在前端配置生成模型和审查模型。

## 数据位置

- 文件：`data/library/{yyyymm}/{sha256}.{ext}`
- 解析缓存：`data/cache/parsed/{sha256}.txt`
- SQLite：`data/app.db`

## API

- `POST /api/library/upload`
- `GET /api/library/files`
- `GET /api/library/files/{id}/preview`
- `PATCH /api/library/files/{id}`
- `DELETE /api/library/files/{id}`
- `POST /api/generate`
- `POST /api/generate/multipart`
- `GET /api/generate/{id}/stream`
- `GET /api/generate/{id}`
- `POST /api/generate/{id}/review`，可传 `{ "mode": "llm_only" | "document_only" | "hybrid" }`
- `GET /api/generate/{id}/export?format=md`
- `GET /api/history`
- `GET /api/system/config`
- `POST /api/system/config`
- `POST /api/system/subjects`
- `POST /api/system/test-llm`
- `POST /api/system/llm-presets`
- `POST /api/system/llm-presets/{preset_name}/apply`
- `DELETE /api/system/llm-presets/{preset_name}`
- `GET /api/system/healthz`
