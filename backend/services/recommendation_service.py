"""业务编排层（SVC-01 + F1 双模式）

一条调用链贯通（需求文档 5.1 / 5.4 / 7.2）：
算法推荐 → 合规引擎输入校验 → RAG 检索（Mock）→ LLM 生成 → 输出后合规校验 → 审计落库

解读流水线双模式（F1）：
- generate_explanation(mode="analysis")：合规解读（现状路径）
- generate_explanation(mode="script")：对客参考话术（新增路径，同形态流水线）
"""

import json
import os

from agent import audit_logger
from agent import compliance_engine
from agent import llm_client
from agent import rag_retriever
from agent.prompt_templates import (
    DISCLAIMER,
    build_demo_explanation,
    build_explanation_messages,
    build_fallback_explanation,
    build_script_demo,
    build_script_fallback,
    build_script_messages,
    ensure_script_required_elements,
)
from algorithms import nearest_neighbor as nn
from algorithms.association_rules import recommend_products_by_association

# 演示模式开关（SVC-05）：True 时解读直接返回预置样例、禁止调用任何大模型 API。
# 本地默认关闭（自由调用 LLM）；公开分享链接场景由部署平台注入 DEMO_MODE=True。
DEMO_MODE = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")


def _build_recommend_message(method, recommendations):
    """推荐依据摘要（供前端结果区顶部渲染，N3 前端业务化优化）

    分流结论由结果行的 recommend_type 反推（KNN 整批同型；关联模式按类型计数），
    不修改算法层签名。文案模板化，只写"按…特征匹配生成"，不写承诺性用语。
    """
    if not recommendations:
        return "推荐完成" if method == 'nearest_neighbor' else "关联推荐完成"

    if method == 'nearest_neighbor':
        types = {p.get("recommend_type") for p in recommendations}
        if types <= {"相似推荐"}:
            return (f"推荐依据：客户画像与产品库匹配距离较小，"
                    f"按偏好分类与投资金额相似度输出 Top {len(recommendations)}（相似推荐）")
        return (f"推荐依据：客户画像与产品库匹配距离较大，已转热门兜底分流，"
                f"按历史热度输出 Top {len(recommendations)}（热门推荐），请人工核对风险适配性")

    assoc = [p for p in recommendations if p.get("recommend_type") == "关联推荐"]
    hot = [p for p in recommendations if p.get("recommend_type") == "热门推荐"]
    if assoc and hot:
        return (f"推荐依据：关联规则命中 {len(assoc)} 条，"
                f"不足 Top {len(recommendations)} 部分以热门产品补齐 {len(hot)} 条")
    if assoc:
        return f"推荐依据：关联规则命中 {len(assoc)} 条，输出 Top {len(recommendations)}"
    return ("推荐依据：历史购买记录不足，未命中关联规则，"
            f"全部按热门产品补齐 Top {len(recommendations)}，请人工核对适配性")


def run_recommendation(data):
    """算法推荐编排（与原 main.py 内联逻辑一致，响应结构不变）"""
    method = data.get('method', 'nearest_neighbor')

    if method == 'nearest_neighbor':
        category_id = data.get('category_id')
        price = data.get('price')

        if not category_id or not price:
            return {"error": "缺少参数"}

        recommendations = nn.recommend_products(category_id, float(price))
        return {
            "recommendations": recommendations,
            "message": _build_recommend_message(method, recommendations)
        }

    elif method == 'association':
        selected_product_id = data.get('selected_product')

        if not selected_product_id:
            return {"error": "请选择商品"}

        try:
            recommendations = recommend_products_by_association(int(selected_product_id))
            return {
                "recommendations": recommendations,
                "message": _build_recommend_message(method, recommendations)
            }
        except Exception as e:
            return {"error": f"关联规则算法错误: {str(e)}"}

    else:
        return {"error": "不支持的算法"}


def _audience_flagged(output_check):
    """输出后校验失败是否因受众漂移（F3）"""
    return any(v.get("type") == "audience" for v in output_check.get("violations", []))


def generate_explanation(recommendations, user_context, mode="analysis"):
    """Agent 合规解读流水线（需求文档 5.4 / 7.2 核心风控流程，F1 双模式）

    mode="analysis"（默认，向后兼容）：合规解读
    mode="script"：对客参考话术

    输入校验 →（拦截则不出 LLM）→ DEMO_MODE 分支（命中则直接返回预置样例，不触及 LLM）
    → RAG 检索 → LLM 生成 → 输出后校验 →（拦截则替换模板）→ 审计落库
    """
    if mode not in ("analysis", "script"):
        return {"error": "不支持的解读模式"}

    if mode == "script":
        return _generate_script(recommendations, user_context)

    input_check = compliance_engine.check_input(json.dumps(user_context, ensure_ascii=False))

    if not input_check['passed']:
        # 注入/违规输入：不调用 LLM，直接回退合规模板
        text = build_fallback_explanation(recommendations, user_context, reason="输入含违规或攻击性内容，已由合规引擎拦截")
        audit_logger.log_agent_call(
            input_payload={"recommendations": recommendations, "user_context": user_context, "mode": "analysis"},
            output_text=text,
            compliance_result="blocked_input",
            is_degraded=True,
        )
        return _build_response(text, source="template", degraded=True,
                               compliance=input_check, error="输入被合规引擎拦截")

    if DEMO_MODE:
        # 演示模式（SVC-05）：无论有无 key/网络，一律返回预置样例，代码路径不触及 llm_client
        text = build_demo_explanation(recommendations, user_context)
        output_check = compliance_engine.validate_output(text)
        if not output_check['passed']:
            if _audience_flagged(output_check):
                text = build_fallback_explanation(recommendations, user_context,
                                                  reason="演示样例含对客第二人称（受众漂移），已替换")
                audit_result = "audience_drift"
            else:
                text = build_fallback_explanation(recommendations, user_context,
                                                  reason="演示样例校验未通过，已替换")
                audit_result = "blocked_output"
        else:
            audit_result = "pass"
        audit_logger.log_agent_call(
            input_payload={"recommendations": recommendations, "user_context": user_context, "mode": "analysis"},
            output_text=text,
            compliance_result=audit_result,
            is_degraded=False,
            model="demo",
        )
        return _build_response(text, source="demo", degraded=False,
                               compliance=output_check, error=None)

    rag_context = rag_retriever.retrieve_context(json.dumps(recommendations, ensure_ascii=False))
    messages = build_explanation_messages(recommendations, user_context, rag_context)
    llm_result = llm_client.generate_explanation(messages, recommendations, user_context)
    text = llm_result["text"]

    output_check = compliance_engine.validate_output(text)
    if not output_check['passed']:
        # 输出后校验失败：整段替换为预置合规模板（输出后校验兜底）；
        # 受众漂移（F3）单独记审计枚举，便于复盘统计
        if _audience_flagged(output_check):
            text = build_fallback_explanation(recommendations, user_context,
                                              reason="输出含对客第二人称（受众漂移），已由合规引擎拦截替换")
            audit_result = "audience_drift"
        else:
            text = build_fallback_explanation(recommendations, user_context,
                                              reason="输出含违规表述，已由合规引擎拦截替换")
            audit_result = "blocked_output"
    else:
        audit_result = "pass"

    audit_logger.log_agent_call(
        input_payload={"recommendations": recommendations, "user_context": user_context, "mode": "analysis"},
        output_text=text,
        compliance_result=audit_result,
        is_degraded=llm_result["degraded"] or not output_check['passed'],
        model=llm_result.get("model"),
    )

    return _build_response(text, source=llm_result["source"], degraded=llm_result["degraded"] or not output_check['passed'],
                           compliance=output_check, error=llm_result["error"])


def _generate_script(recommendations, user_context):
    """script 模式流水线（F1）：对客参考话术，与 analysis 同形态

    输入校验 →（拦截则不出 LLM）→ DEMO_MODE → RAG → LLM → 输出后校验（script 规则）
    → 强制要素兜底 → 审计落库。响应契约与 analysis 一致（文本键为 script）。
    """
    input_check = compliance_engine.check_input(json.dumps(user_context, ensure_ascii=False))

    if not input_check['passed']:
        text = build_script_fallback(recommendations, user_context,
                                     reason="输入含违规或攻击性内容，已由合规引擎拦截")
        audit_logger.log_agent_call(
            input_payload={"recommendations": recommendations, "user_context": user_context, "mode": "script"},
            output_text=text,
            compliance_result="blocked_input",
            is_degraded=True,
        )
        return _build_response(text, source="template", degraded=True,
                               compliance=input_check, error="输入被合规引擎拦截", key="script")

    if DEMO_MODE:
        text = ensure_script_required_elements(build_script_demo(recommendations, user_context))
        output_check = compliance_engine.validate_output(text, mode="script")
        if not output_check['passed']:
            text = build_script_fallback(recommendations, user_context, reason="演示样例校验未通过，已替换")
        audit_logger.log_agent_call(
            input_payload={"recommendations": recommendations, "user_context": user_context, "mode": "script"},
            output_text=text,
            compliance_result="pass" if output_check['passed'] else "blocked_output",
            is_degraded=False,
            model="demo",
        )
        return _build_response(text, source="demo", degraded=False,
                               compliance=output_check, error=None, key="script")

    rag_context = rag_retriever.retrieve_context(json.dumps(recommendations, ensure_ascii=False))
    messages = build_script_messages(recommendations, user_context, rag_context)
    llm_result = llm_client.generate_explanation(messages, recommendations, user_context)
    text = llm_result["text"]

    if llm_result["source"] == "template":
        # llm_client 内部降级默认造 analysis 模板；script 侧重造话术模板（llm_client 零改动）
        text = build_script_fallback(recommendations, user_context, reason=llm_result["error"])

    output_check = compliance_engine.validate_output(text, mode="script")
    if not output_check['passed']:
        text = build_script_fallback(recommendations, user_context,
                                     reason="输出含违规表述，已由合规引擎拦截替换")
    text = ensure_script_required_elements(text)   # 强制要素兜底（幂等）

    audit_logger.log_agent_call(
        input_payload={"recommendations": recommendations, "user_context": user_context, "mode": "script"},
        output_text=text,
        compliance_result="pass" if output_check['passed'] else "blocked_output",
        is_degraded=llm_result["degraded"] or not output_check['passed'],
        model=llm_result.get("model"),
    )

    return _build_response(text, source=llm_result["source"],
                           degraded=llm_result["degraded"] or not output_check['passed'],
                           compliance=output_check, error=llm_result["error"], key="script")


def _build_response(text, source, degraded, compliance, error, key="explanation"):
    """统一解读响应结构（SVC-02 契约：解读 + 合规结果 + 免责声明）

    key 参数复用：analysis=explanation / script=script，其余契约字段不变。
    """
    return {
        key: text,
        "source": source,
        "degraded": degraded,
        "compliance": compliance,
        "disclaimer": DISCLAIMER,
        "error": error,
    }
