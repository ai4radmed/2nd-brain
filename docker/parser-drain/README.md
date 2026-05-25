# parser-drain — host-측 자동 파싱 드레인

`sources/00_inbox` 의 미파싱 바이너리(PDF·HWP·docx·xlsx)를 **2nd-brain-parser 컨테이너로 순차 파싱**해 `<원본>_parse/docling.json` 을 만든다. 검증·노트화는 `brainify`(별도).

**왜 host systemd인가**: 게이트웨이(openclaw) cron→agent-turn 으로 무거운 파싱을 돌리면 ⑴watchdog(블로킹 무출력 타임아웃) ⑵docker socket 노출(호스트 탈취) 위험. 그래서 **게이트웨이는 파일만 드롭, host systemd 가 트리거·실행**한다. 배치도: [`../../docs/2nd-brain-parser-strategy.md`](../../docs/2nd-brain-parser-strategy.md), 일반 원리: [`../../docs/how-to-make-my-process.md`](../../docs/how-to-make-my-process.md).

## 구성
- `parser-drain.sh` — 드레인 본체. concurrency=1(systemd 단일인스턴스 + flock + 순차루프), 멱등(완료분 skip), atomic(tmp→rename), warm 데몬(모델 init amortize), watchdog 밖.
- `parser-drain.service` — oneshot, `parser-drain.sh` 실행.
- `parser-drain.timer` — 10분 폴링(도는 서비스는 또 안 띄움).

## 설치·활성
```bash
cd ~/projects/2nd-brain/docker && make install-parser-drain
systemctl --user enable --now parser-drain.timer      # 활성
systemctl --user start parser-drain.service           # 즉시 1회 드레인(선택)
sudo loginctl enable-linger $USER                     # 부팅 영속(1회)
```
로그: `~/.local/state/parser-drain.log`. 정지: `systemctl --user disable --now parser-drain.timer`.

## 현 단계 메모
- **docling 단일** (전략의 PDF dual+mineru+diff 는 목표 — MinerU CPU deadlock·2× 비용 때문에 첫 cut은 docling만).
- 활성화 정책은 backlog #4b(볼륨 병목 시) 따름. uid 1000 가정(compose 기본값).
