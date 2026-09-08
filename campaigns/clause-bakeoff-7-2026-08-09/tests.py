import json
from pathlib import Path


def generate_tests():
    path = Path(__file__).with_name("tasks.jsonl")
    return [
        {
            "description": item["id"],
            "vars": {
                "task_id": item["id"],
                "task": item["prompt"],
                "must_cover": json.dumps(item["must_cover"]),
            },
        }
        for item in (json.loads(line) for line in path.read_text().splitlines())
        if item
    ]
