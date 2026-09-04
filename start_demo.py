"""一键启动脚本(DEP-01)

自动完成:
1. secrets 桥接:解析 frontend/.streamlit/secrets.toml(tomllib 内置),
   将 DEEPSEEK_API_KEY/BASE_URL/MODEL 注入后端进程环境变量(解决 st.secrets 仅前端可读的问题)
2. 启动后端(uvicorn 8000)→ 轮询就绪
3. 启动前端(streamlit 8501)→ 轮询就绪
4. 可选 --smoke:启动后自动运行冒烟脚本(ENG-04)
Ctrl+C 一键停止双进程。

用法(必须用 finance-crm 环境解释器):
    /d/Anaconda/envs/finance-crm/python.exe start_demo.py            # 一键启动
    /d/Anaconda/envs/finance-crm/python.exe start_demo.py --smoke    # 启动后自动冒烟
"""

import argparse
import os
import subprocess
import sys
import time
import tomllib  # Python 3.11 内置
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
BACKEND_PORT = 8000
FRONTEND_PORT = 8501
SECRETS_FILE = ROOT / "frontend" / ".streamlit" / "secrets.toml"
ENV_BRIDGE_KEYS = ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL")


def bridge_secrets():
    """st.secrets → 后端进程环境变量桥接(DEP-02 遗留):子进程继承本进程环境"""
    if not SECRETS_FILE.exists():
        print(f"[提示] 未找到 {SECRETS_FILE},LLM 解读将走降级模板路径(无 key 不报错)")
        return
    try:
        with open(SECRETS_FILE, "rb") as fp:
            secrets = tomllib.load(fp)
    except tomllib.TOMLDecodeError as exc:
        print(f"[警告] secrets.toml 解析失败({exc}),跳过 key 注入")
        return
    for key in ENV_BRIDGE_KEYS:
        value = secrets.get(key)
        if value:
            os.environ[key] = str(value)
            masked = value if key != "DEEPSEEK_API_KEY" else f"{value[:8]}...(已注入,不回显)"
            print(f"[secrets 桥接] {key} = {masked}")
        elif key == "DEEPSEEK_API_KEY":
            print("[提示] secrets.toml 未含 DEEPSEEK_API_KEY,LLM 解读将走降级模板路径")


def wait_ready(url, timeout, label):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get(url, timeout=2)
            print(f"[就绪] {label}: {url}")
            return True
        except requests.RequestException:
            time.sleep(1)
    print(f"[失败] {label} 在 {timeout}s 内未就绪: {url}")
    return False


def main():
    parser = argparse.ArgumentParser(description="金融产品智能推荐系统一键启动(DEP-01)")
    parser.add_argument("--smoke", action="store_true", help="启动后自动运行冒烟脚本(ENG-04)")
    parser.add_argument("--demo", action="store_true",
                        help="以 DEMO_MODE=True 启动(解读返回预置样例,禁止调用 LLM;SVC-05)")
    args = parser.parse_args()

    if args.demo:
        os.environ["DEMO_MODE"] = "true"  # 在起后端进程之前设置,子进程继承

    print("=" * 56)
    print("金融产品智能推荐系统 — 一键启动(DEP-01)")
    print("=" * 56)
    if args.demo:
        print("[演示模式] DEMO_MODE=True:AI 解读返回预置样例,禁止调用大模型 API")
    bridge_secrets()

    procs = []
    try:
        backend = subprocess.Popen([PYTHON, "main.py"], cwd=ROOT / "backend")
        procs.append(backend)
        print(f"[启动] 后端 uvicorn (pid={backend.pid})")
        if not wait_ready(f"http://127.0.0.1:{BACKEND_PORT}/", 30, "后端"):
            return 1

        frontend = subprocess.Popen(
            [PYTHON, "-m", "streamlit", "run", "app.py",
             "--server.port", str(FRONTEND_PORT), "--server.headless", "true"],
            cwd=ROOT / "frontend",
        )
        procs.append(frontend)
        print(f"[启动] 前端 Streamlit (pid={frontend.pid})")
        if not wait_ready(f"http://127.0.0.1:{FRONTEND_PORT}", 60, "前端"):
            return 1

        print()
        print(f"后端 API : http://127.0.0.1:{BACKEND_PORT}  (FastAPI 文档 /docs)")
        print(f"前端页面 : http://127.0.0.1:{FRONTEND_PORT}")
        print("按 Ctrl+C 一键停止双进程。")

        if args.smoke:
            print()
            print("[冒烟] 运行 backend/smoke_test.py ...")
            smoke_args = [PYTHON, "smoke_test.py"]
            if args.demo:
                smoke_args.append("--expect-demo")  # 演示模式冒烟断言 source=demo
            result = subprocess.run(smoke_args, cwd=ROOT / "backend")
            print(f"[冒烟] 退出码: {result.returncode}")

        # 前台保持:任一双进程退出则整体停止
        while True:
            for proc in procs:
                if proc.poll() is not None:
                    print(f"[退出] 子进程 {proc.pid} 已结束,停止全部服务")
                    return 1
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n[停止] 收到 Ctrl+C,正在终止双进程...")
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
