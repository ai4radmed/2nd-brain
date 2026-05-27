# 2nd-brain AI 검색 전략 — cloud LLM retrieval 아키텍처

> 자라나는 vault 를 **클라우드 LLM 웹앱(Claude.ai · Gemini)** 이 검색·활용하게 만드는 설계.
> 컨텍스트 윈도우 한계를 *검색(retrieval)* 으로 우회하는 것이 핵심. (2026-05-28 작성)

## 문제

Gmail 브레인화가 1단계 안정화에 들어서며 활용 단계로 이행. 클라우드 Claude/Gemini 웹앱이 vault 를
검색할 수 있어야 하는데:

- **규모**: 현재 knowledge ≈ **675 노트 / 7MB / 약 180만 토큰** — 이미 단일 컨텍스트(1M)를 초과, 계속 증가.
- → **vault 를 통째로 컨텍스트에 넣는 접근은 출발부터 불가능.**

## 원칙: 컨텍스트가 아니라 **검색**

vault 를 통째로 넣으려는 순간 진다. 설계의 제1원칙:

> **질의마다 관련 조각만 검색해 넣는다(RAG).** 데이터가 늘어도 *인덱스만* 커지고 LLM 이 보는 양은
> top-k 로 **bounded** → 컨텍스트 한계와 무관해진다.

이 원칙이 깨지면(=통째 로드 시도) 나머지 설계는 무의미하다.

## 아키텍처: 정본 1개 + 검색 인터페이스, 앱별 최적 커넥터

```
        [살아있는 vault = 단일 진실원본]   (사본·업로드 금지 — 드리프트 방지)
                      │  검색층(retrieval) — 통째로 안 줌, 관련 스니펫만 반환
        ┌─────────────┴──────────────┐
   Claude.ai ──원격 MCP 커넥터──┐      Gemini ── Google Drive 그라운딩
   (search_vault / get_note)    │      (vault md 가 이미 Drive 동기체인에 존재)
                                ▼
              하이브리드 검색(키워드 grep + 임베딩 시맨틱)
              brainify commit / 드레인 때 증분 인덱싱
```

**두 앱이 같은 정본 vault 를 각자 최적 경로로 질의** — 사본을 만들지 않는다.

- **Gemini**: vault 마크다운이 **이미 Google Drive 동기 체인**(SyncThing → Drive)에 있음 → Gemini 웹앱이
  Drive 를 네이티브로 검색·그라운딩. **새 인프라 0 의 최단 경로.** (.md 그라운딩이 약하면 핵심 MOC/요약 노트만
  Google Docs 로 미러링하면 품질↑.)
- **Claude.ai**: **원격 MCP 커넥터**가 정답에 가깝다. `search_vault`·`get_note` 도구를 노출하는 self-hosted
  MCP 서버 → 질의→관련 조각만 반환. **OpenClaw 게이트웨이를 이미 self-host** 중이므로 그 옆이 자연스러운 거처.
  - *임시 대안*: Claude Projects / Drive 커넥터 — 쉽지만 **크기 상한 + 사본 드리프트** → *자라는 전체 vault* 엔 부적합. 출발점용.

## 검색 품질의 절반은 인프라가 아니라 **노트 품질**

retrieval 정확도 = 노트 품질. 이미 갖춘 것이 곧 설계의 절반이다:

- **PARA + MOC/허브 노트** — 작고 항상 로드 가능한 "지도"로 오리엔트 후 drill-down.
- **atomic · 확정본만 · dedup · 요약** (brainify 의 distill 규율: 회의록 확정-only, 인맥 related_events 등) → 신호↑·노이즈↓.
- **companion note(knowledge/)가 검색 대상, PDF(sources/)는 leaf** — 정제 마크다운만 색인.
- **참고 노이즈 제외**: 외부 docs 미러(예: openclaw mirror ~450p) 같은 대량 참조는 **인덱스에서 제외**해 신호를 지킨다.

→ brainify distill 규율을 지키는 것 = RAG 정확도 유지. 별개 작업이 아니다.

## 단계적 경로 (권장)

1. **즉시(저비용)**: Gemini Drive 검색(vault 가 이미 거기) + Claude.ai Drive 커넥터 → 인프라 0 으로 "검색 가능" 확보·한계 체감.
2. **본설계(견고·확장)**: self-hosted **MCP 검색 서버**(하이브리드 키워드+임베딩, 증분 인덱싱) — 게이트웨이 옆.
   Claude.ai 원격 MCP 연결. 정본 1개를 두 앱이 공유.
3. **품질 유지**: 영역별 MOC/인덱스 노트(자동 생성) + brainify distill 규율 지속.

## 보안·노출면 (반드시)

- **클라우드 LLM 검색 = 유출면.** 진료·재정 노트가 클라우드에 검색되면 위험.
- self-hosted 검색층의 핵심 이점 = **어느 PARA 를 색인/노출할지 통제**(진료·재정 제외 등). Drive 경로는
  *Google 이 이미 데이터를 보유* 함을 전제로 판단.
- **MCP 서버 노출 비용**: claude.ai(클라우드)가 WSL2 의 서버에 닿으려면 터널(cloudflared/tailscale) + 인증 필요 —
  본설계의 유일한 실질 인프라 비용. Gemini+Drive 경로는 엔드포인트 노출이 없어 그 점에선 더 저렴.

## 한 줄 결론

> **"vault 를 넣지 말고 검색하라."** 정본 vault 1개를 **self-hosted MCP 검색(Claude) + Drive 그라운딩(Gemini)**
> 으로 노출하고, brainify 의 distill·MOC 규율로 검색 신호를 유지한다. 컨텍스트 한계는 retrieval 로 사라지고,
> 데이터 증가는 인덱스 증분으로 흡수된다.

## 관련

- distill 규율(검색 신호의 절반): `~/.claude/skills/brainify/` · 회의록 확정-only 정책(SKILL.md §3-★).
- 동기 체인(vault ∈ Drive): [multi-device-sync.md](./multi-device-sync.md).
- self-host 거처: OpenClaw 게이트웨이 [openclaw-docker-operations.md](./openclaw-docker-operations.md).
- 파싱→정제 파이프라인(검색 대상 마크다운 생산): [2nd-brain-parser-strategy.md](./2nd-brain-parser-strategy.md).
