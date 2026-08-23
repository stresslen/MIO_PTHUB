from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

logger = logging.getLogger(__name__)


class PriorityCoordinator:
    """
    Điều phối độ ưu tiên tác vụ giữa Lệnh từ Frontend (FE) và Luồng chạy ngầm (BE Background).
    
    Quy tắc hoạt động:
    1. Mọi lệnh do người dùng bấm từ Frontend (Manual Trigger, Cào Nguồn, Cập Nhật, Chấm Điểm)
       sẽ nhận trạng thái ƯU TIÊN TUYỆT ĐỐI (PREEMPTIVE HIGH PRIORITY).
    2. Khi có lệnh từ FE đang chạy:
       - Toàn bộ luồng cào ngầm định kỳ (Daily Scheduler) và hàng đợi (Queue Worker)
         sẽ tự động TẠM DỪNG (Pause & Yield) để nhường 100% CPU, DB Lock và AI Quota cho FE.
    3. Khi lệnh FE hoàn tất:
       - Luồng ngầm tự động KHÔI PHỤC và tiếp tục công việc bình thường.
    """

    def __init__(self):
        self._fe_task_count: int = 0
        self._pause_background_event = asyncio.Event()
        self._pause_background_event.set()  # Mặc định không bị tạm dừng
        self._lock = asyncio.Lock()

    @property
    def is_fe_active(self) -> bool:
        """Kiểm tra có tác vụ Frontend ưu tiên nào đang chạy hay không."""
        return self._fe_task_count > 0

    @asynccontextmanager
    async def fe_priority_context(self, task_name: str = "Frontend User Action"):
        """Context Manager đánh dấu tác vụ ưu tiên cao từ Frontend."""
        async with self._lock:
            self._fe_task_count += 1
            if self._fe_task_count == 1:
                self._pause_background_event.clear()
                logger.info(f"[PriorityManager] ⚡ [{task_name}] FRONTEND PRIORITY ACQUIRED. Tạm dừng toàn bộ luồng BE chạy ngầm để ưu tiên người dùng...")

        try:
            yield
        finally:
            async with self._lock:
                self._fe_task_count = max(0, self._fe_task_count - 1)
                if self._fe_task_count == 0:
                    self._pause_background_event.set()
                    logger.info(f"[PriorityManager] ✅ [{task_name}] FRONTEND TASK FINISHED. Khôi phục luồng BE chạy ngầm.")

    async def yield_if_fe_active(self, worker_name: str = "Background Worker"):
        """
        Được gọi trong các vòng lặp cào ngầm hoặc xử lý hàng đợi.
        Nếu phát hiện có lệnh từ Frontend đang chạy, luồng ngầm sẽ nhường tài nguyên ngay lập tức.
        """
        if not self._pause_background_event.is_set():
            logger.info(f"[PriorityManager] ⏸️ [{worker_name}] Phát hiện lệnh từ Frontend. Luồng ngầm đang tạm nhường tài nguyên...")
            await self._pause_background_event.wait()
            logger.info(f"[PriorityManager] ▶️ [{worker_name}] Tiếp tục luồng ngầm sau khi lệnh Frontend đã hoàn tất.")


priority_coordinator = PriorityCoordinator()
