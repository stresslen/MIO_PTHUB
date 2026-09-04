#!/usr/bin/env python3
"""Test specifically GEMINI_MODEL configured in .env."""

import os
import sys
import time
from pathlib import Path
import requests
from dotenv import load_dotenv

env_path = Path("/home/reg/DATLD/MIO/.env")
load_dotenv(dotenv_path=env_path, override=True)

AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.xah.io/v1").rstrip("/")
XAH_API_KEY = os.getenv("XAH_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "levuphong2909/gemini-3.7-flash-high")

print("=" * 65)
print(f"BẮT ĐẦU TEST RIÊNG GEMINI MODEL: {GEMINI_MODEL}")
print(f"Gateway URL: {AI_BASE_URL}/chat/completions")
print("=" * 65)

headers = {
    "Authorization": f"Bearer {XAH_API_KEY}",
    "Content-Type": "application/json",
}

# 1. Test Simple Prompt
print("\n[Test 1] Simple Ping / JSON Response...")
payload1 = {
    "model": GEMINI_MODEL,
    "messages": [{"role": "user", "content": "Trả về duy nhất 1 JSON: {\"status\": \"ok\", \"model\": \"3.7\"}"}],
    "temperature": 0.1,
}
t0 = time.time()
try:
    r1 = requests.post(f"{AI_BASE_URL}/chat/completions", headers=headers, json=payload1, timeout=40)
    elapsed1 = time.time() - t0
    print(f"  -> HTTP Status: {r1.status_code} | Thời gian phản hồi: {elapsed1:.2f}s")
    if r1.status_code == 200:
        ans1 = r1.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"  -> Kết quả: {ans1.strip()[:200]}")
    else:
        print(f"  -> Lỗi HTTP {r1.status_code}: {r1.text[:300]}")
except Exception as e:
    elapsed1 = time.time() - t0
    print(f"  -> Thất bại / Timeout sau {elapsed1:.2f}s: {e}")

# 2. Test Extraction Prompt (Mô phỏng bóc tách cơ hội)
print("\n[Test 2] AI Extraction (Mô phỏng bóc tách bài thầu / dự án)...")
sample_text = """
UBND Tỉnh Quảng Ninh thông báo mời thầu gói: Mua sắm và triển khai hệ thống Camera AI giám sát giao thông thông minh.
Giá gói thầu: 15.000.000.000 VNĐ (Mười lăm tỷ đồng).
Hạn nộp hồ sơ: 20/09/2026.
Đơn vị mời thầu: Ban Quản lý Dự án Đầu tư Xây dựng Tỉnh Quảng Ninh.
Email: bqldaxaydung@quangninh.gov.vn, SĐT: 0203.3838388.
"""
payload2 = {
    "model": GEMINI_MODEL,
    "messages": [
        {"role": "system", "content": "Bạn là chuyên gia bóc tách thông tin thầu B2B/B2G. Trả về JSON."},
        {"role": "user", "content": f"Bóc tách thông tin cơ hội từ văn bản sau thành JSON gồm organization_name, need_summary, budget_value, contact_email, deadline:\n{sample_text}"}
    ],
    "temperature": 0.1,
}
t0 = time.time()
try:
    r2 = requests.post(f"{AI_BASE_URL}/chat/completions", headers=headers, json=payload2, timeout=45)
    elapsed2 = time.time() - t0
    print(f"  -> HTTP Status: {r2.status_code} | Thời gian phản hồi: {elapsed2:.2f}s")
    if r2.status_code == 200:
        ans2 = r2.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"  -> Kết quả JSON bóc tách:\n{ans2.strip()[:350]}")
    else:
        print(f"  -> Lỗi HTTP {r2.status_code}: {r2.text[:300]}")
except Exception as e:
    elapsed2 = time.time() - t0
    print(f"  -> Thất bại / Timeout sau {elapsed2:.2f}s: {e}")

# 3. Test Scoring Prompt (Mô phỏng chấm điểm)
print("\n[Test 3] AI Scoring & Sales Suggestion...")
payload3 = {
    "model": GEMINI_MODEL,
    "messages": [
        {"role": "user", "content": "Chấm điểm cơ hội sau từ 0-100 và đưa ra recommended_action (CALL/EMAIL/NURTURE). Trả về JSON:\nTiêu đề: Gói thầu Camera AI giao thông\nNgân sách: 15 tỷ VNĐ\nĐơn vị: BQL Dự án Quảng Ninh\nEmail: bql@quangninh.gov.vn"}
    ],
    "temperature": 0.1,
}
t0 = time.time()
try:
    r3 = requests.post(f"{AI_BASE_URL}/chat/completions", headers=headers, json=payload3, timeout=45)
    elapsed3 = time.time() - t0
    print(f"  -> HTTP Status: {r3.status_code} | Thời gian phản hồi: {elapsed3:.2f}s")
    if r3.status_code == 200:
        ans3 = r3.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"  -> Kết quả chấm điểm:\n{ans3.strip()[:350]}")
    else:
        print(f"  -> Lỗi HTTP {r3.status_code}: {r3.text[:300]}")
except Exception as e:
    elapsed3 = time.time() - t0
    print(f"  -> Thất bại / Timeout sau {elapsed3:.2f}s: {e}")

print("\n" + "=" * 65)
print("KẾT THÚC KIỂM TRA GEMINI 3.7")
print("=" * 65)
