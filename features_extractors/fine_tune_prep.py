import pandas as pd
import json
import re

# 1. Configuration
INPUT_CSV = 'extracted_jobs_llm.csv'
OUTPUT_JSON = 'job_ner_train.json'

# Labels map
LABELS = [
    'O',
    'B-HARD_SKILL', 'I-HARD_SKILL',
    'B-SOFT_SKILL', 'I-SOFT_SKILL',
    'B-SALARY',     'I-SALARY',
    'B-NIVEL',      'I-NIVEL',
    'B-CONTRATO',   'I-CONTRATO'
]

def tag_spans(text, spans):
    tokens = str(text).split()
    tags = ['O'] * len(tokens)
    
    for span_text, label in spans:
        if not span_text or pd.isna(span_text) or str(span_text).lower() == "não informado": 
            continue
        
        span_tokens = str(span_text).split()
        n = len(span_tokens)
        if n == 0: continue
        
        for i in range(len(tokens) - n + 1):
            if [t.lower() for t in tokens[i:i+n]] == [t.lower() for t in span_tokens]:
                tags[i] = f'B-{label}'
                for j in range(1, n):
                    tags[i+j] = f'I-{label}'
    return tokens, tags

def prepare_dataset():
    print(f"Loading labels from {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV)
    
    records = []
    
    for idx, row in df.iterrows():
        desc = row.get('description')
        if not desc or pd.isna(desc):
            continue
        
        job_id = row.get('id')
        spans = []
        
        h_skills = str(row.get('hard_skills', ''))
        if h_skills and h_skills.lower() != "nan":
            for skill in h_skills.split(','):
                spans.append((skill.strip(), 'HARD_SKILL'))
            
        s_skills = str(row.get('soft_skills', ''))
        if s_skills and s_skills.lower() != "nan":
            for skill in s_skills.split(','):
                spans.append((skill.strip(), 'SOFT_SKILL'))
            
        if pd.notna(row.get('salary')) and str(row['salary']).lower() != "não informado":
            spans.append((str(row['salary']).strip(), 'SALARY'))
        if pd.notna(row.get('level')) and str(row['level']).lower() != "não informado":
            spans.append((str(row['level']).strip(), 'NIVEL'))
        if pd.notna(row.get('contract_type')) and str(row['contract_type']).lower() != "não informado":
            spans.append((str(row['contract_type']).strip(), 'CONTRATO'))
            
        tokens, tags = tag_spans(desc, spans)
        
        if any(t != 'O' for t in tags):
            records.append({
                "id": str(job_id),
                "tokens": tokens,
                "ner_tags": tags
            })
        
        if len(records) % 100 == 0:
            print(f"Processed {len(records)} examples...")

    print(f"Generated {len(records)} tagged examples.")
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    prepare_dataset()
