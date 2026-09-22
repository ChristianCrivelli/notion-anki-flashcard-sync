import os
from dotenv import load_dotenv
from notion_client import Client
from notion_utils import get_data_source_id, paginate_data_source

load_dotenv()

notion_key = os.getenv("notion_key")
db_id = os.getenv("database")

if not notion_key:
    raise RuntimeError("Missing 'notion_key' in .env")
if not db_id:
    raise RuntimeError("Missing 'database' in .env")

notion = Client(auth=notion_key)

def get_words() -> list[tuple[str, str]]:
    """
    Returns a list of (page_id, word) tuples from the Notion database.
    page_id is needed later to archive the entry once processed.
    """
    data_source_id = get_data_source_id(notion, db_id)

    words = []
    for page in paginate_data_source(notion, data_source_id):
        props = page["properties"]
        title_key = next(k for k, v in props.items() if v['type'] == 'title')
        title_parts = props[title_key]["title"]
        if title_parts:
            word = title_parts[0]["plain_text"].strip()
            if word:
                words.append((page["id"], word))

    return words