"""Map layers of metropolitan France for choosing a study area.

  basins       the 7 river-basin districts of the Water Framework Directive (Sandre)
  subbasins    their 34 administrative sub-basins (Sandre)
  regions      the 13 regions
  departments  the 96 departments

The official Sandre layers weigh 60-90 MB, far too much for a browser. They are
fetched ONCE, simplified (Ramer-Douglas-Peucker) to a few hundred KB, and kept on disk
in backend/cache/, so later starts read the small file. Each feature keeps an id, a
name and its bounding box (used to decide which datasets cover the chosen area).

Sources (public, free of charge):
  Sandre WFS https://services.sandre.eaufrance.fr/geo/sandre  (BassinDCE_FXX, SsBassinDCEAdmin_FXX)
  france-geojson (simplified IGN boundaries) https://github.com/gregoiredavid/france-geojson
"""
import json
import pathlib
import threading

import httpx

CACHE_DIR = pathlib.Path(__file__).resolve().parent.parent / "cache"
SANDRE = ("https://services.sandre.eaufrance.fr/geo/sandre?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
          "&TYPENAMES={layer}&OUTPUTFORMAT=geojson&SRSNAME=EPSG:4326")
FRANCE_GEOJSON = "https://cdn.jsdelivr.net/gh/gregoiredavid/france-geojson@master/{file}"

LAYERS = {
    "basins": {
        "title": "River basins", "url": SANDRE.format(layer="sa:BassinDCE_FXX"),
        "id": "CdEuBassinDCE", "name": "NomDistrict", "tolerance": 0.012,
        "note": "Water Framework Directive river-basin districts (Sandre)",
    },
    "subbasins": {
        "title": "Sub-basins", "url": SANDRE.format(layer="sa:SsBassinDCEAdmin_FXX"),
        "id": "CdEuSsBassinDCEAdmin", "name": "NomSsBassinDCEAdmin", "tolerance": 0.008,
        "note": "Administrative sub-basins of the river-basin districts (Sandre)",
    },
    "regions": {
        "title": "Regions", "url": FRANCE_GEOJSON.format(file="regions-version-simplifiee.geojson"),
        "id": "code", "name": "nom", "tolerance": 0.004,
        "note": "Administrative regions (IGN, simplified)",
    },
    "departments": {
        "title": "Departments", "url": FRANCE_GEOJSON.format(file="departements-version-simplifiee.geojson"),
        "id": "code", "name": "nom", "tolerance": 0.004,
        "note": "Departments (IGN, simplified)",
    },
}
METROPOLITAN = (-5.6, 41.2, 10.0, 51.2)            # lon/lat box of metropolitan France with Corsica

_memory: dict[str, dict] = {}
_locks = {name: threading.Lock() for name in LAYERS}


def simplify(points: list[list[float]], tolerance: float) -> list[list[float]]:
    """Ramer-Douglas-Peucker on one closed ring.

    A closed ring starts and ends on the same point, which gives the algorithm no line to
    measure against: the ring is cut at its point farthest from the start, and each half
    is simplified on its own.
    """
    if len(points) < 5:
        return points
    x0, y0 = points[0][:2]
    far = max(range(len(points)), key=lambda i: (points[i][0] - x0) ** 2 + (points[i][1] - y0) ** 2)
    if far in (0, len(points) - 1):
        return _rdp(points, tolerance)
    return _rdp(points[: far + 1], tolerance)[:-1] + _rdp(points[far:], tolerance)


def _rdp(points: list[list[float]], tolerance: float) -> list[list[float]]:
    """Ramer-Douglas-Peucker on an open line, iterative (lines have up to 10^5 points)."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (x1, y1), (x2, y2) = points[first][:2], points[last][:2]
        dx, dy = x2 - x1, y2 - y1
        norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
        worst, index = 0.0, -1
        for i in range(first + 1, last):
            x, y = points[i][:2]
            distance = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm
            if distance > worst:
                worst, index = distance, i
        if worst > tolerance and index > 0:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))
    return [p for p, k in zip(points, keep) if k]


def ring_area(ring: list[list[float]]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))) / 2


def light(geometry: dict, tolerance: float) -> list[list[list[list[float]]]]:
    """Any polygon geometry -> a simplified MultiPolygon (list of polygons of rings)."""
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    found = []
    for polygon in polygons:
        rings = []
        for i, ring in enumerate(polygon):
            short = [[round(x, 3), round(y, 3)] for x, y, *_ in simplify(ring, tolerance)]
            if len(short) >= 4 and ring_area(short) > tolerance * tolerance * 4:
                rings.append(short)
            elif i == 0:
                break                                   # outer ring too small: drop the polygon
        if rings:
            found.append(rings)
    return found


def build(layer: str) -> dict:
    spec = LAYERS[layer]
    response = httpx.get(spec["url"], timeout=300, follow_redirects=True)
    response.raise_for_status()
    raw = response.json()
    features = []
    for feature in raw["features"]:
        if not feature.get("geometry"):
            continue
        polygons = light(feature["geometry"], spec["tolerance"])
        xs = [x for polygon in polygons for ring in polygon for x, _ in ring]
        ys = [y for polygon in polygons for ring in polygon for _, y in ring]
        if not xs:
            continue
        box = [min(xs), min(ys), max(xs), max(ys)]
        # metropolitan France only (the IGN files also hold the overseas departments)
        if box[2] < METROPOLITAN[0] or box[0] > METROPOLITAN[2] or box[3] < METROPOLITAN[1] or box[1] > METROPOLITAN[3]:
            continue
        properties = feature["properties"]
        features.append({
            "type": "Feature",
            "properties": {"id": str(properties[spec["id"]]), "name": str(properties[spec["name"]]).title()
                           if layer == "basins" else str(properties[spec["name"]]), "bbox": box},
            "geometry": {"type": "MultiPolygon", "coordinates": polygons},
        })
    features.sort(key=lambda f: f["properties"]["name"])
    return {"type": "FeatureCollection", "layer": layer, "title": spec["title"], "note": spec["note"],
            "features": features}


# Names as they are written in French. Sandre gives the districts in capitals without accents
# (title-cased here: "Rhone", "Adour Garonne"), and names both parts of the Meuse district
# "Meuse": the second one (FRB2) is the Sambre, as its sub-basin FRB2_SAMB says.
# Applied on read, so an existing disk cache is corrected too.
NAME_FIXES = {"basins": {"FRB2": "Sambre", "FRD": "Rhône", "FRF": "Adour-Garonne", "FRA": "Escaut-Somme"}}


def _fix_names(name: str, collection: dict) -> dict:
    fixes = NAME_FIXES.get(name)
    if fixes:
        for feature in collection["features"]:
            fixed = fixes.get(feature["properties"]["id"])
            if fixed:
                feature["properties"]["name"] = fixed
        collection["features"].sort(key=lambda f: f["properties"]["name"])
    return collection


def layer(name: str) -> dict:
    """One layer, from memory, else from the disk cache, else fetched and simplified once."""
    if name in _memory:
        return _memory[name]
    with _locks[name]:
        if name not in _memory:
            path = CACHE_DIR / f"geo_{name}.json"
            if path.exists():
                _memory[name] = _fix_names(name, json.loads(path.read_text(encoding="utf-8")))
            else:
                built = _fix_names(name, build(name))
                CACHE_DIR.mkdir(exist_ok=True)
                path.write_text(json.dumps(built, separators=(",", ":")), encoding="utf-8")
                _memory[name] = built
    return _memory[name]


def layers() -> list[dict]:
    """The layers that can be shown, and whether they are ready (in memory or on disk)."""
    return [{"id": name, "title": spec["title"], "note": spec["note"],
             "ready": name in _memory or (CACHE_DIR / f"geo_{name}.json").exists()}
            for name, spec in LAYERS.items()]


# ---- Topographic watersheds (BD Topage), shown inside the chosen study area ----------------
#
# "Bassins versants topographiques - Métropole 2026 - BD Topage" (IGN / OFB, served by Sandre):
# https://www.sandre.eaufrance.fr/atlas/srv/fre/catalog.search#/metadata/c58a954a-3a36-4ba9-b888-4db2a4493c7b
# 6,190 watersheds, 100 MB as GeoJSON: fetched once, simplified, kept on disk. A request for one
# study area returns the watersheds whose centre lies inside that area.

WATERSHEDS = {
    "title": "Topographic watersheds",
    "url": ("https://services.sandre.eaufrance.fr/geo/topage2026?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
            "&TYPENAMES=sa:BassinVersantTopographique_FXX_Topage2026&OUTPUTFORMAT=geojson&SRSNAME=EPSG:4326"),
    "tolerance": 0.0025,
    "note": "Topographic watersheds, BD Topage 2026 (IGN / OFB, Sandre)",
    "source": "https://www.sandre.eaufrance.fr/atlas/srv/fre/catalog.search#/metadata/c58a954a-3a36-4ba9-b888-4db2a4493c7b",
}
_watershed_lock = threading.Lock()
_by_area: dict[str, dict] = {}


def centroid(rings: list[list[list[float]]]) -> tuple[float, float]:
    """Centre of the outer ring of a polygon (shoelace formula; the mean of its points if flat)."""
    ring = rings[0]
    area = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(area) < 1e-12:
        return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
    return cx / (3 * area), cy / (3 * area)


def inside(point: tuple[float, float], polygons: list) -> bool:
    """Is the point inside a MultiPolygon (even-odd rule, holes included)?"""
    x, y = point
    hit = False
    for polygon in polygons:
        for ring in polygon:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
                if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                    hit = not hit
    return hit


def build_watersheds() -> dict:
    response = httpx.get(WATERSHEDS["url"], timeout=600, follow_redirects=True)
    response.raise_for_status()
    raw = json.loads(response.content.decode("utf-8"))
    features = []
    for feature in raw["features"]:
        if not feature.get("geometry"):
            continue
        polygons = light(feature["geometry"], WATERSHEDS["tolerance"])
        if not polygons:
            continue
        xs = [x for polygon in polygons for ring in polygon for x, _ in ring]
        ys = [y for polygon in polygons for ring in polygon for _, y in ring]
        largest = max(polygons, key=lambda polygon: ring_area(polygon[0]))
        cx, cy = centroid(largest)
        properties = feature["properties"]
        features.append({
            "type": "Feature",
            "properties": {"id": str(properties["CdOH"]), "name": str(properties.get("TopoOH") or properties["CdOH"]),
                           "bbox": [min(xs), min(ys), max(xs), max(ys)], "centre": [round(cx, 4), round(cy, 4)],
                           "basin": str(properties.get("CdBH") or "")},
            "geometry": {"type": "MultiPolygon", "coordinates": polygons},
        })
    return {"type": "FeatureCollection", "layer": "watersheds", "title": WATERSHEDS["title"],
            "note": WATERSHEDS["note"], "source": WATERSHEDS["source"], "features": features}


def all_watersheds() -> dict:
    """Every watershed of metropolitan France, simplified (memory, else disk, else fetched once)."""
    if "watersheds" in _memory:
        return _memory["watersheds"]
    with _watershed_lock:
        if "watersheds" not in _memory:
            path = CACHE_DIR / "geo_watersheds.json"
            if path.exists():
                _memory["watersheds"] = json.loads(path.read_text(encoding="utf-8"))
            else:
                built = build_watersheds()
                CACHE_DIR.mkdir(exist_ok=True)
                path.write_text(json.dumps(built, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
                _memory["watersheds"] = built
    return _memory["watersheds"]


def watersheds_in(layer_name: str, area_id: str) -> dict:
    """The watersheds whose centre lies inside one area of a layer (basin, region...)."""
    key = f"{layer_name}:{area_id}"
    if key in _by_area:
        return _by_area[key]
    area = next((f for f in layer(layer_name)["features"] if f["properties"]["id"] == area_id), None)
    if area is None:
        raise KeyError(area_id)
    x0, y0, x1, y1 = area["properties"]["bbox"]
    polygons = area["geometry"]["coordinates"]
    found = []
    for feature in all_watersheds()["features"]:
        cx, cy = feature["properties"]["centre"]
        if x0 <= cx <= x1 and y0 <= cy <= y1 and inside((cx, cy), polygons):
            found.append(feature)
    found.sort(key=lambda f: f["properties"]["name"])
    result = {"type": "FeatureCollection", "layer": "watersheds", "title": WATERSHEDS["title"],
              "note": WATERSHEDS["note"], "source": WATERSHEDS["source"],
              "area": area, "features": found}
    if len(_by_area) > 200:
        _by_area.clear()
    _by_area[key] = result
    return result
