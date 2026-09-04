#!/usr/bin/env bash
# 一键启动(Git Bash / Linux 入口,逻辑同 start_demo.py)
cd "$(dirname "$0")"
exec /d/Anaconda/envs/finance-crm/python.exe start_demo.py "$@"
