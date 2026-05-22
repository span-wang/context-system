# 专业版真题分析 + 题库 App 平台完整架构方案

## 1. 项目定位

本项目不建议继续按“素材库工具”或“单一真题统计工具”建设，而应升级为一套统一底座：

- 真题分析中台
- 专业版教研后台
- 学员题库 App
- 机构版升级底座
- 内容生产与发布工作流

目标不是只解决“统计某学科真题考点频率”，而是建立一套围绕题目、考点、学习行为、内容生产、商业化运营的完整数据与业务系统。

推荐产品名义定位：

`教研分析中台 + 题库学习平台 + 内容生产后台`


## 2. 核心产品形态

整个平台建议拆成 1 个中台、2 个前台、1 套机构版升级能力。

### 2.1 中台

中台负责统一管理：

- 题库资产
- 真题试卷
- 题目解析
- 考点体系
- 分析报告
- 学员练习数据
- 内容生产数据

### 2.2 专业版后台

面向教培主理人、教研老师、内容运营人员，负责：

- 上传和解析真题
- 管理题目和考点
- 统计高频考点和趋势
- 生成报告和专题训练包
- 把分析结果转化为内容选题和发布素材

### 2.3 学员题库 App

面向 C 端学员或机构学员，负责：

- 刷题
- 章节练习
- 高频考点练习
- 模拟考试
- 错题本
- 学习计划
- 学习分析

### 2.4 机构版升级能力

机构版不应单独重做，而是在当前架构上升级：

- 多租户
- 校区
- 班级
- 老师
- 学员
- 数据权限
- 套餐和额度
- API 开放平台
- 私有化部署


## 3. 总体业务闭环

```text
真题文件上传
  -> OCR / 文本解析
  -> 切题 / 抽取答案 / 解析
  -> 题目标准化
  -> 考点识别与人工复核
  -> 高频 / 趋势 / 易错分析
  -> 生成分析报告
  -> 生成专题题包 / 模考卷
  -> 学员刷题
  -> 学习行为回流
  -> 优化考点热度与推荐策略
  -> 输出内容选题 / 短内容 / 讲义
```

这个闭环是平台长期价值的核心。


## 4. 功能全景

## 4.1 平台管理

- 用户登录
- 角色权限
- 单租户专业版
- 多租户预留
- 操作日志
- 套餐额度预留
- 系统配置
- 学科配置

## 4.2 素材与试卷管理

- 批量上传 PDF / 图片 / DOCX / Markdown / TXT
- 真题文件元数据维护
- OCR 提取
- 可选文本提取
- 解析缓存
- 文件预览
- 试卷创建与绑定
- 试卷状态流转

## 4.3 真题解析中心

- 自动识别试卷结构
- 识别题型分区
- 切分题号
- 抽取题干
- 抽取选项
- 抽取答案
- 抽取解析
- 关联源页码
- 重复题识别
- 解析结果人工修正

## 4.4 考点知识库

- 学科管理
- 类目管理
- 章节树管理
- 考点树管理
- 考点别名
- 关键词词典
- 易混考点关系
- 前置依赖关系
- 共现考点关系

## 4.5 智能标注与复核

- 规则召回候选考点
- 模型分类候选考点
- LLM 辅助解释
- 置信度评分
- 主考点和次考点标注
- 人工审核
- 打回与修正
- 版本记录

## 4.6 真题分析中心

- 高频考点统计
- 年份趋势统计
- 章节热力图
- 题型分布
- 分值分布
- 难度分布
- 易错点统计
- 考点共现分析
- 高频题型组合分析
- 冲刺优先级排序

## 4.7 报告中心

- 高频考点报告
- 趋势变化报告
- 章节覆盖报告
- 易错点报告
- 考前冲刺报告
- 模考建议报告
- Excel 导出
- PDF 导出
- 报告快照存档

## 4.8 题库中心

- 原始题管理
- 标准题管理
- 标签体系
- 专题题包
- 高频题包
- 章节题包
- 组卷规则
- 模考卷生成
- 题目上下架

## 4.9 学员题库 App

- 账号登录
- 章节练习
- 高频考点练习
- 历年真题
- 智能练习
- 模拟考试
- 收藏
- 错题本
- 学习计划
- 学习报告
- 掌握度分析
- 每日任务

## 4.10 内容生产联动

- 从分析结果创建工作流选题
- 从高频考点生成讲义
- 从易错点生成纠错内容
- 从趋势报告生成冲刺专题
- 接入现有生成、审核、导出链路

## 4.11 机构版预留能力

- 多租户数据隔离
- 校区组织结构
- 班级与课程
- 老师分组
- 学员分组
- 作业布置
- 班级报告
- API 开放接口
- 配额和套餐
- 私有化部署参数化


## 5. 题目模型设计原则

题库 App 和真题分析必须共用底层资产，但不能直接共用同一层题目实体。

建议采用 3 层题目模型：

### 5.1 原始题

来自试卷切题的原始结果，保留原貌。

用途：

- 真题统计
- 来源追踪
- 解析纠错
- 审核和回放

### 5.2 标准题

从原始题中清洗、去重、规范化后的题。

用途：

- 题库 App 刷题
- 组卷
- 专题训练
- 模考

### 5.3 投放题

标准题在某次练习、试卷、模考中的实例。

用途：

- 学习记录
- 成绩统计
- 推荐系统
- 错题本

这样可以同时兼顾分析准确性和学员端体验。


## 6. 技术架构

## 6.1 技术栈建议

### 后端

- FastAPI
- SQLAlchemy 2.x
- Alembic
- Pydantic
- Celery
- Redis

### 数据库

- MySQL 8.0

### 前端

- Next.js 作为后台管理端
- Taro + React 作为题库 App

### 文件与对象存储

- 第一阶段：本地文件系统
- 第二阶段：兼容 MinIO / S3

### OCR 与解析

- 继续复用现有 parser 逻辑
- 增加版面分析和切题规则

### AI 能力

- 规则识别
- 文本分类模型
- embedding 检索
- LLM 辅助解释与纠偏


## 6.2 建议部署形态

### 开发 / 专业版单机部署

- web
- api
- mysql
- redis
- local storage

### 机构版或商业版部署

- web
- student-app
- api
- worker
- mysql
- redis
- object storage
- nginx


## 7. 推荐仓库结构

在当前仓库基础上建议逐步升级为：

```text
apps/
  api/
    alembic/
    app/
      api/
        admin/
        analysis/
        auth/
        content/
        knowledge/
        learning/
        question_bank/
        system/
        workflow/
      core/
      db/
      models/
      repositories/
      schemas/
      services/
      tasks/
      utils/
      main.py
  web/
    app/
      analysis/
      knowledge/
      papers/
      question-bank/
      reports/
      workflow/
      settings/
    components/
    lib/
  student-app/
    src/
      pages/
      components/
      services/
      store/
      hooks/
packages/
  shared-types/
  shared-utils/
docs/
  PRO_EDU_PLATFORM_ARCHITECTURE.md
```


## 8. 后端代码实现架构

## 8.1 分层原则

后端必须做清晰分层，避免继续把所有逻辑塞到 router 和单个 db 工具类里。

建议层次如下：

### Router 层

职责：

- 参数校验
- 鉴权
- 响应返回

示例：

- `api/analysis/papers.py`
- `api/question_bank/questions.py`
- `api/learning/practice.py`

### Service 层

职责：

- 编排业务流程
- 调用 repository
- 调用任务和 AI 服务

示例：

- `PaperIngestionService`
- `QuestionExtractionService`
- `KnowledgeClassificationService`
- `AnalysisReportService`
- `PracticeSessionService`

### Repository 层

职责：

- 只负责数据库增删改查
- 不做复杂业务编排

示例：

- `PaperRepository`
- `QuestionRepository`
- `KnowledgePointRepository`
- `PracticeRepository`

### Domain / Rule 层

职责：

- 放业务规则
- 放评分算法
- 放状态机

示例：

- `ExamPaperStateMachine`
- `HotScoreCalculator`
- `KnowledgeLinkingPolicy`

### Task 层

职责：

- 处理耗时任务

示例：

- OCR
- 题目切分
- LLM 分类
- 报告生成
- 批量重算统计


## 8.2 后端核心模块拆分

### auth

负责：

- 登录
- 刷新 token
- 用户信息
- 角色
- 权限

关键 service：

- `AuthService`
- `PermissionService`

### assets

负责：

- 文件上传
- 文件校验
- 解析缓存
- OCR 任务发起

关键 service：

- `AssetService`
- `AssetParseService`

### papers

负责：

- 试卷管理
- 试卷状态
- 试卷与素材绑定
- 试卷结构切分

关键 service：

- `PaperService`
- `PaperParseService`
- `PaperSectionService`

### questions

负责：

- 原始题抽取
- 原始题管理
- 去重
- 题目质量评分

关键 service：

- `QuestionExtractionService`
- `QuestionNormalizationService`
- `QuestionDedupService`

### knowledge

负责：

- 学科
- 类目
- 章节
- 考点树
- 词典

关键 service：

- `KnowledgeTreeService`
- `KnowledgeAliasService`

### analysis

负责：

- 考点识别
- 高频分析
- 趋势分析
- 报告生成

关键 service：

- `QuestionClassificationService`
- `FrequencyAnalysisService`
- `TrendAnalysisService`
- `ReportGenerationService`

### question_bank

负责：

- 标准题管理
- 专题题包
- 模考试卷
- 智能组卷

关键 service：

- `QuestionBankService`
- `PracticeSetService`
- `MockExamService`

### learning

负责：

- 学员练习
- 答题记录
- 错题本
- 掌握度
- 学习计划

关键 service：

- `PracticeSessionService`
- `WrongBookService`
- `MasteryService`
- `StudyPlanService`

### workflow

负责：

- 与现有内容工作流打通
- 从分析结果创建内容选题

关键 service：

- `AnalysisToTopicService`


## 8.3 任务编排

异步任务建议统一从 `tasks/` 模块发起。

推荐任务：

- `parse_asset_task`
- `extract_questions_task`
- `classify_question_task`
- `rebuild_paper_stats_task`
- `generate_report_task`
- `build_practice_set_task`

任务状态统一保存到：

- `job_type`
- `status`
- `progress`
- `result_summary`
- `error_message`


## 9. 前端代码实现架构

## 9.1 专业版后台

建议在 `apps/web/app` 下新增页面分区：

```text
app/
  analysis/
    dashboard/page.tsx
    papers/page.tsx
    questions/page.tsx
    reports/page.tsx
  knowledge/
    page.tsx
  question-bank/
    page.tsx
    practice-sets/page.tsx
    mock-exams/page.tsx
  learners/
    page.tsx
  workflow/
    page.tsx
  settings/
    page.tsx
```

建议配套组件分层：

```text
components/
  analysis/
  knowledge/
  question-bank/
  learners/
  workflow/
  shared/
```

状态组织建议：

- 页面请求走 `lib/api.ts`
- 公共类型拆到 `packages/shared-types`
- 若状态复杂，可引入 Zustand


## 9.2 学员题库 App

建议独立为 `apps/student-app`，不要和后台混在一起。

页面建议：

```text
pages/
  home/
  subject/
  chapter-practice/
  high-frequency/
  real-exams/
  mock-exam/
  wrong-book/
  favorites/
  study-plan/
  profile/
```

功能模块建议：

- `services/` 调接口
- `store/` 存用户态和练习状态
- `hooks/` 放练习生命周期逻辑
- `components/` 放题卡、答题卡、结果页等通用组件


## 10. 数据库设计

数据库统一使用 MySQL，所有核心业务表建议预留：

- `tenant_id`
- `created_at`
- `updated_at`
- `created_by`
- `updated_by`

专业版当前只需要一条默认 tenant 数据，但表结构必须先预留。


## 10.1 平台与权限

### tenants

- id
- code
- name
- status
- plan_type
- created_at
- updated_at

### users

- id
- tenant_id
- username
- password_hash
- display_name
- mobile
- email
- user_type
- status
- last_login_at
- created_at
- updated_at

### roles

- id
- tenant_id
- role_code
- role_name
- is_system
- created_at

### user_roles

- id
- tenant_id
- user_id
- role_id


## 10.2 学科与知识点

### subjects

- id
- tenant_id
- code
- name
- status

### subject_categories

- id
- tenant_id
- subject_id
- name
- sort_order

### chapters

- id
- tenant_id
- subject_id
- parent_id
- name
- level
- path
- sort_order

### knowledge_points

- id
- tenant_id
- subject_id
- category_id
- chapter_id
- parent_id
- name
- level
- path
- description
- keywords_json
- status
- sort_order
- created_at
- updated_at

### knowledge_point_aliases

- id
- tenant_id
- knowledge_point_id
- alias_name

### knowledge_point_relations

- id
- tenant_id
- from_kp_id
- to_kp_id
- relation_type


## 10.3 文件与试卷

### assets

- id
- tenant_id
- subject_id
- asset_type
- source_type
- source_title
- filename
- mime_type
- storage_path
- sha256
- file_size
- parse_status
- ocr_status
- parsed_text
- token_count
- year
- region
- tags_json
- created_by
- created_at
- updated_at

### exam_papers

- id
- tenant_id
- subject_id
- asset_id
- paper_name
- paper_code
- exam_year
- exam_month
- exam_region
- exam_type
- paper_type
- source_channel
- status
- total_question_count
- total_score
- parsed_version
- review_status
- created_by
- created_at
- updated_at

### paper_sections

- id
- tenant_id
- paper_id
- section_name
- question_type
- start_no
- end_no
- score
- sort_order


## 10.4 题目中心

### exam_questions

- id
- tenant_id
- paper_id
- subject_id
- section_id
- question_no
- question_uid
- question_type
- stem_text
- options_json
- answer_text
- analysis_text
- source_page_from
- source_page_to
- score
- difficulty_level
- quality_score
- is_duplicate
- duplicate_group_id
- parse_status
- review_status
- reviewed_by
- reviewed_at
- created_at
- updated_at

### question_bank_items

- id
- tenant_id
- subject_id
- canonical_stem
- canonical_options_json
- canonical_answer
- canonical_analysis
- question_type
- difficulty_level
- quality_score
- source_count
- status
- created_at
- updated_at

### question_source_links

- id
- tenant_id
- bank_question_id
- exam_question_id
- paper_id
- source_year
- source_region


## 10.5 题目与考点关联

### question_knowledge_links

- id
- tenant_id
- question_id
- question_layer
- knowledge_point_id
- link_type
- confidence_score
- evidence_text
- tag_source
- is_primary
- review_status
- reviewed_by
- reviewed_at
- created_at


## 10.6 报告与任务

### analysis_jobs

- id
- tenant_id
- job_type
- subject_id
- scope_type
- scope_config_json
- status
- progress
- result_summary_json
- error_message
- created_by
- started_at
- finished_at
- created_at

### analysis_reports

- id
- tenant_id
- subject_id
- report_type
- report_name
- scope_config_json
- filters_json
- snapshot_date
- version_no
- status
- report_json
- created_by
- created_at


## 10.7 题包与模考

### practice_sets

- id
- tenant_id
- subject_id
- set_type
- title
- description
- source_report_id
- difficulty_policy
- question_count
- status
- created_by
- created_at

### practice_set_questions

- id
- tenant_id
- practice_set_id
- bank_question_id
- sort_order
- score

### mock_exams

- id
- tenant_id
- subject_id
- title
- exam_mode
- duration_minutes
- total_score
- status
- created_by
- created_at

### mock_exam_questions

- id
- tenant_id
- mock_exam_id
- bank_question_id
- sort_order
- score


## 10.8 学习行为

### learner_profiles

- id
- tenant_id
- user_id
- target_exam
- target_year
- level
- preferred_subjects_json
- created_at
- updated_at

### practice_sessions

- id
- tenant_id
- learner_id
- session_type
- subject_id
- practice_set_id
- mock_exam_id
- status
- started_at
- submitted_at
- score
- accuracy_rate
- duration_seconds

### practice_answers

- id
- tenant_id
- session_id
- bank_question_id
- learner_answer
- is_correct
- score
- spent_seconds
- knowledge_snapshot_json
- created_at

### wrong_book_items

- id
- tenant_id
- learner_id
- bank_question_id
- source_session_id
- wrong_count
- last_wrong_at
- mastered
- created_at
- updated_at

### favorites

- id
- tenant_id
- learner_id
- bank_question_id
- created_at

### mastery_snapshots

- id
- tenant_id
- learner_id
- subject_id
- knowledge_point_id
- mastery_score
- answered_count
- correct_count
- snapshot_date


## 10.9 审核与审计

### review_tasks

- id
- tenant_id
- task_type
- target_type
- target_id
- status
- assigned_to
- priority
- review_note
- created_by
- created_at
- completed_at

### audit_logs

- id
- tenant_id
- user_id
- module
- action
- target_type
- target_id
- request_id
- payload_json
- created_at


## 11. 分析引擎设计

分析引擎建议采用 4 段式架构，而不是单独依赖 LLM。

## 11.1 第一段：解析层

负责：

- OCR
- 文本清洗
- 页码定位
- 题号识别
- 选项识别
- 答案识别
- 解析识别

输出：

- 原始题结构化数据

## 11.2 第二段：规则召回层

负责：

- 基于考点词典召回候选考点
- 基于章节和题型过滤候选集

输出：

- 候选考点列表

## 11.3 第三段：模型判断层

负责：

- 分类模型或 embedding 匹配
- 输出主考点和次考点概率

输出：

- 候选考点 + 置信度

## 11.4 第四段：LLM 解释层

负责：

- 辅助判断
- 给出解释理由
- 识别规则不足的边界案例

输出：

- 主考点
- 次考点
- 证据片段
- 解释说明
- 置信度

## 11.5 人工复核层

负责：

- 对低置信度结果人工确认
- 修正错误映射
- 留下训练反馈数据


## 12. 核心计算指标

专业版统计不能只看“出现次数”，建议至少支持以下指标：

- 出现次数
- 覆盖试卷数
- 近 3 年频次
- 近 5 年频次
- 频次增速
- 所占分值
- 题型分布
- 难度分布
- 易错关联度
- 共现强度

建议综合热度分：

```text
hot_score =
  0.35 * frequency_score +
  0.25 * paper_coverage_score +
  0.20 * recent_growth_score +
  0.10 * score_weight_score +
  0.10 * difficulty_weight_score
```


## 13. API 架构设计

建议所有新接口统一挂在以下命名空间：

- `/api/auth`
- `/api/system`
- `/api/assets`
- `/api/papers`
- `/api/questions`
- `/api/knowledge`
- `/api/analysis`
- `/api/question-bank`
- `/api/learning`
- `/api/workflow`


## 13.1 认证接口

- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/auth/me`
- `POST /api/auth/logout`

## 13.2 试卷与题目接口

- `POST /api/papers/upload`
- `GET /api/papers`
- `GET /api/papers/{id}`
- `POST /api/papers/{id}/parse`
- `POST /api/papers/{id}/extract-questions`
- `GET /api/questions`
- `GET /api/questions/{id}`
- `PATCH /api/questions/{id}`
- `POST /api/questions/{id}/reclassify`

## 13.3 知识点接口

- `GET /api/knowledge/subjects`
- `GET /api/knowledge/points`
- `POST /api/knowledge/points`
- `PATCH /api/knowledge/points/{id}`
- `POST /api/knowledge/points/import`

## 13.4 分析接口

- `GET /api/analysis/dashboard`
- `GET /api/analysis/frequencies`
- `GET /api/analysis/trends`
- `GET /api/analysis/co-occurrence`
- `POST /api/analysis/reports`
- `GET /api/analysis/reports`
- `GET /api/analysis/reports/{id}`
- `POST /api/analysis/reports/{id}/export`
- `POST /api/analysis/reports/{id}/create-workflow-topics`

## 13.5 题库接口

- `GET /api/question-bank/questions`
- `GET /api/question-bank/questions/{id}`
- `POST /api/question-bank/practice-sets`
- `GET /api/question-bank/practice-sets`
- `POST /api/question-bank/mock-exams`
- `GET /api/question-bank/mock-exams`

## 13.6 学员学习接口

- `GET /api/learning/home`
- `GET /api/learning/practice-sets`
- `POST /api/learning/sessions`
- `GET /api/learning/sessions/{id}`
- `POST /api/learning/sessions/{id}/answer`
- `POST /api/learning/sessions/{id}/submit`
- `GET /api/learning/wrong-book`
- `POST /api/learning/favorites`
- `GET /api/learning/mastery`


## 14. 权限模型

专业版建议先做 RBAC，后续机构版在 RBAC 基础上叠加数据权限。

角色建议：

- `super_admin`
- `admin`
- `teacher`
- `reviewer`
- `operator`
- `viewer`
- `student`

后台权限维度建议：

- 试卷管理
- 题目审核
- 考点管理
- 报告查看
- 报告导出
- 题库发布
- 学员查看
- 内容工作流
- 系统配置


## 15. 代码迁移建议

基于当前项目，必须优先做以下结构升级。

## 15.1 数据访问层重构

当前项目数据库层是手写 SQLite 模式，不适合作为专业版长期基础。

建议改为：

- 用 SQLAlchemy 定义模型
- 用 Alembic 管理迁移
- 用 Repository 封装查询

不要继续在原来的单一 `storage/db.py` 上堆业务表和统计逻辑。

## 15.2 配置重构

数据库配置应改为支持 MySQL DSN，例如：

```env
DB_URL=mysql+pymysql://root:password@127.0.0.1:3306/exam_kit
```

配置对象建议：

- `db.url`
- `db.echo`
- `db.pool_size`
- `db.max_overflow`

## 15.3 依赖注入重构

从“全局单例 Database 对象”改为：

- `engine`
- `SessionLocal`
- `get_db_session`

service 层通过 session 或 repository 注入。

## 15.4 异步任务重构

将耗时操作移到 worker：

- OCR
- 切题
- 大批量标注
- 报告生成

## 15.5 前端模块化

后台继续沿用 Next.js，但页面要按域拆分，不再只围绕：

- library
- workflow
- generate

新主导航建议：

- 分析看板
- 试卷中心
- 题目中心
- 考点体系
- 报告中心
- 题库中心
- 工作流
- 设置


## 16. 建议的后端类设计

下面是建议优先建立的 service 类。

```text
AuthService
TenantService
AssetService
AssetParseService
PaperService
PaperParseService
QuestionExtractionService
QuestionNormalizationService
QuestionDedupService
KnowledgeTreeService
QuestionClassificationService
FrequencyAnalysisService
TrendAnalysisService
ReportGenerationService
PracticeSetService
MockExamService
PracticeSessionService
WrongBookService
MasteryService
AnalysisToTopicService
```


## 17. 建议的后端模型文件划分

```text
models/
  tenant.py
  user.py
  role.py
  subject.py
  chapter.py
  knowledge_point.py
  asset.py
  exam_paper.py
  exam_question.py
  question_bank_item.py
  question_knowledge_link.py
  analysis_job.py
  analysis_report.py
  practice_set.py
  mock_exam.py
  learner_profile.py
  practice_session.py
  practice_answer.py
  review_task.py
  audit_log.py
```


## 18. 建议的开发顺序

## 第一期：底座重构

- MySQL 接入
- SQLAlchemy 模型层
- Alembic
- 用户与权限
- 资产表、试卷表、原始题表

## 第二期：真题分析 MVP

- 试卷上传
- OCR / 解析
- 切题
- 题目管理
- 考点树
- 手工标注
- 高频统计

## 第三期：智能分析版

- 候选考点识别
- LLM 辅助分类
- 趋势分析
- 易错点分析
- 报告生成

## 第四期：题库 App

- 标准题
- 题包
- 学员刷题
- 错题本
- 收藏
- 模考
- 学习报告

## 第五期：闭环增强

- 从分析结果生成内容选题
- 自动专题训练包
- 掌握度推荐
- 套餐和额度
- 机构版升级位开放


## 19. 当前项目的落地结论

基于你现有仓库，推荐的最优路线不是继续做“素材库的小扩展”，而是：

1. 保留现有 `web + api` 双端结构
2. 将当前项目升级为专业版后台
3. 把数据库从 SQLite 模式重构到 MySQL
4. 新增 `analysis`、`question_bank`、`learning` 三条主业务线
5. 未来新增 `student-app`
6. 通过 `tenant_id + RBAC + 配额设计` 给机构版留接口


## 20. 一句话架构总结

最终形态应该是：

`一个以真题、题目、考点为核心资产的数据中台，上承教研分析和内容生产，下承学员题库和机构化运营。`

这套设计既能满足专业版落地，也不会阻断后续机构版和题库 App 的升级路径。


## 21. 开发完成情况记录

本节用于记录当前仓库已经落地的开发成果，方便后续会话继续推进时快速接手。

### 21.1 当前完成阶段

当前已完成：

- 第一期底座重构的核心骨架
- 专业版后台的主导航与页面骨架
- 分析中心、题库中心、学习中心、工作流中心的首版可运行演示链路

当前状态可以概括为：

`原有素材库/生成工作流功能已保留为默认产品入口，新专业版平台以并行方式接入，后端新分层可运行，前端新平台页可构建。`


### 21.2 已完成的后端改造

已新增新的 FastAPI 分层目录：

```text
apps/api/app/
  api/
    routes/
  core/
  db/
  models/
  repositories/
  schemas/
  services/
  tasks/
```

已完成的具体事项：

- 新建 `app.main` 作为专业版平台的新应用骨架
- 新建 `core/config.py`，支持新的配置模型，并将 SQLite 路径解析为绝对路径
- 新建 SQLAlchemy `engine`、`SessionLocal`、`get_db_session`
- 新建 `alembic.ini`、`alembic/env.py`，完成 Alembic 基础接入
- 新建 31 个左右的核心业务模型，覆盖 tenant、user、subject、paper、question、analysis、question_bank、learning、review 等主线
- 新建 repository/service/router 三层骨架
- 在不覆盖旧接口的前提下，将专业版新接口并行挂载到 `/platform` 前缀下：
  - `/platform/api/auth`
  - `/platform/api/system`
  - `/platform/api/knowledge`
  - `/platform/api/papers`
  - `/platform/api/questions`
  - `/platform/api/analysis`
  - `/platform/api/question-bank`
  - `/platform/api/learning`
  - `/platform/api/workflow`

已实现的接口能力不是完整业务版，而是“可运行骨架 + 演示数据返回”，用于承接后续真实开发。


### 21.3 已完成的数据层与种子数据

已在 `app/db/bootstrap.py` 中完成初始化逻辑：

- `Base.metadata.create_all(...)`
- 首次启动自动写入演示租户、角色、管理员、学员
- 自动写入演示学科、章节、考点
- 自动写入演示素材、试卷、分区、原始题
- 自动写入标准题、题源关联、题目考点关联
- 自动写入分析任务、分析报告
- 自动写入练习题包、模考试卷
- 自动写入学习会话、错题本、收藏、掌握度快照
- 自动写入审核任务

当前演示数据规模：

- 学科：4
- 试卷：1
- 原始题：4
- 分析报告：1
- 练习会话：1


### 21.4 已完成的前端改造

前端当前采取“旧功能保留 + 新平台并行入口”策略：

- 旧导航仍保留：
  - 工作流
  - 素材库
  - 生成中心
  - 历史审查
  - 模型配置
- 新增并行入口：
  - 新平台

已新增页面：

```text
apps/web/app/
  analysis/dashboard/page.tsx
  analysis/papers/page.tsx
  analysis/questions/page.tsx
  analysis/reports/page.tsx
  knowledge/page.tsx
  question-bank/page.tsx
  question-bank/practice-sets/page.tsx
  question-bank/mock-exams/page.tsx
  learners/page.tsx
  platform/page.tsx
  platform/settings/page.tsx
  platform/workflow/page.tsx
```

已完成的具体事项：

- 恢复 `apps/web/lib/api.ts` 作为旧功能共享 API
- 新增 `apps/web/lib/pro-api.ts` 作为新平台共享 API
- 恢复旧导航，并新增“新平台”并行入口
- 新增 `components/shared/LoadState.tsx`
- 新增 `components/shared/StatusBadge.tsx`
- 恢复首页与旧页面默认入口
- 新平台页面继续保留在 `analysis / knowledge / question-bank / learners / platform` 下
- 新平台正式访问前缀统一为 `/platform/*`
- 旧功能页面与新平台页面已同时通过前端构建验证


### 21.5 当前已经通过的验证

后端验证通过：

- `GET /api/system/healthz`
- `GET /api/library/files`
- `GET /api/workflow/topics`
- `GET /platform/api/system/healthz`
- `GET /platform/api/system/status`
- `GET /platform/api/auth/me`
- `GET /platform/api/knowledge/subjects`
- `GET /platform/api/papers`
- `POST /platform/api/papers/upload`
- `GET /platform/api/questions`
- `GET /platform/api/analysis/dashboard`
- `GET /platform/api/analysis/reports`
- `GET /platform/api/question-bank/questions`
- `GET /platform/api/learning/home`
- `GET /platform/api/workflow/topics`

已验证的示例返回结果：

- 分析看板返回了学科数、试卷数、原始题数、报告数
- 学习首页返回了目标考试、错题数、收藏数、薄弱考点
- 试卷上传服务级集成验证通过：文件写入 `data/papers/{yyyymm}/...`，并生成 `assets` 与 `exam_papers` 记录，状态为 `uploaded / pending`
- 2026-05-06 追加集成验证通过：上传中文文本试卷 -> 解析切题 -> 候选考点召回 -> 标准题同步 -> 生成题包/模考/报告 -> 开始并提交练习

前端验证通过：

- `npx tsc --noEmit`
- `npm run build`

### 21.5.1 2026-05-06 续做完成情况

本次继续推进了专业版平台的第一条真实写入链路：

- 新增 `POST /platform/api/papers/upload`
- 上传文件支持 `PDF / 图片 / DOCX / Markdown / TXT`
- 上传时写入 `assets` 表，保存文件 SHA256、MIME、大小、存储路径、年份、地区、标签等基础元数据
- 上传时写入 `exam_papers` 表，生成试卷记录，初始状态为 `uploaded`，审核状态为 `pending`
- 重复文件按 SHA256 识别；若已存在同一素材和试卷，则直接返回已有试卷
- 主后端入口 `apps/api/main.py` 启动时已调用新平台 `initialize_database()`，一键启动后可直接访问 `/platform/api/*`
- 前端 `/platform/analysis/papers` 已新增“上传试卷”表单，上传成功后自动刷新试卷列表并选中新试卷
- `apps/web/lib/pro-api.ts` 新增 `apiFormFetch`，用于 multipart 表单提交
- `apps/web/app/globals.css` 补充上传错误提示样式

当前这条链路已经从“保存文件 + 元数据入库”推进到“解析文本 + 规则切题 + 答案/解析抽取 + 候选考点召回”。

### 21.5.2 2026-05-06 再次续做完成情况

本次继续把专业版平台从“上传入库”推进到首版真实业务闭环：

- 新增 `POST /platform/api/papers/{paper_id}/parse`
- 复用现有 `library.parser.parse_bytes`，可对 `PDF / 图片 / DOCX / Markdown / TXT` 执行文本解析或 OCR 兜底
- 新增保守规则切题逻辑，识别题号、选项、答案、解析，并写入 `paper_sections` 与 `exam_questions`
- 新增 `app/services/tagging.py`，按考点名称和关键词进行规则候选召回，并写入 `question_knowledge_links`
- 新增 `PATCH /platform/api/questions/{question_id}`，支持原始题人工编辑
- 新增 `POST /platform/api/questions/{question_id}/retag`，支持单题重新执行规则候选考点召回
- 新增 `POST /platform/api/question-bank/standardize`，可将原始题同步为标准题，并写入题源关联
- 新增 `POST /platform/api/question-bank/practice-sets/generate`，可基于标准题生成练习题包
- 新增 `POST /platform/api/question-bank/mock-exams/generate`，可基于标准题生成模考试卷
- 新增 `POST /platform/api/analysis/reports/generate`，可基于当前考点频次和趋势生成报告快照
- 新增 `GET /platform/api/analysis/reports/{report_id}/export.md`，可导出 Markdown 报告
- 新增 `POST /platform/api/learning/sessions` 与 `POST /platform/api/learning/sessions/{session_id}/submit`
- 学习提交会写入 `practice_answers`、更新错题本，并按题目考点更新掌握度快照
- 前端试卷中心已接入“解析并切题”
- 前端题库中心已接入“原始题同步标准题 / 生成题包 / 生成模考”
- 前端报告中心已接入“生成当前报告 / 导出 Markdown”
- 前端学员学习页已接入“开始并提交演示练习”

当前这些能力仍属于第一版规则实现，适合跑通闭环和积累数据；后续应继续强化版面分析、复杂题型切分、人工复核体验、权限和迁移体系。

### 21.5.3 2026-05-06 认证续做完成情况

本次继续补齐专业版平台认证底座：

- 新增 `apps/api/app/core/security.py`
- 使用标准库实现 PBKDF2-SHA256 密码哈希与 HMAC-SHA256 JWT
- 新增 `security.secret_key` 与 `security.access_token_expires_minutes` 配置
- 种子管理员默认账号为 `admin / admin123456`
- 种子学员默认账号为 `learner_demo / learner123456`
- `POST /platform/api/auth/login` 已改为真实密码校验并返回 Bearer Token
- `GET /platform/api/auth/me` 支持解析 `Authorization: Bearer <token>` 获取当前用户
- 兼容当前开发体验：未带 Token 访问 `/me` 时仍返回默认 admin，避免新平台页面被硬登录墙打断
- 前端 `apps/web/lib/pro-api.ts` 已支持从 `localStorage` 注入 Bearer Token
- 前端 `/platform/settings` 已新增登录/退出面板

当前认证已从 demo token 推进到第一版真实登录；后续仍需补齐刷新令牌、强制鉴权依赖、角色权限校验、操作日志和生产级密钥管理。

### 21.5.4 2026-05-06 权限与审计续做完成情况

本次继续把认证底座推进到关键写接口可控可追踪：

- 新增 `apps/api/app/api/deps.py` 中的 `require_user` 与 `require_roles(...)`
- 关键写接口已强制要求 Bearer Token
- 写接口已接入角色校验，`super_admin` 默认拥有全部写权限
- 已保护的写接口包括：
  - `POST /platform/api/papers/upload`
  - `POST /platform/api/papers/{paper_id}/parse`
  - `PATCH /platform/api/questions/{question_id}`
  - `POST /platform/api/questions/{question_id}/retag`
  - `POST /platform/api/question-bank/standardize`
  - `POST /platform/api/question-bank/practice-sets/generate`
  - `POST /platform/api/question-bank/mock-exams/generate`
  - `POST /platform/api/analysis/reports/generate`
  - `POST /platform/api/learning/sessions`
  - `POST /platform/api/learning/sessions/{session_id}/submit`
- 新增 `apps/api/app/repositories/audit.py`
- 新增 `apps/api/app/services/audit.py`
- 上述关键写接口成功执行后会写入 `audit_logs`
- 前端 `pro-api` 已统一处理 401/403，未登录时提示去 `/platform/settings` 登录

当前权限和审计是第一版：关键写操作已受控，但只读接口仍保持开放以方便开发和演示；后续应继续补齐细粒度数据权限、租户隔离、日志筛选分页、刷新令牌和登出失效。

### 21.5.5 2026-05-06 操作日志查询续做完成情况

本次继续把审计能力从“落库”推进到“可查看”：

- 新增 `AuditLogResponse`
- 新增 `AuditRepository.list_logs`
- 新增 `AuditService.list_logs`
- 新增 `GET /platform/api/system/audit-logs?limit=...`
- 操作日志查询接口已接入 `require_roles("super_admin", "admin", "viewer")`
- 前端 `/platform/settings` 已展示最近操作日志
- 前端登录后会尝试加载最近 20 条日志；未登录或无权限时保持空列表，不阻断系统状态页
- 已通过临时 SQLite 验证：写入 `audit_logs` 后可查询并返回用户名、模块、动作、目标和载荷

当前仍未记录失败请求和只读访问；如果后续需要更完整的合规审计，应继续接入全局中间件或异常处理器。

### 21.5.6 2026-05-06 刷新令牌与失败请求审计续做完成情况

本次继续补齐认证和审计的生产化细节：

- 新增 `auth_token_sessions` 模型，用于保存刷新令牌哈希、过期时间、吊销状态
- 新增 `security.refresh_token_expires_days` 配置，默认 14 天
- `POST /platform/api/auth/login` 现在会同时返回 `access_token` 与 `refresh_token`
- 新增真实 `POST /platform/api/auth/refresh`，可用 refresh token 换取新的 access token
- `POST /platform/api/auth/logout` 现在会将 refresh token 对应会话标记为 `revoked`
- 前端 `pro-api` 已支持 access/refresh 双令牌存储
- 前端请求遇到 401 时会自动尝试 refresh 一次并重试原请求
- 前端退出登录会调用后端 logout，并清理本地 access/refresh token
- 新增 `FailedRequestAuditMiddleware`
- 主后端入口 `apps/api/main.py` 已挂载失败请求审计中间件；历史 `apps/api/app/main.py` 已不再作为启动入口
- `/api/*` 与 `/platform/api/*` 的 4xx/5xx 响应会写入 `audit_logs`，记录状态码、路径、方法和 query
- 已通过临时 SQLite 验证：refresh/logout 生效，logout 后 refresh 会失败；401 请求可写入 `failed_request` 审计日志

当前 refresh token 是服务端可吊销的第一版实现；后续可以继续补设备信息、IP 记录、同账号多端管理、过期会话清理任务和日志筛选分页。

### 21.5.7 2026-05-06 MySQL 接入与 Alembic 首迁续做完成情况

本次继续优先推进了文档中排第一位的数据库迁移任务，把新平台从 `create_all` 过渡到可持续的迁移驱动模式：

- 新增环境变量覆盖能力：
  - `DB_URL`
  - `DB_ECHO`
  - `DB_POOL_SIZE`
  - `DB_MAX_OVERFLOW`
  - `SECURITY_SECRET_KEY`
  - `SECURITY_ACCESS_TOKEN_EXPIRES_MINUTES`
  - `SECURITY_REFRESH_TOKEN_EXPIRES_DAYS`
- `apps/api/app/core/config.py` 现在会在读取 `config.yaml` 后再叠加上述环境变量，便于本地 SQLite、Docker MySQL 和后续生产环境切换
- `config.yaml` 已显式补齐 `db.echo / db.pool_size / db.max_overflow`
- `.env.example` 已补齐数据库与安全相关示例配置
- `docker-compose.yml` 已新增 `mysql:8.0` 服务，并让 `api` 默认支持通过 `DB_URL` 连接 MySQL
- `apps/api/alembic/env.py` 已统一使用 `settings.db.resolved_url`，避免 Alembic 和 SQLAlchemy 指向不同的 SQLite 文件
- `apps/api/alembic/env.py` 已显式排除旧产品的 `library_files / generation_jobs / workflow_topics / workflow_events`，避免首个迁移误删旧功能表
- 新增首个真实 Alembic 迁移文件：
  - `apps/api/alembic/versions/7987b9d25a7f_init_professional_platform_schema.py`
- `apps/api/app/db/bootstrap.py` 已不再调用 `Base.metadata.create_all(...)`
- `initialize_database()` 现在会先执行 Alembic `upgrade head`，再检查并补种子数据
- 为兼容当前开发库，已补充两类过渡逻辑：
  - 若数据库中专业版表已齐全但尚未写入迁移版本，则自动 `stamp head`
  - 若检测到“只建了一部分新平台表且没有可用 revision”，则抛出明确错误，避免静默写坏库
- 已验证当前仓库实际 `data/app.db` 存在的“`alembic_version` 空表”遗留状态，可在启动时自动修正为 `7987b9d25a7f`
- 已通过临时空 SQLite 库验证：
  - `alembic upgrade head` 可成功创建新平台全量表
  - 随后 `initialize_database()` 可正常写入演示租户、用户和业务种子数据
  - `alembic_version` 可正确写入 `7987b9d25a7f`

当前这一阶段说明：

`专业版平台的数据层已经从“手工建表 / create_all 演示态”推进到“首个真实迁移版本 + 启动自动迁移 + 兼容旧库过渡态”。`

### 21.5.8 2026-05-06 真实 MySQL 联调与本地自管实例续做完成情况

本次继续把上一节的迁移底座推进到“真实 MySQL 可跑通”的状态，并补齐了本地可复用的独立实例方案：

- `apps/api/requirements.txt` 新增 `cryptography==45.0.2`
- 原因：本机 MySQL 9.x 默认认证方式需要 `cryptography`，否则 PyMySQL 无法完成密码认证
- 新增 `scripts/start-local-mysql.ps1`
- 新增 `scripts/stop.ps1` 中对 `mysql-local.pid` 的停止逻辑
- `scripts/start-local-mysql.ps1` 会基于本机已安装的 `mysqld.exe` 创建项目自管 MySQL 实例：
  - 默认端口 `3307`
  - 默认数据库 `exam_kit_local`
  - 默认账号 `examkit / examkit123`
  - 默认 root 密码 `root123456`
  - 数据目录位于 `data/mysql-local/`
- 自管 MySQL 脚本已处理两类 Windows 细节：
  - `my.ini` 中统一输出为 MySQL 可识别的正斜杠路径
  - 初始化 SQL 改为无 BOM 编码，避免 `init-file` 阶段把 UTF-8 BOM 误当成 SQL 语法
- `apps/api/app/services/system.py` 已修正 `mysql_ready` 判断逻辑：
  - 现在仅在 `database_url.startswith("mysql")` 时返回 `true`
  - 不再把 SQLite 错误地显示成 MySQL ready
- 已验证项目自管 MySQL 实例可正常登录：
  - `root / root123456`
  - `examkit / examkit123`
- 已验证真实 MySQL 空库链路：
  - 新建空库 `exam_kit_alembic_seq`
  - 执行 `alembic upgrade head`
  - 再执行 `initialize_database()`
  - 最终 `alembic_version = 7987b9d25a7f`
  - 种子数据条数验证通过：`tenants = 1`、`users = 2`、`subjects = 4`
- 已验证同一条 `DB_URL` 下 `python -m compileall app` 通过

本次同时确认了一个重要操作约束：

- 真实 MySQL 回归必须串行执行
- 不要并行同时跑 `alembic upgrade head` 和 `initialize_database()`
- 否则会出现两个进程同时抢建首批表，表现为 `Table 'tenants' already exists`

当前这一步说明：

`专业版平台已经不只是“理论支持 MySQL”，而是已经在真实 MySQL 实例上跑通了空库迁移、版本写入和种子初始化。`

### 21.5.9 2026-05-06 MySQL 切换与回滚说明

为了方便后续会话直接接手，补充当前可执行的 MySQL 切换/回滚步骤：

#### 切换到项目自管 MySQL

1. 启动本地 MySQL 实例：
   - `powershell -ExecutionPolicy Bypass -File .\scripts\start-local-mysql.ps1`
2. 也可指定独立端口和库名，例如：
   - `powershell -ExecutionPolicy Bypass -File .\scripts\start-local-mysql.ps1 -Port 3308 -Database exam_kit_alembic_seq -Reinitialize`
3. 将 API 进程的 `DB_URL` 指向对应实例，例如：
   - `mysql+pymysql://examkit:examkit123@127.0.0.1:3307/exam_kit_local?charset=utf8mb4`
4. 首次空库执行：
   - `alembic upgrade head`
   - 再运行应用，或直接执行 `initialize_database()`
5. 若数据库已完成迁移，只需正常启动 API，`initialize_database()` 会检查 revision 并补种子

#### 从 SQLite 开发态切回 MySQL

- 保留现有 `data/app.db` 作为旧演示库
- 不要覆盖 `data/app.db`
- 通过环境变量覆盖 `DB_URL` 即可切换
- 推荐只对 API 进程单独设置 `DB_URL`，避免误影响旧产品链路

#### 回滚到 SQLite

1. 清除当前 API 进程的 `DB_URL` 环境变量，或改回：
   - `sqlite:///./data/app.db`
2. 重新启动 API
3. 若本地自管 MySQL 不再需要，可执行：
   - `powershell -ExecutionPolicy Bypass -File .\scripts\stop.ps1`
4. 如需彻底重建本地自管 MySQL，可再次执行：
   - `powershell -ExecutionPolicy Bypass -File .\scripts\start-local-mysql.ps1 -Reinitialize`

#### 当前回滚注意事项

- 不要把 SQLite 的旧表手工导入到新平台 MySQL 库中
- 不要手工创建专业版业务表后再跑首个 Alembic 迁移
- 如果业务表已经手工创建过，应通过 `stamp` 或重建空库后重跑迁移来收敛，而不是混用两套建表方式

### 21.5.10 2026-05-06 关键读接口回归与一键启动集成续做完成情况

本次继续按上一轮文档顺序，把真实 MySQL 的应用层回归和启动集成补齐：

- 已在同一个真实 MySQL `DB_URL` 下验证以下关键读接口：
  - `GET /platform/api/system/status`
  - `GET /platform/api/auth/me`
  - `GET /platform/api/knowledge/subjects`
  - `GET /platform/api/papers`
  - `GET /platform/api/analysis/dashboard`
- 验证时使用的真实 MySQL 库为：
  - `mysql+pymysql://examkit:examkit123@127.0.0.1:3308/exam_kit_alembic_seq?charset=utf8mb4`
- 回归结果：
  - `system/status` 返回 `mysql_ready = true`
  - `/auth/me` 在开发兼容模式下可返回默认 `admin`
  - `/knowledge/subjects` 返回 4 条学科
  - `/papers` 返回 1 条试卷
  - `/analysis/dashboard` 返回 4 个 metrics、3 个 focus_points、1 个待复核任务
- `scripts/start.ps1` 已新增本地 MySQL 集成参数：
  - `-UseLocalMySql`
  - `-MySqlPort`
  - `-MySqlDatabase`
- `scripts/start.ps1` 现在在 `-UseLocalMySql` 模式下会：
  - 调用 `scripts/start-local-mysql.ps1`
  - 读取对应端口的 `mysql-local-<port>.json`
  - 将其中的 `db_url` 注入 API 进程启动环境
  - 在 `ports.json` 中记录 `mysql_port / mysql_db_url`
- `scripts/start.ps1` 还补了一个兼容策略：
  - 若 `-UseLocalMySql` 模式下发现默认 API 端口已被旧实例占用，不再直接复用旧 API
  - 而是自动切换到新的可用 API 端口，保证当前 MySQL 和当前 API 成对启动
- `scripts/start-local-mysql.ps1` 已进一步改为“按端口隔离数据目录”：
  - 例如 `data/mysql-local-3307/`
  - 例如 `data/mysql-local-3308/`
  - 例如 `data/mysql-local-3309/`
- `scripts/stop.ps1` 已同步支持停止：
  - `mysql-local-*.pid`
- 已验证：
  - `start.ps1 -UseLocalMySql -MySqlPort 3309 -MySqlDatabase exam_kit_startps1 -NoBrowser -NoTunnel -NoInstall`
  - 可正常带起 `3309` 上的本地 MySQL
  - 可正常带起 `8000` 上的 API

本次还确认了两个后续操作约束：

- `start-local-mysql.ps1` 现在是“一个端口对应一个独立数据目录”，不要再让多个端口复用同一个 `data/mysql-local/`
- 如果要做 MySQL 端到端回归，优先复用已有空库 + 串行执行；不要把“建库脚本、Alembic、应用初始化”并发触发

当前这一步说明：

`真实 MySQL 下的关键只读接口已经回归通过，同时一键启动脚本也已经具备可选带起项目自管 MySQL 的能力。`

### 21.5.11 2026-05-06 扩展读接口回归与 ports.json 落盘续做完成情况

本次继续沿着 `start.ps1 -UseLocalMySql` 模式，把更多只读接口回归和端口信息落盘补齐：

- 已在 `start.ps1 -UseLocalMySql` 模式下确认以下端口链路同时成立：
  - `3310` 上的项目自管 MySQL
  - `8000` 上的 API
  - `3000` 上的 Web
- 本次新增回归通过的只读接口：
  - `GET /platform/api/questions`
  - `GET /platform/api/analysis/reports`
  - `GET /platform/api/question-bank/questions`
  - `GET /platform/api/learning/home`
  - `GET /platform/api/workflow/review-tasks`
- 回归结果摘要：
  - `/questions` 返回 4 条原始题
  - `/analysis/reports` 返回 1 条报告
  - `/question-bank/questions` 返回 4 条标准题
  - `/learning/home` 返回学员首页聚合信息
  - `/workflow/review-tasks` 返回 1 条待复核任务
- 结合上一轮结果，当前已在真实 MySQL 下回归通过的读接口包括：
  - `GET /platform/api/system/status`
  - `GET /platform/api/auth/me`
  - `GET /platform/api/knowledge/subjects`
  - `GET /platform/api/papers`
  - `GET /platform/api/analysis/dashboard`
  - `GET /platform/api/questions`
  - `GET /platform/api/analysis/reports`
  - `GET /platform/api/question-bank/questions`
  - `GET /platform/api/learning/home`
  - `GET /platform/api/workflow/review-tasks`
- `scripts/start.ps1` 已补充 `ports.json` 的稳定落盘字段：
  - `use_local_mysql`
  - `mysql_port`
  - `mysql_db_url`
- `use_local_mysql` 已改为标准布尔值写入，而不是 PowerShell 的 `SwitchParameter` 对象

当前这一阶段说明：

`UseLocalMySql 模式下的 API / Web / MySQL 组合链路已经能稳定拉起，且核心查询型页面依赖的多条只读接口已经完成真实 MySQL 回归。`

### 21.5.12 2026-05-06 剩余读接口回归补齐与回归脚本落盘完成情况

本次继续沿着 `21.8` 的第 1 步，把剩余题库 / 学习 / 工作流只读接口补齐回归，并把这一步沉淀为可重复执行的脚本：

- 本次实际回归链路为：
  - `Web: http://127.0.0.1:3000`
  - `API: http://127.0.0.1:8000`
  - `DB_URL: mysql+pymysql://examkit:examkit123@127.0.0.1:3310/exam_kit_portsverify?charset=utf8mb4`
- 本次新增回归通过的只读接口：
  - `GET /platform/api/question-bank/practice-sets`
  - `GET /platform/api/question-bank/mock-exams`
  - `GET /platform/api/learning/practice-sets`
  - `GET /platform/api/learning/sessions`
  - `GET /platform/api/learning/sessions/{id}`
  - `GET /platform/api/learning/wrong-book`
  - `GET /platform/api/learning/mastery`
  - `GET /platform/api/workflow/topics`
- 回归结果摘要：
  - `/question-bank/practice-sets` 返回 `1` 条练习题包
  - `/question-bank/mock-exams` 返回 `1` 条模考试卷
  - `/learning/practice-sets` 返回 `1` 条可练习题包
  - `/learning/sessions` 返回 `1` 条已提交练习记录，状态为 `submitted`
  - `/learning/sessions/1` 可返回对应练习详情
  - `/learning/wrong-book` 返回 `1` 条错题记录
  - `/learning/mastery` 返回 `2` 条掌握度快照
  - `/workflow/topics` 返回 `1` 条由报告衍生的工作流选题
- 已新增可复跑脚本：
  - `scripts/verify-platform-read-apis.ps1`
  - 默认优先读取 `data/run/ports.json` 中的 `api_base`
  - 如无 `ports.json`，回退到 `http://127.0.0.1:8000`
  - 会串行校验 `system.status / question-bank.practice-sets / question-bank.mock-exams / learning.practice-sets / learning.sessions / learning.session_detail / learning.wrong-book / learning.mastery / workflow.topics`
- 本轮同时确认了两个运行约束：
  - `/platform/api/system/status` 当前只反映配置中的 `DB_URL`，不会额外探测对应 MySQL 端口是否仍然存活；如果本地 MySQL 进程退出，`status` 仍可能显示 `mysql_ready = true`，但真正查库的接口会返回 `500`
  - 当同一仓库的 `apps/web` 已经有一个 `next dev` 进程在运行时，`start.ps1 -UseLocalMySql` 再尝试拉第二个 Web 实例会被 Next.js 拒绝；这一轮因此复用了现有 `3000 / 8000 / 3310` 链路做回归，而没有继续启第二个 `3011 / 8011` Web 对

当前这一步说明：

`21.8 中“剩余读接口回归”这一项已经完成，且已经补上可重复执行的回归脚本，后续会话可以先跑脚本再继续开发。`

### 21.5.13 2026-05-06 `/platform/settings` 数据库状态接入续做完成情况

本次继续沿着 `21.8` 的第 1 项，把前端系统设置页从“只展示 API 摘要”推进到“同时消费 API 状态与本地运行时端口信息”：

- 新增 Next 运行时接口：
  - `GET /api/runtime/ports`
  - 读取 `data/run/ports.json`
  - 兼容旧格式中的 `use_local_mysql = { IsPresent: true }`
  - 返回 `api_base / api_port / web_url / web_port / use_local_mysql / mysql_port / mysql_db_url / started_at`
- `/platform/settings` 已新增以下展示信息：
  - 数据库类型
  - 数据库来源
  - API 当前配置中的 `database_url`
  - `ports.json` 中记录的 `mysql_db_url`
  - `ports.json` 中记录的 `mysql_port`
  - 当前 `api_base / web_url`
  - `ports.json` 是否存在
  - `system.status` 与 `ports.json` 是否对齐
- 页面当前会把数据库说明分成两层：
  - API 自报配置
  - 本地运行时记录
- 当两者一致时会显示 `aligned`
- 当 `ports.json` 缺失或与 API 当前返回不一致时，会显示明确的提示语，帮助判断是不是启动脚本中途失败、`ports.json` 沿用了上一轮结果
- 本次前端构建验证通过：
  - `npm run build`

当前这一步说明：

`21.8 中“在 /platform/settings 中展示数据库类型、MySQL 端口或来源说明”这一项已经完成第一版，当前页面已能直接帮助判断本地联调链路到底连向哪里。`

### 21.5.14 2026-05-06 `start.ps1` 冲突提示与 `/platform/settings` 在线探测续做完成情况

本次继续沿着 `21.8` 的前两项，把“本地链路是否真的在线”与“同仓库第二个 Web 实例冲突”这两个高频误判点补齐：

- `scripts/start.ps1` 已补充 `-UseLocalMySql` 下的显式冲突/复用分支：
  - 启动前会先扫描当前仓库 `apps/web` 对应的 `next dev` 相关进程
  - 如果当前链路仍是 `3000 / 8000` 且现有 Web 可用，会明确打印“复用现有 Web”的提示，不再让人误以为拉起了第二组 Web
  - 如果 `UseLocalMySql` 导致 API 自动切到新端口，例如 `8011`，而仓库里又已经有一个旧 Web 在跑，则会直接中止并提示：
    - 当前仓库不应并行拉第二个 Next.js dev server
    - 需要先执行 `scripts/stop.ps1 -AlsoKnownPorts`
    - 或直接复用现有 `3000 / 8000` 链路继续联调
- `scripts/start.ps1` 的执行顺序已调整为：
  - 先判断 API 端口占用后的目标 API 端口
  - 再判断是否存在现有 `apps/web` 的 `next dev` 冲突
  - 再启动 `scripts/start-local-mysql.ps1`
  - 最后在拿到 `mysql-local-<port>.json` 中的 `db_url` 后再拉起新的 API
  - 这样可以避免新 API 在 `UseLocalMySql` 下先于 `DB_URL` 注入启动
- `GET /api/runtime/ports` 已增强为“读取 + 在线探测”：
  - 保留原有 `ports.json` 字段：`api_base / api_port / web_url / web_port / use_local_mysql / mysql_port / mysql_db_url / started_at`
  - 新增 `probes.api`
    - 通过 `${api_base}/api/system/healthz` 探测 API 是否在线
    - 返回 `configured / online / status_code`
  - 新增 `probes.web`
    - 通过 `${web_url}/generate` 探测 Web 是否在线
    - 返回 `configured / online / status_code`
  - 新增 `probes.mysql`
    - 通过 TCP 连接 `127.0.0.1:mysql_port` 探测 MySQL 是否在线
    - 返回 `configured / online / port`
- `/platform/settings` 已新增“在线探测”展示：
  - `API 在线探测`
  - `Web 在线探测`
  - `MySQL 在线探测`
  - 页面现在会同时展示：
    - `ports.json` 是否存在
    - `system.status` 与 `ports.json` 是否对齐
    - API / Web / MySQL 是否真的在线
  - 页面提示语也已拆成两层：
    - “配置是否存在 / 是否对齐”
    - “实例是否真的在线”
- 本次验证结果：
  - `apps/web` 执行 `npm run build` 通过
  - `GET http://127.0.0.1:3000/api/runtime/ports` 当前可返回：
    - `probes.api.online = true`
    - `probes.web.online = true`
    - 在未启用本地 MySQL 的当前链路下，`probes.mysql.configured = false`

当前这一步说明：

`21.8` 中第 1 项“为 start.ps1 -UseLocalMySql 补充 Web 冲突提示或替代流程”和第 2 项“增强 /platform/settings 的在线探测”都已经完成第一版，后续会话可以直接通过 `/platform/settings` 判断“配置存在”和“实例在线”是否一致。

### 21.5.15 2026-05-06 试卷解析器第一版增强续做完成情况

本次继续沿着 `21.8` 的下一项，优先把当前“规则切题”从“整张卷子一个 section + 简单双分类”推进到“分区识别 + 多题型识别 + 小问信息保留”的第一版：

- `apps/api/app/services/papers.py` 已新增第一版大题分区识别：
  - 可识别如下大题标题：
    - `一、单项选择题`
    - `二、案例分析题`
    - `第X部分 单项选择题`
    - `多项选择题 / 判断题 / 填空题 / 简答题 / 计算题 / 综合题 / 材料分析题`
  - 解析时不再默认整张卷子只创建一个 `paper_sections`
  - 会按识别到的大题分区逐段切题，并分别写入 `paper_sections`
- `parse_paper()` 已改为“按 section 逐段入库”：
  - 每个分区单独生成 `PaperSection`
  - 每道题挂到对应 `section_id`
  - `start_no / end_no` 现在会按分区连续计算
  - `section.question_type` 会根据分区类型和区内题型结果自动归并
- 当前第一版题型识别已从“`single_choice / short_answer` 二分”扩展为：
  - `single_choice`
  - `multiple_choice`
  - `judge`
  - `fill_blank`
  - `short_answer`
  - `calculation`
  - `case_analysis`
  - `material_analysis`
  - `composite`
- 识别策略当前为规则版：
  - 若命中大题标题，则优先继承该分区题型
  - 若未命中分区类型，则退回 mixed 场景判断：
    - 有选项且答案为多选格式 -> `multiple_choice`
    - 有选项 -> `single_choice`
    - 答案为 `正确/错误/对/错/√/×` -> `judge`
    - 存在多个 `(1)/(2)` 小问 -> `case_analysis`
    - 题干前段包含“计算” -> `calculation`
    - 题干前段包含“材料/阅读下列” -> `material_analysis`
    - 存在连续下划线 -> `fill_blank`
    - 其余回退 `short_answer`
- 已新增小问计数：
  - 当前使用 `SUBQUESTION_PATTERN` 识别 `(1)/(2)/(3)` 或 `（一）（二）`
  - 会参与 `question_type` 与 `difficulty_level / quality_score` 的估计
- 本次还顺手修了两个可持续开发问题：
  - `apps/api/app/__init__.py` 去掉了 `from .main import app` 的导入副作用，避免在独立验证规则函数时误触发整套应用启动
  - `_split_paper_sections()` 已显式去除 UTF-8 BOM，避免 UTF-8 文本样本第一段大题标题被 BOM 干扰导致漏识别
- 本次已通过的核心验证：
  - `papers.py` 源码级 `compile(...)` 通过
  - 用 UTF-8 文本样本验证 `_split_paper_sections()` 后，当前可得到：
    - `单项选择题 -> 2 道`
    - `案例分析题 -> 1 道`
  - 同一样本下 `_parse_question_block()` 当前可得到：
    - 选择题 -> `single_choice`
    - 案例题 -> `case_analysis`
    - 案例题 `subquestion_count = 2`
- 旧的解析器规则回归脚本链路（`scripts/verify_paper_parser.py` / `scripts/verify-paper-parser.ps1`）已随规则切题退役，不再作为当前回归入口
- 本次还做了真实 `parse_paper` 端到端回归探测，并把环境差异查清楚了：
  - 已显式绑定到当前 API 正在使用的 MySQL：
    - `mysql+pymysql://examkit:examkit123@127.0.0.1:3310/exam_kit_portsverify?charset=utf8mb4`
  - 当前需要注意的是：
    - 系统 `python` 环境里 `fitz / paddleocr` 都可能不可用
    - 但 `apps/api/.venv/Scripts/python.exe` 环境里：
      - `fitz` 可用
      - `paddleocr` 为 OCR 标准依赖，需以当前 `.venv` 的安装结果为准
  - 因此真实回归必须以 `apps/api/.venv` 为准，而不能直接用系统 `python` 的结果判断解析器是否失效
  - 在 `.venv + 当前 DB_URL` 下重新执行 `PaperService(session).parse_paper(2)` 后，返回结果为：
    - `question_count = 57`
    - `section_count = 5`
    - `paper_status = parsed`
  - 进一步核对当前 MySQL 写库结果后确认：
    - `paper_sections` 已按新规则生成 5 个分区：
      - `单项选择题` `1-13`
      - `多项选择题` `14-27`
      - `判断题` `28-28`
      - `单项选择题` `29-42`
      - `多项选择题` `43-57`
    - `exam_questions` 已按分区写入新的 `section_id`
    - 当前 `question_type` 已正确落成：
      - `single_choice`
      - `multiple_choice`
      - `judge`
  - 这说明当前端到端回归的真实结论已经更新为：
    - 新的分区/题型规则本身可用
    - 当前主要环境差异风险不再是 `fitz` 缺失本身，而是“不要误用系统 python 去判断 API 运行环境”
- 历史回归脚本 `scripts/verify-paper-parser.ps1` 已退役；当前应以 API 端到端回归和数据集样本人工复核为准

当前这一步说明：

`21.8` 中“将当前规则切题升级为更可靠的版面分析和多题型解析器”已经完成第一版核心规则升级，且规则回归脚本与真实 `parse_paper` 端到端回归都已跑通；当前更值得推进的重心已经转向“原始题人工复核工作台”。

### 21.5.16 2026-05-06 原始题人工复核工作台第一版续做完成情况

本次继续沿着 `21.8` 的下一项，优先落地“原始题人工复核工作台”的第一版最小闭环：

- 后端 `questions` 已补齐人工复核所需的最小数据结构：
  - `apps/api/app/models/question.py`
    - 为 `exam_questions` 新增 `review_note`
  - `apps/api/app/schemas/questions.py`
    - `QuestionPatchRequest` 已支持 `review_note`
    - 新增 `QuestionBatchReviewRequest`
    - 新增 `QuestionBatchReviewResponse`
    - `QuestionSummary` 已补充 `review_note`
- 后端题目查询已支持筛选：
  - `GET /platform/api/questions`
  - 新增可选筛选参数：
    - `review_status`
    - `question_type`
- 后端已新增批量复核接口：
  - `POST /platform/api/questions/batch-review`
  - 支持：
    - `question_ids`
    - `review_status`
    - `review_note`
  - 当前允许的复核状态：
    - `pending`
    - `approved`
    - `rejected`
    - `needs_revision`
  - 批量复核时会写入：
    - `review_status`
    - `review_note`
    - `reviewed_by`
    - `reviewed_at`
  - 并写入 `audit_logs`：
    - `module = questions`
    - `action = batch_review`
- 前端题目页已从“只读查看页”升级为第一版复核工作台：
  - 文件：
    - `apps/web/app/platform/analysis/questions/page.tsx`
  - 已新增能力：
    - 按 `review_status` 筛选
    - 按 `question_type` 筛选
    - 当前列表勾选 / 全选
    - 录入批量 `review_note`
    - 批量通过
    - 批量标记为 `needs_revision`
    - 批量退回
    - 详情侧栏展示 `review_status / review_note / 题干 / 答案 / 解析 / 考点映射`
- 前端构建验证已通过：
  - `apps/web -> npm run build`

- 本次联调验证结论需要分成两层看：
  - 代码层/构建层：
    - 已完成并通过
  - 真实 HTTP 联调层：
    - 初次回归时 `http://127.0.0.1:8000/platform/api/questions/batch-review` 返回 `405 Method Not Allowed`
    - 后续已定位根因并修复：
      - 原因不是路由实现缺失
      - 而是 `questions` 路由里静态路径 `/batch-review` 写在动态路径 `/{question_id}` 后面，被动态路由先截走了
      - 当前已把 `@router.post("/batch-review")` 提前到动态路由之前
  - 本地服务层直连验证层：
    - 我尝试使用 `.venv` 直接调用 `QuestionExtractionService.batch_review_questions(...)`
    - 但当时联调 MySQL `3310` 已经不在监听，导致无法完成直连写库验证
  - 后续继续收尾时又发现了第二个真实阻塞点：
    - 模型已新增 `review_note`
    - 但数据库还没有迁移该列，导致 `batch-review` 在进入真实执行阶段后会因为缺列进到 `500`
  - 本次已补齐增量 Alembic 迁移：
    - `apps/api/alembic/versions/5f6c7a8b9d10_add_review_note_to_exam_questions.py`
    - 当前 SQLite 已成功升级到：
      - `5f6c7a8b9d10`
    - `exam_questions.review_note` 列已实际存在
  - 本轮最后的真实状态是：
    - 路由顺序问题已修掉
    - 数据库缺列问题已修掉
    - 当前 `8000` 上的 API 进程仍在启动过程中进行 Paddle/Paddlex 模型初始化，`system/status` 在 15 秒窗口内仍可能超时
    - 因此 `batch-review` 的最终 HTTP 成功回归还差“等待 API 启动完成后再重跑一次”
  - 因此本次这一步的真实状态应表述为：
    - “复核工作台第一版代码已落地，前端可构建，后端接口与迁移已实现”
    - “当前缺的不是功能代码，而是等待最新 API 完成启动后，再做一次真实 HTTP 回归”

当前这一步说明：

`21.8` 中“建设原始题人工复核工作台，支持批量确认、退回和版本记录”已经完成第一版代码、路由修正和数据库迁移；下一步最值得做的是在当前 API 完成启动后，补最后一轮 `batch-review` HTTP 成功回归，然后继续补“候选考点人工审核”。


### 21.5.17 2026-05-06 候选考点人工审核第一版完成情况

本次继续沿着 `21.8` 的顺序推进，在不新增表结构的前提下，把“候选考点人工审核”补成了第一版最小闭环：

- 后端已补齐候选考点审核接口与最小业务规则：
  - 文件：
    - `apps/api/app/repositories/questions.py`
    - `apps/api/app/schemas/questions.py`
    - `apps/api/app/services/questions.py`
    - `apps/api/app/api/routes/questions.py`
  - 新增接口：
    - `POST /platform/api/questions/{question_id}/knowledge-links/review`
  - 入参支持：
    - `link_ids`
    - `review_status`
      - `approved`
      - `rejected`
      - `pending`
    - `primary_link_id`
  - 当前已支持的审核动作：
    - 批量确认候选考点
    - 批量退回候选考点
    - 在本次确认通过的候选中指定主考点
    - 若退回的是当前主考点，则自动尝试把剩余已通过映射中的一个补为主考点
  - 已写入审计日志：
    - `module = questions`
    - `action = review_knowledge_links`

- 前端题目页已从“原始题复核工作台”扩成“原始题复核 + 候选考点审核”第一版：
  - 文件：
    - `apps/web/app/platform/analysis/questions/page.tsx`
    - `apps/web/lib/pro-api.ts`
  - 已新增能力：
    - 题目详情侧直接展示全部考点映射
    - 默认勾选待审核候选考点
    - 勾选/取消勾选候选考点
    - 指定主考点
    - 批量确认候选考点
    - 批量退回候选考点
    - 重新执行规则召回：
      - `POST /platform/api/questions/{question_id}/retag`
  - 当前页面定位：
    - 先把“单题候选考点人工收口”跑通
    - 暂未做“跨题批量候选考点审核面板”

- 本次验证结论：
  - 后端静态编译：
    - 已通过 `py_compile`
  - 前端构建：
    - `apps/web -> npm run build`
    - 已通过
  - 真实 HTTP 联调：
    - 本轮未完成
    - 原因不是本次新增接口代码报错，而是当前 `http://127.0.0.1:8000/platform/api/system/status` 在 5 秒窗口内仍超时，说明 API 仍未稳定完成启动或当前 `8000` 链路不可直接用于本轮快速回归

当前这一步说明：

`21.8` 中“在原始题复核工作台基础上，继续建设候选考点人工审核，支持主/次考点批量确认”已经完成第一版代码闭环与前端操作面板；下一步最值得做的是在当前 API 可稳定访问后，补 `knowledge-links/review` 和 `retag` 的真实 HTTP 回归，再决定是否继续升级成跨题批量候选考点审核台。


### 21.5.18 2026-05-06 MySQL 迁移闭环收口完成情况

按“一个功能做完整再碰下一个”的方式，本次只继续收口 MySQL 迁移，不推进其它业务功能。

- 本次补齐的目标不是“再加一个业务接口”，而是把 MySQL 迁移本身做成可管理、可观测、可验证的完整闭环。

- 配置层已补充迁移控制开关，且保留后续扩展预留：
  - 文件：
    - `apps/api/app/core/config.py`
    - `.env.example`
  - 新增配置：
    - `DB_AUTO_MIGRATE`
    - `DB_SEED_ON_STARTUP`
    - `DB_MIGRATION_TARGET`
  - 当前含义：
    - `DB_AUTO_MIGRATE`
      - 控制 API 启动时是否自动执行迁移
    - `DB_SEED_ON_STARTUP`
      - 控制空库启动时是否自动写入演示种子
    - `DB_MIGRATION_TARGET`
      - 预留后续按 revision 定点迁移或灰度迁移的入口，当前默认 `head`

- 迁移底座已补齐状态查询能力：
  - 文件：
    - `apps/api/app/db/bootstrap.py`
    - `apps/api/app/services/system.py`
    - `apps/api/app/schemas/system.py`
  - 新增能力：
    - `get_current_revision()`
    - `get_head_revision()`
    - `get_migration_status()`
  - 当前 `migration_status` 会区分：
    - `up_to_date`
    - `outdated`
    - `stamp_needed`
    - `partial_schema`
    - `empty_schema`
    - `unknown`
  - `/platform/api/system/status` 现在会返回：
    - `database_type`
    - `migration_target`
    - `auto_migrate`
    - `seed_on_startup`
    - `alembic_current_revision`
    - `alembic_head_revision`
    - `migration_status`
    - `migration_ready`
    - `database_ping_ok`

- 迁移执行链路已补成独立脚本：
  - 文件：
    - `scripts/db-migrate.ps1`
  - 当前支持：
    - 使用当前 `DB_URL` 执行 `alembic upgrade`
    - 可选自动拉起项目自管 MySQL
    - 可选仅查看状态而不重复迁移
    - 可选在迁移完成后补种子数据
  - 当前参数：
    - `-Revision`
    - `-UseLocalMySql`
    - `-MySqlPort`
    - `-MySqlDatabase`
    - `-SeedData`
    - `-SkipMigrate`

- 文档与使用入口已补齐：
  - 文件：
    - `README.md`
  - 已新增：
    - MySQL 迁移的单独说明
    - 推荐执行方式
    - 新增环境变量解释

- 这一步的“功能完成标准”现在变成：
  - 不只是“有 Alembic”
  - 还包括：
    - 可以控制启动时是否自动迁移
    - 可以控制是否自动写种子
    - 可以查看当前 revision 和 head 是否一致
    - 可以用单独脚本完成本地 MySQL 迁移与验收

- 本次验证计划：
  - 先做 Python 静态编译
  - 再用 `scripts/db-migrate.ps1` 在本地 MySQL 上做一次真实迁移状态验证
  - 验证结果将在本节后续补充

当前这一步说明：

MySQL 迁移已经从“底座可用”推进到“功能闭环基本完整”。本轮剩余工作不再扩展新模块，而是继续把这条链路的真实验证跑完并把结论写回。

- 本次真实验证结果已补充：
  - Python 静态编译：
    - `apps/api/app/core/config.py`
    - `apps/api/app/db/bootstrap.py`
    - `apps/api/app/services/system.py`
    - `apps/api/app/schemas/system.py`
    - 已通过
  - 真实迁移状态验证：
    - 执行：
      - `.\scripts\db-migrate.ps1 -UseLocalMySql -MySqlPort 3309 -MySqlDatabase exam_kit_local -SkipMigrate`
    - 实际结果：
      - `database_type = mysql`
      - `migration_target = head`
      - `head_revision = 5f6c7a8b9d10`
      - `status = empty_schema`
      - `migration_ready = true`
      - `database_ping_ok = true`
    - 说明：
      - 当前 `3309 / exam_kit_local` 已可被项目脚本稳定接管
      - 在未执行 upgrade 的前提下，状态可正确识别为空库待迁移，而不是“误报正常”或“直接报错”
  - 系统状态服务验证：
    - 通过 `.venv` 直调 `SystemService().get_status()`
    - 已确认 `/platform/api/system/status` 现在可返回：
      - 当前 `DB_URL`
      - `alembic_current_revision`
      - `alembic_head_revision`
      - `migration_status`
      - `migration_ready`
      - `database_ping_ok`

- 本轮额外修掉的真实问题：
  - `scripts/db-migrate.ps1` 初版在项目根目录执行 Python，导致 `app` 包不可导入
    - 当前已修正为在 `apps/api` 工作目录下执行状态检查与种子逻辑
  - `scripts/start-local-mysql.ps1` 复用已存在本地 MySQL 实例时，只复用了端口，没有保证“目标库存在 + 目标用户有库权限”
    - 当前已补齐：
      - `CREATE DATABASE IF NOT EXISTS`
      - `GRANT ALL PRIVILEGES ON <db>.*`
    - 这意味着后续切换到新的本地数据库名时，不再需要手工补库和授权
  - `get_migration_status()` 初版在数据库不可连接时会直接抛异常
    - 当前已改为返回：
      - `status = connection_failed`
      - `database_ping_ok = false`
    - 这样系统状态页和脚本都能把问题显示出来，而不是直接炸掉

当前这一步说明：

MySQL 迁移这个功能已经完成了“配置控制 + 脚本执行 + 状态可观测 + 真实本地 MySQL 验证”这一轮闭环。下一步如果仍只做这一个功能，最值得继续推进的是再补一次真正的 `alembic upgrade head` + `seed` 端到端验证，并把迁移规范固化成团队使用约定。


### 21.6 当前仍未完成的部分

以下内容当前仍处于“骨架/占位/演示数据”阶段，尚未实现真实业务逻辑：

- MySQL 生产化部署参数收敛与团队统一切换方式
- Alembic 后续增量迁移规范与变更流程
- 登录设备管理、过期会话清理任务
- 操作日志筛选分页和只读访问审计
- 细粒度数据权限与租户隔离策略
- 高质量 OCR / 版面分析
- 复杂题型切题和小问结构化
- 原始题人工复核工作台
- 标准题高级去重与归并
- 候选考点人工审核与批量确认
- LLM 辅助分类
- PDF / Excel 报告导出
- 自动组卷策略配置
- 学员答题完整 App 体验
- 工作流真实写操作
- student-app 独立工程

已从“未完成”推进到“第一版可用”的部分：

- 试卷上传：已完成文件保存、素材入库、试卷入库和前端上传入口
- OCR / 文本解析：已复用现有 parser 接入试卷解析接口
- 切题：已完成规则切题并写入 `paper_sections`、`exam_questions`
- 原始题编辑：已完成单题 PATCH 接口
- 候选考点识别：已完成基于关键词的规则候选召回
- 候选考点人工审核：已完成单题详情侧的第一版人工审核闭环，支持候选确认、退回、指定主考点与重新召回
- 标准题同步：已完成原始题到标准题和题源关联的第一版链路
- 报告导出：已完成 Markdown 报告导出
- 自动组卷：已完成自动生成题包和模考的第一版链路
- 学员答题写入：已完成开始练习、提交答案、错题本和掌握度更新
- 真实登录鉴权与 JWT：已完成密码哈希、登录发 Token、`/me` Token 解析和前端 Token 注入
- 强制鉴权、角色权限和操作日志：已完成关键写接口的 Bearer Token、角色校验和 `audit_logs` 写入
- 操作日志查询页：已完成最近日志接口和 `/platform/settings` 展示
- 刷新令牌与登出失效：已完成 refresh token 会话表、刷新接口和服务端吊销
- 失败请求审计：已完成 `/api/*` 与 `/platform/api/*` 的 4xx/5xx 记录
- MySQL / Alembic 迁移底座：已完成环境变量覆盖、`docker-compose` 中的 MySQL 服务、首个迁移文件、启动自动 `upgrade head` 与旧库 `stamp` 兼容
- 真实 MySQL 联调：已完成项目自管 MySQL 实例、自定义 `DB_URL`、空库 `alembic upgrade head`、`initialize_database()` 和数据条数验证
- 真实 MySQL 读接口回归与一键启动集成：已完成关键读接口回归、`start.ps1 -UseLocalMySql` 和端口隔离数据目录方案
- 扩展读接口回归：已完成 `questions / analysis.reports / question-bank.questions / learning.home / workflow.review-tasks`
- 剩余读接口回归补齐：已完成 `question-bank.practice-sets / question-bank.mock-exams / learning.practice-sets / learning.sessions / learning.session_detail / learning.wrong-book / learning.mastery / workflow.topics`
- 读接口回归脚本化：已完成 `scripts/verify-platform-read-apis.ps1`
- `/platform/settings` 运行态数据库状态接入：已完成 `system.status + ports.json` 的第一版展示

也就是说：

`在不影响原有内容生产工具的前提下，并行接入了专业版平台第一期底座，并开始把演示骨架替换为真实业务流程。`


### 21.7 当前需要注意的兼容事项

仓库当前采取双栈并行策略：

- 旧 SQLite 表：
  - `library_files`
  - `generation_jobs`
  - `workflow_topics`
  - `workflow_events`
- 旧前端组件已恢复：
  - `PublishPackagePreview.tsx`
  - `ReviewActionList.tsx`
  - `ReviewFloatingPanel.tsx`
- 新平台共享能力位于：
  - `apps/api/app/*`
  - `apps/web/lib/pro-api.ts`
  - `apps/web/app/analysis/*`
  - `apps/web/app/knowledge/page.tsx`
  - `apps/web/app/question-bank/*`
  - `apps/web/app/learners/page.tsx`
  - `apps/web/app/platform/*`

说明：

- 默认用户路径仍然走旧功能
- 新平台通过并行页面与 `/platform/api/*` 接口进入
- 新平台前端页面统一通过 `/platform/*` 进入
- 主启动入口 `apps/api/main.py` 已同时初始化旧 SQLite 存储和新平台 SQLAlchemy 迁移链路
- 上传的专业版试卷文件默认进入 `data/papers/{yyyymm}/`
- 当前切题规则偏保守，复杂排版、材料题、多小问、答案区分离的试卷仍需后续增强
- 当前 `security.secret_key` 默认值仅适合开发环境，生产或公网部署必须通过环境变量或配置文件替换
- `/platform/api/auth/me` 当前为了兼容开发仍允许无 Token 返回 admin；关键写接口已强制 Bearer Token
- 目前审计日志查询页只展示最近日志，筛选、分页和只读访问尚未记录
- 当前 Alembic 已显式忽略旧产品表 `library_files / generation_jobs / workflow_topics / workflow_events`，后续不要把这些旧表误并入新平台 metadata
- 当前本地 `data/app.db` 已被自动 `stamp` 到 `7987b9d25a7f`；若后续手工改库后出现“部分新表 + revision 丢失”，应先备份，再决定是重建还是手工校正版本
- 当前仓库已提供项目自管 MySQL 实例脚本 `scripts/start-local-mysql.ps1`，优先建议用它做本地联调，而不是直接依赖系统级 MySQL 服务的现有密码和配置
- 当前真实 MySQL 验证已经跑通，但 API 接口回归仍建议在同一 `DB_URL` 下串行执行，不要把 `alembic upgrade head` 和 `initialize_database()` 并行触发
- 当前本地 MySQL 辅助信息文件已经按端口区分：
  - `data/run/mysql-local-3307.json`
  - `data/run/mysql-local-3308.json`
  - `data/run/mysql-local-3309.json`
- 当前本地 MySQL 数据目录也已经按端口区分：
  - `data/mysql-local-3307/`
  - `data/mysql-local-3308/`
  - `data/mysql-local-3309/`
- `ports.json` 现在已预留并写入：
  - `use_local_mysql`
  - `mysql_port`
  - `mysql_db_url`
- 当前 `ports.json` 只有在 `start.ps1` 成功走完整个 API / Web 启动流程后才会刷新；如果启动中途因 Web 冲突失败，`data/run/ports.json` 可能仍是上一次成功运行的内容
- 真正联调时仍应以启动脚本打印出的 `DB_URL` 或显式传入的 `DB_URL` 为准
- 当前 `start.ps1 -UseLocalMySql` 模式下若 8000 端口已有旧 API，会自动切到新的 API 端口；联调时请优先读取 `data/run/ports.json`
- 如果 `/platform/api/system/status` 仍显示 MySQL 配置，但题库 / 学习 / 工作流查询接口突然开始 `500`，先检查对应 `mysql_port` 是否还在监听；必要时先执行 `scripts/start-local-mysql.ps1 -Port <port> -Database <db>`
- 当前同一仓库下不适合并行拉起第二个 `apps/web` 的 `next dev` 进程；如需重做 `UseLocalMySql` 联调，优先复用现有 `3000` Web，或先停止已有 Web 再启动新链路
- 当前 `/platform/settings` 已增加 API / Web / MySQL 的第一版在线探测，但仍然以 `ports.json` 为探测入口；如果 `ports.json` 本身已经陈旧，页面会提示“配置存在但实例离线”，这时仍要结合启动脚本输出和实际监听端口一起判断
- PowerShell 管道直接传中文测试脚本可能出现编码降级，集成验证建议使用 UTF-8 文件或 Unicode 转义字符串
- 后续若继续推进专业版平台，应继续保持“不覆盖旧功能”的接入原则
- 本次验证时还确认了一个脚本约束：`UseLocalMySql` 场景下应先完成 Web 冲突判断，再启动本地 MySQL，再启动新 API；后续若再改 `start.ps1`，不要把这个顺序改回去
- 历史 `verify-paper-parser.ps1` / `verify_paper_parser.py` 链路已随规则切题移除，不再维护；继续推进解析器时，优先走 API 端到端链路或直接复核已导出的 `ai_prediction`
- 当前解析器端到端回归必须显式使用 `apps/api/.venv/Scripts/python.exe` 或直接走正在运行的 API；不要再用系统 `python` 的依赖情况误判真实联调链路
- 当前 `.venv` 环境下应以 `fitz` 与 `paddleocr` 作为 PDF/图像解析依赖基线；后续增强结构化解析时继续围绕 PaddleOCR 能力扩展
- 当前解析器仍然是“文本规则版”，尚未做到真正的 PDF 版面坐标分析；复杂材料题、跨页题、表格题和 OCR 噪声场景仍需要后续增强
- 当前原始题复核工作台第一版代码已完成，但要做真实接口回归时，必须确认当前 `8000` 上运行的是最新源码；若 `POST /platform/api/questions/batch-review` 仍返回 `405`，优先重启 API，而不是先怀疑路由代码缺失
- 当前通过 `system.status` 可看到 API 配置仍指向 `3310` 上的 MySQL，但本轮后半段该端口已拒绝连接；继续联调前应先确认 MySQL 是否仍在监听，必要时先重启本地 MySQL 或更新 `ports.json`
- 当前 `questions.batch-review` 的两个主要代码级阻塞已经处理：
  - 路由顺序冲突已修复
  - `exam_questions.review_note` 缺列已通过 Alembic 迁移补齐
- 当前 API 启动耗时明显受 Paddle/Paddlex 模型初始化影响；如果 `start.ps1` 看起来超时，不代表迁移失败，应优先看 `data/logs/api.err.log` 是否仍在打印模型加载日志
- 当前候选考点人工审核第一版直接复用了 `question_knowledge_links`，未新增备注字段或版本表；因此当前只能表达“通过 / 退回 / 主次考点”，还不能记录更细的人工审核意见
- 当前 `knowledge-links/review` 的第一版是“单题详情侧闭环”，还没有做跨题批量候选审核队列；如果后续要继续扩展，优先建议先补筛选维度和批量面板，而不是先拆新表
- 当前 `retag` 仍然是规则召回重跑：会删除当前题目下 `tag_source = rule_keyword` 且 `review_status = pending` 的旧候选，再重新写入新候选；已审核通过或已退回的映射不会被这一步清掉
- 本轮快速探测里 `http://127.0.0.1:8000/platform/api/system/status` 在 5 秒超时，说明继续做真实 HTTP 回归前，仍要先确认当前 `8000` 是否已经跑到最新源码并完成启动

### 21.7.1 Cloudflare Tunnel 接入

当前项目已补充 Cloudflare named tunnel 配置，参照 `DESK` 项目结构：

- `deploy/cloudflare/config.named.example.yml`
- `deploy/cloudflare/config.yml`
- `deploy/cloudflare/start_named_tunnel.bat`
- `deploy/cloudflare/README.md`

当前预设公网入口：

- `https://context.panspan.cloud`

当前 ingress 指向：

- `context.panspan.cloud -> http://127.0.0.1:3000`

说明：

- 由于新平台前端统一在 `/platform/*`
- 且新平台 API 统一走 `/platform/api/*`
- 所以 Cloudflare tunnel 只需要暴露 Web 端口 `3000`
- 旧产品仍保留本地默认入口，不受该公网入口影响


### 21.8 后续会话推荐的继续开发顺序

建议下一会话开始时，优先按以下顺序继续：

1. 等待当前 API 完成启动后，重跑 `POST /platform/api/questions/batch-review` 的真实 HTTP 回归，并核对 SQLite 写库结果
2. 在当前 API 可稳定访问后，补 `POST /platform/api/questions/{question_id}/knowledge-links/review` 与 `POST /platform/api/questions/{question_id}/retag` 的真实 HTTP 回归
3. 将当前候选考点审核从“单题详情侧闭环”升级为“跨题批量候选审核队列”，补待审核筛选、批量主/次考点确认与批量退回
4. 将当前标准题同步升级为相似题去重、归并和版本管理
5. 建设操作日志筛选分页、会话管理页和过期会话清理任务
6. 将学习练习页面从演示提交升级为真实答题 UI
7. 补齐 PDF / Excel 导出和报告模板
8. 如需继续增强解析器，再补更细的 PDF 版面坐标分析与复杂题型结构化


### 21.9 本次改造涉及的核心文件

后端核心新增：

- `apps/api/main.py`
- `apps/api/app/core/config.py`
- `apps/api/app/core/security.py`
- `apps/api/app/db/session.py`
- `apps/api/app/db/bootstrap.py`
- `apps/api/app/models/*`
- `apps/api/app/repositories/*`
- `apps/api/app/repositories/audit.py`
- `apps/api/app/services/*`
- `apps/api/app/services/audit.py`
- `apps/api/app/services/tagging.py`
- `apps/api/app/api/routes/*`
- `apps/api/main.py`
- `apps/api/alembic.ini`
- `apps/api/alembic/env.py`
- `apps/api/alembic/versions/7987b9d25a7f_init_professional_platform_schema.py`
- `docker-compose.yml`
- `config.yaml`
- `.env.example`
- `scripts/start-local-mysql.ps1`
- `scripts/verify-platform-read-apis.ps1`
- `scripts/start.ps1`
- `scripts/stop.ps1`

前端核心新增/重写：

- `apps/web/lib/pro-api.ts`
- `apps/web/app/api/runtime/ports/route.ts`
- `apps/web/app/platform/settings/page.tsx`
- `apps/web/components/shared/*`
- `apps/web/app/analysis/*`
- `apps/web/app/platform/analysis/papers/page.tsx`
- `apps/web/app/platform/analysis/reports/page.tsx`
- `apps/web/app/platform/question-bank/page.tsx`
- `apps/web/app/platform/learners/page.tsx`
- `apps/web/app/knowledge/page.tsx`
- `apps/web/app/question-bank/*`
- `apps/web/app/learners/page.tsx`
- `apps/web/app/platform/*`

前端兼容保留：

- `apps/web/lib/api.ts`
- `apps/web/components/Nav.tsx`
- `apps/web/app/generate/page.tsx`
- `apps/web/app/history/page.tsx`
- `apps/web/app/library/page.tsx`
- `apps/web/app/settings/page.tsx`
- `apps/web/app/workflow/page.tsx`
- `apps/web/components/PublishPackagePreview.tsx`
- `apps/web/components/ReviewActionList.tsx`
- `apps/web/components/ReviewFloatingPanel.tsx`


### 21.10 给后续会话的接手提示

如果后续会话要继续开发，建议先读以下文件：

1. `docs/PRO_EDU_PLATFORM_ARCHITECTURE.md`
2. `apps/api/main.py`
3. `apps/api/app/db/bootstrap.py`
4. `apps/api/app/models/__init__.py`
5. `apps/api/app/api/router.py`
6. `apps/web/lib/api.ts`
7. `apps/web/lib/pro-api.ts`
8. `apps/web/components/Nav.tsx`
9. `apps/web/app/analysis/dashboard/page.tsx`
10. `scripts/verify-platform-read-apis.ps1`
11. `apps/web/app/platform/settings/page.tsx`
12. `apps/web/app/api/runtime/ports/route.ts`

接手时可默认认为：

- 原有功能仍然是默认可用入口
- 新平台已经并行接入
- `21.8` 的第 1 步“剩余读接口回归”已经完成；继续开发前可先运行 `scripts/verify-platform-read-apis.ps1`
- 如果回归脚本里只有 `system.status` 通过、其余查库接口失败，优先检查 `data/run/ports.json` 指向的本地 MySQL 端口是否仍在监听
- `/platform/settings` 现在已经能同时展示数据库来源、`ports.json` 对齐状态和 API / Web / MySQL 在线探测；如果页面显示“配置存在但实例离线”，优先检查 `ports.json` 是否陈旧、以及对应进程是否已退出
- `start.ps1 -UseLocalMySql` 现在已经补上同仓库 `apps/web` 的显式冲突提示；如果它提示不要拉第二个 Next.js dev server，优先复用现有 `3000 / 8000` 链路，或先执行 `scripts/stop.ps1 -AlsoKnownPorts`
- 解析器当前应以 API 端到端链路和已导出的 `ai_prediction` 为回归基准；旧 `verify-paper-parser.ps1` 已下线
- 真实 `parse_paper` 端到端回归已经在当前 MySQL 上跑通；继续接手解析器时，优先复用 `apps/api/.venv/Scripts/python.exe` 或直接走 API，而不是系统 `python`
- 原始题人工复核工作台第一版代码已经落地；如果当前 `8000` 上调 `batch-review` 仍是 `405`，优先重启 API 进程并确认 MySQL 端口仍在线
- 当前 `batch-review` 的路由顺序和 `review_note` 缺列问题都已经修完；如果下次仍调不通，优先判断的是“API 是否完成启动”，而不是继续改这两处代码
- 候选考点人工审核第一版已经落到 `questions` 模块里，新增的核心入口是 `POST /platform/api/questions/{question_id}/knowledge-links/review`；接手时如果前端已能构建但接口还没验通，优先先做真实 HTTP 回归
- 当前候选考点审核仍是“单题详情侧收口”模式；如果下个会话继续推进，优先补“跨题待审核候选队列”和“批量审核”能力，而不是先重构数据模型
- 下一步更值得推进的是“复核工作台真实回归收尾”和“候选考点审核批量化”，继续把新平台演示骨架替换为真实业务流程
