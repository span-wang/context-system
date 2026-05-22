# 小红书备考资料生产工具

一个本地优先的备考资料内容生产工具，支持两种模式：

- 模式 A：连接 RAGFlow 个人知识库，按学科、类目、章节检索资料后生成。
- 模式 B：从本地素材库选择资料，或只填写学科信息直接生成。

当前 MVP 已包含 FastAPI 后端、Next.js 前端、素材库、6 种内容类型、生成历史和内容审查报告。内容审查支持纯大模型、仅依据文档、混合审查三种模式。没有 LLM Key 时会使用本地模板链路跑通流程；后续可接入 Claude/OpenAI 兼容接口。
在 `/settings` 配置 DeepSeek、OpenAI 兼容接口或 Anthropic 后，新建的生成任务会走对应模型；本地模板/本地规则仍可作为无 Key 兜底。
配置页支持维护统一模型库，并为生成、审查、试卷 AI 切题、题目补全标准化、自动考点标注等功能分别选择要使用的模型。

## 本地启动

### 一键启动

Windows 下直接双击根目录的 `一键启动.bat`。脚本会自动检查依赖、启动后端和前端，并打开浏览器。
当前默认会先带起项目本地 MySQL，再启动 API 和前端。

停止服务时双击 `一键停止.bat`。

如需使用外部 LLM，可复制 `.env.example` 为 `.env`，填写 `DEEPSEEK_GENERATOR_API_KEY`、`DEEPSEEK_REVIEWER_API_KEY` 或通用的 `DEEPSEEK_API_KEY` 后重新启动。后端会按 `.env.local` > `.env` > `.evn` 的优先级读取本地环境文件；`.evn` 仅用于兼容拼写误差，建议统一使用 `.env`。

高级参数：

```powershell
& .\scripts\start.ps1 -ApiPort 8000 -WebPort 3000
& .\scripts\start.ps1 -NoInstall -NoBrowser
& .\scripts\stop.ps1 -AlsoKnownPorts
```

如需远程访问前端，推荐配置 `deploy\cloudflare\config.yml` 后直接运行 `scripts\start.ps1`。
启动脚本会自动识别 tunnel hostname，把它注入 Next.js 的远程 origin 白名单，并在控制台与平台设置页显示公网地址。

### 后端

```powershell
cd apps/api
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### MySQL 迁移

推荐把迁移和启动拆开执行，先把数据库迁移到目标 revision，再决定是否带种子启动应用。

```powershell
# 使用当前 DB_URL 执行迁移
powershell -ExecutionPolicy Bypass -File .\scripts\db-migrate.ps1

# 启动项目自管 MySQL，迁移到 head，并写入种子数据
powershell -ExecutionPolicy Bypass -File .\scripts\db-migrate.ps1 -UseLocalMySql -MySqlPort 3309 -MySqlDatabase exam_kit_local -SeedData

# 只查看迁移状态，不重复执行 upgrade
powershell -ExecutionPolicy Bypass -File .\scripts\db-migrate.ps1 -UseLocalMySql -SkipMigrate

# 把旧 SQLite 数据导入本地 MySQL
powershell -ExecutionPolicy Bypass -File .\scripts\migrate-sqlite-to-mysql.ps1 -TruncateTarget
```

迁移相关环境变量：

- `DB_URL`
- `DB_AUTO_MIGRATE`
- `DB_SEED_ON_STARTUP`
- `DB_MIGRATION_TARGET`

说明：

- `DB_AUTO_MIGRATE=true` 时，API 启动会自动执行迁移。
- `DB_SEED_ON_STARTUP=true` 时，空库启动会自动写入演示数据。
- `DB_MIGRATION_TARGET` 默认为 `head`，用于预留后续按 revision 灰度迁移的入口。
- `/platform/api/system/status` 现在会返回 Alembic 当前 revision、head revision、迁移状态和数据库连通性，可直接用来判断迁移链路是否健康。

说明：
- 素材库现在支持上传 `PDF / 图片 / DOCX / Markdown / TXT`。
- 普通 PDF 会优先提取可选中文本；扫描版 PDF 和图片会自动尝试 OCR。
- 系统默认使用 `PaddleOCR` 做 PDF OCR，默认模型为 `PP-OCRv5_server_det` + `PP-OCRv5_server_rec`；`PyMuPDF` 仍用于可选中文本直提。
- `PDF_OCR_ENGINE` 保留为兼容配置项，默认值为 `paddle`。
- 大 PDF 会按页段解析，默认每批 `4` 页；试卷中心和素材库前端可调每批页数，也可通过 `PDF_PARSE_PAGE_CHUNK_SIZE` 设置默认值。
- OCR/版面解析会按页写入 `data/cache/pdf_ocr_checkpoints`，任务中断后再次用相同解析参数会复用已完成页继续解析。
- API 启动后会后台定时巡检 `data/cache/pdf_ocr_checkpoints`，自动删除已经失联的 OCR/版面缓存目录；巡检日志会写入 API 日志输出，可在 `data/logs/api.out.log` / `data/logs/api.err.log` 中查看。
- 可通过 `OCR_CACHE_SWEEP_ENABLED`、`OCR_CACHE_SWEEP_INTERVAL_SECONDS`、`OCR_CACHE_SWEEP_RUN_ON_STARTUP` 调整巡检开关、间隔和启动即执行行为。
- 如果机器性能不足，可在环境变量中把 `PDF_OCR_DETECTION_MODEL` / `PDF_OCR_RECOGNITION_MODEL` 改回 `PP-OCRv5_mobile_det` / `PP-OCRv5_mobile_rec`，或关闭 `PDF_OCR_USE_TEXTLINE_ORIENTATION`。
- 如果扫描件预览仍为空，通常是图片清晰度过低，或 OCR 依赖没有安装成功。

### 前端

```powershell
cd apps/web
npm install
npm run dev
```

打开 http://localhost:3000。

## 主要页面

- `/library`：上传、筛选、预览和管理素材。
- `/workflow`：管理选题库、内容日历、审核状态、责任人、素材引用和版本记录，并串起生成、审查、确认、导出发布包。
- `/generate`：选择模式 A/RAGFlow 或模式 B/直通生成，提交生成任务。
- `/history`：查看生成历史、小红书发布包和审查报告。
- `/settings`：在前端维护模型库，并为各功能选择使用的模型。

如果你已经不再保留 SQLite 作为运行库，后续只需要维护 MySQL；`data/app.db` 仅作为一次性历史数据源。

## 数据位置

- 文件：`data/library/{yyyymm}/{sha256}.{ext}`
- 解析缓存：`data/cache/parsed/{sha256}.txt`
- 本地 MySQL：`data/mysql-local-3309/`
- 旧 SQLite 导入源：`data/app.db`

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
- `GET /api/generate/{id}/export?format=md`（导出 Markdown 格式的小红书发布包）
- `GET /api/workflow/topics`
- `POST /api/workflow/topics`
- `PATCH /api/workflow/topics/{id}`
- `POST /api/workflow/topics/{id}/generate`
- `POST /api/workflow/topics/{id}/review`
- `POST /api/workflow/topics/{id}/confirm`
- `POST /api/workflow/topics/{id}/export`
- `GET /api/workflow/topics/{id}/events`
- `GET /api/history`
- `GET /api/system/config`
- `POST /api/system/config`
- `POST /api/system/test-llm`
- `POST /api/system/llm-models`
- `DELETE /api/system/llm-models/{model_id}`
- `POST /api/system/llm-presets`
- `POST /api/system/llm-presets/{preset_name}/apply`
- `DELETE /api/system/llm-presets/{preset_name}`
- `GET /api/system/healthz`
