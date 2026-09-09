@echo off
REM ============================================================
REM  Zoho Payment Escalator - Daily Run
REM  Runs once, sends reminders, then exits.
REM  Set this to trigger "Daily" at a fixed time in Task Scheduler.
REM  UPDATE PROJECT_DIR below to match your actual working folder
REM  (the one containing .env and venv, not just an upload copy).
REM ============================================================

set PROJECT_DIR=D:\GIT\zoho-payment-escalator

cd /d "%PROJECT_DIR%"
call venv\Scripts\activate
python escalator.py >> escalator_log.txt 2>&1
