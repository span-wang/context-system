# PDF OCR Pipeline

## 目标

这套方案面向两类需求：

- 对 PDF 做 `OCR 前清理`，尽量去掉页眉、页脚、重复噪音和浅色水印。
- 输出 `可直接使用的结构化结果`，方便后续做切片、入库、检索或喂给 LLM。

## 输出文件

运行脚本后会生成三份文件：

- `*.ocr.json`
- `*.ocr.md`
- `*.ocr.txt`

其中 `JSON` 是主输出，结构大致如下：

```json
{
  "filename": "sample.pdf",
  "provider": "pdf_ocr_pipeline",
  "used_ocr": true,
  "text": "全文纯文本",
  "markdown": "全文 Markdown",
  "pages": [
    {
      "page_number": 1,
      "width": 595.0,
      "height": 842.0,
      "text": "单页文本",
      "markdown": "单页 Markdown",
      "blocks": [
        {
          "page_number": 1,
          "block_id": "p1-b1",
          "text": "识别出的文本块",
          "bbox": [12.0, 18.0, 120.0, 36.0],
          "score": 0.98,
          "block_type": "text",
          "latex": null,
          "removed_as_noise": false
        }
      ],
      "headers_removed": [],
      "footers_removed": [],
      "repeated_noise_removed": [],
      "formulas": [],
      "warnings": []
    }
  ],
  "warnings": [],
  "metadata": {
    "filename": "sample.pdf",
    "page_count": 3,
    "options": {}
  }
}
```

## 使用方式

在仓库根目录运行：

```powershell
python .\scripts\pdf_ocr_pipeline.py .\data\sample.pdf
```

指定输出目录：

```powershell
python .\scripts\pdf_ocr_pipeline.py .\data\sample.pdf --output-dir .\output\pdf_ocr
```

覆盖清理参数：

```powershell
python .\scripts\pdf_ocr_pipeline.py .\data\sample.pdf --options-json "{\"crop_header_ratio\": 0.05, \"crop_footer_ratio\": 0.06, \"enable_formula_recognition\": true}"
```

PowerShell 下也可以直接这样写，通常更省心：

```powershell
python .\scripts\pdf_ocr_pipeline.py .\data\sample.pdf --options-json "{'crop_header_ratio': 0.05, 'crop_footer_ratio': 0.06, 'enable_formula_recognition': true}"
```

## 可调参数

`OCRPipelineOptions` 支持这些核心字段：

- `render_dpi`
  页面渲染分辨率，默认 `240`。更高通常更准，但更慢。
- `crop_header_ratio`
  按页面高度裁掉顶部区域，例如 `0.05` 表示裁掉顶部 5%。
- `crop_footer_ratio`
  按页面高度裁掉底部区域，例如 `0.06` 表示裁掉底部 6%。
- `trim_margins`
  是否自动裁掉大块空白边缘。
- `remove_repeated_lines`
  是否移除跨页重复出现的文本，适合页眉、页脚、页码、版权提示。
- `repeated_line_min_pages`
  至少在多少页重复才算噪音，默认 `2`。
- `watermark_detection`
  是否尝试弱化浅色水印。
- `watermark_brightness_threshold`
  亮度超过该阈值的像素会被强制提亮到白色，适合浅灰水印。
- `enable_formula_recognition`
  是否启用公式识别。
- `formula_confidence_threshold`
  公式识别的最低置信度阈值。

## 公式识别说明

### 能力边界

- 普通 OCR 可以识别一部分简单公式文本，比如 `x^2 + y^2 = 1`。
- 真正结构化的数学公式建议走 `公式识别`，目标输出 `LaTeX`。
- 如果公式被深色水印遮挡，OCR 无法恢复被盖住的原始字符。

### 当前脚本的行为

- 当 `enable_formula_recognition=false` 时：
  只做普通 OCR，公式会以普通文本形式保留。
- 当 `enable_formula_recognition=true` 且环境支持时：
  会对疑似公式块做二次识别，并把结果写入 `block.latex`，同时在 Markdown 中用 `$$ ... $$` 输出。
- 当公式模块不可用时：
  管线不会失败，只会在 `warnings` 里提示已降级。

## 依赖建议

基础版至少需要：

- `paddleocr`
- `PyMuPDF` 或 `pymupdf`
- `Pillow`
- `numpy`

默认 OCR 模型为 `PP-OCRv5_server_det` + `PP-OCRv5_server_rec`，优先照顾扫描试卷和 PDF 的识别精度。可通过以下环境变量覆盖：

- `PDF_OCR_VERSION`
- `PDF_OCR_DETECTION_MODEL`
- `PDF_OCR_RECOGNITION_MODEL`
- `PDF_OCR_USE_TEXTLINE_ORIENTATION`
- `PDF_OCR_USE_DOC_ORIENTATION`
- `PDF_OCR_USE_DOC_UNWARPING`

如果部署机器启动慢、显存不足或只需要快速预览，可把模型改成 `PP-OCRv5_mobile_det` + `PP-OCRv5_mobile_rec`。

如果你想做更强的图像级去噪，建议再装：

- `opencv-python`

如果你想提升公式识别，优先使用 PaddleOCR 官方公式识别模块。官方文档：

- https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/formula_recognition.html
- https://www.paddleocr.ai/main/en/version3.x/module_usage/formula_recognition.html

## 适合的场景

- 扫描 PDF
- 带固定页眉页脚的教材、试卷、讲义
- 带浅色水印或重复广告条的文档
- 需要输出 `page -> block -> bbox` 级结构化结果的下游任务

## 不适合直接指望一次解决的场景

- 深色、半透明且覆盖正文的水印
- 复杂双栏、跨页表格、手写批注严重的扫描件
- 大量复杂数学排版且需要高质量 LaTeX 还原的论文

这些场景建议再叠加更细的版面分析或专门的公式模型。
