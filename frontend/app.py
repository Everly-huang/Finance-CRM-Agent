"""金融产品智能推荐系统（合规版）— Streamlit 单页应用（UI-01 + 前端业务化优化 N1-N5）

五区布局（需求文档 5.5 / 9）：
1. 侧边参数配置区：业务场景切换（新客户冷启动 / 老客户关联挖掘）、客户偏好分类、投资金额、关联目标产品
2. 核心功能按钮区：一键计算推荐 / 生成 AI 合规解读
3. 算法结果展示区：推荐依据摘要 + 推荐产品表格（含适配提示标注）+ 人工复核确认 + CSV 下载
4. AI 合规解读区：解读文本渲染 + 降级标注 + MD 报告下载
5. 底部合规声明区：常驻免责声明

实现要点（需求文档 5.5）：单文件 app.py；st.session_state 管理推荐结果与解读状态；
requests 调用后端 /api/recommend 与 /api/recommend/explain（服务端调用，不受 CORS 约束）。
业务化优化（N1-N5，2026-09-04）：场景语言化入口 / 人工复核确认步（无解锁逻辑）/
推荐依据摘要条 / 下载出口 / 适配性软提示（只标注不过滤）。
"""

import os
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")

# 分类回退默认值(权威源为后端 GET /api/categories/,启动预热成功后覆盖;两者须保持同步)
CATEGORY_NAMES = {70: "稳健理财", 71: "成长基金", 72: "进取投资"}

# 业务场景 → 后端 method 单向映射（N1：文案与算法解耦，payload 只依赖 method 值）
SCENE_LABELS = {
    "nearest_neighbor": "新客户冷启动（无购买记录）",
    "association": "老客户关联挖掘（有历史购买）",
}
SCENE_CAPTIONS = {
    "nearest_neighbor": "算法：KNN 相似推荐（画像匹配，偏差过大自动转热门兜底）",
    "association": "算法：关联规则推荐（Apriori 共现挖掘，不足 Top6 以热门补齐）",
}
METHOD_BY_SCENE = {label: method for method, label in SCENE_LABELS.items()}

# 高风险等级集合（对齐种子库 risk_level 取值，供 KNN 行级适配提示）
HIGH_RISK_LEVELS = {"高风险", "极高风险"}

# 人工复核确认文案（N2：仅留痕自证，不做任何解锁/放行逻辑）
REVIEW_TEXT = "我已人工复核本批推荐与解读的风险等级与适配性，确认仅作内部业务参考"

# 话术双区固定标题（F1：与后端 prompt_templates.SCRIPT_NOTES_HEADER 一字不差，供渲染切分）
SCRIPT_NOTES_HEADER = "## 【经理备注（勿对客）】"

# ---------- UI-03 可视化常量 ----------
# 有序等级与类型映射；颜色固定实体、跨批次稳定（dataviz 参考调色板：蓝序贯 step 250→700 / 分类槽 1-3）
RISK_LEVEL_ORDER = ["低风险", "中低风险", "中风险", "中高风险", "高风险", "极高风险"]
RISK_LEVEL_COLORS = {"低风险": "#86b6ef", "中低风险": "#5598e7", "中风险": "#2a78d6",
                     "中高风险": "#1c5cab", "高风险": "#104281", "极高风险": "#0d366b"}
TYPE_ORDER = ["相似推荐", "关联推荐", "热门推荐"]
TYPE_COLORS = {"相似推荐": "#2a78d6", "关联推荐": "#eb6834", "热门推荐": "#1baf7a"}
FALLBACK_COLOR = "#898781"  # 未知等级/类型的归拢色（超 7 类折叠「其他」）

# 图表墨色/网格基线（dataviz 表面规范：主墨标注、发丝网格、浅表面）
CHART_INK = "#0b0b0b"
CHART_MUTED = "#52514e"
CHART_GRID = "#e1e0d9"
CHART_BASELINE = "#c3c2b7"
CHART_SURFACE = "#fcfcfb"

# 常驻合规声明（需求文档 6.5：仅为内部辅助工具，需人工复核）
DISCLAIMER = (
    "**合规声明**：本系统仅为银行内部业务辅助工具，所有推荐结果与 AI 解读不构成任何投资建议；"
    "所有结果需理财经理人工复核后方可使用，系统无任何自动化对外触达能力。"
)

# ---------- UI 风格统一注入（Ana · 2026-09-04） ----------
# 与 UI-03 图表 dataviz 语言同源：序贯蓝 #2a78d6 系 / 暖白浅表面 #fcfcfb /
# 墨色 #0b0b0b / 次墨 #52514e / 发丝线 #e1e0d9 系 / 雅黑字体栈（无外部 CDN，离线可用）。
# 仅调整视觉（配色/字号层级/分区边界/面板/间距），不触碰任何业务逻辑与合规文案；
# 组件字体细节由 config.toml 主题与下方 CSS 共同完成。
_UI_CSS = """
/* ========== 基底：字体与表面（银行内部工具气质） ========== */
html, body {
    font-family: "Microsoft YaHei", "PingFang SC", "Microsoft JhengHei",
                 system-ui, -apple-system, "Segoe UI", sans-serif;
}
[data-testid="stAppViewContainer"] * {
    font-family: "Microsoft YaHei", "PingFang SC", "Microsoft JhengHei",
                 system-ui, -apple-system, "Segoe UI", sans-serif;
}
/* 恢复 Streamlit 图标字体（通配符 * 会覆盖 Material Symbols Rounded，导致图标名显示为文本） */
[data-testid="stAppViewContainer"] [data-testid="stIconMaterial"] {
    font-family: "Material Symbols Rounded", sans-serif !important;
}
[data-testid="stAppViewContainer"] pre,
[data-testid="stAppViewContainer"] code {
    font-family: "Cascadia Mono", "Consolas", "Courier New", monospace;
}
[data-testid="stAppViewContainer"] {
    background-color: #fcfcfb;
    color: #0b0b0b;
}
::selection { background: #d7e5f8; }

/* 主区：内容宽度与留白（宽屏可读性，窄屏自动收窄） */
[data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] {
    max-width: 1240px;
    margin-left: auto;
    margin-right: auto;
    padding: 2.2rem 2.4rem 3.4rem;
}

/* ========== 侧边参数配置区 ========== */
[data-testid="stSidebar"] {
    background-color: #f4f5f1;
    border-right: 1px solid #e2e1d9;
}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    font-size: 13.5px;
    font-weight: 600;
    line-height: 1.5;
    color: #26262a;
    margin: 0.1rem 0 0.3rem;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    font-size: 14px;
    line-height: 1.6;
    color: #16181c;
    padding: 0.12rem 0;
    gap: 0.5rem;
}

/* ========== 文案层级（正文 15px / caption 12.5px，扫读密度友好） ========== */
[data-testid="stAppViewContainer"] [data-testid="stCaptionContainer"] p {
    font-size: 12.5px;
    line-height: 1.65;
    color: #6f6d64;
    margin: 0.15rem 0 0.35rem;
}
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] p {
    font-size: 15px;
    line-height: 1.75;
    color: #0b0b0b;
    margin: 0.2rem 0 0.55rem;
}
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] ul,
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] ol {
    margin: 0.3rem 0 0.7rem;
    padding-left: 1.4rem;
}
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] li {
    font-size: 15px;
    line-height: 1.75;
    color: #0b0b0b;
    margin: 0.12rem 0;
}
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] a {
    color: #1c5cab;
    text-decoration: none;
}
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] a:hover {
    text-decoration: underline;
}
/* AI 解读/话术正文里后端返回的 markdown 标题（非页面分区标题） */
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] h2 {
    font-size: 1.22rem; font-weight: 700; color: #0b0b0b; line-height: 1.5;
    margin: 1.5rem 0 0.45rem;
}
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] h3 {
    font-size: 1.08rem; font-weight: 650; color: #141414; line-height: 1.5;
    margin: 1.3rem 0 0.35rem;
}
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] h4 {
    font-size: 1rem; font-weight: 650; color: #141414;
    margin: 1rem 0 0.3rem;
}

/* ========== 页面结构性标题（st.title / st.subheader 等，与正文 md 标题分离） ========== */
[data-testid="stAppViewContainer"] [data-testid="stHeading"] h1 {
    font-size: 1.78rem;
    font-weight: 700;
    letter-spacing: 0.01em;
    line-height: 1.4;
    color: #0b0b0b;
    margin: 0 0 0.2rem;
}
[data-testid="stAppViewContainer"] [data-testid="stHeading"] h2 {
    font-size: 1.16rem;
    font-weight: 700;
    color: #0b0b0b;
    line-height: 1.5;
    margin: 0.6rem 0 0.55rem;
}
/* 区标题下缘发丝线 + 加大上间距：五区边界一目了然 */
[data-testid="stAppViewContainer"] [data-testid="stHeading"] h3 {
    font-size: 1.07rem;
    font-weight: 650;
    letter-spacing: 0.02em;
    color: #141414;
    line-height: 1.6;
    margin: 2.3rem 0 0.6rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #e2e1d9;
}

/* ========== 区 5 分隔线（常驻合规声明前的 st.divider 即 hr） ========== */
[data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] hr {
    margin: 2.4rem 0 1rem;
    border: 0;
    border-top: 1px solid #dcdbd1;
    opacity: 1;
}

/* ========== 按钮：主 CTA 实心（AA 白字对比 6.5:1）/ 次操作白底描边 ========== */
[data-testid="stAppViewContainer"] [data-testid^="stBaseButton-"] {
    border-radius: 10px;
    font-weight: 600;
    letter-spacing: 0.02em;
}
[data-testid="stAppViewContainer"] [data-testid="stBaseButton-primary"] {
    background-color: #1c5cab;
    border-color: #1c5cab;
    color: #ffffff;
}
[data-testid="stAppViewContainer"] [data-testid="stBaseButton-primary"]:hover {
    background-color: #104281;
    border-color: #104281;
    color: #ffffff;
}
[data-testid="stAppViewContainer"] [data-testid="stBaseButton-primary"]:active {
    background-color: #0d366b;
    border-color: #0d366b;
}
[data-testid="stAppViewContainer"] [data-testid="stBaseButton-primary"]:disabled {
    background-color: #c9d4e2;
    border-color: #c9d4e2;
    color: #ffffff;
}
[data-testid="stAppViewContainer"] [data-testid="stBaseButton-secondary"] {
    background-color: #ffffff;
    border-color: #c9c8bd;
    color: #16181c;
}
[data-testid="stAppViewContainer"] [data-testid="stBaseButton-secondary"]:hover {
    background-color: #f7f8f5;
    border-color: #9cb8de;
    color: #0b0b0b;
}
[data-testid="stAppViewContainer"] [data-testid="stBaseButton-secondary"]:disabled {
    background-color: #f2f2ed;
    border-color: #e2e1d9;
    color: #a3a196;
}

/* ========== 提示条（info/warning/error）：圆角 + 统一内文 ========== */
[data-testid="stAppViewContainer"] [data-testid="stAlert"] {
    border-radius: 12px;
}
[data-testid="stAppViewContainer"] [data-testid="stAlert"] p {
    font-size: 14.5px;
    line-height: 1.65;
    color: #16181c;
    margin: 0.1rem 0;
}

/* ========== 人工复核 checkbox：字号舒适、勾选语义不改 ========== */
[data-testid="stAppViewContainer"] [data-testid="stCheckbox"] label p {
    font-size: 14.5px;
    line-height: 1.55;
    color: #16181c;
}
[data-testid="stAppViewContainer"] [data-testid="stCheckbox"] label {
    padding: 0.1rem 0;
    gap: 0.5rem;
}

/* ========== 结果面板：图表与表格做成同族卡片（与图表发丝网格同色系） ========== */
[data-testid="stAppViewContainer"] [data-testid="stPlotlyChart"] {
    background-color: #ffffff;
    border: 1px solid #e6e5de;
    border-radius: 12px;
    overflow: hidden;  /* hidden 稳定布局，防 resize 循环；标题靠 margin.t 在 SVG 内可见 */
    padding-top: 8px;   /* 标题呼吸空间，防止紧贴边框 */
}
[data-testid="stAppViewContainer"] [data-testid="stDataFrame"] {
    background-color: #ffffff;
    border: 1px solid #e6e5de;
    border-radius: 12px;
    overflow: hidden;
    --gdg-accent-color: #2a78d6;
    --gdg-accent-fg: #ffffff;
    --gdg-bg-cell: #ffffff;
    --gdg-bg-header: #f7f7f3;
    --gdg-text-header: #52514e;
    --gdg-text-dark: #0b0b0b;
    --gdg-text-medium: #52514e;
    --gdg-border-color: #e9e8e0;
    --gdg-horizontal-border-color: #f0efe9;
    --gdg-header-bottom-border-color: #dfded5;
    --gdg-font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
}
"""

st.set_page_config(page_title="金融产品智能推荐系统", page_icon="📊", layout="wide")
st.markdown(f"<style>{_UI_CSS}</style>", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def fetch_all_products():
    """获取所有金融产品（页面加载预热，同时触发后端建表播种）"""
    response = requests.get(f"{API_BASE}/api/products/all/", timeout=5)
    response.raise_for_status()
    return response.json()["products"]


@st.cache_data(ttl=300)
def fetch_categories():
    """获取金融产品分类（权威源：后端 /api/categories/，消除前端硬编码漂移）"""
    response = requests.get(f"{API_BASE}/api/categories/", timeout=5)
    response.raise_for_status()
    return {c["id"]: c["name"] for c in response.json()["categories"]}


def get_price_range():
    """产品库起投金额区间（供适配性提示动态取值，避免硬编码漂移）"""
    try:
        products = fetch_all_products()
        if not products:
            return 30000, 250000
        return int(min(p["price"] for p in products)), int(max(p["price"] for p in products))
    except requests.RequestException:
        return 30000, 250000


def call_recommend(payload):
    response = requests.post(f"{API_BASE}/api/recommend/", json=payload, timeout=15)
    response.raise_for_status()
    return response.json()


def call_explain(recommendations, user_context, mode="analysis"):
    response = requests.post(
        f"{API_BASE}/api/recommend/explain",
        json={"recommendations": recommendations, "user_context": user_context, "mode": mode},
        timeout=90,  # 后端 LLM 30s 超时 + 重试 1 次 = 60s 上限,前端留余量
    )
    response.raise_for_status()
    return response.json()


def build_md_report(explanation):
    """解读报告 MD（N4）：正文 + 免责声明（响应内 disclaimer 优先，去重）+ 生成时间"""
    body = explanation["explanation"].rstrip()
    disclaimer = explanation.get("disclaimer") or DISCLAIMER
    parts = [body, "", "---", ""]
    if disclaimer not in body:  # LLM/降级/演示三路径正文可能已含声明，避免重复拼接
        parts.append(disclaimer)
    parts.append(f"\n生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    return "\n".join(parts)


def build_script_download(text):
    """话术下载内容（F2）：仅对客区 + 文件头三重标注，经理备注区留页面不外流"""
    customer_part = text.split(SCRIPT_NOTES_HEADER, 1)[0].rstrip()
    lines = customer_part.splitlines()
    if lines and lines[0].startswith("**") and lines[0].endswith("**"):
        lines = lines[1:]  # 去掉"演示样例/基础版话术"标注行
    header = "对客参考话术（草稿）\n参考草稿 | 需人工复核 | 禁止系统自动发送\n\n"
    return header + "\n".join(lines)


def build_result_df(recommendations, method):
    """推荐结果 DataFrame（UI-03 提取：表格/图表/CSV 三处共用同一数据源）"""
    rows = []
    for product in recommendations:
        row = {
            "产品名称": product.get("name"),
            "产品分类": CATEGORY_NAMES.get(product.get("category_id"), "未知"),
            "风险等级": product.get("risk_level"),
            "起投金额（元）": product.get("price"),
            "业绩比较基准（%，非承诺）": product.get("expected_return"),
            "推荐类型": product.get("recommend_type"),
        }
        if "support" in product:
            row["支持度"] = product["support"]
            row["置信度"] = product["confidence"]
        if method == "nearest_neighbor":
            # N5：只标注不过滤，适配判断留给人工
            row["适配提示"] = (
                "请人工核对适配性" if product.get("risk_level") in HIGH_RISK_LEVELS else ""
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _base_layout(fig):
    """两图共用的 dataviz 布局基线：浅表面/发丝网格/墨色标注/整数计数轴

    标题不在 Plotly SVG 内渲染（防 overflow 裁剪 + resize 循环），
    改由 render_chart_row 用 Streamlit 文本元素在图上方渲染。
    """
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",  # 与 Streamlit 表面融合
        plot_bgcolor=CHART_SURFACE,
        font={"family": "Microsoft YaHei, PingFang SC, system-ui, sans-serif",
              "color": CHART_MUTED},
        margin={"t": 16, "b": 48, "l": 40, "r": 16},  # t 减小（SVG 内无标题）
        height=340,
        showlegend=False,
        xaxis={"showgrid": False, "linecolor": CHART_BASELINE,
               "tickfont": {"color": CHART_MUTED, "size": 12},
               "tickangle": 0,  # 横向文字，防倾斜遮挡
               "automargin": True},  # 自动留足标签空间
        yaxis={"showgrid": True, "gridcolor": CHART_GRID, "linecolor": CHART_BASELINE,
               "dtick": 1, "tickfont": {"color": CHART_MUTED},
               "title": {"text": "产品数", "font": {"color": CHART_MUTED}}},
    )
    return fig


def build_risk_chart(df):
    """UI-03 图 A：风险等级分布（常驻，计数柱状图，x 轴固定 6 级，零计数留空）

    小样本诚实守则：计数轴不用百分比；柱顶直标数字；hover 仅增强。
    等级身份由 x 轴文字承担，颜色只做序贯强化（不用红绿，避免"高=坏"价值判断）。
    """
    if "风险等级" not in df.columns or df["风险等级"].isna().all():
        return None
    counts = df["风险等级"].value_counts()
    others = int(sum(c for k, c in counts.items() if k not in RISK_LEVEL_ORDER))
    levels = list(RISK_LEVEL_ORDER) + (["其他"] if others else [])
    values = [int(counts.get(lv, 0)) for lv in RISK_LEVEL_ORDER] + ([others] if others else [])
    colors = [RISK_LEVEL_COLORS.get(lv, FALLBACK_COLOR) for lv in RISK_LEVEL_ORDER]
    if others:
        colors.append(FALLBACK_COLOR)
    total = len(df)
    fig = go.Figure(go.Bar(
        x=levels, y=values,
        marker_color=colors,
        text=[str(v) if v else "" for v in values],  # 零计数不标注"0"，保留空刻度传达"未覆盖"
        textposition="outside",
        textfont={"color": CHART_INK, "size": 13},
        customdata=[[f"{v / total:.0%}" if total else "—"] for v in values],
        hovertemplate="%{x} · %{y} 条 · 占本批 %{customdata[0]}<extra></extra>",
    ))
    _base_layout(fig)
    return fig, f"风险等级分布 · 本批共 {total} 条"


def build_type_chart(df):
    """UI-03 图 B：推荐类型构成（条件图：本批类型 ≥2 才渲染）

    单类型 100% 横条属零信息反模式（KNN 整批同型），故不渲染；
    关联模式的「关联+热门补齐」混合正是此图要揭穿的信息。
    颜色固定实体映射，跨批次/跨模式恒定（颜色跟实体不跟排名）。
    """
    if "推荐类型" not in df.columns or df["推荐类型"].nunique() < 2:
        return None
    counts = df["推荐类型"].value_counts()
    types = [t for t in TYPE_ORDER if t in counts.index]
    extra = [t for t in counts.index if t not in TYPE_ORDER]
    total = len(df)
    fig = go.Figure()
    for t in types + extra:
        value = int(counts[t])
        fig.add_trace(go.Bar(
            x=[t], y=[value],
            name=t,
            marker_color=TYPE_COLORS.get(t, FALLBACK_COLOR),
            text=[str(value)],
            textposition="outside",
            textfont={"color": CHART_INK, "size": 13},
            customdata=[[f"{value / total:.0%}" if total else "—"]],
            hovertemplate="%{x} · %{y} 条 · 占本批 %{customdata[0]}<extra></extra>",
        ))
    _base_layout(fig)
    fig.update_layout(
        showlegend=True,  # ≥2 系列必有图例（每柱即一"系列"）
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02,
                "xanchor": "center", "x": 0.5, "font": {"size": 11, "color": CHART_MUTED}},
        margin={"t": 40, "b": 48, "l": 40, "r": 16},  # t 留图例空间，b 留横标签空间
        xaxis={"categoryorder": "array", "categoryarray": types + extra,
               "showgrid": False, "linecolor": CHART_BASELINE,
               "tickfont": {"color": CHART_MUTED, "size": 12},
               "tickangle": 0,  # 横向文字，防与图例/相邻标签遮挡
               "automargin": True},
    )
    return fig, f"推荐类型构成 · 本批共 {total} 条"


def render_chart_row(df):
    """UI-03 布局编排：双图 columns(2) 并排 / 单图整行（图 B 条件渲染，图 A 常驻）

    标题用 Streamlit caption 渲染在图上方，不进 Plotly SVG（防 overflow 裁剪 + resize 循环）。
    """
    result_a = build_risk_chart(df)
    result_b = build_type_chart(df)
    if not result_a and not result_b:
        return
    chart_kwargs = {"width": "stretch", "config": {"displaylogo": False, "scrollZoom": False, "responsive": False}}
    if result_a and result_b:
        col1, col2 = st.columns(2)
        with col1:
            fig_a, title_a = result_a
            st.caption(f"**{title_a}**")
            st.plotly_chart(fig_a, **chart_kwargs)
        with col2:
            fig_b, title_b = result_b
            st.caption(f"**{title_b}**")
            st.plotly_chart(fig_b, **chart_kwargs)
    else:
        fig, title = result_a or result_b
        st.caption(f"**{title}**")
        st.plotly_chart(fig, **chart_kwargs)


# ---------- 启动检查与预热（ENG-04 口径：首访 GET 产品列表触发建表播种） ----------
try:
    fetch_all_products()
except requests.RequestException:
    st.error(f"无法连接后端服务（{API_BASE}）。请先启动后端：cd backend && python main.py")
    st.stop()

# 权威分类源覆盖回退默认值（后端 categories 为硬编码、不依赖建表；失败保留顶部回退值）
try:
    CATEGORY_NAMES = fetch_categories()
except requests.RequestException:
    pass

# ---------- 区 1：侧边参数配置区 ----------
st.sidebar.header("⚙️ 参数配置")

scene_label = st.sidebar.radio("业务场景", options=list(SCENE_LABELS.values()))
method = METHOD_BY_SCENE[scene_label]
st.sidebar.caption(SCENE_CAPTIONS[method])

user_context = {}
if method == "nearest_neighbor":
    category_id = st.sidebar.selectbox(
        "客户偏好分类",
        options=list(CATEGORY_NAMES.keys()),
        format_func=lambda cid: CATEGORY_NAMES[cid],
    )
    price = st.sidebar.number_input(
        "预期起投金额（元）", min_value=0, max_value=1000000, value=50000, step=1000
    )
    user_context = {"客户偏好分类": CATEGORY_NAMES[category_id], "预期起投金额": f"{int(price)} 元"}
else:
    products = fetch_all_products()
    target_product = st.sidebar.selectbox(
        "关联目标产品",
        options=products,
        format_func=lambda p: f"{p['name']}（{CATEGORY_NAMES.get(p['category_id'], '未知分类')}）",
    )
    user_context = {"关联目标产品": target_product["name"]}

st.sidebar.caption("高级算法参数（K 值/阈值）一期固定为后端默认值，不向业务侧开放")

# ---------- 区 2：核心功能按钮区 ----------
st.title("📊 金融产品智能推荐系统")
st.caption("算法精准匹配 — AI 合规解读 — 人工复核兜底")
st.caption("操作路径：选场景 → 填客户信息 → 一键计算 → AI 解读 → 人工复核后使用")

col_calc, col_explain = st.columns(2)
calc_clicked = col_calc.button("🚀 一键计算推荐", type="primary", width="stretch")
explain_clicked = col_explain.button("🤖 生成 AI 合规解读", width="stretch")

if calc_clicked:
    payload = (
        {"method": "nearest_neighbor", "category_id": category_id, "price": float(price)}
        if method == "nearest_neighbor"
        else {"method": "association", "selected_product": target_product["id"]}
    )
    try:
        result = call_recommend(payload)
    except requests.RequestException as exc:
        st.error(f"请求推荐接口失败：{exc}")
        result = None

    if result:
        if "error" in result:
            st.error(f"推荐失败：{result['error']}")
        else:
            st.session_state["recommendations"] = result["recommendations"]
            st.session_state.pop("explanation", None)  # 新结果清空旧解读
            st.session_state.pop("script_result", None)  # 新结果清空旧话术（防旧话术配新推荐）
            st.session_state["recommend_message"] = result.get("message", "推荐完成")
            st.session_state["result_gen"] = st.session_state.get("result_gen", 0) + 1  # N2 批次号
            st.session_state.pop("review_time", None)  # N2 新批次清复核状态

if explain_clicked:
    if not st.session_state.get("recommendations"):
        st.warning("请先生成推荐结果，再获取 AI 解读")
    else:
        try:
            st.session_state["explanation"] = call_explain(
                st.session_state["recommendations"], user_context
            )
        except requests.RequestException as exc:
            st.error(f"请求解读接口失败：{exc}")

# ---------- 区 3：算法结果展示区 ----------
st.subheader("📈 推荐结果")

price_min, price_max = get_price_range()
st.caption(
    "本批结果未做风险等级硬性适配校验；"
    f"输入金额超出产品库区间（{price_min // 10000} 万~{price_max // 10000} 万元）时系统自动裁剪"
)

recommendations = st.session_state.get("recommendations")
if recommendations and st.session_state.get("recommend_message"):
    st.info(st.session_state["recommend_message"])

if recommendations:
    df = build_result_df(recommendations, method)
    render_chart_row(df)  # UI-03：批次总览图表（图 A 常驻；图 B 类型≥2 才渲染）
    st.dataframe(df, width="stretch", hide_index=True)

    # N2：人工复核确认步（仅留痕自证，无任何解锁/放行逻辑）
    review_key = f"review_chk_{method}_{st.session_state.get('result_gen', 0)}"
    for k in [k for k in st.session_state if k.startswith("review_chk_") and k != review_key]:
        del st.session_state[k]
    reviewed = st.checkbox(REVIEW_TEXT, key=review_key)
    if reviewed:
        if not st.session_state.get("review_time"):
            st.session_state["review_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"已复核 · {st.session_state['review_time']} · 仅内部业务参考，不构成投资建议")

    # N4：结果清单 CSV（utf-8-sig 防 Windows Excel 中文乱码）
    st.download_button(
        "下载推荐结果 CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"推荐结果_{datetime.now():%Y%m%d_%H%M%S}.csv",
        mime="text/csv",
        width="stretch",
    )
else:
    st.info("请在侧边栏配置参数后，点击「一键计算推荐」开始使用")

# ---------- 区 4：AI 合规解读区 ----------
st.subheader("🤖 AI 合规解读")

explanation = st.session_state.get("explanation")
if explanation:
    if explanation.get("source") == "demo":
        st.info("演示样例（演示模式，未调用 AI 生成）")
    elif explanation.get("degraded"):
        st.warning(f"基础版解读（{explanation.get('error') or 'LLM 暂不可用，已回退模板'}）")
    st.markdown(explanation["explanation"])
    # N4：解读报告 MD 下载（自动拼接免责声明，不提供任何分享/发送能力）
    st.download_button(
        "下载解读报告 MD",
        data=build_md_report(explanation).encode("utf-8"),
        file_name=f"AI合规解读_{datetime.now():%Y%m%d_%H%M%S}.md",
        mime="text/markdown",
        width="stretch",
    )
elif recommendations:
    st.caption("点击「生成 AI 合规解读」获取合规化解读文案")
else:
    st.caption("生成推荐结果后，可一键获取 AI 合规解读")

# ---------- 区 4b：对客参考话术区（F1/F2） ----------
st.subheader("💬 对客参考话术")

script_clicked = st.button(
    "💬 生成对客参考话术", disabled=not st.session_state.get("recommendations")
)
if not st.session_state.get("recommendations"):
    st.caption("先生成推荐结果，再生成对客参考话术")

if script_clicked:
    try:
        st.session_state["script_result"] = call_explain(
            st.session_state["recommendations"], user_context, mode="script"
        )
    except requests.RequestException as exc:
        st.error(f"请求话术接口失败：{exc}")

script = st.session_state.get("script_result")
if script:
    if script.get("source") == "demo":
        st.info("演示样例（演示模式，未调用 AI 生成）")
    elif script.get("degraded"):
        st.warning(f"基础版话术（{script.get('error') or 'LLM 暂不可用，已回退模板'}）")

    text = script["script"]
    if SCRIPT_NOTES_HEADER in text:
        customer_part, notes_part = text.split(SCRIPT_NOTES_HEADER, 1)
    else:
        customer_part, notes_part = text, ""  # 容错：无标题时全文按对客区渲染

    st.caption("【对客参考话术】— 参考草稿，需人工复核后使用，禁止系统自动发送")
    st.markdown(customer_part)
    if notes_part:
        st.warning("【经理备注（勿对客）】")
        st.markdown(notes_part)

    # F2：下载仅对客区 + 文件头三重标注（备注区留页面）
    st.download_button(
        "下载话术草稿 MD",
        data=build_script_download(text).encode("utf-8"),
        file_name=f"客户跟进话术参考草稿_{datetime.now():%Y%m%d_%H%M%S}.md",
        mime="text/markdown",
        width="stretch",
    )

# ---------- 区 5：底部合规声明区（常驻） ----------
st.divider()
st.markdown(DISCLAIMER)
