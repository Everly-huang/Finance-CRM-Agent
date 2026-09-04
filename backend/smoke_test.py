"""冒烟测试脚本(ENG-04)

验收口径对齐需求文档 6.2 / 6.3 / SVC-02:
- KNN: Top6 整批分流(最小距离≤0.3 → 相似推荐;>0.3 → 热门推荐);输出 8 字段,无数值相似度(ALG-01 规划)
- Apriori: Top6,关联推荐带 support/confidence 百分比字符串、无提升度;不足 Top6 以热门补齐
- explain: 响应含 explanation/source/degraded/compliance/disclaimer 契约字段

用法:先启动后端(cd backend && /d/Anaconda/envs/finance-crm/python.exe main.py),再运行本脚本:
    cd backend && /d/Anaconda/envs/finance-crm/python.exe smoke_test.py
    cd backend && /d/Anaconda/envs/finance-crm/python.exe smoke_test.py --expect-demo  # 后端以 DEMO_MODE=True 启动时
退出码:0 = 全绿;1 = 存在失败项
"""

import argparse
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"
FAILURES = []


def check(step, condition, detail):
    """登记冒烟结果:PASS/FAIL 并收集失败项"""
    print(f"[{'PASS' if condition else 'FAIL'}] {step} — {detail}")
    if not condition:
        FAILURES.append(step)


def main(expect_demo=False):
    # 1. 预热:GET 产品列表,触发惰性建表播种(CLAUDE.md 已知陷阱规避)
    resp = requests.get(f"{BASE}/api/products/all/", timeout=10)
    products = resp.json().get("products", []) if resp.status_code == 200 else []
    check("预热 GET /api/products/all/", len(products) == 10, f"产品数={len(products)}(预期 10)")

    # 2. KNN 相似推荐(需求文档 6.2:category 70 + 50000 → 最小距离 0 → 相似推荐 Top6)
    resp = requests.post(
        f"{BASE}/api/recommend/",
        json={"method": "nearest_neighbor", "category_id": 70, "price": 50000},
        timeout=15,
    )
    recs = resp.json().get("recommendations", []) if resp.status_code == 200 else []
    all_similar = recs and all(p.get("recommend_type") == "相似推荐" for p in recs)
    check("KNN 相似推荐(70, 50000)", len(recs) == 6 and all_similar,
          f"条数={len(recs)},整批类型={'相似推荐' if all_similar else '不一致'}")

    expected_keys = {"id", "name", "category_id", "price", "risk_level",
                     "expected_return", "description", "recommend_type"}
    check("KNN 输出字段(6.2 口径:8 字段,无 similarity/distance)",
          bool(recs) and set(recs[0].keys()) == expected_keys,
          f"实际字段={sorted(recs[0].keys()) if recs else '无'}")

    # 3. KNN 异常分流(需求文档 6.2:250000 → 最小距离 0.4>0.3 → 整批热门推荐)
    resp = requests.post(
        f"{BASE}/api/recommend/",
        json={"method": "nearest_neighbor", "category_id": 70, "price": 250000},
        timeout=15,
    )
    recs2 = resp.json().get("recommendations", []) if resp.status_code == 200 else []
    all_hot = recs2 and all(p.get("recommend_type") == "热门推荐" for p in recs2)
    check("KNN 异常分流(70, 250000)→ 整批热门推荐", len(recs2) == 6 and all_hot,
          f"条数={len(recs2)},整批类型={'热门推荐' if all_hot else '不一致'}")

    # 4. Apriori 关联推荐(需求文档 6.3:产品 4 → 关联项 + 热门补齐,共 Top6)
    resp = requests.post(
        f"{BASE}/api/recommend/",
        json={"method": "association", "selected_product": 4},
        timeout=15,
    )
    recs3 = resp.json().get("recommendations", []) if resp.status_code == 200 else []
    assoc = [p for p in recs3 if p.get("recommend_type") == "关联推荐"]
    fallback = [p for p in recs3 if p.get("recommend_type") == "热门推荐"]
    check("Apriori 关联推荐(产品 4)", len(recs3) == 6 and len(assoc) >= 1,
          f"关联={len(assoc)} 条,热门补齐={len(fallback)} 条")

    check("Apriori 指标格式(6.3 口径:百分比字符串,无提升度字段)",
          bool(assoc) and "%" in str(assoc[0].get("support", "")) and "lift" not in assoc[0],
          f"support={assoc[0].get('support') if assoc else '-'},"
          f"confidence={assoc[0].get('confidence') if assoc else '-'}")

    # 5. explain 解读端点(SVC-02 契约:五个字段齐全;--expect-demo 时断言 SVC-05 演示模式)
    sample = recs if recs else recs3
    resp = requests.post(
        f"{BASE}/api/recommend/explain",
        json={"recommendations": sample, "user_context": {"客户偏好分类": "稳健理财"}},
        timeout=60,
    )
    body = resp.json() if resp.status_code == 200 else {}
    contract_ok = all(k in body for k in ("explanation", "source", "degraded", "compliance", "disclaimer"))
    if expect_demo:
        demo_ok = (body.get("source") == "demo" and body.get("degraded") is False
                   and "演示样例" in body.get("explanation", ""))
        check("POST /api/recommend/explain 演示模式契约(SVC-05)",
              resp.status_code == 200 and contract_ok and demo_ok,
              f"source={body.get('source')},degraded={body.get('degraded')}")
    else:
        check("POST /api/recommend/explain 响应契约",
              resp.status_code == 200 and contract_ok and body.get("explanation"),
              f"source={body.get('source')},degraded={body.get('degraded')}")

    # 6. script 模式话术契约(F1:五字段齐全,文本键为 script;--expect-demo 时断言演示样例)
    resp = requests.post(
        f"{BASE}/api/recommend/explain",
        json={"recommendations": sample, "user_context": {"客户偏好分类": "稳健理财"}, "mode": "script"},
        timeout=60,
    )
    body = resp.json() if resp.status_code == 200 else {}
    script_contract_ok = all(k in body for k in ("script", "source", "degraded", "compliance", "disclaimer"))
    if expect_demo:
        demo_ok = (body.get("source") == "demo" and body.get("degraded") is False
                   and "演示样例" in body.get("script", ""))
        check("script 模式演示契约(F1)",
              resp.status_code == 200 and script_contract_ok and demo_ok,
              f"source={body.get('source')},degraded={body.get('degraded')}")
    else:
        # 无 key 时降级路径 source=template 含"基础版话术";注入真实 key 时 source=llm,两者均合法
        script_ok = (body.get("script") and body.get("source") in ("template", "llm")
                     and (body.get("source") != "template" or "基础版话术" in body.get("script", "")))
        check("script 模式契约(F1)",
              resp.status_code == 200 and script_contract_ok and script_ok,
              f"source={body.get('source')},degraded={body.get('degraded')}")

    print()
    if FAILURES:
        print(f"冒烟失败 {len(FAILURES)} 项:{FAILURES}")
        sys.exit(1)
    print("冒烟全部通过 ✓")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="后端冒烟测试(ENG-04)")
    parser.add_argument("--expect-demo", action="store_true",
                        help="后端以 DEMO_MODE=True 启动时使用,断言解读响应 source=demo(SVC-05)")
    main(expect_demo=parser.parse_args().expect_demo)
