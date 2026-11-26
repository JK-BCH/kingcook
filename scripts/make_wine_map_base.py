#!/usr/bin/env python3
"""와인 지도 밑그림(scripts/wine_map_base.json) 생성기 — 지도 모양을 바꿀 때만 돌리는 도구.

대시보드 빌드(CI 포함)는 이 결과 파일만 읽으므로 평소엔 다시 돌릴 필요가 없다.
패널 범위나 해상도를 바꾸고 싶을 때만 아래처럼 원본을 받아 실행한다.

    mkdir -p /tmp/geo && cd /tmp/geo
    npm pack world-atlas@2 us-atlas@3 && for f in *.tgz; do tar -xzf "$f" --one-top-level; done
    python3 scripts/make_wine_map_base.py \\
        /tmp/geo/world-atlas-2.0.2/package/countries-110m.json \\
        /tmp/geo/world-atlas-2.0.2/package/countries-50m.json \\
        /tmp/geo/us-atlas-3.0.1/package/states-10m.json

데이터 출처 (둘 다 퍼블릭 도메인)
  - 국가 경계: Natural Earth — world-atlas@2 패키지로 재배포된 TopoJSON
  - 미국 주 경계: U.S. Census Bureau cartographic boundary — us-atlas@3

처리: TopoJSON 해독 → 패널 투영(build_wine_dashboard.project와 같은 함수)
      → 패널 사각형 밖 잘라내기(Sutherland–Hodgman) → 화면 해상도 기준 단순화(RDP)
      → 소수 1자리 상대좌표 SVG path.
"""

import importlib.util
import json
import math
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("bwd", HERE / "build_wine_dashboard.py")
bwd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bwd)
project, equal_earth = bwd.project, bwd.equal_earth

# 세계 패널은 남극 제외, 위도 −56~84로 자른다(티에라델푸에고~그린란드 북단).
WORLD = {"id": "world", "title": "세계", "W": 1000, "lat": (-56.0, 84.0), "tol": 0.4}
# 확대 패널: 와인이 몰린 두 곳. 범위는 로그의 산지 핀이 가장자리에 붙지 않을 만큼만.
ZOOMS = [
    {"id": "usw", "title": "미국 서부", "W": 220, "bbox": (-124.9, 34.9, -118.4, 48.6), "tol": 0.35},
    {"id": "weu", "title": "서유럽", "W": 900, "bbox": (-9.8, 38.0, 17.2, 51.2), "tol": 0.45},
]
ANTARCTICA = "010"


# ── TopoJSON ────────────────────────────────────────────────────
def load_topo(path: str, obj: str) -> list[tuple[str, list]]:
    """[(id, [polygon, …])] — polygon은 [ring, …], ring은 [(lon, lat), …]."""
    topo = json.loads(Path(path).read_text(encoding="utf-8"))
    tf = topo.get("transform")
    arcs = []
    for arc in topo["arcs"]:
        if tf:
            (sx, sy), (tx, ty) = tf["scale"], tf["translate"]
            x = y = 0
            pts = []
            for dx, dy in arc:
                x += dx
                y += dy
                pts.append((x * sx + tx, y * sy + ty))
        else:
            pts = [tuple(p) for p in arc]
        arcs.append(pts)

    def ring(idxs):
        out = []
        for i in idxs:
            seg = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(seg[1:] if out else seg)
        return out

    feats = []
    for g in topo["objects"][obj]["geometries"]:
        t = g.get("type")
        if t == "Polygon":
            polys = [[ring(r) for r in g["arcs"]]]
        elif t == "MultiPolygon":
            polys = [[ring(r) for r in poly] for poly in g["arcs"]]
        else:
            continue
        feats.append((str(g.get("id", "")), polys))
    return feats


# ── 기하 처리 ───────────────────────────────────────────────────
def clip_ring(pts, x0, y0, x1, y1):
    """Sutherland–Hodgman — 닫힌 링을 사각형으로 자른다(밖으로 나간 부분은 가장자리에 붙음)."""
    def clip(pts, inside, cross):
        out = []
        if not pts:
            return out
        prev = pts[-1]
        for cur in pts:
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur))
            prev = cur
        return out

    def at_x(a, b, x):
        t = (x - a[0]) / (b[0] - a[0])
        return (x, a[1] + t * (b[1] - a[1]))

    def at_y(a, b, y):
        t = (y - a[1]) / (b[1] - a[1])
        return (a[0] + t * (b[0] - a[0]), y)

    pts = clip(pts, lambda p: p[0] >= x0, lambda a, b: at_x(a, b, x0))
    pts = clip(pts, lambda p: p[0] <= x1, lambda a, b: at_x(a, b, x1))
    pts = clip(pts, lambda p: p[1] >= y0, lambda a, b: at_y(a, b, y0))
    pts = clip(pts, lambda p: p[1] <= y1, lambda a, b: at_y(a, b, y1))
    return pts



def split_antimeridian(ring):
    """경도 ±180°(날짜변경선)를 넘는 링을 동·서 두 조각으로 자른다.

    피지·러시아 동단처럼 179° 다음 점이 −179°인 링을 그대로 투영하면 지도 오른쪽 끝에서
    왼쪽 끝까지 가로줄이 그어진다. 음수 경도를 +360으로 펴서 이어 붙인 뒤
    경위도 공간에서 180° 기준으로 잘라 양쪽에 따로 그린다.
    """
    if not any(abs(b[0] - a[0]) > 180 for a, b in zip(ring, ring[1:])):
        return [ring]
    flat = [(lon + 360 if lon < 0 else lon, lat) for lon, lat in ring]
    east = clip_ring(flat, -1e9, -90.0, 180.0, 90.0)
    west = clip_ring([(lon - 360, lat) for lon, lat in flat], -180.0, -90.0, 1e9, 90.0)
    return [r + r[:1] for r in (east, west) if len(r) >= 3]

def rdp(pts, eps):
    """Ramer–Douglas–Peucker(반복형). eps는 viewBox 단위 ≈ 화면 px."""
    n = len(pts)
    if n < 3:
        return pts
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        s, e = stack.pop()
        ax, ay = pts[s]
        bx, by = pts[e]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        dmax, idx = -1.0, -1
        for i in range(s + 1, e):
            px, py = pts[i]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / L if L else math.hypot(px - ax, py - ay)
            if d > dmax:
                dmax, idx = d, i
        if idx > 0 and dmax > eps:
            keep[idx] = True
            stack += [(s, idx), (idx, e)]
    return [p for p, k in zip(pts, keep) if k]


def area(pts):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2


def num(v: float) -> str:
    s = f"{round(v, 1):.1f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def ring_d(pts) -> str:
    """닫힌 링 → 'M x,y l dx,dy … z'. 반올림한 절대좌표끼리의 차라 오차가 쌓이지 않는다."""
    r = [(round(x, 1), round(y, 1)) for x, y in pts]
    out = [r[0]]
    for p in r[1:]:
        if p != out[-1]:
            out.append(p)
    if len(out) > 1 and out[-1] == out[0]:
        out.pop()
    if len(out) < 3:
        return ""
    s = f"M{num(out[0][0])},{num(out[0][1])}"
    for (xa, ya), (xb, yb) in zip(out, out[1:]):
        s += f"l{num(xb - xa)},{num(yb - ya)}"
    return s + "z"


def shapes_for(feats, proj, W, H, tol, prefix=""):
    m = 6.0                                   # 잘라낼 때 화면 밖 여유(테두리 선이 안 보이게)
    out = []
    for fid, polys in feats:
        parts = []
        for poly in polys:
            rings = [(k, r) for k, ring in enumerate(poly)
                     for r in (split_antimeridian(ring) if proj["type"] == "ee" else [ring])]
            for k, ring in rings:
                pts = [project(proj, lon, lat) for lon, lat in ring]
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                if max(xs) < -m or min(xs) > W + m or max(ys) < -m or min(ys) > H + m:
                    continue
                if pts[0] == pts[-1]:
                    pts = pts[:-1]
                pts = clip_ring(pts, -m, -m, W + m, H + m)
                if len(pts) < 3:
                    continue
                pts = rdp(pts + [pts[0]], tol)[:-1]
                if len(pts) < 3 or (k == 0 and area(pts) < 1.5):
                    continue                  # 1.5px² 미만 섬은 버림(구멍은 유지)
                d = ring_d(pts)
                if d:
                    parts.append(d)
        if parts:
            out.append([prefix + fid, "".join(parts)])
    return out


def sample_box(proj, bbox, step=0.5):
    """경위도 사각형 테두리를 촘촘히 찍어 투영 — Equal Earth에선 경선이 휘어서 직선으로 못 그림."""
    lo0, la0, lo1, la1 = bbox
    def rng(a, b):
        n = max(2, int(abs(b - a) / step) + 1)
        return [a + (b - a) * i / (n - 1) for i in range(n)]
    edge = ([(lo, la0) for lo in rng(lo0, lo1)] + [(lo1, la) for la in rng(la0, la1)][1:]
            + [(lo, la1) for lo in rng(lo1, lo0)][1:] + [(lo0, la) for la in rng(la1, la0)][1:-1])
    return [project(proj, lo, la) for lo, la in edge]


# ── 패널 조립 ───────────────────────────────────────────────────
def world_panel(feats110):
    W = WORLD["W"]
    xmax = equal_earth(180, 0)[0]
    ytop, ybot = equal_earth(0, WORLD["lat"][1])[1], equal_earth(0, WORLD["lat"][0])[1]
    k = W / (2 * xmax)
    proj = {"type": "ee", "lon0": 0.0, "k": round(k, 6), "x0": W / 2, "y0": round(k * ytop, 4)}
    H = round(k * (ytop - ybot), 1)
    feats = [f for f in feats110 if f[0] != ANTARCTICA]
    lo, hi = WORLD["lat"]
    outline = ring_d(sample_box(proj, (-180, lo, 180, hi), step=2))
    frames = []
    for z in ZOOMS:
        pts = sample_box(proj, z["bbox"])
        frames.append({"to": z["id"], "d": ring_d(pts),
                       "lx": round(min(p[0] for p in pts), 1),
                       "ly": round(min(p[1] for p in pts), 1)})
    return {"id": "world", "title": WORLD["title"], "proj": proj, "vb": [W, H],
            "outline": outline, "frames": frames,
            "shapes": shapes_for(feats, proj, W, H, WORLD["tol"])}


def zoom_panel(z, feats50, states):
    lo0, la0, lo1, la1 = z["bbox"]
    W = z["W"]
    c = math.cos(math.radians((la0 + la1) / 2))
    k = W / ((lo1 - lo0) * c)
    proj = {"type": "eqr", "lon0": lo0, "lat0": la1, "cos": round(c, 6), "k": round(k, 6)}
    H = round((la1 - la0) * k, 1)
    if z["id"] == "usw":
        shapes = shapes_for(states, proj, W, H, z["tol"], prefix="us-")
        shapes += shapes_for([f for f in feats50 if f[0] in ("124", "484")], proj, W, H, z["tol"])
    else:
        shapes = shapes_for(feats50, proj, W, H, z["tol"])
    return {"id": z["id"], "title": z["title"], "proj": proj, "vb": [W, H],
            "bbox": list(z["bbox"]), "shapes": shapes}


def main(argv) -> int:
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    f110 = load_topo(argv[1], "countries")
    f50 = load_topo(argv[2], "countries")
    st = load_topo(argv[3], "states")
    base = {
        "about": "와인 지도 밑그림. scripts/make_wine_map_base.py가 생성 — 직접 수정하지 말 것.",
        "generated": date.today().isoformat(),
        "sources": ["Natural Earth (public domain) via world-atlas@2",
                    "U.S. Census Bureau cartographic boundaries (public domain) via us-atlas@3"],
        "panels": [world_panel(f110)] + [zoom_panel(z, f50, st) for z in ZOOMS],
    }
    out = HERE / "wine_map_base.json"
    out.write_text(json.dumps(base, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✓ {out.name} — {out.stat().st_size / 1024:.0f} KB")
    for p in base["panels"]:
        size = sum(len(s[1]) for s in p["shapes"]) / 1024
        print(f"  {p['id']:5} viewBox {p['vb'][0]}×{p['vb'][1]} · 도형 {len(p['shapes'])}개 · {size:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
