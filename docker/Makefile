.PHONY: sync clean \
        build-brain-pdf up-brain-pdf down-brain-pdf shell-brain-pdf run-brain-pdf \
        build-openclaw up-openclaw down-openclaw restart-openclaw logs-openclaw shell-openclaw install-systemd-openclaw

UID := $(shell id -u)
GID := $(shell id -g)
export UID GID

# brain-pdf 의 compose 체인은 PC 환경 (NVIDIA 유무) 에 따라 다름 — scripts/detect-compose.sh
# 가 nvidia-smi + docker runtime 을 검사해 GPU overlay 를 자동 포함/제외.
# 양 PC (데스크탑 kimbi RTX 3060 / 노트북 Intel Arc) 에서 같은 타겟 사용 가능.
# Override: `BRAIN_PDF_FORCE_VARIANT=gpu|cpu make ...` (디버깅 / 감지 misfire).
COMPOSE_BRAIN_PDF := $(shell ./scripts/detect-compose.sh)

# 호스트 native Claude Code 버전을 openclaw 이미지의 번들 claude 바이너리 핀
# (.env CLAUDE_CODE_VERSION) 에 맞춰 재빌드. 호스트가 진실의 원천.
sync:
	./scripts/bin/sync-claude-version.sh

# openclaw 이미지 + brain-pdf 이미지 정리. (sb-claude 폐기로 compose.yml 부재 —
# `docker compose down -v` 대신 명시 이미지 제거.)
clean:
	docker compose $(COMPOSE_OPENCLAW) down 2>/dev/null || true
	docker images --format '{{.Repository}}:{{.Tag}}' \
	  | grep -E '^2nd-brain/(openclaw-gateway|brain-pdf):' \
	  | xargs -r docker rmi 2>/dev/null || true

# ── brain-pdf (Docling + MinerU PDF parser) ──────────────────────────────────
# 양 PC 공통 타겟. detect-compose.sh 가 NVIDIA 환경 자동 감지.
#
# Override (드물게):
#   BRAIN_PDF_FORCE_VARIANT=cpu make run-brain-pdf   # GPU 있는 PC 에서 강제 CPU
#   BRAIN_PDF_FORCE_VARIANT=gpu make build-brain-pdf  # 감지 실패 시 강제 GPU

build-brain-pdf:
	docker compose $(COMPOSE_BRAIN_PDF) build brain-pdf

# Daemon 모드 — 모델 RAM 상주 (4~8GB). 14GB WSL2 한도에서는 sb-openclaw 와 합산 점검 필요.
up-brain-pdf:
	docker compose $(COMPOSE_BRAIN_PDF) up -d brain-pdf

down-brain-pdf:
	docker compose $(COMPOSE_BRAIN_PDF) stop brain-pdf
	docker compose $(COMPOSE_BRAIN_PDF) rm -f brain-pdf

shell-brain-pdf:
	docker exec -it sb-brain-pdf /bin/bash

# Ephemeral 일회성 실행 — 인자를 그대로 forward.
# 예: `make run-brain-pdf ARGS="brain-pdf parse-docling /home/user/projects/2nd-brain-vault/sources/00_inbox/sample.pdf"`
run-brain-pdf:
	docker compose $(COMPOSE_BRAIN_PDF) run --rm brain-pdf $(ARGS)

# ── openclaw-gateway (containerized control plane) ───────────────────────────
# 호스트 systemd-user openclaw-gateway.service 를 대체. standalone compose.
# 컨테이너가 곧 sandbox — 내부 sandbox.mode=off (cutover).
# 전제: 호스트 게이트웨이 stop+disable, .env 에 OPENCLAW_VERSION +
# GOG_OPENCLAW_KEYRING_PASSWORD. 상세: docs/openclaw-docker-install.md.
COMPOSE_OPENCLAW := -f compose.openclaw.yml

# GOG_OPENCLAW_KEYRING_PASSWORD is irrelevant at build time but compose
# interpolates the whole file (the runtime `:?` guard would otherwise block
# build before Phase 2). Inject a throwaway only for build; up-openclaw still
# requires the real value from .env.
build-openclaw:
	GOG_OPENCLAW_KEYRING_PASSWORD=$${GOG_OPENCLAW_KEYRING_PASSWORD:-_unused_at_build_} docker compose $(COMPOSE_OPENCLAW) build

up-openclaw:
	docker compose $(COMPOSE_OPENCLAW) up -d

down-openclaw:
	docker compose $(COMPOSE_OPENCLAW) down

restart-openclaw:
	docker compose $(COMPOSE_OPENCLAW) down
	docker compose $(COMPOSE_OPENCLAW) up -d

logs-openclaw:
	docker compose $(COMPOSE_OPENCLAW) logs -f openclaw

shell-openclaw:
	docker exec -it sb-openclaw /bin/bash

# 부팅 자동기동 (compose restart:unless-stopped + Docker daemon autostart 가
# 1차. systemd-user 유닛은 boot 시 `compose up -d` 를 한 번 보장하는 보강).
install-systemd-openclaw:
	install -d $(HOME)/.config/systemd/user
	install -m 0644 scripts/sb-openclaw.service $(HOME)/.config/systemd/user/sb-openclaw.service
	systemctl --user daemon-reload
	systemctl --user enable --now sb-openclaw.service
	@echo
	@echo "Boot persistence requires (one-time, sudo):"
	@echo "    sudo loginctl enable-linger $$USER"
