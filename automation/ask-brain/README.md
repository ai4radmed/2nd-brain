# ask-brain — 텔레그램에서 2nd-brain vault 검색·추론 (마운트 없는 비동기 RAG)

PC 앞에 없어도 텔레그램으로 2nd-brain 의 지식을 꺼내 쓰기 위한 **MVP 스켈레톤**.
무거운 검색·추론을 OpenClaw 게이트웨이(컨테이너) 안에서 동기로 돌리지 않고, **호스트 Claude Code 에 비동기 위임**한다.

## 왜 이 구조인가 (설계 원칙)

- **vault 를 컨테이너에 마운트하지 않는다.** 재무·PHI·인맥이 든 vault 를 *무인·자율·외부입력* 컴포넌트(OpenClaw)
  안에 넣으면 인젝션→egress 유출 위험(MERGE 덱 슬20 공격면). vault 는 **호스트에 남고, "답만" 텔레그램으로 건너간다.**
- **비동기 = 분리(decouple)**, 느림이 아니다. systemd *path* 유닛(파일 생기면 즉시 발화)이라 응답은 수 초 — 거의 대화형.
  무거운 추론을 게이트웨이 밖에서 돌려 idle/polling watchdog 도 회피.
- 한 줄: **vault 는 호스트에, 답만 텔레그램으로.** (MERGE 덱 슬22 = 2nd-brain keystone 도식의 운영형)

## 3조각

```
텔레그램 질문
   │  (OpenClaw 에이전트가 트리거 스킬 1회 실행)
   ▼
① enqueue  ~/.openclaw/workspace/skills/ask-brain/{SKILL.md,enqueue.sh}   ← 컨테이너(공유 마운트)
   │  질문+chat_id 를 job 으로 적고 즉시 끝 (watchdog 회피)
   ▼  ~/.openclaw/workspace/ask-brain-queue/jobs/<id>.json
② watcher  ask-brain.path  → DirectoryNotEmpty → ask-brain.service                ← 호스트 systemd(user)
   ▼
③ runner   ask-brain.sh : cd vault → claude -p (READ ONLY, --output-format json)  ← 호스트 Claude Code
   │  .result 를 docker exec <gw> node /app/dist/index.js message send --channel telegram --target <chat_id>
   ▼
텔레그램으로 답 회신  (job 은 done/ 으로 이동 → 큐 비워져 재무장)
```

- ①은 openclaw-workspace repo(git), ②③은 2nd-brain repo(git). 큐(`ask-brain-queue/`)는 **런타임 상태 → gitignore**.

## 설치 (Dr. Ben 가 실행 — 자동 활성화 안 함)

```bash
# 0. 권한
chmod +x ~/projects/2nd-brain/automation/ask-brain/ask-brain.sh \
         ~/.openclaw/workspace/skills/ask-brain/enqueue.sh

# 1. 회신 대상(자기 텔레그램 chat id) 설정 — 단일 사용자 MVP 기본값
systemctl --user edit ask-brain.service        # [Service] / Environment=ASK_BRAIN_TARGET=<chat_id>

# 2. systemd user 유닛 링크 + path 워처 활성
ln -sf ~/projects/2nd-brain/automation/ask-brain/ask-brain.service ~/.config/systemd/user/
ln -sf ~/projects/2nd-brain/automation/ask-brain/ask-brain.path    ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ask-brain.path

# 3. OpenClaw 가 트리거 스킬을 인식하도록 게이트웨이 재시작 (workspace/skills 스캔)
#    (docker 재시작 또는 openclaw 재로드 — 현 환경 절차에 따름)

# 4. 큐 디렉터리를 openclaw-workspace .gitignore 에 추가 (런타임 상태, 동기 금지)
echo 'ask-brain-queue/' >> ~/.openclaw/workspace/.gitignore
```

## 수동 테스트 (게이트웨이 없이 ③만)

```bash
mkdir -p ~/.openclaw/workspace/ask-brain-queue/jobs
echo '{"id":"t1","question":"IAEA 벨라루스 일정이 언제였지?","reply_channel":"telegram","reply_target":""}' \
  > ~/.openclaw/workspace/ask-brain-queue/jobs/t1.json
ASK_BRAIN_TARGET="" ~/projects/2nd-brain/automation/ask-brain/ask-brain.sh
tail -n 20 ~/.local/state/ask-brain.log   # target 없으면 답을 로그로만 출력
```

## 환경변수

| 변수 | 기본 | 뜻 |
|---|---|---|
| `ASK_BRAIN_TARGET` | (없음) | 회신 텔레그램 chat id 기본값. job 에 reply_target 있으면 그게 우선 |
| `ASK_BRAIN_VAULT` | `~/projects/2nd-brain-vault` | 검색 대상 vault |
| `ASK_BRAIN_MODEL` | `claude-opus-4-7` | 모델 |
| `ASK_BRAIN_CAP` | `0.50` | 질문당 $ 상한 |
| `CLAUDE_TIMEOUT` | `300` | claude 호출당 초 |

## 검증·확장 TODO (스켈레톤 → 운영)

- [ ] **회신 대상 동적화**: OpenClaw 트리거가 *현재 대화 chat id* 를 `enqueue.sh "<질문>" "<chat_id>"` 로 넘기게.
      (현재는 못 넘기면 `ASK_BRAIN_TARGET` 기본값 — 단일 사용자라 충분하나 그룹/다중 대화면 필수)
- [~] **read-only flag**: `--allowedTools` 표기 정상 동작, 읽기 검색 성공(2026-06-18). Edit/Write 차단은 명시적
      미테스트(질의가 쓰기 시도 안 함) — 프롬프트의 READ ONLY 가 보조 방어. 추후 쓰기시도 케이스로 한 번 확인 권장.
- [x] ~~`message send --token`~~ → **토큰 불필요 확정(2026-06-18 실측)**: `message send` 에 `--token` 옵션 자체가
      없음(컨테이너 CLI 가 게이트웨이에 이미 인증). 스크립트에서 제거함. 호스트 ②③ + 텔레그램 송신 leg **검증 완료**.
- [ ] **검색 품질 2차**: 1차는 에이전틱 grep+read. 의미 검색이 필요하면 vault 임베딩 인덱스(민감 폴더 제외) 추가.
- [ ] **다중 PC**: 큐는 gitignore 라 비동기. 게이트웨이가 활성인 PC 에서만 job 생성·처리되게(단일 발화 원칙).
      필요 시 `/cron` 토글에 `ask-brain.path` 편입 검토.
- [ ] 긴 답 분할(텔레그램 4096자) — 현재 3500자 컷. 필요하면 청크 전송.
