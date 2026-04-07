import re

text = """
[EMOTION:happy]
{
  "action": "youtube_search",
  "params": {
    "query": "Yorushika"
  }
}
Oke! Aku bantu carikan Yorushika di YouTube.
"""

patterns = [
    r'(\{\s*"action"\s*:\s*"[^"]+"\s*,\s*"params"\s*:\s*\{[^}]*\}\s*\})',
    r'(\{\s*"action"\s*:\s*"[^"]+"[^}]*\})',
    r'(\[\s*\{[^\]]+\}\s*\])',
]

for p in patterns:
    matches = re.findall(p, text, re.DOTALL)
    print(matches)
