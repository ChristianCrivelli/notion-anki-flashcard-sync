"""Shared helpers for reading a Notion database through the Data Source API.

Both word_bank.py and clean_notion.py need to (1) resolve a database's
underlying data source and (2) page through every row in it. This module is
the single place that logic lives, so a future Notion API change only has to
be made once. (See issue #5.)
"""


def get_data_source_id(notion, db_id: str) -> str:
    """Retrieve the underlying Data Source ID for a database (Notion API 2025-09-03+)."""
    db_info = notion.databases.retrieve(database_id=db_id)
    return db_info["data_sources"][0]["id"]


def paginate_data_source(notion, data_source_id: str):
    """Yield every page (row) from a data source, handling pagination."""
    has_more = True
    start_cursor = None

    while has_more:
        response = notion.data_sources.query(
            data_source_id=data_source_id,
            start_cursor=start_cursor
        )
        for page in response.get("results", []):
            yield page
        has_more = response.get("has_more")
        start_cursor = response.get("next_cursor")