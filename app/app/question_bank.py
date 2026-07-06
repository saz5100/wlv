"""
Structured question bank for Care2Care past papers.
Each question has a type, marks, and the input format needed.
"""
import json

# ─── CARE/01 June 2024 — Computer Systems ──────────────────────────────

PAPER_CARE_01_JUN2024 = {
    "id": "j277-01-jun2024",
    "label": "CARE/01 June 2024",
    "paper": 1,
    "year": 2024,
    "month": "June",
    "total_marks": 80,
    "questions": [
        # Q1 — Number systems (pages 2-3)
        {
            "id": "p1q1a",
            "number": 1,
            "part": "a",
            "type": "table",
            "marks": 3,
            "question": "The following table has either the binary or denary value of 3 numbers. Complete the table by converting the 8-bit binary number into denary and the denary number into 8-bit binary.",
            "table": {
                "headers": ["8-bit Binary", "Denary"],
                "rows": [
                    {"cells": ["11110000", ""]},
                    {"cells": ["", "105"]},
                    {"cells": ["00011110", ""]},
                ]
            }
        },
        {
            "id": "p1q1b",
            "number": 1,
            "part": "b",
            "type": "table",
            "marks": 4,
            "question": "Complete the table by writing the answer to each statement.",
            "table": {
                "headers": ["Statement", "Answer"],
                "rows": [
                    {"cells": ["The smallest denary number that can be represented by a 4-bit binary number", ""]},
                    {"cells": ["The largest denary number that can be represented by a 6-bit binary number", ""]},
                    {"cells": ["The maximum number of different colours that can be represented with a colour depth of 7-bits", ""]},
                    {"cells": ["The minimum number of bits needed to represent 150 different characters in a character set", ""]},
                ]
            }
        },
        {
            "id": "p1q1c",
            "number": 1,
            "part": "c",
            "type": "short",
            "marks": 1,
            "question": "Show the result of a left binary shift of 4 places on the binary number 00001111."
        },
        {
            "id": "p1q1d",
            "number": 1,
            "part": "d",
            "type": "written",
            "marks": 2,
            "question": "Describe how to convert a 2-digit hexadecimal number into denary. Use an example in your answer."
        },
        # Q2 — Networks (pages 4-5)
        {
            "id": "p1q2ai",
            "number": 2,
            "part": "a(i)",
            "type": "short",
            "marks": 1,
            "question": "State what is meant by a MAC address."
        },
        {
            "id": "p1q2aii",
            "number": 2,
            "part": "a(ii)",
            "type": "written",
            "marks": 2,
            "question": "Describe the format of a MAC address."
        },
        {
            "id": "p1q2bi",
            "number": 2,
            "part": "b(i)",
            "type": "written",
            "marks": 2,
            "question": "Describe two benefits to the airport of using wired connections in their Local Area Network."
        },
        {
            "id": "p1q2bii",
            "number": 2,
            "part": "b(ii)",
            "type": "written",
            "marks": 2,
            "question": "The airport is planning to add a wireless network for passengers. Describe one benefit and one drawback of using wireless connections."
        },
        {
            "id": "p1q2ci",
            "number": 2,
            "part": "c(i)",
            "type": "diagram",
            "marks": 3,
            "question": "One office in the airport has five computers connected to one switch. There are two printers in the office that can be accessed by all computers. The computers are connected using a star topology. Draw a diagram to show how the five computers, switch and two printers are connected in a star topology.",
            "diagram_hint": "Describe your diagram or upload a photo/scan"
        },
        {
            "id": "p1q2cii",
            "number": 2,
            "part": "c(ii)",
            "type": "split",
            "marks": 2,
            "question": "Give one benefit and one drawback of the office using a star topology instead of a mesh topology.",
            "sub_fields": [
                {"label": "Benefit", "key": "benefit"},
                {"label": "Drawback", "key": "drawback"}
            ]
        },
        # Q3 — OS & Utility (page 6)
        {
            "id": "p1q3a",
            "number": 3,
            "part": "a",
            "type": "table",
            "marks": 4,
            "question": "The table contains operating system functions and a task that each function performs. Complete the table by writing the two missing function names and a task performed by the two given functions.",
            "table": {
                "headers": ["Function", "Task"],
                "rows": [
                    {"cells": ["", "Moves data from secondary storage to RAM"]},
                    {"cells": ["Peripheral management", ""]},
                    {"cells": ["", "Allows the user to create, name and delete folders"]},
                    {"cells": ["User interface", ""]},
                ]
            }
        },
        {
            "id": "p1q3b",
            "number": 3,
            "part": "b",
            "type": "written",
            "marks": 2,
            "question": "Complete the description of utility system software using the words provided in the box. Not all words are used.\n\nWords: access, amount, apart, compression, consecutive, defragmentation, deleted, encryption, key, lock, quantity, separate, speed, understood\n\n'...... software changes data using a ...... . If the data is intercepted, it cannot be ...... .'"
        },
        # Q4 — Open source vs proprietary (page 8)
        {
            "id": "p1q4",
            "number": 4,
            "part": "",
            "type": "extended",
            "marks": 8,
            "question": "A computer programmer has developed a computer game that they want to release for users to download over the internet. The programmer needs to decide whether to release the game as open source or proprietary software.\n\nDiscuss the features, benefits and drawbacks of each type of licence for this program and make a recommendation to the programmer.\n\nYou should include the following in your answer:\n• features of each licence\n• legal and ethical issues of each licence\n• benefits and drawbacks of each licence"
        },
        # Q5 — Sound & Storage (pages 10-11)
        {
            "id": "p1q5ai",
            "number": 5,
            "part": "a(i)",
            "type": "mcq",
            "marks": 1,
            "question": "Tick (✓) one box to identify the correct description of sound sampling.",
            "options": [
                "The frequency of the wave is measured a set number of times each second.",
                "The amplitude of the wave is measured at set intervals.",
                "The digital sound wave is measured a set number of times each second.",
                "The analogue sound wave's resolution is measured at set intervals."
            ]
        },
        {
            "id": "p1q5aii",
            "number": 5,
            "part": "a(ii)",
            "type": "written",
            "marks": 2,
            "question": "Explain how changing the bit depth will affect the sound file."
        },
        {
            "id": "p1q5aiii",
            "number": 5,
            "part": "a(iii)",
            "type": "mcq",
            "marks": 1,
            "question": "Tick (✓) one box to identify the smallest secondary storage capacity.",
            "options": [
                "2.1 GB",
                "300 MB",
                "200 000 KB",
                "0.0021 TB"
            ]
        },
        {
            "id": "p1q5aiv",
            "number": 5,
            "part": "a(iv)",
            "type": "calculation",
            "marks": 2,
            "question": "The musician's recordings have an average (mean) file size of 3 MB. The musician has 1000 recordings. Calculate an estimate of the storage space in GB that the 1000 files will require, assuming they are each 3 MB in size. Show your working out.",
            "sub_fields": [
                {"label": "Working", "key": "working", "type": "textarea"},
                {"label": "Answer (GB)", "key": "answer", "type": "text"}
            ]
        },
        # Q6 — CPU (page 12)
        {
            "id": "p1q6a",
            "number": 6,
            "part": "a",
            "type": "written",
            "marks": 2,
            "question": "Describe what happens during the fetch-execute cycle."
        },
        {
            "id": "p1q6b",
            "number": 6,
            "part": "b",
            "type": "table",
            "marks": 2,
            "question": "Complete the table by writing the name of two registers used in the fetch-execute cycle and describing the purpose of each.",
            "table": {
                "headers": ["Register", "Purpose"],
                "rows": [
                    {"cells": ["", ""]},
                    {"cells": ["", ""]},
                ]
            }
        },
        # Q7 — Embedded systems (page 13)
        {
            "id": "p1q7a",
            "number": 7,
            "part": "a",
            "type": "written",
            "marks": 2,
            "question": "A car has a 'Follow Me' system that uses a cruise control feature to allow the car to follow the car in front of it. It will keep the same speed and distance without the driver's intervention. The cruise control system is an example of an embedded system.\n\nExplain the reasons why the 'Follow Me' system is an example of an embedded system."
        },
    ]
}

# ─── All papers list ───────────────────────────────────────────────────

ALL_PAPERS = [
    # June series
    {"id": "j277-01-jun2022", "label": "CARE/01 June 2022", "paper": 1, "year": 2022, "month": "June", "active": True, "duration_minutes": 90},
    {"id": "j277-02-jun2022", "label": "CARE/02 June 2022", "paper": 2, "year": 2022, "month": "June", "active": True},
    {"id": "j277-01-jun2023", "label": "CARE/01 June 2023", "paper": 1, "year": 2023, "month": "June", "active": True},
    {"id": "j277-02-jun2023", "label": "CARE/02 June 2023", "paper": 2, "year": 2023, "month": "June", "active": True},
    {"id": "j277-01-jun2024", "label": "CARE/01 June 2024", "paper": 1, "year": 2024, "month": "June", "active": True},
    {"id": "j277-02-jun2024", "label": "CARE/02 June 2024", "paper": 2, "year": 2024, "month": "June", "active": True},
    {"id": "j277-01-jun2025", "label": "CARE/01 June 2025", "paper": 1, "year": 2025, "month": "June", "active": True},
    {"id": "j277-02-jun2025", "label": "CARE/02 June 2025", "paper": 2, "year": 2025, "month": "June", "active": True},
]

# ─── Paper lookup ──────────────────────────────────────────────────────

PAPER_QUESTIONS = {
    "j277-01-jun2024": PAPER_CARE_01_JUN2024,
}

def get_paper(paper_id):
    """Get paper metadata."""
    for p in ALL_PAPERS:
        if p["id"] == paper_id:
            return p
    return None

def get_paper_questions(paper_id):
    """Get structured questions for a paper, or None if not built yet."""
    return PAPER_QUESTIONS.get(paper_id)

def get_paper_json(paper_id):
    """Get paper data as JSON string."""
    paper = get_paper(paper_id)
    questions = get_paper_questions(paper_id)
    if not paper:
        return None
    return json.dumps({
        "paper": paper,
        "questions": questions["questions"] if questions else [],
        "total_marks": questions["total_marks"] if questions else 0,
    })
