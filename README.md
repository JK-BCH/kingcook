# 👑🍳 kingcook

**나만의 요리 데이터베이스** — 가진 재료와 조리 기구를 등록해두면,
Claude Code가 그에 맞춰 초보도 할 수 있는 레시피를 추천해준다.

## 어떻게 쓰나
이 레포에서 Claude Code 세션을 열고 말만 하면 된다:

- 🥚 **등록** — "계란 6개, 두부 한모 있어. 에어프라이어 샀어."
- 🍳 **추천** — "오늘 뭐 해먹지?" → 지금 재료로 가능한 요리 3~5개
- 📖 **저장** — "이거 맘에 들어" → `recipes/`에 보관
- ✍️ **기록** — "이거 만들었어" → `history/log.md`

## 구조
```
data/
  ingredients.json  # 재료 (냉장/냉동/실온/양념)
  equipment.json    # 조리 기구
  profile.json      # 취향·알레르기·난이도
recipes/            # 저장한 레시피
history/log.md      # 만든 요리 기록
CLAUDE.md           # Claude 운영 규칙 (동작 방식·스키마)
```

> 운영 규칙과 데이터 스키마는 [`CLAUDE.md`](./CLAUDE.md) 참고.

## 🍷 와인 대시보드
마신 와인 기록(`drinks/wine-log.md`)을 통계·검색·필터로 볼 수 있는 단일 페이지.

**👉 https://jk-bch.github.io/kingcook/** (GitHub Pages)

- `main`에 푸시하면 [`.github/workflows/pages.yml`](./.github/workflows/pages.yml)이 로그에서 대시보드를 다시 만들어 자동 배포한다.
- 사이트에 올라가는 건 대시보드 한 장뿐이고, 재료·프로필·레시피 같은 나머지 파일은 사이트에 포함되지 않는다.
- 수동으로 만들려면 `python3 scripts/build_wine_dashboard.py` → `drinks/dashboard.html`.
