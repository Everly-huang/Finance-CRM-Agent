"""LLM 客户端（AGT-02）

接入 Deepseek API（OpenAI 兼容端点），使用 requests 直连以减少依赖（ENG-02）。
降级策略（需求文档 8.1 / 清单 AGT-02）：timeout 30s + 失败重试 1 次 + 模板降级——
断网 / 无 key / 超时一律回退预置合规模板并标注"基础版解读"，不向调用方抛异常。
（30s 依据:真实解读五段文本实测生成耗时约 18s,8s 会 ReadTimeout 误判降级）
"""

import os

import requests

from agent.prompt_templates import build_fallback_explanation

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 2  # 1 次调用 + 1 次重试


def generate_explanation(messages, recommendations, user_context):
    """调用 LLM 生成解读；任何失败均降级为模板，绝不抛异常。

    返回 {'text': 解读文本, 'source': 'llm'|'template',
          'degraded': 是否降级, 'error': 失败原因（正常时为 None）,
          'model': 实际使用的模型标识}
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return _degraded(recommendations, user_context, "未配置 DEEPSEEK_API_KEY")

    base_url = os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL)
    last_error = None

    for _ in range(MAX_ATTEMPTS):
        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.3,
                    "stream": False,
                },
                timeout=TIMEOUT_SECONDS,
            )
            if response.status_code == 200:
                text = response.json()["choices"][0]["message"]["content"]
                return {
                    "text": text,
                    "source": "llm",
                    "degraded": False,
                    "error": None,
                    "model": model,
                }
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last_error = f"请求异常: {exc.__class__.__name__}"

    return _degraded(recommendations, user_context, last_error, model)


def _degraded(recommendations, user_context, error, model=None):
    """构造降级响应：预置合规模板 + 标注基础版解读"""
    text = build_fallback_explanation(recommendations, user_context, reason=error)
    return {
        "text": text,
        "source": "template",
        "degraded": True,
        "error": error,
        "model": model,
    }
