# 2nd-brain — 공개 운영 저장소

`2nd-brain` 시스템의 **공개 운영층** 저장소. 새 사용자가 *clone 하는 단일 입구*이며, 설치 절차·운영 방법론·vault 골격·부트스트랩을 한곳에 담는다. 실제 개인 데이터는 여기 들어오지 않는다.

## 3-tier 모델에서의 위치

| tier | 저장소 | 내용 | 가시성 |
|---|---|---|---|
| **공개 운영** *(이곳)* | `ai4radmed/2nd-brain` | 설치문서·방법론·템플릿·골격·bootstrap | 공개 |
| **데이터** | `2nd-brain-vault` | knowledge + sources + 얇은 `CLAUDE.md` 로더 | 비공개 (SyncThing) |
| **개인 운영** | (별도 비공개 repo, 예정) | 개인 가정 박힌 스킬·슬래시명령·개인 config | 비공개 |

원리: **데이터(무엇을 안다) / 코드(어떻게 한다, 공유가능) / 설정(나는 누구다, 개인)** 의 분리. 이 repo 는 *코드(공유가능)* tier.

## 디렉토리

| 경로 | 내용 |
|---|---|
| `docs/` | 설치 절차 + 운영 방법론(`brain-system/`·`security/`·`setup/`). `docs/brain-system/README.md`·`claude-instruction-layers.md` 는 vault 얇은 `CLAUDE.md` 가 `@`-import 하는 대상 |
| `templates/` | `vault-skeleton/` (빈 PARA 골격) + 노트 템플릿 |
| `bootstrap.sh` | 새 vault 생성 — 골격 복사 + 얇은 `CLAUDE.md` 로더 생성 + git init (멱등·안전장치) |

## 사용 흐름

1. 이 repo 를 `~/projects/2nd-brain` 에 clone.
2. `docs/` 의 설치 절차로 OpenClaw 컨테이너 등 컴포넌트 구축.
3. `./bootstrap.sh` 로 자기 `2nd-brain-vault` 생성 (데이터 tier).
4. 생성된 vault 의 얇은 `CLAUDE.md` 가 이 repo 의 `docs/brain-system/` 을 `@`-import → 운영 규약 적용.
5. `sources/00_inbox/` 에 자료 투입 → brainify 로 흡수.

## 작성 원칙

- **명령은 한 줄씩 paste 가능** — `\` 줄바꿈 없이.
- **공식 docs 가 권위** — 변형이 필요하면 *왜* 를 명시.
- **secret 직접 박지 않음** — placeholder(`<your-bot-token>`)·환경변수·onboarding 위저드로만.
- **한국어 존댓말** — 한국어 청중 대상.
- **공개 안전** — 개인 가정(계정·경로·조직)이 박힌 내용은 이 repo 에 넣지 않는다. 그런 것은 데이터 tier(vault) 또는 개인 운영 repo 로.

## 권위 위계

| 영역 | 정본 위치 |
|---|---|
| 컴포넌트 설치 절차 | 이 repo `docs/` |
| 운영 방법론 (PARA·companion note·brainify) | 이 repo `docs/brain-system/` |
| 다기기 동기 — 전략·실행 | 전략·카테고리 = 이 repo `docs/setup/prerequisite-repos.md`, 실행 절차(git+SyncThing) = `docs/multi-device-sync.md`. **실제 repo 목록 권위 = vault `repos.md`**, 일괄 실행 = 슬래시 명령 `/git-routine` |
| 데이터 운영 규약 | `2nd-brain-vault/CLAUDE.md` (얇은 layer + 본 repo `@`-import) |
| OpenClaw 자체 (이미지·CLI·설치 스크립트) | 공식 <https://docs.openclaw.ai> |

## 메타

- `2nd-brain-setup` 에서 rename (2026-05-23). 동시에 구 `2nd-brain-vault-guide` 의 방법론·템플릿·config 를 흡수 — 공개 저장소 둘을 하나의 단일 입구로 통합.
- 2026-05-25 — `2nd-brain-docker`(docker 실행자산: openclaw-gateway 이미지·compose·2nd-brain-parser·scripts·docs)도 `docker/`·`docs/` 로 흡수. `2nd-brain-vault-guide`·`2nd-brain-docker` 로컬 삭제(고유 자산 0 확인) → **공개 운영층 단일 `2nd-brain` 통합 완료**. (GitHub repo 2개 삭제는 `delete_repo` scope 필요 — 별도.)
