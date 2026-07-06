CREATE TABLE IF NOT EXISTS mark_schemes (
    id SERIAL PRIMARY KEY,
    topic VARCHAR(50) NOT NULL,
    marks INTEGER DEFAULT 6,
    question TEXT NOT NULL,
    mark_scheme TEXT,
    model_answer TEXT,
    key_terms TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO mark_schemes (topic, marks, question, mark_scheme, model_answer, key_terms) VALUES
('Reading Comprehension', 6, 'Explain how the writer uses language to create a sense of tension in the extract.',
'1 mark per technique identified and analysed. Max 6 marks.',
'The writer creates tension through several language techniques. Short, staccato sentences create urgency. Sensory language builds atmosphere. Pathetic fallacy reinforces mood. Rhetorical questions share uncertainty. Gradual pace of revelation maintains suspense. Semantic field of danger sustains tension.',
'language techniques, short sentences, sensory imagery, pathetic fallacy, rhetorical questions, semantic field'),

('Reading Comprehension', 6, 'Analyse how the structure of the extract engages the reader.',
'1 mark per structural feature identified and analysed. Max 6 marks.',
'The structure engages through several features. Opening in medias res creates intrigue. Cyclical structure provides closure. Shift from external to internal builds connection. Varying pacing controls tension. Strategic cliffhangers encourage continuation. Flashback or foreshadowing adds depth.',
'structural features, in medias res, cyclical structure, shift in focus, pacing, cliffhanger'),

('Creative Writing', 6, 'Describe how to structure a piece of descriptive writing for maximum impact.',
'1 mark per structural element explained. Max 6 marks.',
'Effective descriptive writing follows a clear structure. Begin with a striking opening image. Use logical sensory progression. Vary sentence lengths. Incorporate figurative language. Maintain consistent tone. End with a powerful closing image.',
'descriptive writing, opening image, sensory progression, sentence variety, figurative language, closing image'),

('Creative Writing', 6, 'Explain the key features of effective narrative writing.',
'1 mark per feature explained. Max 6 marks.',
'Effective narrative writing combines several features. Clear plot structure with beginning, middle, end. Well-developed characters with distinct voices. Consistent narrative voice. Effective dialogue. Clearly established setting. Central theme giving meaning.',
'narrative writing, plot structure, character development, narrative voice, dialogue, setting'),

('SPaG', 6, 'Explain the correct use of commas in complex sentences.',
'1 mark per rule explained with example. Max 6 marks.',
'Commas serve several functions. They separate items in a list. They set off introductory phrases. They surround non-essential information. They separate independent clauses with conjunctions. They clarify meaning and prevent ambiguity. They set off direct speech.',
'commas, lists, introductory phrases, parenthetical information, coordinating conjunctions, direct speech'),

('SPaG', 6, 'Describe the difference between active and passive voice and when to use each.',
'1 mark per point explained. Max 6 marks.',
'Active voice has the subject performing the action. Passive voice has the subject receiving the action. Use active for clarity and energy. Use passive to emphasise the recipient or when the agent is unknown. Overuse of passive makes writing weak.',
'active voice, passive voice, subject performs action, subject receives action, clarity, formal writing')
ON CONFLICT DO NOTHING;
