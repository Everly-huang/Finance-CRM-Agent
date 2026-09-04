"""审计日志写入模块（DAT-01 / AGT-05）

需求文档 5.4 / 8.2：记录每次 Agent 调用（输入、输出、校验结果）到 agent_audit_log 表。
供服务编排层在 Agent 流水线末尾调用（AGT-05：审计写入打通）。
"""

import json

from database import db_connection


def log_agent_call(input_payload, output_text, compliance_result, is_degraded=False, model=None):
    """写入一条审计记录；payload 为 dict/list 时序列化为 JSON 文本。

    返回审计记录 ID（写入失败返回 None，不向调用方抛异常）。
    compliance_result 取值：pass / blocked_input / blocked_output / audience_drift
    """
    if not isinstance(input_payload, str):
        input_payload = json.dumps(input_payload, ensure_ascii=False)
    return db_connection.add_audit_log(
        input_payload=input_payload,
        output_text=output_text,
        compliance_result=compliance_result,
        is_degraded=int(is_degraded),
        model=model,
    )
