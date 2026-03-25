@echo off
chcp 65001 >nul
cd /d "C:\Users\Administrator\.openclaw\skills\yinhua-daily-monitor\scripts"
python yinhua_monitor.py --once
