"""
Seed content loader for WLV English Equivalency - English
Reads from seed_data.json
"""
import json, os
from database import query, query_one, execute

DATA_FILE = os.path.join(os.path.dirname(__file__), "seed_data.json")

def main():
    print(f"Seeding WLV English Equivalency - English content...")
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        lessons = json.load(f)
    for lesson in lessons:
        execute("INSERT INTO lessons (title, content, subject) VALUES (?, ?, ?)",
               (lesson["title"], lesson["content"], lesson["subject"]))
    print(f"  {len(lessons)} lessons seeded")

if __name__ == "__main__":
    main()
