import argparse
import random
import string
import json
import requests
import sys

def generate_key():
    parts = []
    for _ in range(4):
        parts.append(''.join(random.choices(string.ascii_uppercase + string.digits, k=4)))
    return '-'.join(parts)

def load_config():
    try:
        with open("firebase_config.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("ERROR: firebase_config.json not found!")
        print("Please configure your Firebase Database URL and Secret.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="INDRA License Generator (Firebase)")
    parser.add_argument("-n", "--number", type=int, default=1, help="Number of keys to generate")
    args = parser.parse_args()

    config = load_config()
    db_url = config.get("FIREBASE_DATABASE_URL", "").rstrip("/")
    secret = config.get("FIREBASE_SECRET", "")
    
    if not db_url or "YOUR-PROJECT-ID" in db_url:
        print("ERROR: You must configure FIREBASE_DATABASE_URL in firebase_config.json")
        sys.exit(1)

    print(f"Generating {args.number} keys and uploading to Firebase...")
    
    keys = {}
    for _ in range(args.number):
        k = generate_key()
        print(f"KEY: {k}")
        # Initialize key with empty hwid. If hwid is empty, it can be claimed.
        keys[k] = {"hwid": "", "status": "active"}

    # Upload to Firebase
    url = f"{db_url}/licenses.json"
    if secret:
        url += f"?auth={secret}"
        
    try:
        # We use PATCH so we don't overwrite existing keys
        response = requests.patch(url, json=keys)
        if response.status_code == 200:
            print("\nSUCCESS: Successfully uploaded to Firebase!")
        else:
            print(f"\nERROR: Failed to upload. Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"\nERROR: Network error: {e}")

if __name__ == "__main__":
    main()
