"""RAG 检索模块（AGT-04 一期 Mock 占位）

需求文档 5.4：一期返回空上下文；二期接入 Chroma 向量库与产品文档表（AGT-06），
届时替换本实现即可，调用方无需改动。
"""


def retrieve_context(query, top_k=3):
    """一期 Mock：固定返回空上下文列表（接口签名与二期实现保持一致）"""
    return []
