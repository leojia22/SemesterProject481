import json
import csv
import sys

def split_json_entries(filepath):
    with open(filepath, 'r') as f:
        raw = f.read().strip()
    
    # Strip outer quote characters if the whole thing is a quoted string
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    
    # Unescape the backslash-escaped quotes
    raw = raw.replace('\\"', '"')
    
    # Now parse as a JSON array
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        return

    if not records:
        print("No records parsed.")
        return

    fieldnames = list(records[0].keys())

    with open(filepath, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)

    print(f"Done: {len(records)} records written to {filepath}")

if __name__ == '__main__':
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'input.csv'
    split_json_entries(filepath)