#!/usr/bin/env python3
"""drinks/wine-log.md -> drinks/dashboard.html 생성기.

와인 로그를 파싱해서 대시보드 템플릿(scripts/wine_dashboard_template.html)에
데이터를 주입한다. 로그에 와인을 추가한 뒤 이 스크립트를 다시 실행하면
대시보드의 모든 수치·목록이 자동으로 갱신된다.

    python3 scripts/build_wine_dashboard.py
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "drinks" / "wine-log.md"
TEMPLATE = ROOT / "scripts" / "wine_dashboard_template.html"
OUT = ROOT / "drinks" / "dashboard.html"
PLACEHOLDER = "/*__DATA__*/[]"
UNDATED = "미분류"  # 마신 날짜를 모르는 기록을 묶는 섹션명 (템플릿 JS와 값이 같아야 함)

# 지역 표기 -> 국가. 위에서부터 먼저 매칭되는 것을 쓴다(하위 산지가 먼저 와야 함).
REGION_COUNTRY = [
    ("말보로", "뉴질랜드"), ("뉴질랜드", "뉴질랜드"),
    ("모젤", "독일"), ("자르", "독일"), ("독일", "독일"),
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

# 차트에서 개별 항목으로 뽑는 품종(나머지는 "기타"로 묶임)
VARIETY_KEYS = [
    ("샤르도네", ["샤르도네"]),
    ("피노 누아", ["피노 누아"]),
    ("카베르네 소비뇽", ["카베르네 소비뇽"]),
    ("보르도 블렌드", ["보르도 블렌드"]),
    ("소비뇽 블랑", ["소비뇽 블랑"]),
    ("네비올로", ["네비올로"]),
    ("시라/시라즈", ["시라"]),
]


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
        if ("와인" in line and "종류" in line) or re.match(r"^\|[-\s|]+$", line):
            continue  # 헤더 / 구분선
        cols = [c.strip() for c in line.strip("|").split("|")]
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


def varieties_of(varreg: str) -> list[str]:
    hits = [label for label, kws in VARIETY_KEYS if any(k in varreg for k in kws)]
    return hits or ["기타"]


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
            "vt": varieties_of(varreg),
        })
    return out


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

    data = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(template.replace(PLACEHOLDER, data, 1), encoding="utf-8")

    kinds = Counter(r["k"] for r in records)
    countries = Counter(r["c"] for r in records)
    sessions = {r["d"] for r in records} - {UNDATED}   # 미분류는 '자리'가 아님
    n_undated = sum(1 for r in records if r["d"] == UNDATED)
    print(f"✓ {OUT.relative_to(ROOT)} 생성 — {len(records)}종 / "
          f"{len(sessions)}개 시음 자리"
          + (f" (+ 미분류 {n_undated}종)" if n_undated else ""))
    print(f"  종류: {dict(kinds)}")
    print(f"  국가: {dict(countries.most_common())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
