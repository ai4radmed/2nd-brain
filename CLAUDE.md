# 2nd-brain-setup — 컴포넌트 설치 안내

`2nd-brain` 시스템의 컴포넌트를 *자기 머신에 깔기 위한 절차* 만 담는 저장소.

## 짝 저장소와의 관계

| 저장소 | 역할 | 위치 | 공개 |
|---|---|---|---|
| **2nd-brain-setup** (이곳) | 컴포넌트 설치 안내 — native·container 두 옵션 | `~/projects/2nd-brain-setup/` · GitHub `ai4radmed/2nd-brain-setup` | 공개 |
| **2nd-brain-vault-guide** | PARA 운영 방법론·템플릿·빈 vault 골격 — 깔린 *뒤* 의 운영 | `~/projects/2nd-brain-vault-guide/` · GitHub `ai4radmed/2nd-brain-vault-guide` | 공개 |
| **2nd-brain-vault** | knowledge·sources 데이터 — Ben 본인의 정본 | `~/projects/2nd-brain-vault/` (WSL2 ext4 native), Syncthing 동기 | 비공개 |

비유:

- **setup** = 건물을 짓는 절차서
- **vault-guide** = 건물 안에서의 생활 규칙
- **vault** = 그 건물에서 살아가는 한 사람의 살림살이

## 콘텐츠 범위

| 담는 것 | 안 담는 것 |
|---|---|
| 컴포넌트별 설치 절차 (native·container) | 운영 방법론 (vault-guide 가 권위) |
| 명령은 한 줄씩 paste 가능 형태 | 실제 Dockerfile·compose 자산 |
| 트러블슈팅·검증 명령 | Dr. Ben 본인의 prod 운영 자산 (`openclaw-config` 등 비공개) |

## 작성 원칙

- **명령은 한 줄씩 paste 가능** — `\` 줄바꿈 없이.
- **공식 docs 가 권위** — 공식 절차에서 벗어나지 않는다. 변형이 필요하면 *왜* 를 명시.
- **secret 직접 박지 않음** — onboarding 위저드·환경변수로 흘려보냄. 문서엔 placeholder (`<your-bot-token>`) 로만 표기.
- **한국어 존댓말** — 한국어 청중 대상이라 vault 문서들과 동일 톤.

## 권위 위계

| 영역 | 정본 위치 |
|---|---|
| 컴포넌트 설치 절차 | 이 저장소 (자기참조) — 공식 docs 를 *어떻게 따라할지* 의 한국어 정리 |
| 운영 방법론 (PARA·companion note·brainify) | `2nd-brain-vault-guide` |
| 데이터 운영 규약 | `2nd-brain-vault/CLAUDE.md` (얇은 layer + guide `@`-import) |
| OpenClaw 자체 (이미지·CLI·설치 스크립트) | 공식 <https://docs.openclaw.ai> |
