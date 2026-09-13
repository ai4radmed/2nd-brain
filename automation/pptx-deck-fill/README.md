# pptx-deck-fill

**markdown 덱 소스 → pptx 산출물.** 발표·회신용 pptx 의 작업 표면을 마크다운으로 옮긴다.
마크다운이 내용 권위, pptx 는 매번 재생성되는 산출물이다.

```
hwpx:  <stem>_fillable.md  ── fill.py ──▶  <stem>_filled.hwpx
pptx:  <stem>_deck.md      ── fill.py ──▶  <출력 pptx>
```

설계가 `hwpx-report-fill` 과 평행하다 — **양식은 불변 베이스, 값만 주입, 산출물은 멱등 재생성.**

## 왜 이 방식인가 (2026-09-13 Dr. Ben 결정)

| 방안 | 판정 |
|---|---|
| pptx 직접 편집 | 바이너리라 AI 왕복편집·diff·grep·버전추적 전부 불가. 문안 SSOT 가 pptx 안으로 들어가 원본 노트와 이중화 |
| Slidev → pptx export | **실측: 슬라이드를 통째로 PNG 로 굽는다(텍스트 런 0개, 16:9 고정).** 수신처가 취합·재편집·텍스트검색 불가 → 제출물 부적합 |
| **이 도구** | 편집은 마크다운, 산출물은 **네이티브 텍스트 pptx**. 표지·판형·서식은 양식에서 승계 → 수신처 양식 이탈 없음 |

Slidev 는 자기 발표용 덱(`_slidable.md` → `_exported.pdf`)에는 여전히 정답이다.
이 도구는 **"남의 양식에 맞춰 제출해야 하는 pptx"** 전용이다.

## 사용

```bash
fill.py <deck>.md              # frontmatter 의 output 으로 생성
fill.py <deck>.md -o out.pptx  # 명시적 출력
fill.py <deck>.md --dry-run    # 생성 없이 슬라이드 수·줄 수·최장 줄 점검
```

기존 산출물이 있으면 `.pptx.bak` 로 백업한 뒤 덮어쓴다.

## 덱 마크다운 형식

```markdown
---
base:   sources/.../양식.pptx      # vault-root 상대 또는 절대경로
output: sources/.../산출물.pptx
title_size: 2400                   # 선택 (1/100 pt)
body_size:  1600                   # 선택 — ○ 줄
sub_size:   1350                   # 선택 — - 줄
---

## 슬라이드 제목

○ 큰 항목 (굵게)
- 하위 항목
- 하위 항목

```notes
발표 스크립트. 슬라이드 노트로 들어간다.
```
```

- `## ` = 새 슬라이드. base 의 **표지(slide1)는 보존**되고 그 뒤에 붙는다.
- 두 단계(`○` / `-`)만 쓴다 — 원 양식의 서식 체계.
- 노트 블록은 선택. 없으면 그 슬라이드에 notesSlide 를 만들지 않는다.
- 한 줄 62자를 넘으면 `--dry-run` 이 ⚠ 로 알린다(슬라이드에서 줄바꿈됨).

## 양식(base)에 필요한 것

| 파트 | 용도 |
|---|---|
| `slide1` | 표지 — 그대로 승계 |
| `slide2` | 본문 모델 — 서식 기준 (실제 XML 은 이 도구가 생성) |
| `slideLayout3` | 모든 본문 슬라이드가 참조 |
| `notesMaster1` | 발표자 노트용. **없으면 노트가 안 붙는다** |

양식의 마스터·레이아웃·테마·미디어는 손대지 않고 전량 승계하며, `slide2` 이후와
`notesSlides` 만 재생성한다.

## 검증 (생성 후 권장)

1. **텍스트 대조** — 이전본(`.bak`)과 `<a:t>` 전량 비교로 문안 손실 0 확인.
2. **구조 검증** — 모든 `.rels` Target 존재 / `[Content_Types].xml` 커버리지 /
   `sldIdLst` r:id 해석 / 고아 슬라이드 / 노트 역참조 일치.
3. **시각 확인** — PowerPoint·한컴에서 열어 줄바꿈·넘침 확인. *(WSL2 에 `libreoffice-impress`
   가 없으면 headless PDF 변환은 불가 — Writer/Calc 만으로는 pptx 를 로드하지 못한다.)*

## 의존성

없음. python3 stdlib (`zipfile` + 문자열 템플릿)만 쓴다.
python-pptx 는 슬라이드 복제를 정식 지원하지 않아 deepcopy 우회가 필요한데,
그 우회보다 XML 직접 생성이 서식 재현에 더 정확해서 채택하지 않았다.

## 첫 적용

`2026-09_원안위-제4차종합계획-의견수렴-학회간담회` — KARP 의학위원장 회신 PPT
(`2026-09-13_KARP_4차종합계획_회신PPT_deck.md` → 8슬라이드 + 노트 7매).
