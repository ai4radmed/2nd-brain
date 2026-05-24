# brain-pdf — 문서 파서 컨테이너 (PDF·docx·xlsx → markdown)

> 붙여넣기용 명령 + 최소 이유. openclaw-docker 처럼 **컨테이너로 띄워 쓰는** 도구다.
> 역할: 첨부 바이너리(PDF 등)를 **로컬에서 markdown 으로 파싱** → brainify(요약·분류)의 *선행 파서*.

**왜 컨테이너**: Docling·MinerU·torch 등 무거운 ML 의존성을 격리하고, **외부 API 0**(로컬 전용)으로 재무·민감 자료의 leak 을 막는다.

**파이프라인 위치**: `capture(라벨 라우터) → 00_inbox(바이너리+_thread.md) → **brain-pdf 파싱(여기)** → brainify(LLM 노트)`. brainify(Claude Code)가 이 컨테이너를 서브프로세스로 호출한다.

## 전제

- **Docker Engine + Compose v2**.
- (선택) NVIDIA GPU — 수식 포함 학술 PDF 면 권장. 회계·일반 문서는 **CPU 로 충분**.
- 디스크: 이미지 ~수 GB + 첫 실행 시 모델 가중치 ~5GB(named volume 영속).

## 1. 이미지 받기 (빌드 아님 — pull)

```bash
docker pull ghcr.io/ai4radmed/brain-pdf:latest
```

> openclaw 처럼 **빌드 없이 pull** 만. (이미지 메인테이너 빌드·발행은 맨 아래 "메인테이너" 절.)

## 2. compose 파일

`compose.brain-pdf.yml` (이 repo `docker/brain-pdf/` 에도 동봉):

```yaml
services:
  brain-pdf:
    image: ghcr.io/ai4radmed/brain-pdf:${BRAIN_PDF_VERSION:-latest}
    user: "${UID:-1000}:${GID:-1000}"        # 런타임 uid (prebuilt 는 uid 굽지 않음)
    working_dir: /home/user/work
    cap_drop: [ALL]
    security_opt: [ "no-new-privileges:true" ]
    environment:
      HF_HOME: /home/user/.cache/huggingface
      TRANSFORMERS_OFFLINE: "0"              # 첫 실행 모델 다운로드 허용
    volumes:
      - ${SB_DATA:-${HOME}/projects/2nd-brain-vault}:/home/user/projects/2nd-brain-vault
      - brain-pdf-models:/home/user/.cache/huggingface   # 모델 가중치 영속
    command: ["sleep", "infinity"]           # 데몬 default; run 으로 override
volumes:
  brain-pdf-models:
```

> ⚠️ **uid**: 이미지는 uid 1000 기준. 호스트 uid 가 1000 이 아니면 `UID`/`GID` env 로 맞추되, 모델 volume·vault 쓰기 권한을 확인하라.

## 3. 파싱 실행 (ephemeral)

```bash
export UID=$(id -u) GID=$(id -g)
docker compose -f compose.brain-pdf.yml run --rm brain-pdf parse-docling <PDF경로>
docker compose -f compose.brain-pdf.yml run --rm brain-pdf parse-mineru  <PDF경로>   # PDF 듀얼 체크
docker compose -f compose.brain-pdf.yml run --rm brain-pdf diff <docling.md> <mineru.md>
```

- 출력은 원본 옆 **`<원본.확장자>_parse/{docling.md, mineru.md, refined.md}`** (vault `_parse` 규약). 동반 노트 frontmatter `parse:` 가 이 폴더를 가리킨다.
- **첫 실행**은 HF 모델 ~5GB 다운로드(volume 에 영속 → 이후 빠름).

## 4. CPU / GPU

- **CPU**(기본) — 회계·일반 문서 충분. 위 compose 그대로.
- **GPU**(수식 PDF) — NVIDIA 호스트에서 overlay 추가:
  ```yaml
  # compose.brain-pdf.gpu.yml
  services:
    brain-pdf:
      deploy: { resources: { reservations: { devices: [ { driver: nvidia, count: all, capabilities: [gpu] } ] } } }
  ```
  `docker compose -f compose.brain-pdf.yml -f compose.brain-pdf.gpu.yml run --rm brain-pdf ...`
  (전제: `nvidia-container-toolkit` + `docker run --rm --gpus all nvidia/cuda:12.x-base nvidia-smi` 통과)

## 보안

- **외부 네트워크 호출 0** (모델 1회 다운로드 제외) — 재무·민감 PDF 가 외부로 안 나간다.
- `cap_drop: ALL` + `no-new-privileges` — 최소 권한.

## 트러블슈팅 (요약)

| 증상 | 해결 |
|---|---|
| `EACCES` (vault/모델 쓰기 실패) | `UID`/`GID` 를 호스트 사용자에 맞춰 export 후 재실행 |
| MinerU 수식 deadlock(CPU) | 수식 없는 문서면 `parse-docling` 만; 학술 PDF 는 GPU overlay |
| 첫 실행 매우 느림 | 모델 ~5GB 최초 다운로드 — volume 캐시되면 이후 빠름 |

## 메인테이너 — ghcr 이미지 빌드·발행

사용자는 pull 만 — **이 repo(2nd-brain)엔 빌드소스가 없다**(pull-compose + 이 문서뿐). **이미지 빌드·발행은 메인테이너가** (GPU 데스크탑 권장), 빌드소스는 **`2nd-brain-docker/images/brain-pdf/`**(ai4radmed 공개):

```bash
# 빌드 (소스 = 2nd-brain-docker, 이 repo 아님)
docker build -t ghcr.io/ai4radmed/brain-pdf:$(date +%Y.%m.%d) \
             -t ghcr.io/ai4radmed/brain-pdf:latest \
             ~/projects/2nd-brain-docker/images/brain-pdf
# ghcr 로그인 (PAT: write:packages)
echo "$GHCR_PAT" | docker login ghcr.io -u <user> --password-stdin
docker push ghcr.io/ai4radmed/brain-pdf --all-tags
```

> ⚠️ prebuilt 이식성을 위해 빌드 전 Dockerfile 의 **uid 베이킹 제거** 필요 (`useradd -u $UID` ARG → 고정 uid 1000). 런타임은 compose `user: ${UID}:${GID}` 로 오버라이드.
> 빌드소스가 `2nd-brain-docker`(박물관)에 있는 게 거슬리면 별도 build repo 로 옮기는 건 후속 결정 — pull UX 와는 무관.

## 다음

- 파서 출력(`_parse/markdown`)을 소비하는 brainify: [`templates/skills/claude-code/`](../templates/skills/claude-code/README.md)
- 컨테이너 운영 일반: [openclaw-docker-container.md](./openclaw-docker-container.md)
