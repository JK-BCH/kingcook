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
