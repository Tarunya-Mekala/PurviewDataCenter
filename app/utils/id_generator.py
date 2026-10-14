import uuid


def generate_id(prefix: str) -> str:
    """
    Generate a UUID-based identifier with an entity prefix.
    
    Examples:
        generate_id("proj") -> "proj_6b2d6a4574924cbbba942d9df8df3c8f"
        generate_id("doc")  -> "doc_d4f82a1b9e30472cb192837465abcde1"
    """
    clean_prefix = prefix.rstrip("_")
    return f"{clean_prefix}_{uuid.uuid4().hex}"
