"""合规规则引擎（AGT-01 + F1 双模式 / F3 受众检测）

需求文档 5.4 / 6.4 / 8.2：关键词黑名单 + 正则拦截 + 输出后校验。
- check_input：输入侧校验（用户上下文/参数），拦截 Prompt 注入攻击与违规表述
- validate_output(text, mode)：输出后校验
  - 基础规则（黑名单+正则+否定语境豁免）两模式共用，零语义变更
  - mode="analysis"：追加受众检测（检出「您」即受众漂移，F3）
  - mode="script"：追加话术专项规则（收益裸数字/饥饿营销/绝对化/算法指标进对客区，F1）
"""

import re

from agent.prompt_templates import SCRIPT_NOTES_HEADER

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

# 否定语境豁免：命中项所在句子含以下否定词组时视为合规教育/免责语境，放行。
# 例：LLM 输出「中低风险不等于无风险」「不构成任何收益保证」「严禁宣传"保证收益"」
# ——这些是合规话术，不应被裸关键词误拦；真承诺句（无否定词）仍被拦截。
NEGATION_PHRASES = (
    "不等于", "不代表", "不构成", "不作为", "并非", "不是", "不得", "不应",
    "严禁", "禁止", "杜绝", "否认", "绝不", "避免", "不要", "切勿", "请勿",
)

# ---------- F3 受众检测（analysis 模式专用） ----------
# 检出「您」即受众漂移：analysis 解读唯一听众是理财经理，提及客户须第三人称。
# 无否定豁免需求：不存在含「您」的合法合规教育句（模板与免责声明均无「您」）。
AUDIENCE_PATTERNS = [r"您"]

# ---------- F1 话术专项规则（script 模式专用） ----------
# 算法内部指标词：只在对客区扫描（备注区允许出现）；「距离」不单列，规避普通语义误伤
SCRIPT_METRIC_TERMS = ("支持度", "置信度", "相似度", "匹配距离", "关联规则", "关联分数")

# SR-1 收益裸数字：收益/回报/年化后 10 字符内出现百分比数字且句内无限定语 → 拦截
SR1_NUMBER_PATTERN = re.compile(r"(收益|回报|年化)[^，。；！？\n]{0,10}\d+(\.\d+)?%")
SR1_QUALIFIERS = ("业绩比较基准", "参考", "不代表", "非承诺", "浮动", "历史", "不保证", "模拟")

# SR-2 时间压力/饥饿营销 + SR-4 绝对化夸大（复用否定语境豁免：
# 备注区"严禁使用'仅限今天'"式合规教育话术放行）
SCRIPT_MARKETING_PATTERNS = [
    r"(额度|名额)(紧张|有限|告急|不多|告罄)",
    r"(仅限|限时|最后|截止)(今天|今日|本周|三天|一周|7天)",
    r"即将售罄|最后机会|先到先得|错过不再|抢购|马上截止",
    r"(最好|最优|最佳|最低|最高)(的)?(收益|回报|风险|亏损|利息|涨幅|产品|选择|方案)",
    r"收益(最|极)(高|好|优|佳)",
    r"(行业|全行|全市场|全网|同类|同档次)(最低|最高|最好|领先|第一)",
    r"唯一(的)?(适合|正确|值得|选择|最优)",
    r"(顶级|最强|极致)(产品|收益|表现|安全)",
    r"绝对(不会|不亏|盈利|赚钱|安全|有保障)",
    r"百分百(盈利|赚钱|安全|保本)",
]

_COMPILED_BLOCKED = [re.compile(pattern) for pattern in BLOCKED_PATTERNS]
_COMPILED_INJECTION = [re.compile(pattern) for pattern in INJECTION_PATTERNS]
_COMPILED_AUDIENCE = [re.compile(pattern) for pattern in AUDIENCE_PATTERNS]
_COMPILED_SCRIPT_MARKETING = [re.compile(pattern) for pattern in SCRIPT_MARKETING_PATTERNS]
_SENTENCE_SEPARATORS = ("。", "；", "!", "！", "\n")


def _is_negated_context(text, match_start):
    """判断命中位置是否处于否定语境（所在句子含否定词组）"""
    seg_start = 0
    for sep in _SENTENCE_SEPARATORS:
        idx = text.rfind(sep, 0, match_start)
        seg_start = max(seg_start, idx + 1)
    seg_end = len(text)
    for sep in _SENTENCE_SEPARATORS:
        idx = text.find(sep, match_start)
        if idx != -1:
            seg_end = min(seg_end, idx)
    sentence = text[seg_start:seg_end]
    return any(phrase in sentence for phrase in NEGATION_PHRASES)


def _sentence_contains_any(text, position, terms):
    """判断命中位置所在句子是否包含 terms 中的任一限定词（SR-1 限定语豁免）"""
    seg_start = 0
    for sep in _SENTENCE_SEPARATORS:
        idx = text.rfind(sep, 0, position)
        seg_start = max(seg_start, idx + 1)
    seg_end = len(text)
    for sep in _SENTENCE_SEPARATORS:
        idx = text.find(sep, position)
        if idx != -1:
            seg_end = min(seg_end, idx)
    sentence = text[seg_start:seg_end]
    return any(term in sentence for term in terms)


def _scan_text(text):
    """黑名单关键词 + 违规正则扫描，返回违规项列表（否定语境豁免）"""
    violations = []
    for keyword in BLACKLIST_KEYWORDS:
        start = text.find(keyword)
        while start != -1:
            if not _is_negated_context(text, start):
                violations.append({"type": "keyword", "term": keyword})
                break
            start = text.find(keyword, start + 1)
    for pattern in _COMPILED_BLOCKED:
        match = pattern.search(text)
        while match:
            if not _is_negated_context(text, match.start()):
                violations.append({"type": "regex", "term": match.group(0)})
                break
            match = pattern.search(text, match.end())
    return violations


def _scan_audience(text):
    """受众漂移检测（F3，analysis 模式）：检出「您」即违规"""
    violations = []
    for pattern in _COMPILED_AUDIENCE:
        for match in pattern.finditer(text):
            violations.append({"type": "audience", "term": match.group(0)})
    return violations


def _split_script_regions(text):
    """按备注区标题切分话术文本：返回 (对客区, 备注区)。无标题时全文视为对客区（更严，安全方向）。"""
    idx = text.find(SCRIPT_NOTES_HEADER)
    if idx == -1:
        return (text, "")
    return (text[:idx], text[idx:])


def _scan_script_rules(text):
    """script 模式专项规则（F1）：指标词进对客区 / SR-1 收益裸数字 / SR-2+SR-4 营销与绝对化"""
    violations = []
    customer_part, _ = _split_script_regions(text)
    for term in SCRIPT_METRIC_TERMS:
        if term in customer_part:
            violations.append({"type": "script_metric", "term": term})
    # SR-1 只扫对客区：裸收益数字是对客区禁项；备注区经理教育句
    # （如"客户若询问8%以上产品，切勿直接推荐"）不应误拦
    for match in SR1_NUMBER_PATTERN.finditer(customer_part):
        if not _sentence_contains_any(customer_part, match.start(), SR1_QUALIFIERS):
            violations.append({"type": "script", "term": match.group(0)})
    for pattern in _COMPILED_SCRIPT_MARKETING:
        for match in pattern.finditer(text):
            if not _is_negated_context(text, match.start()):
                violations.append({"type": "script", "term": match.group(0)})
    return violations


def check_input(text):
    """输入侧校验：Prompt 注入检测 + 违规表述扫描（LLM 调用前执行）"""
    violations = _scan_text(text)
    for pattern in _COMPILED_INJECTION:
        match = pattern.search(text)
        if match:
            violations.append({"type": "injection", "term": match.group(0)})
    return {"passed": not violations, "violations": violations}


def validate_output(text, mode="analysis"):
    """输出后校验：基础规则两模式共用（零语义变更），mode 追加专项规则。

    mode="analysis"（默认）：+ 受众检测（「您」即漂移）
    mode="script"：+ 话术专项规则（收益裸数字/饥饿营销/绝对化/算法指标进对客区）
    """
    violations = _scan_text(text)
    if mode == "analysis":
        violations += _scan_audience(text)
    elif mode == "script":
        violations += _scan_script_rules(text)
    return {"passed": not violations, "violations": violations}
