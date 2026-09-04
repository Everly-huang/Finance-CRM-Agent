"""金融产品智能推荐系统（合规版）— Streamlit 单页应用（UI-01）

五区布局（需求文档 5.5 / 9）：
1. 侧边参数配置区：算法模式切换、客户偏好分类、投资金额、关联目标产品
2. 核心功能按钮区：一键计算推荐 / 生成 AI 合规解读
3. 算法结果展示区：推荐产品表格（Plotly 可视化随 UI-03 落地）
4. AI 合规解读区：解读文本渲染 + 降级标注
5. 底部合规声明区：常驻免责声明

实现要点（需求文档 5.5）：单文件 app.py；st.session_state 管理推荐结果与解读状态；
requests 调用后端 /api/recommend 与 /api/recommend/explain（服务端调用，不受 CORS 约束）。
"""

import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")

CATEGORY_NAMES = {70: "稳健理财", 71: "成长基金", 72: "进取投资"}

# 常驻合规声明（需求文档 6.5：仅为内部辅助工具，需人工复核）
DISCLAIMER = (
    "**合规声明**：本系统仅为银行内部业务辅助工具，所有推荐结果与 AI 解读不构成任何投资建议；"
    "所有结果需理财经理人工复核后方可使用，系统无任何自动化对外触达能力。"
)

st.set_page_config(page_title="金融产品智能推荐系统", page_icon="📊", layout="wide")


@st.cache_data(ttl=300)
def fetch_all_products():
    """获取所有金融产品（页面加载预热，同时触发后端建表播种）"""
    response = requests.get(f"{API_BASE}/api/products/all/", timeout=5)
    response.raise_for_status()
    return response.json()["products"]


def call_recommend(payload):
    response = requests.post(f"{API_BASE}/api/recommend/", json=payload, timeout=15)
    response.raise_for_status()
    return response.json()


def call_explain(recommendations, user_context):
    response = requests.post(
        f"{API_BASE}/api/recommend/explain",
        json={"recommendations": recommendations, "user_context": user_context},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


# ---------- 启动检查与预热（ENG-04 口径：首访 GET 产品列表触发建表播种） ----------
try:
    fetch_all_products()
except requests.RequestException:
    st.error(f"无法连接后端服务（{API_BASE}）。请先启动后端：cd backend && python main.py")
    st.stop()

# ---------- 区 1：侧边参数配置区 ----------
st.sidebar.header("⚙️ 参数配置")

method_label = st.sidebar.radio("算法模式", ["KNN 相似推荐", "关联规则推荐"])

user_context = {}
if method_label == "KNN 相似推荐":
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

col_calc, col_explain = st.columns(2)
calc_clicked = col_calc.button("🚀 一键计算推荐", type="primary", width="stretch")
explain_clicked = col_explain.button("🤖 生成 AI 合规解读", width="stretch")

if calc_clicked:
    payload = (
        {"method": "nearest_neighbor", "category_id": category_id, "price": float(price)}
        if method_label == "KNN 相似推荐"
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
            st.session_state["recommend_message"] = result.get("message", "推荐完成")

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

recommendations = st.session_state.get("recommendations")
if recommendations:
    rows = []
    for product in recommendations:
        row = {
            "产品名称": product.get("name"),
            "产品分类": CATEGORY_NAMES.get(product.get("category_id"), "未知"),
            "风险等级": product.get("risk_level"),
            "起投金额（元）": product.get("price"),
            "预期收益（%）": product.get("expected_return"),
            "推荐类型": product.get("recommend_type"),
        }
        if "support" in product:
            row["支持度"] = product["support"]
            row["置信度"] = product["confidence"]
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
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
elif recommendations:
    st.caption("点击「生成 AI 合规解读」获取合规化解读文案")
else:
    st.caption("生成推荐结果后，可一键获取 AI 合规解读")

# ---------- 区 5：底部合规声明区（常驻） ----------
st.divider()
st.markdown(DISCLAIMER)
