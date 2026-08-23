from types import SimpleNamespace

from app.config import settings
from app.services.google_sheets_service import (
    GoogleSheetsService,
    LEAD_HEADERS,
)


class FakeWorksheet:
    def __init__(self):
        self.id = 0
        self.headers = []
        self.appended = []
        self.formatted = []

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

    def format(self, cell_range, cell_format):
        self.formatted.append((cell_range, cell_format))


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

    new_lead = make_lead("new-id")
    new_lead.contact_phone = 826891248
    synced = service.sync_sqlite(FakeDb([make_lead("existing-id"), new_lead]))

    assert synced == 1
    assert spreadsheet.requested_gid == 0
    assert worksheet.headers == LEAD_HEADERS
    assert worksheet.appended[0][0] == "new-id"
    assert worksheet.appended[0][LEAD_HEADERS.index("contact_phone")] == "0826891248"
    assert worksheet.formatted == [("P2:P", {"numberFormat": {"type": "TEXT"}})]
