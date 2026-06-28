import json
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import api.main as main

with open(ROOT / 'data' / 'city_registry.json') as f:
    cities = json.load(f)

for slug in ['new-delhi', 'greater-noida']:
    bbox = next((c['bbox'] for c in cities if c['slug'] == slug), None)
    print('slug:', slug, 'bbox:', bbox)
    print('has slug in store:', slug in main.get_store().city_slugs())
    print('zone_count:', main.get_store().zone_count(slug))
    rows = main.get_store().zones_in_bbox(*bbox, city=slug, limit=10)
    print('bbox rows:', len(rows), [r['zone_id'] for r in rows[:3]])
    stats = main.get_store().stats(city=slug, bbox=tuple(bbox))
    print('stats:', stats.get('city'), stats.get('zone_count'), stats.get('scene_id'), stats.get('scene_date'))
    print('---')

print('new-delhi via city_stats:', main.city_stats(city='new-delhi', bbox=','.join(str(x) for x in bbox)))
