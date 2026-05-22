# Paper Parser Dataset Workflow

这套流程先解决当前项目里最容易提升的一层：

- 用现有 `asset.parsed_text` 导出切题样本
- 人工修正 `gold.json`
- 用回归脚本评估当前解析器
- 再决定是继续改规则，还是把 OCR 微调结果接回运行时

现在试卷解析成功后，会自动把样本导入到数据集目录，不需要再手动跑导出脚本。

## 1. 导出样本

### 1.1 自动导入

当前默认行为：

- 只要试卷解析流程跑完并完成入库，不管切题结果如何
- 系统就会自动在 `data/paper_parser_dataset/` 下更新对应样本目录
- 已存在的 `gold.json` 不会被覆盖
- `gold.template.json / prediction.json / source.txt / meta.json` 会同步刷新

默认环境变量：

```powershell
PAPER_DATASET_AUTO_EXPORT=true
PAPER_DATASET_AUTO_INIT_GOLD=true
PAPER_DATASET_INCLUDE_SOURCE=false
```

可选覆盖：

```powershell
$env:PAPER_DATASET_ROOT="D:\\paper_parser_dataset"
```

### 1.2 手动补导

在仓库根目录执行：

```powershell
python .\scripts\export_paper_dataset.py --limit 20 --needs-review-only --init-gold
```

常用参数：

- `--paper-id 123`
  导出指定试卷，可重复传多次
- `--needs-review-only`
  只导出当前已经被标成 `needs_review` 的试卷
- `--include-source`
  把原始 PDF / 图片 / 文档一起复制到样本目录
- `--init-gold`
  首次导出时自动生成 `gold.json`
- `--overwrite-gold`
  配合 `--init-gold` 使用，覆盖已有 `gold.json`

默认输出目录：

```text
data/paper_parser_dataset/
```

每个样本目录会生成：

```text
paper_000123_xxx/
  source.txt
  meta.json
  prediction.json
  gold.template.json
  gold.json              # 仅在 --init-gold 时生成
  raw/                   # 仅在 --include-source 时生成
```

## 2. 标注规则

`gold.json` 是人工修正后的标准答案。

根结构：

```json
{
  "version": 1,
  "label_status": "draft",
  "notes": "",
  "sections": []
}
```

每个 section：

```json
{
  "title": "单项选择题",
  "section_type": "single_choice",
  "questions": []
}
```

每道题：

```json
{
  "question_no": "1",
  "question_type": "single_choice",
  "stem_text": "题干",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "answer_text": "A",
  "analysis_text": "解析"
}
```

建议只改这几类错误：

- 分区错
- 题号错
- 题型错
- 题干缺段或串题
- 选项拆错
- 答案/解析抽取错

## 3. 回归评估

原 `scripts/eval_paper_parser.py` 已下线。规则切题链路已经移除，仓库不再支持 `source.txt -> 规则 prediction` 的批量回归评估。

当前建议：

- 继续使用 `scripts/export_paper_dataset.py` 导出最新 `ai_prediction`、`gold.template.json` 和 `meta.json`
- 在样本目录中对照 `gold.json` 与 `gold.template.json` 做人工复核
- 需要端到端验证时，直接走试卷解析 API 或前端页面链路

当前这套样本更适合做结构性回归和人工抽检，而不是继续维护旧的规则评估分数。

## 4. 训练结果如何反哺

### 4.1 先反哺切题规则

如果错主要集中在 `section / question_no / stem / options`，优先改：

- `apps/api/app/services/papers.py`

重点函数：

- `_split_paper_sections`
- `_split_question_blocks`
- `_parse_question_block`

这是当前项目里收益最高、落地最快的一步。

### 4.2 再反哺 OCR 模型

如果你后面做了 PaddleOCR 微调，并导出了本地模型目录，可以通过环境变量切回主流程：

```powershell
$env:PDF_OCR_DETECTION_MODEL_DIR="C:\\models\\det"
$env:PDF_OCR_RECOGNITION_MODEL_DIR="C:\\models\\rec"
```

当前运行时会优先读取这两个目录覆盖默认模型名，入口在：

- `apps/api/library/pdf_ocr_pipeline.py`
- `apps/api/library/parser.py`

这意味着训练链路可以独立跑，API 仍然只负责推理。

## 5. 推荐节奏

建议先标 30 到 50 份最差样本：

- 先把规则切题打稳
- 再判断 OCR 是否还是主瓶颈
- 只有 OCR 仍明显拖后腿，再补 OCR 训练集和微调
