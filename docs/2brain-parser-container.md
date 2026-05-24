# 2brain-parser — 문서 파서 컨테이너 (PDF·Office·한글·레거시 → markdown)

> 붙여넣기용 명령 + 최소 이유. openclaw-docker 처럼 **컨테이너로 띄워 쓰는** 도구다.
> 역할: 첨부 바이너리(PDF 등)를 **로컬에서 markdown 으로 파싱** → brainify(요약·분류)의 *선행 파서*.

**왜 컨테이너**: Docling·MinerU·torch 등 무거운 ML 의존성을 격리하고, **외부 API 0**(로컬 전용)으로 재무·민감 자료의 leak 을 막는다.

**배포 방식**: **ghcr 에서 prebuilt 이미지 pull** (사용자는 빌드 X). torch(~843MB) 등 무거운 의존성이 이미 이미지에 포함돼, 사용자는 ghcr 에서 한 번 받기만 한다 (PyTorch CDN 의 큰 wheel 을 직접 받다 실패하는 문제 회피).

**파이프라인 위치**: `capture(라벨 라우터) → 00_inbox(바이너리+_thread.md) → **2brain-parser 파싱(여기)** → brainify(LLM 노트)`. brainify(Claude Code)가 이 컨테이너를 서브프로세스로 호출한다.

## 전제

- **Docker Engine + Compose v2**, 이 repo clone.
- (선택) NVIDIA GPU — 수식 포함 학술 PDF 면 권장. 회계·일반 문서는 **CPU 로 충분**.
- 디스크: 이미지 ~수 GB + 첫 실행 시 모델 가중치 ~5GB(named volume 영속).

## 1. 이미지 받기 (빌드 아님 — pull)

```bash
docker pull ghcr.io/benkorea/2brain-parser:latest
```

## 2. 파싱 실행 (ephemeral)

```bash
export UID=$(id -u) GID=$(id -g)
C="docker compose -f docker/2brain-parser/compose.2brain-parser.yml run --rm 2brain-parser"
$C 2brain-parser parse-docling <PDF경로>
$C 2brain-parser parse-docling <HWP경로>          # hwp/hwpx → LibreOffice 로 docx 자동변환 후 Docling
$C 2brain-parser parse-mineru  <PDF경로>          # PDF 듀얼 체크
$C 2brain-parser diff <docling.md> <mineru.md>
```

> **지원 포맷** (모두 `parse-docling` 한 명령):
> - **PDF·docx·pptx·xlsx** → Docling 직접.
> - **hwp/hwpx · 구 바이너리(doc/ppt/xls) · odf(odt/odp/ods)** → 내부에서 **LibreOffice 로 모던 OOXML(docx/pptx/xlsx) 변환 후 Docling**. 출력 JSON `via:` 에 경로 표시 (예: `hwp→docx→docling`, `xls→xlsx→docling`). 변환은 확장자별 자동 dispatch.
> - **PDF 경유 안 함** — CJK 글리프 매핑이 깨져 텍스트 추출 불가(실측). 그림 속 글자는 별도 OCR 영역.
> - 검증됨: pdf·docx·pptx·xlsx·hwp·xls(레거시). doc/ppt(레거시)는 동일 dispatch 경로.

> `2brain-parser` 가 두 번 나오는 건 정상 — 앞은 compose **서비스명**, 뒤는 **CLI 명령**이다 (`docker compose run <service> <command>`).

- 출력은 원본 옆 **`<원본.확장자>_parse/{docling.md, mineru.md, refined.md}`** (vault `_parse` 규약). 동반 노트 frontmatter `parse:` 가 이 폴더를 가리킨다.
- **첫 실행**은 HF 모델 ~5GB 다운로드(volume 에 영속 → 이후 빠름).
- 파싱 대상 파일은 compose 가 마운트한 vault(`${SB_DATA:-~/projects/2nd-brain-vault}`) 안에 있어야 컨테이너가 읽는다.

## 3. CPU / GPU

- **CPU**(기본) — 회계·일반 문서 충분. 위 명령 그대로.
- **GPU**(수식 PDF) — NVIDIA 호스트에서 오버레이 추가:
  ```bash
  docker compose -f docker/2brain-parser/compose.2brain-parser.yml \
                 -f docker/2brain-parser/compose.2brain-parser.gpu.yml \
                 run --rm 2brain-parser 2brain-parser parse-mineru <pdf>
  ```
  (전제: `nvidia-container-toolkit` + `docker run --rm --gpus all nvidia/cuda:12.x-base nvidia-smi` 통과)

## 보안

- **외부 네트워크 호출 0** (모델 1회 다운로드 제외) — 재무·민감 PDF 가 외부로 안 나간다.
- `cap_drop: ALL` + `no-new-privileges` — 최소 권한.

## 트러블슈팅 (요약)

| 증상 | 해결 |
|---|---|
| `EACCES` (vault/모델 쓰기 실패) | `export UID=$(id -u) GID=$(id -g)` 후 재실행 (compose `user:` 에 반영) |
| MinerU 수식 deadlock(CPU) | 수식 없는 문서면 `parse-docling` 만; 학술 PDF 는 GPU 오버레이 |
| 첫 실행 매우 느림 | 모델 ~5GB 최초 다운로드 — volume 캐시되면 이후 빠름 |
| `manifest unknown` (pull 실패) | 이미지 미발행 — 아래 "메인테이너" 절(발행 후 사용 가능) |

## 다음

- 파서 출력(`_parse/markdown`)을 소비하는 brainify: [`templates/skills/claude-code/`](../templates/skills/claude-code/README.md)
- 컨테이너 운영 일반: [openclaw-docker-container.md](./openclaw-docker-container.md)

---

> **메인테이너 메모 — ghcr 이미지 발행**
> 빌드소스(Dockerfile·entrypoint·requirements)는 `2nd-brain-docker/images/brain-pdf/`(공개) 에 있고, 검증된 이미지 `2nd-brain/brain-pdf:<date>` 가 이미 빌드돼 있다. **재빌드는 torch(~843MB) wheel 의 PyTorch CDN 다운로드가 한국망에서 불안정해 막힐 수 있으므로**, 발행은 *기존 검증 이미지를 tag + push* 로 한다 (재빌드 회피):
> ```bash
> # 기존 이미지에 2brain-parser CLI 심링크 1줄 얹기 (재빌드·torch 재다운 0)
> docker run --user root --name rn-parser 2nd-brain/brain-pdf:<date> \
>            ln -sf /usr/local/bin/brain-pdf /usr/local/bin/2brain-parser
> docker commit --change 'USER user' --change 'WORKDIR /home/user/work' \
>               --change 'CMD ["sleep","infinity"]' \
>               rn-parser ghcr.io/benkorea/2brain-parser:latest && docker rm rn-parser
> docker tag ghcr.io/benkorea/2brain-parser:latest ghcr.io/benkorea/2brain-parser:$(date +%Y.%m.%d)
> echo "$GHCR_PAT" | docker login ghcr.io -u <user> --password-stdin
> docker push ghcr.io/benkorea/2brain-parser --all-tags
> ```
> 향후 망이 좋을 때 빌드소스를 `2brain-parser` 로 정식 rename·재빌드하면 심링크 브리지는 불필요.
