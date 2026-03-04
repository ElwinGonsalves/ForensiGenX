import json
import os

SAMPLE_DATA = [
    {
        "id": 1,
        "regions": [
            {
                "region_id": 101,
                "phrase": "A wooden chair is next to a desk near a window.",
                "image_id": 1
            },
            {
                "region_id": 102,
                "phrase": "A man sitting on a chair in a room.",
                "image_id": 1
            }
        ]
    },
    {
        "id": 2,
        "regions": [
            {
                "region_id": 201,
                "phrase": "A small dog sitting under a table near a window.",
                "image_id": 2
            },
            {
                "region_id": 202,
                "phrase": "A man standing beside a car.",
                "image_id": 2
            }
        ]
    },
    {
        "id": 3,
        "regions": [
            {
                "region_id": 301,
                "phrase": "A wooden chair next to a desk!!!   ",
                "image_id": 3
            }
        ]
    }
]

def generate_sample():
    os.makedirs("dataset", exist_ok=True)
    file_path = "dataset/region_descriptions.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(SAMPLE_DATA, f, indent=4)
    print(f"Sample data generated at {file_path}")

if __name__ == "__main__":
    generate_sample()
