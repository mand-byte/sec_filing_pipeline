from typing import Any

from src.models.filing import FilingDocument, FilingIndex


class FilingRepository:
    def __init__(self, session: Any) -> None:
        self.session = session
        self._get_add_mode = hasattr(self.session, "add") and hasattr(
            self.session, "get"
        )

    def _pending_row(
        self, model_cls: type[FilingIndex] | type[FilingDocument], identifier: str
    ) -> FilingIndex | FilingDocument | None:
        pending_rows = getattr(self.session, "new", None)
        if pending_rows is None:
            return None

        id_attr = "filing_id" if model_cls is FilingIndex else "document_id"
        for row in pending_rows:
            if isinstance(row, model_cls) and getattr(row, id_attr) == identifier:
                return row
        return None

    def add_filing_index_if_missing(self, row: FilingIndex) -> None:
        if self._get_add_mode:
            pending = self._pending_row(FilingIndex, row.filing_id)
            if pending is not None:
                return

            existing = self.session.get(FilingIndex, row.filing_id)
            if existing is not None:
                return
            self.session.add(row)
            return

        rows = getattr(self.session, "filing_indexes", [])
        for existing_row in rows:
            if existing_row.filing_id == row.filing_id:
                return
        rows.append(row)
        setattr(self.session, "filing_indexes", rows)

    def add_document_if_missing(self, row: FilingDocument) -> None:
        if self._get_add_mode:
            pending = self._pending_row(FilingDocument, row.document_id)
            if pending is not None:
                return

            existing = self.session.get(FilingDocument, row.document_id)
            if existing is not None:
                return
            self.session.add(row)
            return

        rows = getattr(self.session, "filing_documents", [])
        for existing_row in rows:
            if existing_row.document_id == row.document_id:
                return
        rows.append(row)
        setattr(self.session, "filing_documents", rows)