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


def clear_database():
    data_source_id = get_data_source_id(notion, db_id)

    deleted_count = 0
    print("Fetching and deleting rows... This might take a moment depending on the size.")

    for page in paginate_data_source(notion, data_source_id):
        notion.pages.update(page_id=page["id"], archived=True)
        deleted_count += 1

    print(f"Successfully cleared {deleted_count} words from the database!")