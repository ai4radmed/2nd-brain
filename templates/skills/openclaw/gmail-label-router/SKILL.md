---
name: gmail-label-router
description: Gmail 라벨에 따라 *결정론적* 후속 동작을 수행하는 라우터 (LLM 추론 없음). **자연어 트리거 (이런 발화에 이 스킬을 부른다)**: "1 저장 처리해줘"·"저장 라벨 정리해줘"·"라벨 메일 받아줘" → run.py 실행 / "먼저 몇 건인지 봐줘"·"확인만" → run.py --dry-run. 현재 라우트 — 라벨 "1 저장" 메일의 스레드(본문+첨부)를 저장 디렉토리에 캡처한 뒤 라벨을 "9 완료" 로 교체. 모든 로직은 외부 Python runner(run.py)에 있고, 에이전트는 고른 명령만 1회 실행한다 — **직접 실행, 단계 추론·하위 에이전트 위임 금지**.
allowed_tools: [bash]
---

# gmail-label-router

라벨 기반 **결정형** 후속 처리. 동사를 하나씩 추가하며 키운다. 판단이 0 이라 LLM 추론을 핫패스에서 제거 → 빠르고 watchdog 종료·고아(미아) 위험이 없다.

> 📦 이건 **예제·템플릿**입니다. 적용 전 `run.py` 의 env(`GMAIL_ROUTER_ACCOUNT`)·저장경로를 본인 환경에 맞게 고치세요. **라벨("1 저장"→"9 완료")은 고정 규칙** — 코드를 고치지 말고 Gmail 에 그 라벨을 만들어 쓰세요. 설치·적응법은 같은 폴더 [README.md](./README.md).

## 호출

자연어 트리거는 frontmatter `description` 이 담당한다(에이전트가 거기서 의도 매칭). 아래는 *자연어가 아니라* 에이전트가 고를 **실행 모드**다 — 사용자 발화에 맞는 모드를 골라 **그 명령만 1회** 실행한다.

| 모드 | 사용자 발화 예 | 명령 |
|---|---|---|
| 실행 | "1 저장 처리해줘", "라벨 메일 정리해줘" | `python3 ~/.openclaw/workspace/skills/gmail-label-router/run.py` |
| 확인(검색만) | "먼저 몇 건인지 봐줘", "확인만" | `python3 ~/.openclaw/workspace/skills/gmail-label-router/run.py --dry-run` |

> 에이전트는 고른 명령을 **그대로 1회 실행**한다. 단계를 직접 추론·반복하거나 하위 에이전트로 위임하지 말 것. 비가역(라벨 변경) 동작이라 망설여지면 먼저 `--dry-run` 으로 건수만 보고한 뒤 실행.

## 현재 라우트

- **1 저장** → 스레드(본문 `_thread.md` + 첨부)를 저장 디렉토리(`GMAIL_ROUTER_INBOX`, 기본 `~/.openclaw/workspace/attachments`)의 스레드별 폴더에 캡처 → 라벨 **9 완료** 로 교체.

## 설계 원칙

- **판단 0** = LLM 추론 핫패스에서 제거 (응답 빠름·watchdog/고아 없음).
- **fail-safe**: 캡처 *성공 시에만* 라벨 교체 (실패 시 라벨 유지 → 유실 방지).
- **멱등성**: `_thread.md` 프론트매터의 `gmail_thread_id`+`message_count` 로 중복 캡처 방지 — 동일 스레드 재유입 시 재캡처 생략(중복 0), 메시지 수 변동 시 덮어쓰기 갱신.
- **thread 단위** 처리 + 건별 *한 줄 진행 출력* (watchdog 침묵 방지).
- 환경변수: `GMAIL_ROUTER_ACCOUNT`(필수, 본인 계정), `GMAIL_ROUTER_INBOX`(저장 위치).

## 새 라우트 추가법

run.py 의 라우트 상수(`SRC_LABEL`/`DONE_LABEL`)·`process_thread` 패턴을 본떠 (src_label → action) 한 쌍을 추가한다. SKILL.md 는 짧게 유지 (에이전트 추론 표면 최소화).

## 알려진 한계

- 멱등성은 **00_inbox 범위**(아직 brainify 안 된 버퍼)다. 이미 brainify되어 vault로 옮겨간 스레드가 다시 `1 저장`으로 들어오면, vault 전체 dedup은 brainify 단계(노트 frontmatter의 threadId 대조)가 담당한다.
- 라벨 검색은 `label:"<이름>"` 쿼리 사용 — 라벨명에 공백이 있어 결과가 0 이면 `--dry-run` 으로 확인 후 쿼리 형태 조정.
