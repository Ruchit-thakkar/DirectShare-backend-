import hashlib

def verify_sha256(data: bytes, expected_checksum: str) -> bool:
    """Compare the SHA256 hash of data with the expected checksum string."""
    if not expected_checksum:
        return False
    calculated = calculate_sha256(data)
    return calculated.lower() == expected_checksum.lower()

def calculate_sha256(data: bytes) -> str:
    """Calculate the SHA256 hex digest of the given data."""
    sha256_hash = hashlib.sha256()
    sha256_hash.update(data)
    return sha256_hash.hexdigest()
