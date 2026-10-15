@echo off
rem ============================================================
rem  راه‌اندازی خودکار موتور AHRAM (برای Task Scheduler)
rem  پوشه‌ی پروژه: C:\Users\NikooCom\AHRAM_AI_V2_CLEAN\Ahram_AI_Agent
rem ============================================================
cd /d "C:\Users\NikooCom\AHRAM_AI_V2_CLEAN\Ahram_AI_Agent"
echo [%date% %time%] شروع موتور AHRAM >> logs\launcher.log 2>nul
python ahram_pro.py >> logs\launcher_stdout.log 2>&1
echo [%date% %time%] موتور متوقف شد (کد خروج %errorlevel%) >> logs\launcher.log 2>nul