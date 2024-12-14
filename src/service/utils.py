from typing import List, Optional


def split_keys(v: Optional[str]) -> Optional[List[str]]:
    if v is None or not v:
        return []
    return v.split(",")
