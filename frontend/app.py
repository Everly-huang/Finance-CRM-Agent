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
import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")

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


# ---------- 启动检查与预热（ENG-04 口径：首访 GET 产品列表触发建表播种） ----------
try:
    fetch_all_products()
except requests.RequestException:
    st.error(f"无法连接后端服务（{API_BASE}）。请先启动后端：cd backend && python main.py")
    st.stop()

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
    df = pd.DataFrame(rows)
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
    "生成对客参考话术", disabled=not st.session_state.get("recommendations")
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
