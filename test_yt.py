import urllib.request
import urllib.parse
import re
import json

def search(query):
    encoded = urllib.parse.quote(query)
    url = f"https://www.youtube.com/results?search_query={encoded}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('utf-8')
    
    # Method 1: simple regex
    video_ids = re.findall(r'watch\?v=([a-zA-Z0-9_-]{11})', html)
    # Remove duplicates preserving order
    unique_ids = list(dict.fromkeys(video_ids))
    print("Method 1:", unique_ids[:5])
    
search("Yorushika Itte")
