# find_code.py
import os

KEYWORDS = [
    "options_dashboard",
    "ahram_strategy_data",
    "پوزیشن‌های باز",
    "معامله‌های تسویه‌شده",
    "خرید کال",
    "notification",
    "toast",
    "plyer",
    "Max Pain",
]

print("🔍 در حال اسکن پوشه‌های پروژه برای پیدا کردن فایل‌های هدف...\n")

found_files = set()

for root, dirs, files in os.walk("."):
  # نادیده گرفتن پوشه‌های غیرضروری
  dirs[:] = [
      d
      for d in dirs
      if d not in ["venv", "__pycache__", ".git", ".vscode", "node_modules"]
  ]

  for file in files:
    if file.endswith(".py") and file != "find_code.py":
      filepath = os.path.join(root, file)
      try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
          content = f.read()
          matched = [kw for kw in KEYWORDS if kw.lower() in content.lower()]
          if matched:
            print(f"📄 فایل پیدا شد: {file}")
            print(f"   📍 مسیر کامل: {filepath}")
            print(f"   🔑 کلمات پیدا شده: {', '.join(matched)}\n")
            found_files.add(file)
      except Exception as e:
        pass

if not found_files:
  print("❌ فایلی با این مشخصات پیدا نشد!")