"""
Question loader for WLV English Equivalency - English
Reads from questions_data.json
"""
import json, os
from database import query, query_one, execute

DATA_FILE = os.path.join(os.path.dirname(__file__), "questions_data.json")

QUESTIONS = []

def main():
    print(f"Seeding questions for WLV English Equivalency - English...")
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        questions = json.load(f)
    for q in questions:
        execute("INSERT INTO questions (question, answer, subject) VALUES (?, ?, ?)",
               (q["question"], q["answer"], q["subject"]))
    print(f"  {len(questions)} questions seeded")

if __name__ == "__main__":
    main()
