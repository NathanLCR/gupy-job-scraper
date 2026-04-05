import torch
from transformers import (
    AutoTokenizer,
    AutoModelForTokenClassification,
    TrainingArguments,
    Trainer,
    DataCollatorForTokenClassification,
)
from datasets import Dataset
import numpy as np
import evaluate
import json
import os

# 1. Configuration
MODEL_NAME = 'TechWolf/JobBERT-v3'
TRAIN_DATA_PATH = 'job_ner_train.json'
OUTPUT_DIR = './jobbertbr'

# Mapping
LABELS = [
    'O',
    'B-HARD_SKILL', 'I-HARD_SKILL',
    'B-SOFT_SKILL', 'I-SOFT_SKILL',
    'B-SALARY',     'I-SALARY',
    'B-NIVEL',      'I-NIVEL',
    'B-CONTRATO',   'I-CONTRATO'
]
label2id = {l: i for i, l in enumerate(LABELS)}
id2label = {i: l for i, l in enumerate(LABELS)}

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

def tokenize_and_align(examples):
    tokenized = tokenizer(
        examples["tokens"],
        truncation=True,
        max_length=512,
        is_split_into_words=True,
    )
    all_labels = []
    for i, labels in enumerate(examples["ner_tags"]):
        word_ids = tokenized.word_ids(batch_index=i)
        prev_id = None
        aligned = []
        for wid in word_ids:
            if wid is None:
                aligned.append(-100)
            elif wid != prev_id:
                aligned.append(label2id.get(labels[wid], 0))
            else:
                aligned.append(-100)
            prev_id = wid
        all_labels.append(aligned)
    tokenized["labels"] = all_labels
    return tokenized

def train():
    if not os.path.exists(TRAIN_DATA_PATH):
        print(f"Error: {TRAIN_DATA_PATH} not found. Run fine_tune_prep.py first.")
        return

    print("Loading dataset...")
    # Read the JSON file created by fine_tune_prep.py
    with open(TRAIN_DATA_PATH, 'r') as f:
        data = json.load(f)
    
    # 90/10 train/test split since we have 1735 examples
    n = len(data)
    train_data = data[:int(n*0.9)]
    test_data = data[int(n*0.9):]
    
    ds = {
        "train": Dataset.from_list(train_data),
        "test": Dataset.from_list(test_data),
    }

    tokenized_ds = {
        split: ds[split].map(tokenize_and_align, batched=True)
        for split in ds
    }

    print("Initializing model...")
    model = AutoModelForTokenClassification.from_pretrained(
        MODEL_NAME,
        num_labels=len(LABELS),
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True
    )

    # Use MPS acceleration on Mac if possible, else CPU
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(device)
    print(f"Using device: {device}")

    # Metrics computation logic
    seqeval = evaluate.load("seqeval")
    def compute_metrics(p):
        preds, labels = p
        preds = np.argmax(preds, axis=2)
        true_preds  = [[id2label[p] for p, l in zip(pred, label) if l != -100] for pred, label in zip(preds, labels)]
        true_labels = [[id2label[l] for p, l in zip(pred, label) if l != -100] for pred, label in zip(preds, labels)]
        r = seqeval.compute(predictions=true_preds, references=true_labels)
        return {"f1": r["overall_f1"], "precision": r["overall_precision"], "recall": r["overall_recall"]}

    args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=3,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=16,
        learning_rate=2e-5,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        push_to_hub=False,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=tokenized_ds["train"],
        eval_dataset=tokenized_ds["test"],
        # tokenizer=tokenizer,
        data_collator=DataCollatorForTokenClassification(tokenizer),
        compute_metrics=compute_metrics
    )

    print("Starting training...")
    trainer.train()
    
    # Save the final model
    trainer.save_model(OUTPUT_DIR + "-final")
    print(f"Extraction and Fine-tuning complete! Model saved to {OUTPUT_DIR}-final")

if __name__ == "__main__":
    train()
