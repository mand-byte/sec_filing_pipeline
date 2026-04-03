from datetime import datetime, timezone

from src.storage.owner_discovery import DiscoveryCursor, discover_owner_filings


def test_discover_owner_filings_filters_out_seen_accessions() -> None:
    payload = {
        "filings": {
            "recent": {
                "form": ["4", "4/A", "5"],
                "accessionNumber": [
                    "0000320193-24-000012",
                    "0000320193-24-000011",
                    "0000320193-24-000010",
                ],
                "acceptanceDateTime": [
                    "2024-04-03T12:30:00Z",
                    "2024-04-02T12:30:00Z",
                    "2024-04-01T12:30:00Z",
                ],
                "primaryDocument": ["doc4.xml", "doc4a.xml", "doc5.xml"],
            }
        }
    }
    cursor = DiscoveryCursor(
        last_acceptance_datetime_utc=datetime(2024, 4, 2, 12, 30, tzinfo=timezone.utc),
        last_accession_no="0000320193-24-000011",
    )

    filings = discover_owner_filings(cik="0000320193", payload=payload, cursor=cursor)

    # Keeps the newer owner filing and drops both:
    # - same timestamp with accession <= cursor
    # - strictly earlier timestamp owner filing
    assert [item.accession_no for item in filings] == ["0000320193-24-000012"]


def test_discover_owner_filings_ignores_non_owner_forms() -> None:
    payload = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "accessionNumber": ["0000320193-24-000010"],
                "acceptanceDateTime": ["2024-04-01T12:30:00Z"],
                "primaryDocument": ["doc8k.htm"],
            }
        }
    }

    assert discover_owner_filings(cik="0000320193", payload=payload, cursor=None) == []


def test_discover_owner_filings_handles_uneven_sec_arrays() -> None:
    payload = {
        "filings": {
            "recent": {
                "form": ["4", "8-K"],
                "accessionNumber": ["0000320193-24-000012"],
                "acceptanceDateTime": ["2024-04-03T12:30:00Z"],
                "primaryDocument": ["doc4.xml", "doc8k.htm"],
            }
        }
    }

    filings = discover_owner_filings(cik="0000320193", payload=payload, cursor=None)

    assert [item.accession_no for item in filings] == ["0000320193-24-000012"]
