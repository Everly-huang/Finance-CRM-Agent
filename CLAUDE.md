# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

金融产品智能推荐系统(合规版)——面向银行/券商理财经理的轻量化智能辅助工具。核心方案:「算法精准匹配 — AI 合规解读 — 人工复核兜底」三层递进体系。双数据挖掘算法覆盖两类场景:KNN 最近邻用于新客户冷启动,Apriori 关联规则用于老客户购买行为挖掘;规划中的 AI Agent 层(Deepseek API)负责推荐结果的合规化、通俗化解读。

**权威规格文档是根目录的 [金融产品智能推荐系统需求文档.md](金融产品智能推荐系统需求文档.md)**(V1.1,已对齐代码现状)。代码、注释、API 消息、文档均为中文。

**文档体系三件套**:
- [金融产品智能推荐系统需求文档.md](金融产品智能推荐系统需求文档.md) — 权威规格(「什么与为什么」,现状/规划已标注)
- [项目落地清单.md](项目落地清单.md) — 未实现项待办(「还差什么与怎么验收」,ENG/DAT/ALG/AGT/SVC/UI/DEP 分组)
- [需求文档评审报告.md](需求文档评审报告.md) — 2026-09-03 修订依据(问题清单与证据,归档)

## 当前实现状态(重要)

**已实现**(2026-09-03,四层架构一期全链路贯通):
- 数据层 + 算法层(纯 Python stdlib,4 个文件):[db_connection.py](backend/database/db_connection.py)(含 `agent_audit_log` 审计表)、[nearest_neighbor.py](backend/algorithms/nearest_neighbor.py)、[association_rules.py](backend/algorithms/association_rules.py)
- Agent 合规解读层([backend/agent/](backend/agent/)):[compliance_engine.py](backend/agent/compliance_engine.py)(黑名单+正则+注入检测+输出后校验,含否定语境豁免)、[llm_client.py](backend/agent/llm_client.py)(Deepseek,30s 超时+重试1次+模板降级)、[prompt_templates.py](backend/agent/prompt_templates.py)(System Prompt+降级模板+免责声明)、[audit_logger.py](backend/agent/audit_logger.py)、[rag_retriever.py](backend/agent/rag_retriever.py)(一期 Mock 空上下文)
- 服务编排层([backend/services/recommendation_service.py](backend/services/recommendation_service.py)):推荐编排 + Agent 解读流水线(输入校验→RAG→LLM→输出后校验→审计落库)
- FastAPI 5 个 /api 端点 + 根路径 `/` 健康检查(启动脚本就绪轮询依赖),[main.py](backend/main.py) 路由全部委托编排层
- [frontend/app.py](frontend/app.py):Streamlit 单页应用,五区布局(参数配置/一键计算/结果表格/AI 解读/常驻合规声明),启动时预热触发建表播种
- 根目录 [requirements.txt](requirements.txt)(finance-crm 环境已齐装)

**未实现**(主项;完整清单与验收口径见 [项目落地清单.md](项目落地清单.md) 状态表):Pydantic 模型(SVC-04)、API 错误码 4xx 规范(SVC-03)、算法输出数值字段(ALG-01)、金额裁剪提示(ALG-02)、Plotly 可视化(UI-03)、RAG 二期(AGT-06)、pytest 自动化测试(ENG-05;手动冒烟 ENG-04 已落地,见「常用命令」)

注意:需求文档 V1.1 已与技术栈现状对齐(技术栈表为「当前实现/目标形态」双列:算法层当前=纯 Python stdlib,scikit-learn/mlxtend 为可选演进;Streamlit 前端为规划)。以文档标注的[现状]/[规划]为准。

## 常用命令

无构建/lint/测试命令、无 CI。项目专用 conda 环境 `finance-crm`(D:\Anaconda\envs\finance-crm,Python 3.11.16),依赖见根目录 [requirements.txt](requirements.txt)(2026-09-03 已齐装)。**一键启动**:双击 [start_demo.bat](start_demo.bat)(Git Bash 下用 [start_demo.sh](start_demo.sh);核心逻辑在 `start_demo.py`,支持 `--smoke` 自动冒烟 / `--demo` 演示模式)——自动完成 secrets.toml→后端环境变量桥接、起双进程、轮询就绪。手动分步(本机 `python` 命令是 Windows Store stub 不可用,必须用环境完整路径;先起后端再起前端,前端启动会预热触发建表播种):

```bash
cd backend && /d/Anaconda/envs/finance-crm/python.exe main.py            # 启动 uvicorn: http://127.0.0.1:8000
cd frontend && /d/Anaconda/envs/finance-crm/python.exe -m streamlit run app.py  # Streamlit: http://127.0.0.1:8501
```

API 测试示例:

```bash
# KNN 推荐(category_id: 70 稳健理财 / 71 成长基金 / 72 进取投资)
curl -X POST http://127.0.0.1:8000/api/recommend/ \
  -H "Content-Type: application/json" \
  -d '{"method":"nearest_neighbor","category_id":70,"price":50000}'

# 关联规则推荐(selected_product 为产品 ID)
curl -X POST http://127.0.0.1:8000/api/recommend/ \
  -H "Content-Type: application/json" \
  -d '{"method":"association","selected_product":4}'
```

其他端点:`GET /api/products/`(可按 category_id 过滤)、`GET /api/products/all/`、`GET /api/categories/`、`POST /api/recommend/explain`(AI 合规解读,请求体 `{"recommendations": [...], "user_context": {...}}`,响应含 `explanation/source/degraded/compliance/disclaimer`)。FastAPI 自动文档在 http://127.0.0.1:8000/docs。

### Deepseek API Key 与解读模式(DEP-02)

LLM 调用由后端进程([llm_client.py](backend/agent/llm_client.py))发起,读取环境变量 **`DEEPSEEK_API_KEY`**(可选:`DEEPSEEK_BASE_URL` 默认 `https://api.deepseek.com`、`DEEPSEEK_MODEL` 默认 `deepseek-chat`)。注意:解读由后端生成,key 需注入**后端进程**(uvicorn)而非仅前端:

```bash
# PowerShell(当前会话)
$env:DEEPSEEK_API_KEY = "sk-xxx"
# 或 Git Bash(起后端前)
DEEPSEEK_API_KEY=sk-xxx /d/Anaconda/envs/finance-crm/python.exe main.py
```

- **key 不入 git**:仅通过环境变量或 Streamlit secrets(`frontend/.streamlit/secrets.toml`,模板已建,空 key 即走降级;填真实 key 后 start_demo.bat 自动桥接注入)注入,禁止硬编码进任何代码/文档;.gitignore 已排除 secrets 与数据库文件(ENG-03)
- **无 key 不报错**:llm_client 检测到无 key / 断网 / 超时(30s,重试 1 次;真实解读实测生成约 18s)时自动回退预置合规模板,响应标注"基础版解读"并置 `degraded=true`
- **secrets 桥接(已实现)**:`st.secrets` 属前端进程,后端进程无法直接读;start_demo.py 已实现 `bridge_secrets()`——解析 secrets.toml 后将 key 注入后端子进程环境变量。仅手动分步启动时需自行注入环境变量(见上)
- **DEMO_MODE 开关(SVC-05,已实现)**:环境变量 `DEMO_MODE`(1/true/yes)。`True` 时 [recommendation_service.py](backend/services/recommendation_service.py) 的 `generate_explanation` 直接返回预置演示样例(`source="demo"`,不触及 llm_client,禁止调用任何大模型 API),供公开分享链接场景(零 key 消耗/泄露风险);默认不设=`False` 走 LLM 调用。本地演练:`start_demo.py --demo --smoke`;公开部署:部署平台配置环境变量即可

无测试框架,开发时可绕过 HTTP 直接调算法做冒烟验证(必须以 backend/ 为导入根):

```bash
cd backend && /d/Anaconda/envs/finance-crm/python.exe -c "from algorithms.nearest_neighbor import recommend_products; print(recommend_products(70, 50000))"
cd backend && /d/Anaconda/envs/finance-crm/python.exe -c "from algorithms.association_rules import recommend_products_by_association; print(recommend_products_by_association(4))"
```

后端已启动时的 HTTP 冒烟([smoke_test.py](backend/smoke_test.py),ENG-04,7 项检查,退出码 0=全绿;后端以 DEMO_MODE=True 启动时加 `--expect-demo` 断言 source=demo):

```bash
cd backend && /d/Anaconda/envs/finance-crm/python.exe smoke_test.py
```

## 架构

### 当前(已实现的完整链路)

```
[frontend/app.py](Streamlit 五区) --requests--> [main.py](FastAPI 5 个 /api 端点)
    --> [services/recommendation_service.py](编排层)
        ├─ 推荐: algorithms/ → db_connection.py → SQLite
        └─ 解读: agent/compliance_engine(输入校验)→ rag_retriever(Mock)→ llm_client(LLM/降级)
                 → compliance_engine(输出后校验)→ audit_logger → agent_audit_log 表
```

- **数据访问为过程式风格**:无 ORM、无连接池,每次调用新建 `sqlite3.connect`;`init_database()` 惰性建表+播种(模块级 `_database_initialized` 标志保证幂等),但仅由 `get_financial_products()` 触发(见已知陷阱)
- **数据流**:10 个种子产品、8 位客户 38 条购买记录、硬编码分类 70/71/72;KNN 每次推荐调用 `add_customer_input()` 写入 `customer_inputs` 表(隐式用户行为日志);每次 Agent 解读调用写入 `agent_audit_log` 表(输入/输出/校验结果/是否降级)
- **Agent 解读流水线**(需求文档 7.2 风控流程):输入合规校验(拦截则不调 LLM,直接模板)→ RAG 检索(Mock 空上下文)→ LLM 生成 → 输出后合规校验(违规整段替换模板)→ 审计落库;解读响应统一含 `disclaimer` 免责声明字段
- **算法要点**(均为纯 Python 实现):
  - KNN([nearest_neighbor.py](backend/algorithms/nearest_neighbor.py)):分类权重 0.4 / 价格权重 0.6,归一化欧氏距离;全部产品中的最小距离 ≤0.3 → 整批相似推荐,>0.3 → 整批按预期收益排序的热门推荐;默认 Top 6
  - Apriori([association_rules.py](backend/algorithms/association_rules.py)):min_support=0.2、min_confidence=0.5,按置信度×支持度(association_score)排序;不足 Top 6 用热门产品补齐;入口 `recommend_products_by_association(product_id)`

### 剩余规划(见 [项目落地清单.md](项目落地清单.md))

- RAG 二期:Chroma 向量库 + 产品文档表 + 知识库构建(AGT-06,替换 [rag_retriever.py](backend/agent/rag_retriever.py) Mock 即可,调用方无改动)
- Pydantic 请求/响应模型(SVC-04)、API 错误码 4xx 规范(SVC-03,替代现状 200+error)
- 算法输出数值字段(ALG-01:similarity/distance/lift)、金额裁剪提示(ALG-02)、Plotly 可视化(UI-03)
- 演示排练脚本(DEP-03)、公开部署路径评估(DEP-04);其余(DAT-02/ALG-03/ALG-04/UI-04 等)见清单状态表

## 已知陷阱

- ~~[db_connection.py:8](backend/database/db_connection.py#L8) 硬编码 `db_path = r'D:\programme\CRM\...'`~~ **已于 2026-09-03 修复(ENG-01)**:`get_db_connection()` 现使用 `os.path.join(os.path.dirname(os.path.abspath(__file__)), 'financial_products.db')`,读写均落在仓库内 [financial_products.db](backend/database/financial_products.db)
- **惰性初始化陷阱**:`init_database()` 仅由 `get_financial_products()` 触发,`get_customer_records()` 等其余读函数不触发。全新环境首个请求若为关联规则推荐,会报 `no such table: customer_records`(被编排层 try/except 包装为「关联规则算法错误」返回)。首次启动先访问一次 `GET /api/products/` 或跑一次 KNN 触发建表播种(前端 app.py 启动时会预热,正常走页面流程不受影响)
- ~~CORS 仅允许 5173~~ **已于 2026-09-03 修复(UI-02)**:现允许 `http://localhost:8501` 与 `http://127.0.0.1:8501`(Streamlit 默认端口)
- 全项目无 `__init__.py`——[algorithms/](backend/algorithms/)、[database/](backend/database/)、[agent/](backend/agent/)、[services/](backend/services/) 依赖 Python 3 隐式命名空间包,前提是以 backend/ 为导入根(从 backend/ 目录运行,或 `python backend/main.py`);新建模块沿用此约定即可,无需 `__init__.py`
- **LLM 降级与审核链路**:解读请求的合规校验(输入拦截/输出替换)与审计落库都在 [recommendation_service.py](backend/services/recommendation_service.py) 编排层完成,修改解读流程时勿绕过该层直接调 llm_client;审计失败不抛异常(返回 None),不影响主链路

## 合规约束(核心业务要求)

本系统的核心设计红线:**只做分析、不做决策、不输出投资建议、不直接触达客户**,所有结果必须理财经理人工复核后使用。实现 Agent 层时须遵循需求文档 6.4 / 8.2 的强制规则:

- 禁止输出任何投资建议、买卖指导、收益承诺、保本暗示
- 仅客观解读匹配逻辑、风险等级、用户适配性
- 所有 AI 输出强制标注"AI 辅助分析、需人工复核"免责声明
- 每次 Agent 调用写入审计日志(输入、输出、校验结果)
- 禁止任何自动化对外触达能力

## Claude Code 项目配置

- [.claude/agents/pm.md](.claude/agents/pm.md) — 产品经理 subagent(Alex),用于 PRD/路线图撰写;需求文档由它产出
- [.claude/skills/docx-to-markdown/](.claude/skills/docx-to-markdown/) — docx → Markdown 转换技能,根目录需求文档 .md 即由其从 .docx 生成
