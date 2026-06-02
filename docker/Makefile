.PHONY: clean \
        up-parser down-parser shell-parser run-parser \
        up-openclaw down-openclaw restart-openclaw logs-openclaw shell-openclaw \
        install-parser-drain \
        install-webmail-sidecar

UID := $(shell id -u)
GID := $(shell id -g)
export UID GID

# 2nd-brain-parser compose 체인은 PC 환경(NVIDIA 유무)에 따라 다름 — scripts/detect-compose.sh
# 가 nvidia-smi + docker runtime 을 검사해 GPU overlay 를 자동 포함/제외.
# 양 PC(데스크탑 kimbi RTX 3060 / 노트북 Intel Arc)에서 같은 타겟 사용 가능.
# Override: `PARSER_FORCE_VARIANT=gpu|cpu make ...` (디버깅 / 감지 misfire).
# 이미지는 ghcr pull(빌드 X) — 빌드·발행은 docs/2nd-brain-parser-setup.md 메인테이너 절차.
COMPOSE_PARSER := $(shell ./scripts/detect-compose.sh)

# openclaw 게이트웨이: upstream 이미지(ghcr.io/openclaw/openclaw) pull 구동, build 없음.
COMPOSE_OPENCLAW := -f openclaw-gateway/compose.yml

# pull 한 이미지 정리: 컨테이너 down + parser 이미지 제거(openclaw 는 upstream 이라 보존).
clean:
	docker compose $(COMPOSE_OPENCLAW) down 2>/dev/null || true
	docker compose $(COMPOSE_PARSER) down 2>/dev/null || true
	docker images --format '{{.Repository}}:{{.Tag}}' \
	  | grep -E '^ghcr\.io/benkorea/2nd-brain-parser:' \
	  | xargs -r docker rmi 2>/dev/null || true

# ── 2nd-brain-parser (Docling + MinerU 문서 파서) ────────────────────────────
# 양 PC 공통. detect-compose.sh 가 NVIDIA 환경 자동 감지.
# Override(드물게): `PARSER_FORCE_VARIANT=cpu make run-parser` / `=gpu make up-parser`.

# Daemon 모드 — 모델 RAM 상주(4~8GB). 14GB WSL2 한도에서는 게이트웨이와 합산 점검.
up-parser:
	docker compose $(COMPOSE_PARSER) up -d 2nd-brain-parser

down-parser:
	docker compose $(COMPOSE_PARSER) stop 2nd-brain-parser
	docker compose $(COMPOSE_PARSER) rm -f 2nd-brain-parser

shell-parser:
	docker exec -it 2nd-brain-parser /bin/bash

# Ephemeral 일회성 — 인자 forward.
# 예: `make run-parser ARGS="2nd-brain-parser parse-docling /home/user/projects/2nd-brain-vault/sources/00_inbox/sample.pdf"`
run-parser:
	docker compose $(COMPOSE_PARSER) run --rm 2nd-brain-parser $(ARGS)

# ── openclaw-gateway (containerized control plane) ───────────────────────────
# upstream 이미지(ghcr.io/openclaw/openclaw) pull 구동. 자동기동 =
# openclaw-gateway.service(systemd-user) + compose restart 정책.
# 전제: .env 에 GOG_OPENCLAW_KEYRING_PASSWORD. 상세: docs/openclaw-docker-install.md.

up-openclaw:
	docker compose $(COMPOSE_OPENCLAW) up -d

down-openclaw:
	docker compose $(COMPOSE_OPENCLAW) down

restart-openclaw:
	docker compose $(COMPOSE_OPENCLAW) down
	docker compose $(COMPOSE_OPENCLAW) up -d

logs-openclaw:
	docker compose $(COMPOSE_OPENCLAW) logs -f openclaw-gateway

shell-openclaw:
	docker exec -it 2nd-brain-openclaw-gateway /bin/bash

# ── parser-drain (host systemd 자동 파싱 — watchdog 밖, concurrency=1) ────────
# 게이트웨이는 파일만 드롭, host 가 트리거·실행. 상세: docs/2nd-brain-parser-strategy.md.
install-parser-drain:
	install -d $(HOME)/.config/systemd/user
	install -m 0644 parser-drain/parser-drain.service $(HOME)/.config/systemd/user/
	install -m 0644 parser-drain/parser-drain.timer   $(HOME)/.config/systemd/user/
	chmod +x parser-drain/parser-drain.sh
	systemctl --user daemon-reload
	@echo
	@echo "활성화: systemctl --user enable --now parser-drain.timer"
	@echo "부팅영속(1회 sudo): sudo loginctl enable-linger $$USER"

# ── webmail-sidecar (host systemd 브라우저형 스킬 폴 — headed-under-Xvfb) ──────
# 게이트웨이엔 브라우저가 없어 별도 사이드카(Playwright+Xvfb)를 host 타이머가 1회성
# `docker compose run --rm` 으로 주기 호출. 유닛은 %h specifier 라 PC 비종속.
# 전제(미동기 로컬): 이미지 빌드(docker compose build) + KIRAMS secret
# (~/.openclaw/secrets/webmail-watch-kirams.toml, Bitwarden 정본). 상세: README.md, docs §9b.
install-webmail-sidecar:
	install -d $(HOME)/.config/systemd/user
	install -m 0644 webmail-sidecar/systemd/openclaw-webmail-sidecar.service $(HOME)/.config/systemd/user/
	install -m 0644 webmail-sidecar/systemd/openclaw-webmail-sidecar.timer   $(HOME)/.config/systemd/user/
	systemctl --user daemon-reload
	@echo
	@echo "전제: docker compose -f webmail-sidecar/compose.yml build (이미지 ~1GB)"
	@echo "전제: ~/.openclaw/secrets/webmail-watch-kirams.toml (Bitwarden, mode 600)"
	@echo "활성화는 /cron on 으로 (이중발화 가드+Sheet 마커). 수동: systemctl --user enable --now openclaw-webmail-sidecar.timer"
	@echo "부팅영속(1회 sudo): sudo loginctl enable-linger $$USER"
