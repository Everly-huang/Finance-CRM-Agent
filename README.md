# 金融产品智能推荐系统(合规版)

面向银行/券商理财经理的轻量化智能辅助工具。核心方案:「算法精准匹配 — AI 合规解读 — 人工复核兜底」三层递进体系。

- **KNN 最近邻**:新客户冷启动(画像匹配,偏差过大自动转热门兜底)
- **Apriori 关联规则**:老客户购买行为挖掘(不足 Top6 以热门补齐)
- **AI 合规解读(Deepseek)**:analysis 合规解读 / script 对客参考话术双模式,合规引擎前置拦截 + 输出后校验 + 全量审计留痕;无 key 自动降级预置合规模板,功能不中断

> ⚠️ **合规声明**:本系统仅为银行内部业务辅助工具,所有推荐结果与 AI 解读不构成任何投资建议;所有结果需理财经理人工复核后方可使用,系统无任何自动化对外触达能力。

## 快速开始

环境:Python 3.11(开发环境为 conda env `finance-crm`)

```bash
pip install -r requirements.txt
```

一键启动(Windows 双击 / Git Bash):

```bash
start_demo.bat          # Windows 双击;Git Bash 下 ./start_demo.sh
```

脚本自动完成:secrets 桥接 → 启动后端 → 轮询就绪 → 启动前端 → 保持双进程(Ctrl+C 一键停止)。

数据库无需任何准备:首次启动自动建表播种(10 个示例产品 + 8 位客户 38 条历史购买记录),SQLite 文件在本地自动生成,不随仓库分发。

可选参数:

```bash
python start_demo.py --smoke   # 启动后自动跑后端冒烟(8 项检查)
python start_demo.py --demo    # 演示模式:AI 解读返回预置样例,零 LLM 调用(公开分享场景)
```

启动后:

- 前端页面:http://127.0.0.1:8501
- 后端 API:http://127.0.0.1:8000(FastAPI 交互文档在 /docs)

> 注:start_demo.bat/sh 中的 Python 解释器路径为本机 Anaconda 路径,其他机器请按需修改(或直接手动分步启动,见 [CLAUDE.md](CLAUDE.md)「常用命令」)。

## AI 解读配置(可选,不配置也能用)

解读由**后端进程**调用 Deepseek API(OpenAI 兼容端点),读取环境变量:

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 无 | 未配置时自动回退预置合规模板,响应标注"基础版解读" |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API 地址 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名 |
| `DEMO_MODE` | 关闭 | 设 `1`/`true`/`yes` 时解读返回预置演示样例,禁止调用任何大模型 API |

推荐方式:创建 `frontend/.streamlit/secrets.toml`(已被 .gitignore 排除,不入 git):

```toml
DEEPSEEK_API_KEY = "sk-xxx"
```

一键启动脚本会自动将其桥接注入后端进程;手动分步启动时需自行注入环境变量(见 CLAUDE.md)。

## 架构速览

```
frontend/app.py (Streamlit 五区+双卡+总览图)
    --requests--> backend/main.py (FastAPI 5 个 /api 端点)
        --> services/recommendation_service.py (编排层)
            ├─ 推荐: algorithms/ → database/db_connection.py → SQLite(启动惰性建表播种)
            └─ 解读: agent/compliance_engine(输入校验) → rag_retriever(Mock)
                     → llm_client(LLM/降级) → compliance_engine(输出后校验)
                     → audit_logger → agent_audit_log 表
```

## 文档

- [金融产品智能推荐系统需求文档.md](金融产品智能推荐系统需求文档.md) — 权威规格(现状/规划已标注)
- [项目落地清单.md](项目落地清单.md) — 未实现项与验收口径
- [需求文档评审报告.md](需求文档评审报告.md) — 需求修订依据(归档)
- [CLAUDE.md](CLAUDE.md) — 开发指引(架构/常用命令/已知陷阱/合规约束)
