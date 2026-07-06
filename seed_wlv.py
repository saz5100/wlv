"""
Seed content for WLV English Equivalency - English
Creates topics, lessons, and quiz questions for the WLV platform.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from database import execute, query

TOPICS = [
    {"code": "reading", "title": "Reading Comprehension", "description": "Analyse language, structure, and meaning in fiction extracts", "sort_order": 1, "component": 1},
    {"code": "writing", "title": "Creative Writing", "description": "Develop descriptive and narrative writing skills", "sort_order": 2, "component": 1},
    {"code": "spag", "title": "SPaG", "description": "Spelling, punctuation, and grammar for academic writing", "sort_order": 3, "component": 1},
]

LESSONS = [
    {"topic": "reading", "title": "Language Analysis", "content": "Learn how to identify and analyse language techniques in fiction extracts, including imagery, figurative language, and word choice.", "sort_order": 1},
    {"topic": "reading", "title": "Structure Analysis", "content": "Understand how writers structure texts to engage readers, including openings, shifts in focus, and narrative pacing.", "sort_order": 2},
    {"topic": "reading", "title": "Evaluating a Text", "content": "Develop skills to evaluate and critically assess a writer's choices and their effectiveness.", "sort_order": 3},
    {"topic": "reading", "title": "Comparing Texts", "content": "Learn to compare how different writers approach similar themes and topics.", "sort_order": 4},
    {"topic": "reading", "title": "Inference and Deduction", "content": "Practice reading between the lines to understand implicit meaning and subtext.", "sort_order": 5},
    {"topic": "reading", "title": "Summarising", "content": "Develop concise summarisation skills for key ideas and themes in a text.", "sort_order": 6},
    {"topic": "reading", "title": "Context and Purpose", "content": "Understand how context and authorial purpose shape the content and style of a text.", "sort_order": 7},
    {"topic": "writing", "title": "Descriptive Writing", "content": "Master the art of vivid description using sensory details, figurative language, and varied sentence structures.", "sort_order": 1},
    {"topic": "writing", "title": "Narrative Structure", "content": "Learn to structure a story with effective openings, character development, and satisfying resolutions.", "sort_order": 2},
    {"topic": "writing", "title": "Character and Voice", "content": "Develop techniques for creating believable characters with distinct voices and perspectives.", "sort_order": 3},
    {"topic": "writing", "title": "Setting and Atmosphere", "content": "Learn to establish setting and create atmosphere through careful word choice and sensory imagery.", "sort_order": 4},
    {"topic": "writing", "title": "Dialogue", "content": "Practice writing effective dialogue that reveals character and advances the plot.", "sort_order": 5},
    {"topic": "writing", "title": "Pacing and Tension", "content": "Learn to control pacing and build tension through sentence structure and strategic revelation.", "sort_order": 6},
    {"topic": "writing", "title": "Editing and Redrafting", "content": "Develop skills to critically review and improve your own writing.", "sort_order": 7},
    {"topic": "spag", "title": "Punctuation", "content": "Master the full range of punctuation marks and their correct usage in academic writing.", "sort_order": 1},
    {"topic": "spag", "title": "Grammar", "content": "Understand key grammatical concepts including sentence types, clauses, and verb tenses.", "sort_order": 2},
    {"topic": "spag", "title": "Spelling Strategies", "content": "Learn effective strategies for improving spelling accuracy in your writing.", "sort_order": 3},
    {"topic": "spag", "title": "Sentence Structure", "content": "Develop variety in sentence construction for clearer, more engaging writing.", "sort_order": 4},
    {"topic": "spag", "title": "Paragraphing", "content": "Learn to structure paragraphs effectively for coherence and logical flow.", "sort_order": 5},
    {"topic": "spag", "title": "Register and Tone", "content": "Understand how to match register and tone to audience, purpose, and form.", "sort_order": 6},
    {"topic": "spag", "title": "Proofreading", "content": "Develop systematic proofreading techniques to catch common errors.", "sort_order": 7},
]

QUESTIONS = [
    {"q": "What is a simile?", "opts": ["A comparison using 'like' or 'as'", "A comparison saying something is something else", "Exaggeration for effect", "Giving human qualities to objects"], "ci": 0, "exp": "A simile compares two things using 'like' or 'as', e.g. 'as brave as a lion'.", "diff": 1},
    {"q": "What is personification?", "opts": ["A comparison using 'like' or 'as'", "Giving human qualities to non-human things", "Exaggeration for effect", "A repeated consonant sound"], "ci": 1, "exp": "Personification gives human qualities to objects or ideas, e.g. 'the wind whispered'.", "diff": 1},
    {"q": "What effect do short sentences typically create?", "opts": ["A sense of calm", "Tension or urgency", "Confusion", "Formality"], "ci": 1, "exp": "Short sentences create tension, urgency, or impact by breaking the rhythm of longer sentences.", "diff": 2},
    {"q": "What is pathetic fallacy?", "opts": ["A logical fallacy", "Weather reflecting mood", "A type of rhyme", "An unreliable narrator"], "ci": 1, "exp": "Pathetic fallacy is when the weather or environment mirrors the emotional mood of a scene.", "diff": 2},
    {"q": "What does 'semantic field' mean?", "opts": ["A type of farming", "A group of related words", "A grammatical rule", "A narrative technique"], "ci": 1, "exp": "A semantic field is a group of words related by meaning, e.g. words of violence or nature.", "diff": 3},
    {"q": "What is the purpose of sensory imagery?", "opts": ["To confuse the reader", "To engage the reader's senses", "To shorten the text", "To add humour"], "ci": 1, "exp": "Sensory imagery engages the reader's senses (sight, sound, touch, taste, smell) to create vivid scenes.", "diff": 1},
    {"q": "What is a metaphor?", "opts": ["A comparison using 'like' or 'as'", "A comparison saying something IS something else", "A repeated sound", "An exaggerated statement"], "ci": 1, "exp": "A metaphor directly states that one thing is another, e.g. 'the classroom was a zoo'.", "diff": 1},
    {"q": "What is alliteration?", "opts": ["Repeated vowel sounds", "Repeated consonant sounds at word starts", "Words that sound like their meaning", "A type of rhyme"], "ci": 1, "exp": "Alliteration is the repetition of the same consonant sound at the start of nearby words.", "diff": 1},
]

def seed():
    # Create topics
    for t in TOPICS:
        execute(
            "INSERT INTO topics (code, title, description, sort_order, component) VALUES (%s, %s, %s, %s, %s) ON CONFLICT(code) DO NOTHING",
            (t["code"], t["title"], t["description"], t["sort_order"], t["component"])
        )
    
    # Create lessons
    for l in LESSONS:
        execute(
            "INSERT INTO lessons (topic_code, title, content, sort_order) VALUES (%s, %s, %s, %s)",
            (l["topic"], l["title"], l["content"], l["sort_order"])
        )
    
    # Get lesson IDs
    rows = query("SELECT id FROM lessons ORDER BY id")
    lesson_ids = [r["id"] for r in rows]
    
    # Create questions for each lesson
    for lid in lesson_ids:
        for i, q in enumerate(QUESTIONS):
            execute(
                "INSERT INTO quiz_questions (lesson_id, question, options, correct_index, explanation, difficulty, question_type) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (lid, q["q"], json.dumps(q["opts"]), q["ci"], q["exp"], q["diff"], "mcq")
            )
    
    print(f"Seeded {len(TOPICS)} topics, {len(LESSONS)} lessons, {len(lesson_ids) * len(QUESTIONS)} questions")

if __name__ == "__main__":
    seed()
