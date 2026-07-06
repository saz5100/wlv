#!/usr/bin/env python3
"""
Enrich WLV English Equivalency LLM wiki with:
1. Golden Words (key terminology per topic)
2. Causal links (technique → effect → reader response chains)
3. AO tagging (which Assessment Objectives each file supports)

WLV AOs:
- AO1: Knowledge of language/structural techniques and SPaG rules
- AO2: Analysis of how writers use language/structure for effect
- AO3: Context and comparison (limited in WLV)
- AO5: Content and organisation in writing
- AO6: Technical accuracy (SPaG)
"""

import os
import re
import json

WIKI_DIR = "/root/wlv-lxc/llm-wiki"

# ─── Golden Words by topic area ──────────────────────────────────────────

GOLDEN_WORDS = {
    "language": [
        "simile", "metaphor", "personification", "pathetic fallacy",
        "alliteration", "sibilance", "onomatopoeia", "semantic field",
        "imagery", "connotation", "diction", "juxtaposition",
        "oxymoron", "hyperbole", "euphemism", "colloquial",
        "imperative", "interrogative", "declarative", "exclamative",
        "noun", "verb", "adjective", "adverb", "pronoun", "preposition",
        "conjunction", "determiner", "article", "modifier",
        "denotation", "connotation", "register", "tone",
        "figurative", "literal", "sensory language", "motif"
    ],
    "structure": [
        "focus", "shift", "perspective", "narrative voice",
        "first person", "third person", "omniscient", "limited",
        "chronological", "non-linear", "flashback", "foreshadowing",
        "pace", "rhythm", "tension", "climax", "resolution",
        "exposition", "rising action", "denouement",
        "paragraph", "sentence length", "sentence type",
        "repetition", "parallelism", "listing", "cumulative",
        "zoom", "pan", "close-up", "wide shot", "establishing shot",
        "in medias res", "circular structure", "cyclical",
        "time shift", "temporal marker", "ellipsis of time"
    ],
    "spag": [
        "apostrophe", "possession", "contraction",
        "comma splice", "sentence demarcation",
        "colon", "semicolon", "dash", "hyphen", "bracket",
        "capital letter", "full stop", "question mark",
        "exclamation mark", "quotation mark", "ellipsis",
        "subject-verb agreement", "tense consistency",
        "spelling", "homophone", "its/it's", "your/you're",
        "there/their/they're", "affect/effect",
        "paragraph", "cohesion", "coherence",
        "discourse marker", "connective", "conjunction"
    ],
    "writing": [
        "audience", "purpose", "form", "genre",
        "register", "tone", "voice", "style",
        "description", "narration", "dialogue",
        "sensory detail", "imagery", "atmosphere",
        "character", "setting", "plot", "theme",
        "show don't tell", "pace", "variety",
        "ambitious vocabulary", "precise language",
        "paragraph structure", "opening", "ending",
        "PEEL", "PEEZL", "point", "evidence", "explanation", "link"
    ],
    "exam": [
        "WLV English Equivalency", "AQA Paper 1", "Q1", "Q2", "Q3", "Q5",
        "retrieval", "language analysis", "structural analysis",
        "creative writing", "descriptive writing",
        "mark scheme", "level of response", "indicative standard",
        "AO1", "AO2", "AO3", "AO5", "AO6",
        "SPaG weighting", "time management", "extract",
        "single source", "fixed prompt", "2-hour assessment",
        "4 marks", "8 marks", "25 marks"
    ]
}

# ─── Causal link templates ──────────────────────────────────────────────

CAUSAL_TEMPLATES = {
    "language": [
        "The writer's use of {technique} creates {effect}, which causes the reader to {reader_response}.",
        "By employing {technique}, the writer establishes {effect}, leading the reader to {reader_response}.",
        "{technique} is used to convey {effect}, which in turn makes the reader {reader_response}.",
        "The choice of {technique} produces {effect}, thereby causing the reader to {reader_response}."
    ],
    "structure": [
        "The structural shift from {technique} creates {effect}, which causes the reader to {reader_response}.",
        "By using {technique}, the writer establishes {effect}, leading the reader to {reader_response}.",
        "The {technique} at this point in the text creates {effect}, which makes the reader {reader_response}.",
        "The writer's decision to {technique} produces {effect}, thereby causing the reader to {reader_response}."
    ],
    "spag": [
        "Correct use of {technique} ensures {effect}, which helps the reader to {reader_response}.",
        "Errors in {technique} cause {effect}, leading the reader to {reader_response}.",
        "Mastery of {technique} creates {effect}, which enables the reader to {reader_response}."
    ],
    "writing": [
        "The writer's choice of {technique} achieves {effect}, which causes the reader to {reader_response}.",
        "By using {technique}, the writer creates {effect}, leading the reader to {reader_response}.",
        "{technique} is employed to produce {effect}, which makes the reader {reader_response}."
    ]
}

# ─── AO mapping by topic ────────────────────────────────────────────────

AO_MAP = {
    "language": ["AO1", "AO2"],
    "structure": ["AO1", "AO2"],
    "spag": ["AO1", "AO6"],
    "writing": ["AO5", "AO6"],
    "exam": ["AO1", "AO2", "AO5"],
    "entity": ["AO1", "AO3"],
    "source": ["AO1", "AO3"],
    "reading": ["AO1", "AO2"],
    "past-papers": ["AO1", "AO2", "AO5"],
    "assessment": ["AO1", "AO2", "AO5", "AO6"],
    "overview": ["AO1"],
    "model-answer": ["AO1", "AO2", "AO5", "AO6"],
    "log": ["AO1"],
    "ebook": ["AO1", "AO2", "AO5"],
    "writing-guide": ["AO5", "AO6"],
    "spag-reference": ["AO1", "AO6"],
    "guide": ["AO1", "AO2"],
    "default": ["AO1", "AO2"]
}

# ─── Topic detection from file path and content ────────────────────────

def detect_topic(filepath, content):
    """Detect the primary topic area from file path and content."""
    path_lower = filepath.lower()
    
    if "/concepts/" in path_lower:
        name = os.path.basename(filepath).lower()
        if any(w in name for w in ["spag", "apostrophe", "comma", "colon", "semicolon", "punctuation", "spelling", "grammar", "homophone", "capitalisation"]):
            return "spag"
        if any(w in name for w in ["structur", "narrative", "opening", "shift", "focus", "tension", "pace", "chronolog", "flashback", "foreshadow"]):
            return "structure"
        if any(w in name for w in ["writing", "creative", "descriptive", "ao5", "content-organisation"]):
            return "writing"
        if any(w in name for w in ["exam", "timing", "marking", "level", "assessment-objective", "aqa-gcse", "wlv-vs-aqa", "indicative"]):
            return "exam"
        if any(w in name for w in ["language", "technique", "glossary", "simile", "metaphor", "connotation", "figurative", "word-level", "sentence", "inference", "reiteration"]):
            return "language"
        return "language"  # default for concepts
    
    if "/entities/" in path_lower:
        return "entity"
    if "/sources/" in path_lower:
        return "source"
    if "/spag" in path_lower:
        return "spag"
    if "/writing" in path_lower:
        return "writing"
    if "/reading" in path_lower:
        return "reading"
    if "/past-papers" in path_lower:
        return "past-papers"
    if "/assessments" in path_lower:
        return "assessment"
    if "/queries/" in path_lower:
        return "exam"
    
    # Root-level files
    name = os.path.basename(filepath).lower()
    if name.startswith("q1") or name.startswith("q2") or name.startswith("q3") or name.startswith("q5"):
        return "model-answer"
    if "spag" in name:
        return "spag"
    if "writing" in name or "creative" in name or "descriptive" in name:
        return "writing"
    if "exam" in name or "timing" in name or "strategy" in name:
        return "exam"
    if "overview" in name or "wlv-english-equivalency" in name:
        return "overview"
    if "ebook" in name:
        return "ebook"
    if "log" in name:
        return "log"
    if "common-mistakes" in name:
        return "spag"
    if "index" in name:
        return "overview"
    
    return "default"


def generate_golden_words(topic, content):
    """Select relevant Golden Words for this file based on content matching."""
    words = GOLDEN_WORDS.get(topic, [])
    if not words:
        words = GOLDEN_WORDS.get("language", [])
    
    # Score words by presence in content
    content_lower = content.lower()
    scored = []
    for w in words:
        count = content_lower.count(w.lower())
        if count > 0:
            scored.append((count, w))
    
    scored.sort(reverse=True)
    # Return top 12-15 words that actually appear
    return [w for _, w in scored[:15]]


def generate_causal_links(topic, content):
    """Generate causal link examples relevant to this file's content."""
    templates = CAUSAL_TEMPLATES.get(topic, CAUSAL_TEMPLATES.get("language", []))
    
    # Extract key techniques mentioned in the content
    content_lower = content.lower()
    techniques = []
    
    # Common techniques to look for
    tech_list = {
        "language": ["simile", "metaphor", "personification", "alliteration", "sibilance", 
                     "onomatopoeia", "imagery", "juxtaposition", "oxymoron", "hyperbole",
                     "repetition", "listing", "rhetorical question", "pathetic fallacy",
                     "semantic field", "colloquial language", "imperative verb"],
        "structure": ["flashback", "foreshadowing", "shift in focus", "time shift",
                      "circular structure", "in medias res", "cliffhanger", "zoom",
                      "paragraph break", "sentence length", "narrative perspective",
                      "cyclical structure", "temporal marker", "ellipsis of time"],
        "spag": ["comma splice", "apostrophe of possession", "semicolon", "colon", "dash",
                 "capital letter", "full stop", "paragraph", "tense consistency",
                 "subject-verb agreement", "sentence demarcation"],
        "writing": ["sensory detail", "dialogue", "description", "narrative voice",
                    "show don't tell", "ambitious vocabulary", "varied sentences",
                    "figurative language", "structural features", "discourse markers"]
    }
    
    all_techs = tech_list.get(topic, []) + tech_list.get("language", [])
    for t in all_techs:
        if t in content_lower:
            techniques.append(t)
    
    if not techniques:
        techniques = ["language features", "structural choices", "writing techniques"]
    
    # Extract context-specific effects and responses from the content
    effects = []
    for word in ["tension", "atmosphere", "suspense", "empathy", "contrast", "emphasis",
                 "clarity", "urgency", "intimacy", "mood", "sympathy", "drama",
                 "immediacy", "pace", "rhythm", "cohesion", "coherence"]:
        if word in content_lower:
            effects.append(word)
    if not effects:
        effects = ["tension", "atmosphere", "emphasis"]
    
    responses = []
    for phrase in ["reader", "sympathise", "visualise", "engage", "anticipate",
                   "question", "imagine", "understand", "feel", "share"]:
        if phrase in content_lower:
            responses.append(phrase)
    if not responses:
        responses = ["engage with the text", "understand the writer's intention"]
    
    # Build response phrases
    response_map = {
        "reader": "engage with the text",
        "sympathise": "sympathise with the character",
        "visualise": "visualise the scene",
        "engage": "feel engaged",
        "anticipate": "anticipate what happens next",
        "question": "question the narrator's reliability",
        "imagine": "imagine the setting",
        "understand": "understand the writer's purpose",
        "feel": "share the character's emotions",
        "share": "share the character's perspective"
    }
    
    links = []
    for i, tech in enumerate(techniques[:3]):
        template = templates[i % len(templates)]
        effect = effects[i % len(effects)]
        resp = responses[i % len(responses)]
        resp_phrase = response_map.get(resp, "the reader to engage with the text")
        links.append(template.format(technique=tech, effect=effect, reader_response=resp_phrase))
    
    return links


def enrich_file(filepath):
    """Add enrichment fields to a single markdown file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check it has YAML frontmatter
    if not content.startswith('---'):
        return False
    
    # Split frontmatter from body
    parts = content.split('---', 2)
    if len(parts) < 3:
        return False
    
    frontmatter = parts[1]
    body = parts[2]
    
    topic = detect_topic(filepath, body)
    golden_words = generate_golden_words(topic, body)
    causal_links = generate_causal_links(topic, body)
    aos = AO_MAP.get(topic, AO_MAP["default"])
    
    # Build enrichment YAML block
    enrichment = "\n\n# ─── Enrichment ──────────────────────────────────────────\n"
    enrichment += f"# Golden Words: {', '.join(golden_words)}\n"
    enrichment += f"# Assessment Objectives: {', '.join(aos)}\n"
    enrichment += "# Causal Links:\n"
    for link in causal_links:
        enrichment += f"# - {link}\n"
    
    # Write back
    new_content = f"---{frontmatter}---{body}{enrichment}"
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    return True


def main():
    files = []
    for root, dirs, filenames in os.walk(WIKI_DIR):
        for f in filenames:
            if f.endswith('.md'):
                files.append(os.path.join(root, f))
    
    files.sort()
    enriched = 0
    skipped = 0
    
    for f in files:
        if enrich_file(f):
            enriched += 1
        else:
            skipped += 1
    
    print(f"Enriched: {enriched} files")
    print(f"Skipped: {skipped} files")
    print(f"Total: {enriched + skipped} files")
    
    # Summary by topic
    topics = {}
    for f in files:
        with open(f, 'r', encoding='utf-8') as fh:
            content = fh.read()
        topic = detect_topic(f, content)
        topics[topic] = topics.get(topic, 0) + 1
    
    print("\nBy topic:")
    for t, c in sorted(topics.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")


if __name__ == "__main__":
    main()
