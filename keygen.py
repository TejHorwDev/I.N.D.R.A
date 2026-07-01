import hashlib
import random
import string
import argparse

SECRET_SALT = "INDRA_CORP_OFFLINE_SECRET_2026"

def generate_key() -> str:
    # 1. Generate 8 random uppercase alphanumeric characters for the payload
    payload = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    # 2. Generate the mathematical signature using the secret salt
    hash_input = f"{payload}{SECRET_SALT}".encode('utf-8')
    full_hash = hashlib.sha256(hash_input).hexdigest().upper()
    
    # 3. Take the first 8 characters of the hash as the signature
    signature = full_hash[:8]
    
    # 4. Format into a professional XXXX-XXXX-XXXX-XXXX license key
    raw_key = payload + signature
    formatted_key = f"{raw_key[:4]}-{raw_key[4:8]}-{raw_key[8:12]}-{raw_key[12:16]}"
    
    return formatted_key

def main():
    parser = argparse.ArgumentParser(description="INDRA License Key Generator")
    parser.add_argument("-n", "--number", type=int, default=1, help="Number of keys to generate")
    args = parser.parse_args()

    print("=" * 40)
    print(" INDRA AI - OFFICIAL LICENSE GENERATOR")
    print("=" * 40)
    
    for _ in range(args.number):
        key = generate_key()
        print(f"KEY: {key}")
        
    print("=" * 40)

if __name__ == "__main__":
    main()
