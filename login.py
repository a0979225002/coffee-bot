"""
用你現有的 Chrome 設定檔開啟瀏覽器（已登入的狀態），自動儲存 cookie。
執行前請先關閉所有 Chrome 視窗。
"""
import json
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

COOKIE_FILE = Path(__file__).parent / "cookies.json"

# 用你現有的 Chrome 設定檔，這樣已經登入的帳號會直接帶過來
options = webdriver.ChromeOptions()
options.add_argument("--user-data-dir=" + str(Path.home() / "Library/Application Support/Google/Chrome"))
options.add_argument("--profile-directory=Default")

print("正在開啟 Chrome（使用你現有的登入狀態）...")
print("請先關閉所有 Chrome 視窗！")
input("確認已關閉 Chrome 後按 Enter...")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.get("https://docs.google.com/forms/")
time.sleep(3)

cookies = driver.get_cookies()
COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))
print(f"Cookie 已儲存（{len(cookies)} 個），可以關閉此視窗。")

driver.quit()
