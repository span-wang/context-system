# 清噪与切题自动训练闭环

本文固定当前方案：先把现有清噪和切题规则作为 V0 规则模型，再用线上大模型做 Teacher 生成高置信自动训练样本，最后通过回归评估决定是否回流。

## 1. 模型分层

当前已有能力直接作为基线模型：

- `ocr_cleaner_rule_v1`：基于 `apps/api/library/ocr_cleaner.py` 的清噪规则模型。
- `paper_splitter_rule_v1`：基于 `apps/api/app/services/papers.py` 与 `paper_dataset.py` 的切题规则模型。

后续训练出的模型不能直接覆盖生产链路。运行时应采用：

```text
规则模型高置信 -> 直接使用
规则模型低置信 -> 调用训练模型或 Teacher 补强
规则与模型冲突 -> 标记风险，不自动覆盖
```

## 2. 自动训练数据

自动训练数据统一写入：

```text
data/auto_training/
  ocr_cleaning/
  question_splitting/
  runs/
```

清噪样本格式：

```json
{
  "id": "ocr_clean_000001",
  "input": "原始 OCR 文本，来自 data/paper_parser_dataset/{sample}/raw_source.txt",
  "target": "1. 题干\nA. 甲\nB. 乙",
  "confidence": 0.96,
  "label_sources": ["raw_ocr", "rule", "teacher"],
  "meta": {
    "input_source": "raw_ocr",
    "target_source": "teacher"
  }
}
```

清噪训练必须使用原始 OCR 文本。`source.txt` 继续作为切题训练和目标种子使用；清噪输入统一读取同目录的 `raw_source.txt`。缺少 `raw_source.txt` 的旧样本会写入 `rejected.jsonl`，不会再通过“已清噪文本 + 合成噪声”的方式兼容。

切题样本格式：

```json
{
  "id": "split_000001",
  "input": "单项选择题\n1. 题干\nA. 甲\nB. 乙\n答案：A",
  "target": {
    "sections": []
  },
  "confidence": 0.95,
  "label_sources": ["rule", "teacher", "validator"],
  "meta": {}
}
```

## 3. 线上 Teacher

自动训练可配置独立 Teacher 模型，支持：

- `deepseek`
- `openai_compat`
- `anthropic`
- 本地兼容 OpenAI 接口

Teacher 的职责是生成伪标签和仲裁冲突，不直接作为生产解析结果写库。

## 4. 质量门

清噪入库条件：

- 清噪结果非空。
- 样本必须有 `raw_source.txt`，规则清噪和 Teacher 必须基于同一份原始 OCR 输入。
- 正文保留率不能异常下降。
- 题号和选项标签不能大量消失。
- Teacher 输出或人工目标与原始 OCR 输入之间通过质量门。

切题入库条件：

- 题目数量大于 0。
- 题号、选项、答案结构可解释。
- `section.question_count` 与实际题目数一致。
- 规则结果与 Teacher 结果在题量和题号上高度一致。

低置信样本写入 `rejected.jsonl`，不参与训练。

## 5. 回归与发布

每次自动训练生成：

```text
run_manifest.json
ocr_cleaning_train.jsonl
question_splitting_train.jsonl
rejected.jsonl
eval_report.json
model_card.json
```

只有回归指标优于当前 active 模型时，才允许更新：

```text
data/models/ocr_cleaner/latest.json
data/models/question_splitter/latest.json
```

当前默认不自动发布，但清噪任务已经会自动生成候选版本目录。只有同时满足以下条件，才会更新 active 指针：

- `dry_run=false`
- `auto_publish=true`
- 本轮报告为 `candidate`
- 高置信清噪样本不少于 20 条
- 回归通过率不低于 0.95
- 平均置信度不低于 0.92
- 综合分优于当前 active 版本

## 6. 清噪版本迭代自动化

清噪训练结束后会追加执行版本迭代流程：

```text
ocr_cleaning_train.jsonl
  -> 过滤高置信样本
  -> 当前规则模型回归评估
  -> 生成候选版本
  -> 判断是否允许发布
  -> 条件通过才更新 latest.json
```

新增产物：

```text
data/auto_training/runs/{run_id}/ocr_model_iteration.json

data/models/ocr_cleaner/
  candidates/{run_id}/
    model_card.json
    regression_samples.jsonl
  versions/ocr_cleaner_v000001/
    model_card.json
    artifact.json
    regression_samples.jsonl
  latest.json
```

当前第一阶段的 `artifact.json` 类型是 `rule_regression_pack`，作用是把训练样本固化成可回归的候选版本和发布记录；后续如果接入真实训练模型，可以继续复用同一套 `versions/...` 和 `latest.json` 发布口。

## 7. 人工预览与发布

自动训练控制台的运行历史支持两类人工操作：

```text
预览
  -> GET /api/auto-training/runs/{run_id}/ocr-candidate
  -> 展示候选版本指标、发布原因、样本 input/current/target 逐块对比
  -> 每个变化块返回 status 和 reason，解释删除、保留、修复或冲突原因

发布
  -> POST /api/auto-training/runs/{run_id}/ocr-candidate/publish
  -> 通过质量门后写入 versions/{version_id}
  -> 更新 data/models/ocr_cleaner/latest.json
```

人工发布会绕过 `auto_publish=false` 这个配置限制，但不会绕过核心质量门。以下情况仍会被后端拒绝：

- `dry_run=true`
- 本轮报告不是 `candidate`
- 高置信样本不足
- 回归通过率不足
- 平均置信度不足
- 综合分没有优于当前 active 版本

前端只负责触发预览和发布，最终是否允许发布始终由后端判断。
