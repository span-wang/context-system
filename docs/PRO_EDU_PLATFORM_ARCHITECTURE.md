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
