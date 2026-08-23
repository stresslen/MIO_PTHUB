from types import SimpleNamespace

from app.config import settings
from app.services.google_sheets_service import (
    GoogleSheetsService,
    LEAD_HEADERS,
)


class FakeWorksheet:
    def __init__(self):
        self.headers = []
        self.appended = []

    def row_values(self, row):
        return self.headers if row == 1 else []

    def update(self, values, range_name):
        assert range_name == "A1"
        self.headers = values[0]

    def col_values(self, column):
        assert column == 1
        return ["id", "existing-id"]

    def append_rows(self, rows, value_input_option):
        assert value_input_option == "RAW"
        self.appended.extend(rows)


class FakeSpreadsheet:
    def __init__(self, worksheet):
        self.worksheet = worksheet
        self.requested_gid = None

    def get_worksheet_by_id(self, gid):
        self.requested_gid = gid
        return self.worksheet


class FakeQuery:
    def __init__(self, leads):
        self.leads = leads

    def order_by(self, *_args):
        return self

    def all(self):
        return self.leads


class FakeDb:
    def __init__(self, leads):
        self.leads = leads

    def query(self, _model):
        return FakeQuery(self.leads)


def make_lead(lead_id):
    values = {name: None for name in LEAD_HEADERS}
    values.update(id=lead_id, source="test", source_url="https://example.com", title="Lead")
    return SimpleNamespace(**values)


def test_sync_sqlite_targets_gid_zero_and_appends_only_missing(monkeypatch):
    monkeypatch.setattr(settings, "google_sheets_spreadsheet_id", "sheet-id")
    monkeypatch.setattr(settings, "google_service_account_json", "{}")
    monkeypatch.setattr(settings, "google_sheets_leads_worksheet", "gid:0")

    service = GoogleSheetsService()
    worksheet = FakeWorksheet()
    spreadsheet = FakeSpreadsheet(worksheet)
    monkeypatch.setattr(service, "connect", lambda: spreadsheet)

    synced = service.sync_sqlite(FakeDb([make_lead("existing-id"), make_lead("new-id")]))

    assert synced == 1
    assert spreadsheet.requested_gid == 0
    assert worksheet.headers == LEAD_HEADERS
    assert worksheet.appended[0][0] == "new-id"
