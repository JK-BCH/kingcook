#!/usr/bin/env python3
"""drinks/wine-log.md -> drinks/dashboard.html 생성기.

와인 로그를 파싱해서 대시보드 템플릿(scripts/wine_dashboard_template.html)에
데이터를 주입한다. 로그에 와인을 추가한 뒤 이 스크립트를 다시 실행하면
대시보드의 모든 수치·목록이 자동으로 갱신된다.

    python3 scripts/build_wine_dashboard.py
"""

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "drinks" / "wine-log.md"
TEMPLATE = ROOT / "scripts" / "wine_dashboard_template.html"
OUT = ROOT / "drinks" / "dashboard.html"
DRINKS = ROOT / "drinks"
PLACEHOLDER_TOP100_YEARS = "/*__TOP100_YEARS__*/[]"
TOP100_SHOWN = 2        # 드로어에 나란히 띄울 연도 수(최신부터)
PLACEHOLDER = "/*__DATA__*/[]"
PLACEHOLDER_TOP100 = "/*__TOP100__*/[]"
# 상급 큐베를 가르는 표시 — 공식 와인명에만 이 말이 붙어 있으면 다른 와인으로 본다.
CUVEE_MARKERS = {"riserva", "riserve", "reserva", "reserve", "selezione",
                 "superiore", "vigna", "vigneto", "cru", "premier", "grand"}
UNDATED = "미분류"  # 마신 날짜를 모르는 기록을 묶는 섹션명 (템플릿 JS와 값이 같아야 함)

# 지역 표기 -> 국가. 위에서부터 먼저 매칭되는 것을 쓴다(하위 산지가 먼저 와야 함).
REGION_COUNTRY = [
    ("말보로", "뉴질랜드"), ("뉴질랜드", "뉴질랜드"),
    ("모젤", "독일"), ("자르", "독일"), ("독일", "독일"),
    ("바인피어텔", "오스트리아"), ("바하우", "오스트리아"), ("오스트리아", "오스트리아"),
    ("레바논", "레바논"), ("베카밸리", "레바논"),
    ("멘도자", "아르헨티나"), ("멘도사", "아르헨티나"), ("투풍가토", "아르헨티나"),
    ("우코 밸리", "아르헨티나"), ("아르헨티나", "아르헨티나"),
    ("바로사", "호주"), ("마가렛 리버", "호주"), ("호주", "호주"),
    ("워커베이", "남아공"), ("헤멜엔아르데", "남아공"), ("남아공", "남아공"),
    ("리오하", "스페인"), ("페네데스", "스페인"), ("스페인", "스페인"),
    ("비뉴 베르드", "포르투갈"), ("도루", "포르투갈"), ("포르투갈", "포르투갈"),
    ("바롤로", "이탈리아"), ("바르바레스코", "이탈리아"), ("랑게", "이탈리아"),
    ("피에몬테", "이탈리아"), ("아스티", "이탈리아"), ("콜리오", "이탈리아"),
    ("프리울리", "이탈리아"), ("토스카나", "이탈리아"), ("브루넬로", "이탈리아"),
    ("몬탈치노", "이탈리아"), ("프란차코르타", "이탈리아"), ("이탈리아", "이탈리아"),
    ("부르고뉴", "프랑스"), ("샤블리", "프랑스"), ("뫼르소", "프랑스"),
    ("메르퀴레", "프랑스"), ("라두아", "프랑스"), ("보르도", "프랑스"),
    ("생줄리앙", "프랑스"), ("생테밀리옹", "프랑스"), ("소테른", "프랑스"),
    ("루아르", "프랑스"), ("푸이퓌메", "프랑스"), ("상세르", "프랑스"),
    ("상파뉴", "프랑스"), ("샴페인", "프랑스"), ("방투", "프랑스"),
    ("론밸리", "프랑스"), ("그랑크뤼", "프랑스"), ("프랑스", "프랑스"),
    ("나파", "미국"), ("소노마", "미국"), ("러시안 리버", "미국"),
    ("오리건", "미국"), ("윌라멧", "미국"), ("에올라-아미티", "미국"),
    ("캘리포니아", "미국"), ("워싱턴", "미국"), ("푸젓 사운드", "미국"),
    ("로디", "미국"), ("시에라풋힐스", "미국"), ("산타바바라", "미국"),
    ("세인트헬레나", "미국"),
]

# 품종 사전: (표시 이름, 로그 품종 칸에 쓰는 표기들).
# 하나도 안 맞으면 "품종 미상"(샴페인 블렌드·레드 블렌드처럼 구성이 안 적힌 것) —
# 로그에 새 품종이 나오면 여기 한 줄 추가.
# 차트에 막대로 따로 나올지는 템플릿이 병 수로 정한다(VARIETY_MIN병 이상).
# 매칭은 긴 표기부터 하고 맞은 글자는 지워서, '프티 시라'가 '시라'로,
# '그르나슈 블랑'이 '그르나슈'로, '카베르네 소비뇽'이 '소비뇽'으로 다시 잡히지 않게 한다.
VARIETY_KEYS = [
    # 레드
    ("카베르네 소비뇽", ["카베르네 소비뇽"]),
    ("카베르네 프랑", ["카베르네 프랑"]),
    ("메를로", ["메를로"]),
    ("말벡", ["말벡"]),
    ("프티 베르도", ["프티 베르도", "쁘띠 베르도"]),
    ("보르도 블렌드", ["보르도 블렌드"]),
    ("피노 누아", ["피노 누아"]),
    ("시라/시라즈", ["시라즈", "시라"]),
    ("프티 시라", ["프티 시라", "쁘띠 시라"]),
    ("그르나슈", ["그르나슈", "가르나차"]),
    ("네비올로", ["네비올로"]),
    ("산지오베제", ["산지오베제"]),
    ("몬테풀치아노", ["몬테풀치아노"]),   # 품종(아브루초·마르케). 토스카나 마을 이름(비노 노빌레 디 몬테풀치아노)과 다름
    ("바르베라", ["바르베라"]),
    ("템프라니요", ["템프라니요"]),
    ("그라시아노", ["그라시아노"]),
    ("진판델", ["진판델"]),
    ("가메", ["가메"]),
    ("카리냥", ["카리냥"]),
    ("생소", ["생소"]),
    # 화이트·스파클링
    ("샤르도네", ["샤르도네"]),
    ("피노 뫼니에", ["피노 뫼니에", "피노 뮈니에"]),
    ("소비뇽 블랑", ["소비뇽 블랑", "소비뇽"]),   # 소테른의 '세미용/소비뇽'
    ("세미용", ["세미용"]),
    ("리슬링", ["리슬링"]),
    ("슈냉 블랑", ["슈냉 블랑"]),
    ("비오니에", ["비오니에"]),
    ("피노 그리지오", ["피노 그리지오", "피노 그리"]),
    ("알바리뇨", ["알바리뇨"]),
    ("알리고테", ["알리고테"]),
    ("프리울라노", ["프리울라노"]),
    ("케르너", ["케르너"]),
    ("그르나슈 블랑", ["그르나슈 블랑"]),
    ("루산", ["루산느", "루산"]),
    ("클레레트", ["클레레트"]),
    ("모스카토", ["모스카토", "뮈스카"]),
    ("글레라", ["글레라"]),
    ("온다라비 수리", ["온다라비 수리"]),
    ("마카베오", ["마카베오"]),
    ("사렐로", ["사렐로", "샤렐로"]),
    ("파레야다", ["파레야다"]),
]
_VARIETY_KW = sorted(((kw, label) for label, kws in VARIETY_KEYS for kw in kws),
                     key=lambda x: -len(x[0]))
# 구성 비율이 10% 미만이거나 '소량'으로 적힌 품종은 그 와인의 품종으로 세지 않는다.
# 예: '카베르네 소비뇽 96%·프티 베르도 2%·시라 2%' -> 카베르네 소비뇽만
_MINOR_PAREN = re.compile(r"\([^)]*소량[^)]*\)")
_MINOR_PCT = re.compile(r"[^·/(),]+?\s*(\d{1,3})\s*%?(?=\s*(?:$|[·/(),]))")



# ───────────────────────── 와인 지도 ─────────────────────────
# 밑그림(scripts/wine_map_base.json)은 make_wine_map_base.py가 미리 투영해 둔 것이고,
# 핀은 빌드 때마다 여기서 투영한다. 두 쪽이 반드시 같은 함수를 써야 핀이 제자리에 찍힌다.
MAP_BASE = ROOT / "scripts" / "wine_map_base.json"
MAP_PLACES = ROOT / "scripts" / "wine_places.json"
PLACEHOLDER_MAP = "/*__MAP__*/null"

_EE = (1.340264, -0.081106, 0.000893, 0.003796)   # Equal Earth 계수 (Šavrič et al. 2018)
_EE_M = math.sqrt(3) / 2


def equal_earth(lon: float, lat: float, lon0: float = 0.0) -> tuple[float, float]:
    """Equal Earth 투영(면적 보존 세계지도). 단위 없는 평면 좌표, y는 위쪽이 +."""
    a1, a2, a3, a4 = _EE
    lam = math.radians(lon - lon0)
    th = math.asin(_EE_M * math.sin(math.radians(lat)))
    t2 = th * th
    t6 = t2 ** 3
    x = lam * math.cos(th) / (_EE_M * (a1 + 3 * a2 * t2 + t6 * (7 * a3 + 9 * a4 * t2)))
    y = th * (a1 + a2 * t2 + t6 * (a3 + a4 * t2))
    return x, y


def project(proj: dict, lon: float, lat: float) -> tuple[float, float]:
    """패널 투영 파라미터로 경위도를 SVG 좌표(viewBox 단위, y는 아래쪽이 +)로 바꾼다.

    ee  : 세계 패널 — Equal Earth.            X = x0 + k·x,  Y = y0 − k·y
    eqr : 확대 패널 — 위도 보정 정거원통.      X = (lon−lon0)·cos·k,  Y = (lat0−lat)·k
          좁은 지역이라 중앙 위도의 cos 하나로 보정하면 모양이 거의 그대로다.
    """
    if proj["type"] == "ee":
        x, y = equal_earth(lon, lat, proj.get("lon0", 0.0))
        return proj["x0"] + proj["k"] * x, proj["y0"] - proj["k"] * y
    if proj["type"] == "eqr":
        return ((lon - proj["lon0"]) * proj["cos"] * proj["k"],
                (proj["lat0"] - lat) * proj["k"])
    raise ValueError(f"모르는 투영: {proj['type']}")


def clean(s: str) -> str:
    return re.sub(r"\*\*|✅|⭐\s*", "", s).strip()


def parse_log(text: str) -> list[dict]:
    """마크다운 표에서 와인 항목을 뽑아낸다. 날짜는 직전 '## YYYY-MM-DD' 헤더 기준.

    '## 미분류'(마신 날짜를 모르는 기록) 섹션은 날짜를 UNDATED로 묶는다.
    그 외 날짜가 아닌 '##' 헤더를 만나면 수집을 멈춘다 — 그래야 나중에 다른
    섹션이 생겨도 그 표가 바로 위 자리의 날짜로 잘못 붙지 않는다.
    """
    rows, date = [], None
    for line in text.split("\n"):
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            head = m.group(1)
            dm = re.match(r"(\d{4}-\d{2}-\d{2})", head)
            date = dm.group(1) if dm else (UNDATED if head.startswith(UNDATED) else None)
            continue
        if not (line.startswith("|") and date):
            continue
        if re.match(r"^\|[-\s|]+$", line):
            continue  # 구분선
        cols = [c.strip() for c in line.strip("|").split("|")]
        # 표 헤더는 첫 두 칸을 정확히 비교해서 거른다. 예전처럼 줄 안에 '와인'과
        # '종류'가 둘 다 있는지로 보면, 메모에 그 두 단어가 들어간 와인 행이
        # 헤더로 오인돼 조용히 사라진다(2026-11-16에 실제로 1종 유실).
        if cols[:2] == ["와인", "종류"]:
            continue
        if len(cols) < 6 or not cols[0]:
            continue
        rows.append(dict(zip(
            ["date", "name", "kind", "varreg", "vivino", "critic", "memo"],
            [date] + cols[:6])))
    return rows


def split_varreg(varreg: str) -> tuple[str, str]:
    """'품종 · 지역' -> (품종, 지역).

    구분자는 공백을 낀 ' · '만 인정한다. 품종·지역 안에서 쓰는 붙임표
    ('마카베오·사렐로·파레야다', '산타바바라·몬터레이·솔라노')를 구분자로
    오인해 뒤쪽 한 조각만 지역으로 잘라내는 것을 막기 위함.
    """
    if " · " in varreg:
        grape, region = varreg.split(" · ", 1)
        return clean(grape), clean(region)
    return varreg, ""


def country_of(varreg: str) -> str:
    """지역 표기로 국가를 판정한다.

    반드시 '지역' 부분만 넘길 것. 품종까지 섞인 문자열을 넘기면
    '보르도 블렌드'(나파 와인의 품종명)가 '보르도'에 걸려 프랑스로
    오분류된다.
    """
    for kw, country in REGION_COUNTRY:
        if kw in varreg:
            return country
    return "기타"


def varieties_of(grape: str) -> list[str]:
    """품종 칸 -> 품종 목록(적힌 순서 = 주품종이 앞). 사전에 하나도 없으면 ['품종 미상']."""
    t = _MINOR_PAREN.sub(lambda m: " " * len(m.group(0)), grape)
    t = _MINOR_PCT.sub(lambda m: " " * len(m.group(0)) if int(m.group(1)) < 10 else m.group(0), t)
    first: dict[str, int] = {}
    for kw, label in _VARIETY_KW:
        i = t.find(kw)
        while i != -1:
            first[label] = min(first.get(label, i), i)
            t = t[:i] + "\0" * len(kw) + t[i + len(kw):]   # 같은 길이로 지워 위치 유지
            i = t.find(kw)
    return sorted(first, key=first.get) or ["품종 미상"]


def broad_kind(kind: str) -> str:
    for k in ("스파클링", "디저트", "로제", "화이트", "레드"):
        if k in kind:
            return k
    return "기타"


def max_score(critic: str):
    nums = re.findall(r"\b(8[5-9]|9[0-9]|100)\b", critic)
    return max(int(n) for n in nums) if nums else None


def vivino_of(v: str):
    m = re.search(r"(\d\.\d)", v)
    return float(m.group(1)) if m else None


def build_records(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        varreg = clean(r["varreg"])
        grape, region = split_varreg(varreg)
        out.append({
            "d": r["date"],
            "n": clean(r["name"]),
            "k": broad_kind(r["kind"]),
            "kd": clean(r["kind"]),
            "g": grape,
            "r": region,
            "c": country_of(region or varreg),
            "v": vivino_of(r["vivino"]),
            "s": clean(r["critic"]) if r["critic"] not in ("—", "") else "",
            "ms": max_score(r["critic"]),
            "m": clean(r["memo"]),
            "vt": varieties_of(grape),
        })
    return out


def top100_files() -> list:
    """drinks/ws-top100-<연도>.json을 최신 연도부터. 드로어에 띄울 만큼만 자른다."""
    files = sorted(DRINKS.glob("ws-top100-[0-9][0-9][0-9][0-9].json"), reverse=True)
    return files[:TOP100_SHOWN]


def norm_name(s: str) -> str:
    """이름 비교용 정규화 — 대소문자·구두점 차이를 없앤다.

    따옴표류는 **지워서** 붙인다("Stag\u2019s"→"stags", "\u2018The Estate\u2019"→"the estate").
    공백으로 바꾸면 "'the"처럼 조각난 토큰이 생겨 같은 와인을 못 알아본다.
    """
    s = s.lower()
    s = re.sub(r"[\u2018\u2019\u201c\u201d'\"]+", "", s)
    return " ".join(re.sub(r"[^a-z0-9가-힣]+", " ", s).split())


def drop_vintage(s: str) -> str:
    return " ".join(w for w in s.split() if not re.fullmatch(r"(19|20)\d\d|nv", w))


def load_top100(records: list[dict]) -> list[dict]:
    """Wine Spectator Top 100 목록을 최신 연도부터 읽어 [{year, items}, ...]로 돌려준다.

    각 항목에는 내 기록에 있는지(mine/exact)를 표시해둔다.

    생산자 매칭은 '와인명이 생산자명 + 공백으로 시작하는가'로 본다. 단순 포함으로
    보면 'Ridge'(Lytton Springs)가 'Pine Ridge ...'에 걸리고, 공백을 요구하지 않으면
    한 글자 생산자 'J'가 'Jim Jim ...'에 걸린다.

    exact=True는 **사실상 같은 와인**인 경우 — 빈티지가 같고, 로그에 적은 이름이
    공식 와인명 안에 다 들어가며(로그는 보통 더 짧게 적는다), 공식명에만 있는 말이
    리제르바·크뤼 같은 상급 큐베 표시가 아닐 때. 그래서 'Barbaresco 2021'을 마신
    기록은 'Barbaresco Rabajà Riserva 2021'(2026년 2위)과 같은 와인으로 치지 않는다.
    """
    sets = []
    for path in top100_files():
        items = json.loads(path.read_text(encoding="utf-8")).get("items", [])
        mark_top100(items, records)
        sets.append({"year": path.stem.rsplit("-", 1)[-1], "items": items})
    return sets


def mark_top100(items: list[dict], records: list[dict]) -> None:
    for t in items:
        producer = norm_name(t.get("producer", ""))
        vintage = t.get("vintage", "")
        wine = drop_vintage(norm_name(t.get("wine", "")))
        mine, exact = [], []
        for r in records:
            n = norm_name(r["n"])
            if not (producer and (n == producer or n.startswith(producer + " "))):
                continue
            mine.append(r)
            rest = set(drop_vintage(n[len(producer):].strip()).split())
            same_vintage = (vintage in r["n"]) if vintage != "NV" else ("nv" in n.split())
            words = set(wine.split())
            if same_vintage and rest and rest <= words and not (words - rest) & CUVEE_MARKERS:
                exact.append(r)
        hit = (exact or mine)
        t["mine"] = hit[0]["d"] if hit else None
        t["exact"] = bool(exact)



def place_of(r: dict, places: list[dict]) -> dict | None:
    """와인 한 병의 산지 지점. 지역 → (지역이 비면) 품종 칸 → 와인명 영문 키 순으로 찾는다.

    지역 칸만 먼저 보는 이유는 국가 판정 때와 같다 — '보르도 블렌드' 같은 품종명이
    산지 키워드에 걸리면 엉뚱한 곳에 찍힌다.
    """
    for text in (r["r"], r["g"]):
        if not text:
            continue
        for pl in places:
            if any(k in text for k in pl["keys"]):
                return pl
    for pl in places:
        if any(k in r["n"] for k in pl.get("name_keys", [])):
            return pl
    return None


def build_map(records: list[dict]) -> tuple[dict | None, list[str]]:
    """지도 데이터(패널·핀·산지별 병 수)를 만들고 각 레코드에 산지 id(`pl`)를 붙인다.

    밑그림이나 산지 사전이 없으면 (None, [])을 돌려주고 대시보드에서 지도만 빠진다.
    """
    if not (MAP_BASE.exists() and MAP_PLACES.exists()):
        for r in records:
            r["pl"] = None
        return None, []
    base = json.loads(MAP_BASE.read_text(encoding="utf-8"))
    dic = json.loads(MAP_PLACES.read_text(encoding="utf-8"))
    places, countries = dic["places"], dic["countries"]

    notes, used = [], {}
    for r in records:
        pl = place_of(r, places)
        if pl is None and r["c"] in countries:          # 사전에 없음 → 그 나라 중심점(광역)
            lat, lon = countries[r["c"]]["center"]
            pl = {"id": f"{r['c']}_broad", "name": f"{r['c']}(광역)", "country": r["c"],
                  "lat": lat, "lon": lon, "broad": True}
            notes.append(f"산지 사전에 없어 국가 중심점으로 표시: {r['n']} ({r['c']} · 지역 '{r['r'] or '-'}')")
        if pl is None:
            notes.append(f"지도에서 빠짐(국가 미상): {r['n']}")
            r["pl"] = None
            continue
        r["pl"] = pl["id"]
        used.setdefault(pl["id"], {**pl, "n": 0})["n"] += 1

    zooms = [p for p in base["panels"] if p.get("bbox")]
    def zoom_of(pl):
        for z in zooms:
            lo0, la0, lo1, la1 = z["bbox"]
            if lo0 <= pl["lon"] <= lo1 and la0 <= pl["lat"] <= la1:
                return z["id"]
        return "world"

    visited = {countries[r["c"]]["iso"] for r in records if r["c"] in countries}
    states = {dic["states"][pl["state"]] for pl in used.values() if pl.get("state")}
    panels = []
    for p in base["panels"]:
        pins = []
        for pl in sorted(used.values(), key=lambda x: -x["n"]):   # 큰 핀 먼저 → 작은 핀이 위에
            if zoom_of(pl) != p["id"]:
                continue
            x, y = project(p["proj"], pl["lon"], pl["lat"])
            pins.append({"p": pl["id"], "x": round(x, 1), "y": round(y, 1)})
        hl = ([sid for sid, _ in p["shapes"] if sid.startswith("us-") and sid[3:] in states]
              if p["id"] == "usw" else [sid for sid, _ in p["shapes"] if sid in visited])
        out = {"id": p["id"], "title": p["title"], "vb": p["vb"], "shapes": p["shapes"],
               "hl": hl, "pins": pins}
        if p.get("outline"):
            out["outline"] = p["outline"]
        if p.get("frames"):
            titles = {z["id"]: z["title"] for z in zooms}
            out["frames"] = [{**f, "title": titles[f["to"]],
                              "n": sum(pl["n"] for pl in used.values() if zoom_of(pl) == f["to"])}
                             for f in p["frames"]]
        panels.append(out)
    info = {pid: {"name": pl["name"], "n": pl["n"], "c": pl["country"],
                  "broad": bool(pl.get("broad")), "label": pl.get("label", ""),
                  "z": zoom_of(pl)} for pid, pl in used.items()}
    return {"panels": panels, "places": info}, notes


def main() -> int:
    if not LOG.exists() or not TEMPLATE.exists():
        print(f"필요한 파일이 없습니다: {LOG} / {TEMPLATE}", file=sys.stderr)
        return 1

    records = build_records(parse_log(LOG.read_text(encoding="utf-8")))
    if not records:
        print("와인 항목을 하나도 찾지 못했습니다 — 로그 표 형식을 확인하세요.", file=sys.stderr)
        return 1

    template = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        print(f"템플릿에 {PLACEHOLDER} 자리표시자가 없습니다.", file=sys.stderr)
        return 1

    wine_map, map_notes = build_map(records)           # records에 산지 id(pl)도 붙인다
    data = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    html = template.replace(PLACEHOLDER, data, 1)
    if wine_map:
        html = html.replace(PLACEHOLDER_MAP,
                            json.dumps(wine_map, ensure_ascii=False, separators=(",", ":")), 1)

    top = load_top100(records)
    if top:
        html = html.replace(
            PLACEHOLDER_TOP100,
            json.dumps([s["items"] for s in top], ensure_ascii=False,
                       separators=(",", ":")), 1)
        html = html.replace(
            PLACEHOLDER_TOP100_YEARS,
            json.dumps([s["year"] for s in top], ensure_ascii=False), 1)
    OUT.write_text(html, encoding="utf-8")

    for s in top:
        n_mine = sum(1 for t in s["items"] if t["mine"])
        n_exact = sum(1 for t in s["items"] if t["exact"])
        print(f"  Top100 {s['year']}: {len(s['items'])}개 주입 — "
              f"내 기록과 겹침 {n_mine}개(같은 와인 {n_exact}개)")

    kinds = Counter(r["k"] for r in records)
    countries = Counter(r["c"] for r in records)
    sessions = {r["d"] for r in records} - {UNDATED}   # 미분류는 '자리'가 아님
    n_undated = sum(1 for r in records if r["d"] == UNDATED)
    print(f"✓ {OUT.relative_to(ROOT)} 생성 — {len(records)}종 / "
          f"{len(sessions)}개 시음 자리"
          + (f" (+ 미분류 {n_undated}종)" if n_undated else ""))
    print(f"  종류: {dict(kinds)}")
    print(f"  국가: {dict(countries.most_common())}")
    grapes = Counter(v for r in records for v in r["vt"])
    print(f"  품종: {dict(grapes.most_common())}")
    if wine_map:
        by_zone = Counter()
        for pl in wine_map["places"].values():
            by_zone[pl["z"]] += pl["n"]
        print(f"  지도: 산지 {len(wine_map['places'])}곳 · 미국 서부 {by_zone['usw']}병 · "
              f"서유럽 {by_zone['weu']}병 · 그 밖 {by_zone['world']}병")
    for n in map_notes:
        print(f"  ⚠ {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
