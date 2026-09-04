"""业务编排层（SVC-01）

一条调用链贯通（需求文档 5.1 / 5.4 / 7.2）：
算法推荐 → 合规引擎输入校验 → RAG 检索（Mock）→ LLM 生成 → 输出后合规校验 → 审计落库
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
)
from algorithms import nearest_neighbor as nn
from algorithms.association_rules import recommend_products_by_association

# 演示模式开关（SVC-05）：True 时解读直接返回预置样例、禁止调用任何大模型 API。
# 本地默认关闭（自由调用 LLM）；公开分享链接场景由部署平台注入 DEMO_MODE=True。
DEMO_MODE = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")


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
            "message": "推荐完成"
        }

    elif method == 'association':
        selected_product_id = data.get('selected_product')

        if not selected_product_id:
            return {"error": "请选择商品"}

        try:
            recommendations = recommend_products_by_association(int(selected_product_id))
            return {
                "recommendations": recommendations,
                "message": "关联推荐完成"
            }
        except Exception as e:
            return {"error": f"关联规则算法错误: {str(e)}"}

    else:
        return {"error": "不支持的算法"}


def generate_explanation(recommendations, user_context):
    """Agent 合规解读流水线（需求文档 5.4 / 7.2 核心风控流程）

    输入校验 →（拦截则不出 LLM）→ DEMO_MODE 分支（命中则直接返回预置样例，不触及 LLM）
    → RAG 检索 → LLM 生成 → 输出后校验 →（拦截则替换模板）→ 审计落库
    """
    input_check = compliance_engine.check_input(json.dumps(user_context, ensure_ascii=False))

    if not input_check['passed']:
        # 注入/违规输入：不调用 LLM，直接回退合规模板
        text = build_fallback_explanation(recommendations, user_context, reason="输入含违规或攻击性内容，已由合规引擎拦截")
        audit_logger.log_agent_call(
            input_payload={"recommendations": recommendations, "user_context": user_context},
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
            text = build_fallback_explanation(recommendations, user_context, reason="演示样例校验未通过，已替换")
        audit_logger.log_agent_call(
            input_payload={"recommendations": recommendations, "user_context": user_context},
            output_text=text,
            compliance_result="pass" if output_check['passed'] else "blocked_output",
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
        # 输出后校验失败：整段替换为预置合规模板（输出后校验兜底）
        text = build_fallback_explanation(recommendations, user_context, reason="输出含违规表述，已由合规引擎拦截替换")

    audit_logger.log_agent_call(
        input_payload={"recommendations": recommendations, "user_context": user_context},
        output_text=text,
        compliance_result="pass" if output_check['passed'] else "blocked_output",
        is_degraded=llm_result["degraded"] or not output_check['passed'],
        model=llm_result.get("model"),
    )

    return _build_response(text, source=llm_result["source"], degraded=llm_result["degraded"] or not output_check['passed'],
                           compliance=output_check, error=llm_result["error"])


def _build_response(text, source, degraded, compliance, error):
    """统一解读响应结构（SVC-02 契约：解读 + 合规结果 + 免责声明）"""
    return {
        "explanation": text,
        "source": source,
        "degraded": degraded,
        "compliance": compliance,
        "disclaimer": DISCLAIMER,
        "error": error,
    }
