from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import partial
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PriorityCoordinator:
    """
    Điều phối độ ưu tiên tác vụ giữa Lệnh từ Frontend (FE) và Luồng chạy ngầm (BE Background).
    
    Quy tắc hoạt động:
    1. Mọi lệnh do người dùng bấm từ Frontend (Manual Trigger, Cào Nguồn, Cập Nhật, Chấm Điểm)
       sẽ nhận trạng thái ƯU TIÊN TUYỆT ĐỐI (PREEMPTIVE HIGH PRIORITY).
    2. Khi có lệnh từ FE đang chạy:
       - Luồng cào ngầm định kỳ và hàng đợi không khởi động bước nặng mới.
       - Tác vụ FE dùng executor dự phòng riêng nên không phải chờ pool nền.
    3. Khi lệnh FE hoàn tất:
       - Luồng ngầm tự động KHÔI PHỤC và tiếp tục công việc bình thường.
    """

    def __init__(self):
        self._fe_task_count: int = 0
        self._pause_background_event = asyncio.Event()
        self._pause_background_event.set()  # Mặc định không bị tạm dừng
        self._lock = asyncio.Lock()
        self._frontend_context: ContextVar[bool] = ContextVar(
            "mio_frontend_priority", default=False
        )
        self._frontend_executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="mio-fe-priority"
        )

    @property
    def is_fe_active(self) -> bool:
        """Kiểm tra có tác vụ Frontend ưu tiên nào đang chạy hay không."""
        return self._fe_task_count > 0

    @property
    def is_current_task_frontend(self) -> bool:
        """True only inside the frontend task context, not merely in the process."""
        return self._frontend_context.get()

    @asynccontextmanager
    async def fe_priority_context(self, task_name: str = "Frontend User Action"):
        """Context Manager đánh dấu tác vụ ưu tiên cao từ Frontend."""
        token = self._frontend_context.set(True)
        async with self._lock:
            self._fe_task_count += 1
            if self._fe_task_count == 1:
                self._pause_background_event.clear()
                logger.info(f"[PriorityManager] ⚡ [{task_name}] FRONTEND PRIORITY ACQUIRED. Tạm dừng toàn bộ luồng BE chạy ngầm để ưu tiên người dùng...")

        try:
            yield
        finally:
            self._frontend_context.reset(token)
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

    async def run_blocking(
        self,
        func: Callable[..., T],
        *args: Any,
        worker_name: str = "Blocking Worker",
        **kwargs: Any,
    ) -> T:
        """Run blocking work without letting background saturation delay FE actions.

        Frontend work uses a dedicated executor. Background work cooperatively pauses
        before starting another blocking HTTP, AI, or storage operation.
        """
        is_frontend = self.is_current_task_frontend
        if not is_frontend:
            await self.yield_if_fe_active(worker_name)
        loop = asyncio.get_running_loop()
        executor = self._frontend_executor if is_frontend else None
        return await loop.run_in_executor(executor, partial(func, *args, **kwargs))


priority_coordinator = PriorityCoordinator()
