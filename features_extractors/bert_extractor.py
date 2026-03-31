import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
from sqlalchemy import select
from database import SessionLocal
from entities import JobsPost

MODEL_NAME = 'TechWolf/JobBERT-v3' 
OUTPUT_CSV = 'extracted_jobs_bert.csv'

def extract_jobs_to_csv():   

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, do_lower_case=False)
    model = AutoModelForTokenClassification.from_pretrained(MODEL_NAME)
    
    nlp_ner = pipeline("ner", model=model, tokenizer=tokenizer, aggregation_strategy="simple")

    db = SessionLocal()
    try:
        query = select(JobsPost)
        
        jobs = db.scalars(query).all()

        extracted_data = []

        for job in jobs:
            if not job.description:
                continue
            
            description_truncated = job.description[:1500] 
            
            entities = nlp_ner(description_truncated)
            
            features = {
                "id": job.id,
                "job_title": job.name,
                "hard_skills": [],
                "soft_skills": [],
                "nice_to_have": [],
                "salary": None,
                "contract_type": None,
            }

            for ent in entities:
                label = ent["entity_group"]
                word = ent["word"].strip()
                if "SKILL" in label:
                    features["hard_skills"].append(word)
                elif "SOFT" in label:
                    features["soft_skills"].append(word)
                elif "SALARY" in label:
                    features["salary"] = word

            features["hard_skills"] = ", ".join(list(set(features["hard_skills"])))
            features["soft_skills"] = ", ".join(list(set(features["soft_skills"])))
            
            extracted_data.append(features)
            
            if len(extracted_data) % 10 == 0:
                print(f"Processed {len(extracted_data)} jobs...")

        df = pd.DataFrame(extracted_data)
        df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')

    finally:
        db.close()