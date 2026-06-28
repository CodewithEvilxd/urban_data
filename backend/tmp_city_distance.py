import json
import math
from pathlib import Path

root = Path('data')
with open(root / 'city_registry.json') as f:
    cities = {c['slug']: c for c in json.load(f)}
slugs = ['new-delhi', 'greater-noida', 'noida', 'lucknow']
print('registry:', [s for s in slugs if s in cities])
print('processed:', [p.name for p in sorted((root / 'processed').glob('zones_*.json')) if p.stem.replace('zones_', '') in slugs])

def dist(lat1, lon1, lat2, lon2):
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return round(2 * r * math.asin(math.sqrt(a)), 2)

for slug in slugs:
    c = cities.get(slug)
    if c:
        print(f"\n{slug}: name={c['name']}, state={c['state']}")
        print(f"  center=({c['lat']}, {c['lon']})")
        print(f"  bbox={c['bbox']}")
    else:
        print(f"\n{slug}: missing from registry")

print('\ncenter distances:')
for i, a in enumerate(slugs):
    for b in slugs[i+1:]:
        if a in cities and b in cities:
            da = cities[a]
            db = cities[b]
            print(f"{a} ↔ {b}: {dist(da['lat'], da['lon'], db['lat'], db['lon'])} km")
