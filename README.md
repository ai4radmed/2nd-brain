# 2nd-brain-setup

`2nd-brain` 시스템을 자기 머신에 설치하기 위한 안내 모음. 외부인이 따라 깔 수 있도록 **컴포넌트별 설치 절차** 만 담는다. 운영 방법론은 별도 저장소.

## 짝 저장소

| 저장소 | 역할 | 공개 |
|---|---|---|
| **2nd-brain-setup** (이곳) | 컴포넌트 설치 안내 — native 와 container 두 옵션 | 공개 |
| **[2nd-brain-vault-guide](https://github.com/ai4radmed/2nd-brain-vault-guide)** | PARA 운영 방법론·템플릿·빈 vault 골격 (깔린 *뒤* 의 운영) | 공개 |
| **2nd-brain-vault** | 각자의 knowledge·sources 데이터 (개인 저장소·Syncthing 동기 권장) | 비공개 |

## 컴포넌트

| 컴포넌트 | 역할 | 설치 안내 |
|---|---|---|
| **OpenClaw 게이트웨이** | 2nd-brain 운영체제 (control plane) — Telegram 입구·cron·다중 에이전트 워크스페이스 통합 | [native](./openclaw-native.md) · [container](./openclaw-container.md) |

향후 brain-pdf (PDF 파서)·webmail-watch 등이 추가될 예정.

## OpenClaw — native vs container 결정 가이드

둘 다 같은 게이트웨이를 띄우지만 셋업 비용과 격리 수준이 다르다.

|  | native | container |
|---|---|---|
| **셋업 비용** | 가장 빠름 — 한 줄 인스톨러 | Docker 설치 + 이미지 빌드 (~수 분) |
| **격리** | 호스트 fs·네트워크 직접 사용 | 컨테이너 boundary |
| **데이터 위치** | `~/.openclaw/` (호스트) | `~/.openclaw/` (호스트, bind-mount) |
| **업데이트** | `openclaw update` | 이미지 재빌드 |
| **권장 상황** | 본인 머신, 영속 운영, *낮은 진입장벽 우선* | 데모·테스트·다중 인스턴스, *호스트 오염 회피 우선* |

처음 깔아 본다면 **native** 가 가장 단순하다. 컨테이너는 prod 환경을 흔들지 않고 데모·테스트 해보고 싶거나 공유 호스트 (VPS 등) 에서 깔끔한 boundary 가 필요할 때 적합.

## 작성 약속

각 안내 문서의 명령은 모두 **한 줄씩 그대로 복사·붙여넣기 가능** 한 형태로 작성한다 (`\` 줄바꿈 없음).
