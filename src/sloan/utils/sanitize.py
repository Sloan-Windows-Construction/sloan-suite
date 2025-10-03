import re

_FORBIDDEN = r'["*:<>?\/\\|#%]'  # characters SharePoint forbids
def sanitize_name(s: str, max_len: int = 120) -> str:
    s = (s or "").strip()
    # remove forbidden characters
    s = re.sub(_FORBIDDEN, "", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # disallow leading/trailing dot/space
    s = s.strip(" .")
    # bracket/json cleanup (guard rail)
    s = s.replace("[", "").replace("]", "").replace("{", "").replace("}", "")
    if not s:
        s = "Untitled"
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s

