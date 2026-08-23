"""Transfer all local leads missing from the configured Google Sheet."""

from app.database import SessionLocal, init_db
from app.models.lead import Lead
from app.services.google_sheets_service import google_sheets_service


def main() -> int:
    init_db()
    if not google_sheets_service.configured:
        print("Google Sheets chưa sẵn sàng: cần GOOGLE_SERVICE_ACCOUNT_JSON.")
        return 2

    db = SessionLocal()
    try:
        local_count = db.query(Lead).count()
        synced = google_sheets_service.sync_sqlite(db)
        print(f"Đã kiểm tra {local_count} lead; chuyển thêm {synced} lead lên Google Sheets.")
        return 0
    except Exception as exc:
        print(f"Không thể chuyển dữ liệu: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
