import re
import requests
import browser_cookie3
from config import FORM_VIEW_URL, FORM_SUBMIT_URL, logger


def get_chrome_session():
    """建立帶有 Chrome cookie 的 requests Session"""
    cj = browser_cookie3.chrome(domain_name='.google.com')
    s = requests.Session()
    for c in cj:
        s.cookies.set_cookie(c)
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    })
    return s


def submit_form(name: str, drink: str, temp: str, bean: str, note: str = "") -> tuple:
    """提交 Google Form，回傳 (成功與否, 訊息)"""
    try:
        s = get_chrome_session()
    except Exception as e:
        logger.error(f"無法讀取 Chrome cookie: {e}")
        return False, "無法讀取 Chrome cookie，請確認 Chrome 已登入 Google"

    try:
        r = s.get(FORM_VIEW_URL, timeout=10)
    except Exception as e:
        logger.error(f"無法載入表單頁面: {e}")
        return False, "無法連線到 Google Form"

    if "登入" in r.text and "英文名" not in r.text:
        return False, "Google 登入已過期，請重新在 Chrome 登入 Google 帳號"

    # 從頁面抓取隱藏欄位
    fbzx_match = re.findall(r'name="fbzx" value="([^"]+)"', r.text)
    if not fbzx_match:
        return False, "無法解析表單（找不到 fbzx）"
    fbzx = fbzx_match[0]

    # 從 data-params 解析欄位結構
    # 格式：%.@.[問題ID,"標題",null,類型,[[子欄位ID,...]]]
    # 類型 0 = 文字輸入，類型 2 = 單選（radio）
    field_blocks = re.findall(r'data-params="(%.@\.[^"]+)"', r.text)
    text_fields = []
    radio_fields = []
    for block in field_blocks:
        block = block.replace('&quot;', '"').replace('&amp;', '&')
        type_match = re.search(r',null,(\d+),\[\[(\d+)', block)
        if type_match:
            field_type = int(type_match.group(1))
            sub_id = type_match.group(2)
            if field_type == 0:
                text_fields.append(sub_id)
            elif field_type == 2:
                radio_fields.append(sub_id)

    if len(radio_fields) < 3 or len(text_fields) < 1:
        return False, f"表單欄位數量不符（文字:{len(text_fields)}, 單選:{len(radio_fields)}）"

    # 組合提交資料
    data = {
        f'entry.{text_fields[0]}': name,
        f'entry.{radio_fields[0]}': drink,
        f'entry.{radio_fields[0]}_sentinel': '',
        f'entry.{radio_fields[1]}': temp,
        f'entry.{radio_fields[1]}_sentinel': '',
        f'entry.{radio_fields[2]}': bean,
        f'entry.{radio_fields[2]}_sentinel': '',
        'fvv': '1',
        'pageHistory': '0',
        'fbzx': fbzx,
    }
    if len(text_fields) > 1:
        data[f'entry.{text_fields[1]}'] = note

    try:
        r2 = s.post(FORM_SUBMIT_URL, data=data, headers={'Referer': FORM_VIEW_URL}, timeout=10)
    except Exception as e:
        logger.error(f"提交請求失敗: {e}")
        return False, "網路錯誤，無法提交表單"

    if r2.status_code == 400:
        logger.warning(f"[提交失敗] {name} | {drink}/{temp}/{bean} | HTTP 400")
        return False, "表單拒絕提交（400），可能欄位格式有誤"
    if r2.status_code != 200:
        logger.warning(f"[提交失敗] {name} | {drink}/{temp}/{bean} | HTTP {r2.status_code}")
        return False, f"表單回傳錯誤（HTTP {r2.status_code}）"

    if "回覆" in r2.text or "recorded" in r2.text.lower():
        logger.info(f"[提交成功] {name} | {drink}/{temp}/{bean}")
        return True, "提交成功"

    logger.warning(f"[提交未確認] {name} | {drink}/{temp}/{bean} | 回應中無確認關鍵字")
    return False, "提交後未收到確認，請到表單頁面確認是否成功"
