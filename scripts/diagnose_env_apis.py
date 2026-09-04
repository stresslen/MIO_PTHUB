#!/usr/bin/env python3
"""Diagnose all APIs configured in .env."""

import os
import sys
import time
from pathlib import Path
import requests
from dotenv import load_dotenv

# Load .env explicitly
env_path = Path("/home/reg/DATLD/MIO/.env")
load_dotenv(dotenv_path=env_path, override=True)

AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.xah.io/v1").rstrip("/")
XAH_API_KEY = os.getenv("XAH_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "levuphong2909/gemini-3.8-flash-high")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "dungcsnd113/deepseek-v4-flash-0731")

XAH_SEARCH_URL = os.getenv("XAH_SEARCH_URL", "https://api.xah.io/v1/search")
XAH_SEARCH_MODEL = os.getenv("XAH_SEARCH_MODEL", "dungcsnd113/deepseek-v4-flash-0731")

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")
APIFY_ACTOR = os.getenv("APIFY_LINKEDIN_ACTOR_ID", "harvestapi/linkedin-post-search")


def test_gemini_model():
    print(f"\n[1] TEST GEMINI MODEL ({GEMINI_MODEL}) trên {AI_BASE_URL}...")
    headers = {
        "Authorization": f"Bearer {XAH_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GEMINI_MODEL,
        "messages": [{"role": "user", "content": "Trả về JSON: {\"status\": \"ok\", \"test\": \"gemini\"}"}],
        "temperature": 0.1,
    }
    t0 = time.time()
    try:
        resp = requests.post(f"{AI_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=35)
        elapsed = time.time() - t0
        print(f"    -> HTTP Status: {resp.status_code} (Thời gian: {elapsed:.2f}s)")
        if resp.status_code == 200:
            content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"    -> Kết quả: {content[:150]}")
            return True, elapsed, None
        else:
            print(f"    -> Lỗi ({resp.status_code}): {resp.text[:300]}")
            return False, elapsed, resp.text[:300]
    except Exception as e:
        elapsed = time.time() - t0
        print(f"    -> Ngoại lệ: {e} (sau {elapsed:.2f}s)")
        return False, elapsed, str(e)


def test_openai_model():
    print(f"\n[2] TEST OPENAI/DEEPSEEK MODEL ({OPENAI_MODEL}) trên {AI_BASE_URL}...")
    headers = {
        "Authorization": f"Bearer {XAH_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": "Trả về JSON: {\"status\": \"ok\", \"test\": \"deepseek\"}"}],
        "temperature": 0.1,
    }
    t0 = time.time()
    try:
        resp = requests.post(f"{AI_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=35)
        elapsed = time.time() - t0
        print(f"    -> HTTP Status: {resp.status_code} (Thời gian: {elapsed:.2f}s)")
        if resp.status_code == 200:
            content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"    -> Kết quả: {content[:150]}")
            return True, elapsed, None
        else:
            print(f"    -> Lỗi ({resp.status_code}): {resp.text[:300]}")
            return False, elapsed, resp.text[:300]
    except Exception as e:
        elapsed = time.time() - t0
        print(f"    -> Ngoại lệ: {e} (sau {elapsed:.2f}s)")
        return False, elapsed, str(e)


def test_xah_search():
    print(f"\n[3] TEST XAH SEARCH API ({XAH_SEARCH_URL}) model={XAH_SEARCH_MODEL}...")
    headers = {
        "Authorization": f"Bearer {XAH_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": "Bộ Kế hoạch và Đầu tư mua sắm công",
        "model": XAH_SEARCH_MODEL,
        "search_type": "web",
        "max_results": 3,
        "country": "Vietnam",
        "language": "Vietnam",
    }
    t0 = time.time()
    try:
        resp = requests.post(XAH_SEARCH_URL, headers=headers, json=payload, timeout=35)
        elapsed = time.time() - t0
        print(f"    -> HTTP Status: {resp.status_code} (Thời gian: {elapsed:.2f}s)")
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", data.get("data", []))
            count = len(results) if isinstance(results, list) else 1
            print(f"    -> Tìm thấy {count} kết quả search")
            return True, elapsed, None
        else:
            print(f"    -> Lỗi ({resp.status_code}): {resp.text[:300]}")
            return False, elapsed, resp.text[:300]
    except Exception as e:
        elapsed = time.time() - t0
        print(f"    -> Ngoại lệ: {e} (sau {elapsed:.2f}s)")
        return False, elapsed, str(e)


def test_apify():
    print(f"\n[4] TEST APIFY API (Token={APIFY_API_TOKEN[:15]}...)...")
    headers = {
        "Authorization": f"Bearer {APIFY_API_TOKEN}",
    }
    t0 = time.time()
    try:
        # Check Apify account / token status
        resp = requests.get("https://api.apify.com/v2/users/me", headers=headers, timeout=15)
        elapsed = time.time() - t0
        print(f"    -> HTTP Status (User Info): {resp.status_code} (Thời gian: {elapsed:.2f}s)")
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            username = data.get("username", "Unknown")
            print(f"    -> Apify Username: {username}")
            return True, elapsed, None
        else:
            print(f"    -> Lỗi Apify ({resp.status_code}): {resp.text[:300]}")
            return False, elapsed, resp.text[:300]
    except Exception as e:
        elapsed = time.time() - t0
        print(f"    -> Ngoại lệ: {e} (sau {elapsed:.2f}s)")
        return False, elapsed, str(e)


def test_heavy_prompt():
    print(f"\n[5] TEST GEMINI MODEL VỚI NỘI DUNG DÀI (Mô phỏng Muasamcong / Heavy Prompt)...")
    # Simulate a realistic long prompt with tables/text ~4,000 words
    dummy_table = "\n".join([f"Gói thầu {i}: Mua sắm trang thiết bị CNTT đợt {i}, giá 100.000.000 VNĐ, trúng thầu: Công ty ABC" for i in range(1, 80)])
    prompt = f"Trích xuất JSON ngắn gọn danh sách các bên liên quan từ dữ liệu sau:\n{dummy_table}\nChỉ trả về JSON."
    
    headers = {
        "Authorization": f"Bearer {XAH_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GEMINI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    t0 = time.time()
    try:
        resp = requests.post(f"{AI_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=45)
        elapsed = time.time() - t0
        print(f"    -> HTTP Status: {resp.status_code} (Thời gian: {elapsed:.2f}s)")
        if resp.status_code == 200:
            print(f"    -> Trả về thành công sau {elapsed:.2f}s!")
            return True, elapsed, None
        else:
            print(f"    -> Lỗi ({resp.status_code}): {resp.text[:300]}")
            return False, elapsed, resp.text[:300]
    except Exception as e:
        elapsed = time.time() - t0
        print(f"    -> Ngoại lệ khi chạy prompt dài: {e} (sau {elapsed:.2f}s)")
        return False, elapsed, str(e)


if __name__ == "__main__":
    print("=" * 65)
    print("BẮT ĐẦU KIỂM TRA TOÀN BỘ API TRONG FILE .ENV")
    print("=" * 65)
    test_gemini_model()
    test_openai_model()
    test_xah_search()
    test_apify()
    test_heavy_prompt()
    print("\n" + "=" * 65)
    print("HOÀN THÀNH KIỂM TRA API")
    print("=" * 65)
