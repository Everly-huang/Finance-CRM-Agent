"""合规规则引擎（AGT-01）

需求文档 5.4 / 6.4 / 8.2：关键词黑名单 + 正则拦截 + 输出后校验。
- check_input：输入侧校验（用户上下文/参数），拦截 Prompt 注入攻击与违规表述
- validate_output：输出后校验（LLM 生成文本），拦截违规表述
"""

import re

# 关键词黑名单：保本暗示 / 收益承诺 / 违规表述（需求文档 6.4 禁止项）
BLACKLIST_KEYWORDS = [
    "保本", "稳赚", "稳赚不赔", "零风险", "无风险", "保本保息",
    "必赚", "只涨不跌", "保证收益", "承诺收益", "确保收益", "肯定赚钱",
]

# 正则拦截：覆盖更隐蔽的收益承诺 / 买卖指导表述
BLOCKED_PATTERNS = [
    r"(保证|承诺|确保)[^，。；！？]{0,12}(收益|回报|本金)",
    r"(无|零|没有)风险",
    r"(肯定|一定|必然)(赚|涨|盈利|翻倍)",
    r"(建议|赶紧|立即|马上|抓紧)(买|卖|购|抛|入|清仓|建仓)",
]

# Prompt 注入攻击特征（AGT-03 验收：'你是投资顾问'类攻击被拦截）
INJECTION_PATTERNS = [
    r"你是(一名|一个)?(投资顾问|理财顾问|投资专家|基金经理|荐股师)",
    r"(现在|从现在起|接下来)(开始)?(扮演|担任|作为)",
    r"忽略(以上|上面|之前|上述|所有|先前的)(的)?(指令|规则|约束|设置|提示|要求)",
    r"(无视|忽视|绕过)(以上|上述|系统|合规|安全)",
    r"你(现在是|不再是)",
]

_COMPILED_BLOCKED = [re.compile(pattern) for pattern in BLOCKED_PATTERNS]
_COMPILED_INJECTION = [re.compile(pattern) for pattern in INJECTION_PATTERNS]


def _scan_text(text):
    """黑名单关键词 + 违规正则扫描，返回违规项列表"""
    violations = []
    for keyword in BLACKLIST_KEYWORDS:
        if keyword in text:
            violations.append({"type": "keyword", "term": keyword})
    for pattern in _COMPILED_BLOCKED:
        match = pattern.search(text)
        if match:
            violations.append({"type": "regex", "term": match.group(0)})
    return violations


def check_input(text):
    """输入侧校验：Prompt 注入检测 + 违规表述扫描（LLM 调用前执行）"""
    violations = _scan_text(text)
    for pattern in _COMPILED_INJECTION:
        match = pattern.search(text)
        if match:
            violations.append({"type": "injection", "term": match.group(0)})
    return {"passed": not violations, "violations": violations}


def validate_output(text):
    """输出后校验：LLM 输出文本的违规扫描（LLM 调用后执行）"""
    violations = _scan_text(text)
    return {"passed": not violations, "violations": violations}
