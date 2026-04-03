import clickhouse_connect
from src.core.config import settings

def get_clickhouse_client():
    client = clickhouse_connect.get_client(
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        username=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DB
    )
    return client

def fetch_active_ciks() -> list[str]:
    """Fetches unique valid CIKs from the active stock universe."""
    client = get_clickhouse_client()
    query = """
        SELECT DISTINCT cik 
        FROM us_stock_universe 
        WHERE active = 1 AND cik IS NOT NULL AND cik != ''
    """
    result = client.query(query)
    # result.result_rows is a list of tuples like [('000101',), ...]
    return [str(row[0]) for row in result.result_rows if row[0]]
