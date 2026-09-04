import os
import sys
import time
from app.config import settings

print("=== [1/4] Kiểm tra Cấu hình Đã Nạp ===", flush=True)
print(f"  AI Provider:    {settings.ai_provider}", flush=True)
print(f"  AI Base URL:    {settings.ai_base_url}", flush=True)
print(f"  API Key:        {settings.xah_api_key[:8]}...{settings.xah_api_key[-6:] if settings.xah_api_key else 'None'}", flush=True)
print(f"  Gemini Model:   {settings.gemini_model}", flush=True)
print(f"  OpenAI Model:   {settings.openai_model}", flush=True)
print(f"  XAH Search:     {settings.xah_search_model} @ {settings.xah_search_url}", flush=True)

# 2. Test Gemini call
print("\n=== [2/4] Kiểm tra Gemini LLM (Extract / Score) ===", flush=True)
import requests
endpoint = settings.gemini_base_url if settings.gemini_base_url.endswith("/chat/completions") else f"{settings.gemini_base_url.rstrip('/')}/chat/completions"
t0 = time.time()
try:
    resp = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {settings.gemini_api_key}", "Content-Type": "application/json"},
        json={
            "model": settings.gemini_model,
            "messages": [{"role": "user", "content": "Trả lời đúng 1 chữ: OK"}],
            "max_tokens": 10
        },
        timeout=10
    )
    dt = round(time.time() - t0, 2)
    print(f"  Status: HTTP {resp.status_code} ({dt}s)", flush=True)
    if resp.status_code == 200:
        ans = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        print(f"  Phản hồi: {ans}", flush=True)
    else:
        print(f"  Lỗi: {resp.text[:200]}", flush=True)
except Exception as e:
    print(f"  Exception: {e}", flush=True)

# 3. Test OpenAI model call
print("\n=== [3/4] Kiểm tra OpenAI LLM ===", flush=True)
endpoint = settings.openai_base_url if settings.openai_base_url.endswith("/chat/completions") else f"{settings.openai_base_url.rstrip('/')}/chat/completions"
t0 = time.time()
try:
    resp = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
        json={
            "model": settings.openai_model,
            "messages": [{"role": "user", "content": "Trả lời đúng 1 chữ: OK"}],
            "max_tokens": 10
        },
        timeout=10
    )
    dt = round(time.time() - t0, 2)
    print(f"  Status: HTTP {resp.status_code} ({dt}s)", flush=True)
    if resp.status_code == 200:
        ans = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        print(f"  Phản hồi: {ans}", flush=True)
    else:
        print(f"  Lỗi: {resp.text[:200]}", flush=True)
except Exception as e:
    print(f"  Exception: {e}", flush=True)

# 4. Test XAH Search
print("\n=== [4/4] Kiểm tra XAH Web Search API ===", flush=True)
t0 = time.time()
try:
    from app.services.xah_search_service import xah_search_service
    results = xah_search_service.search("đấu thầu công nghệ")
    dt = round(time.time() - t0, 2)
    found_urls = len(results.get("results", []))
    print(f"  Status: Thành công trong {dt}s. Tìm thấy {found_urls} liên kết.", flush=True)
except Exception as e:
    print(f"  Exception: {e}", flush=True)

print("\n=== HOÀN TẤT KIỂM TRA ===", flush=True)
