import json
import os
import re
import spacy
from tqdm import tqdm

# Load the English NLP model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("Downloading English model for spaCy...")
    from spacy.cli import download
    download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# Abstract nouns to filter out
ABSTRACT_NOUNS = {
    "time", "day", "night", "morning", "evening", "part", "side", "area", "middle", 
    "center", "top", "bottom", "background", "foreground", "front", "back", "left", 
    "right", "way", "corner", "distance", "scene", "view", "reflection", "shadow"
}

# Relation patterns to look for
SPATIAL_RELATIONS = [
    "next to", "in front of", "on top of", "near", "on", "in", "under", "above", 
    "below", "beside", "behind", "over", "around", "inside", "outside", "between"
]

def clean_text(text):
    # Remove extra punctuation
    text = re.sub(r'[^\w\s\.-]', '', text)
    # Remove repeated spaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()

def extract_features(text):
    doc = nlp(text)
    
    objects = set()
    attributes = {}
    relations = []
    
    # 1. Extract Objects using noun chunks
    for chunk in doc.noun_chunks:
        # Get the main noun of the chunk
        main_noun = chunk.root.text
        
        # Filter abstract nouns and pronouns
        if main_noun not in ABSTRACT_NOUNS and chunk.root.pos_ != "PRON":
            objects.add(main_noun)
            
            # 2. Extract Attributes
            # Find adjectives modifying the main noun
            adjs = [token.text for token in chunk.root.children if token.pos_ == "ADJ"]
            if adjs:
                attributes[main_noun] = adjs
                
    objects = list(objects)
    
    # 3. Extract Relations
    relations = []
    
    text_lower = text.lower()
    
    # Sort objects by their position in text to easily find adjacent ones
    obj_spans = []
    for obj in objects:
        for match in re.finditer(rf"\b{re.escape(obj)}\b", text_lower):
            obj_spans.append({"obj": obj, "start": match.start(), "end": match.end()})
            
    obj_spans.sort(key=lambda x: x["start"])
    
    # Check adjacent pairs
    for i in range(len(obj_spans) - 1):
        span1 = obj_spans[i]
        span2 = obj_spans[i+1]
        
        between_text = text_lower[span1["end"]:span2["start"]].strip()
        for rel in SPATIAL_RELATIONS:
            if re.search(rf"\b{re.escape(rel)}\b", between_text):
                rel_formatted = rel.replace(" ", "_")
                relations.append(f"{span1['obj']} {rel_formatted} {span2['obj']}")
                break
                
    relations = list(set(relations))

    return {
        "objects": objects,
        "attributes": attributes,
        "relations": relations
    }

def main():
    dataset_path = "dataset/region_descriptions.json"
    
    if not os.path.exists(dataset_path):
        print(f"Error: {dataset_path} not found. Please run download_sample.py first.")
        return

    print("Loading dataset...")
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("Extracting subset and cleaning text...")
    
    sample_sentences = []
    cleaned_texts = []
    linguistic_features = []
    
    sentence_id = 1
    
    # Process regions
    for image_data in tqdm(data, desc="Processing Images"):
        for region in image_data.get("regions", []):
            phrase = region.get("phrase", "")
            if not phrase:
                continue
                
            # Clean text
            clean_phrase = clean_text(phrase)
            
            # Subsetting for team
            sample_sentence = {
                "id": sentence_id,
                "original_text": phrase,
                "clean_text": clean_phrase,
                "image_id": image_data.get("id"),
                "region_id": region.get("region_id")
            }
            sample_sentences.append(sample_sentence)
            cleaned_texts.append(f"{sentence_id}: {clean_phrase}")
            
            # Linguistic Analysis
            features = extract_features(clean_phrase)
            features["id"] = sentence_id
            features["sentence"] = clean_phrase
            
            linguistic_features.append(features)
            
            sentence_id += 1

    # Save Outputs
    print("Saving outputs...")
    
    with open("sample_sentences.json", "w", encoding="utf-8") as f:
        json.dump(sample_sentences, f, indent=4)
        print("-> Saved sample_sentences.json")
        
    with open("cleaned_text.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(cleaned_texts))
        print("-> Saved cleaned_text.txt")
        
    with open("linguistic_features.json", "w", encoding="utf-8") as f:
        json.dump(linguistic_features, f, indent=4)
        print("-> Saved linguistic_features.json")
        
    print("Pipeline completed successfully!")

if __name__ == "__main__":
    main()
