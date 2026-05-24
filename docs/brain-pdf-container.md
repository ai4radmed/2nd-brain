# brain-pdf — 문서 파서 컨테이너 (PDF·docx·xlsx → markdown)

> 붙여넣기용 명령 + 최소 이유. openclaw-docker 처럼 **컨테이너로 띄워 쓰는** 도구다.
> 역할: 첨부 바이너리(PDF 등)를 **로컬에서 markdown 으로 파싱** → brainify(요약·분류)의 *선행 파서*.

**왜 컨테이너**: Docling·MinerU·torch 등 무거운 ML 의존성을 격리하고, **외부 API 0**(로컬 전용)으로 재무·민감 자료의 leak 을 막는다.

**배포 방식**: 레지스트리 없이 **사용자가 로컬에서 직접 빌드**한다 (이 repo 에 빌드소스 동봉 → clone+build 로 자족적). 사용자가 자기 uid 로 빌드하므로 권한 문제가 없다.

**파이프라인 위치**: `capture(라벨 라우터) → 00_inbox(바이너리+_thread.md) → **brain-pdf 파싱(여기)** → brainify(LLM 노트)`. brainify(Claude Code)가 이 컨테이너를 서브프로세스로 호출한다.

## 전제

- **Docker Engine + Compose v2**, 이 repo clone.
- (선택) NVIDIA GPU — 수식 포함 학술 PDF 면 권장. 회계·일반 문서는 **CPU 로 충분**.
- 디스크: 빌드 이미지 ~수 GB + 첫 실행 시 모델 가중치 ~5GB(named volume 영속).

## 1. 빌드 (1회, ~10–20분)

```bash
export UID=$(id -u) GID=$(id -g)
docker compose -f docker/brain-pdf/compose.brain-pdf.yml build brain-pdf
```

- 빌드소스(`docker/brain-pdf/{Dockerfile, entrypoint.py, requirements.txt}`)에서 빌드. torch/MinerU 등 받느라 처음엔 오래 걸린다(이후 레이어 캐시).
- 버전 갱신 = `git pull` 후 다시 `build`.

## 2. 파싱 실행 (ephemeral)

```bash
docker compose -f docker/brain-pdf/compose.brain-pdf.yml run --rm brain-pdf parse-docling <PDF경로>
docker compose -f docker/brain-pdf/compose.brain-pdf.yml run --rm brain-pdf parse-mineru  <PDF경로>   # PDF 듀얼 체크
docker compose -f docker/brain-pdf/compose.brain-pdf.yml run --rm brain-pdf diff <docling.md> <mineru.md>
```

- 출력은 원본 옆 **`<원본.확장자>_parse/{docling.md, mineru.md, refined.md}`** (vault `_parse` 규약). 동반 노트 frontmatter `parse:` 가 이 폴더를 가리킨다.
- **첫 실행**은 HF 모델 ~5GB 다운로드(volume 에 영속 → 이후 빠름).
- 파싱 대상 파일은 compose 가 마운트한 vault(`${SB_DATA:-~/projects/2nd-brain-vault}`) 안에 있어야 컨테이너가 읽는다.

## 3. CPU / GPU

- **CPU**(기본) — 회계·일반 문서 충분. 위 명령 그대로.
- **GPU**(수식 PDF) — NVIDIA 호스트에서 오버레이 추가:
  ```bash
  docker compose -f docker/brain-pdf/compose.brain-pdf.yml \
                 -f docker/brain-pdf/compose.brain-pdf.gpu.yml \
                 run --rm brain-pdf parse-mineru <pdf>
  ```
  (전제: `nvidia-container-toolkit` + `docker run --rm --gpus all nvidia/cuda:12.x-base nvidia-smi` 통과)

## 보안

- **외부 네트워크 호출 0** (모델 1회 다운로드 제외) — 재무·민감 PDF 가 외부로 안 나간다.
- `cap_drop: ALL` + `no-new-privileges` — 최소 권한.
- 사용자 uid 로 빌드·실행 → vault 파일 소유권 정상.

## 트러블슈팅 (요약)

| 증상 | 해결 |
|---|---|
| `EACCES` (vault/모델 쓰기 실패) | `export UID=$(id -u) GID=$(id -g)` 후 **재빌드**(uid 가 이미지에 구워짐) |
| MinerU 수식 deadlock(CPU) | 수식 없는 문서면 `parse-docling` 만; 학술 PDF 는 GPU 오버레이 |
| 첫 실행 매우 느림 | 모델 ~5GB 최초 다운로드 — volume 캐시되면 이후 빠름 |
| 빌드 OOM/실패 | RAM 여유 확보(빌드 시 수 GB), Docker 디스크 여유 확인 |

## 다음

- 파서 출력(`_parse/markdown`)을 소비하는 brainify: [`templates/skills/claude-code/`](../templates/skills/claude-code/README.md)
- 컨테이너 운영 일반: [openclaw-docker-container.md](./openclaw-docker-container.md)

---

> **메인테이너 메모**: 빌드소스는 이 repo `docker/brain-pdf/` 에 있다 (native 검증본 `2nd-brain-docker/images/brain-pdf/` 에서 복사). 둘이 갈라지면 native(brainify-inbox)와 공개본이 어긋나니, 향후 native 를 이 repo 본으로 repoint 하고 박물관(2nd-brain-docker) 본은 정리하는 cutover 가 후속 과제.
