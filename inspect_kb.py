import os
import re
from pathlib import Path

kb_dir = Path("knowledge_base")
files = sorted(list(kb_dir.glob("*.md")))

print(f"Found {len(files)} files in knowledge_base/\n")

required_keywords = [
    ("helps", "helps / product helps"),
    ("voice should be", "brand voice should be / voice should be"),
    ("avoid", "avoid"),
    ("care about", "customers care about"),
    ("Primary channels", "Primary channels (case-sensitive)"),
    ("Content style", "Content style (case-sensitive)")
]

for f in files:
    content = f.read_text(encoding="utf-8")
    lines = content.splitlines()
    title = lines[0] if lines else "EMPTY"
    
    missing = []
    for kw, label in required_keywords:
        # Check case-insensitive for some, case-sensitive for others
        if kw in ["Primary channels", "Content style"]:
            if kw not in content:
                missing.append(label)
        else:
            if kw.lower() not in content.lower():
                missing.append(label)
                
    print(f"File: {f.name}")
    print(f"  Title: {title}")
    if missing:
        print(f"  MISSING KEYWORDS: {', '.join(missing)}")
    else:
        print(f"  All required keywords present.")
    print("-" * 40)
