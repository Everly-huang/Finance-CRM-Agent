@echo off
chcp 65001 >nul
title 金融产品智能推荐系统 - 一键启动 (DEP-01)
cd /d "%~dp0"

D:\Anaconda\envs\finance-crm\python.exe start_demo.py
if errorlevel 1 (
    echo.
    echo [失败] 启动异常,请检查上方日志。
    echo [提示] 后端启动后可访问 http://127.0.0.1:8000/docs 排查。
)
pause
