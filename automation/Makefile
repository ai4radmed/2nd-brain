# 2nd-brain host 자동화 (게이트웨이 밖 systemd-user 드레인)
.PHONY: install-brain-drain

# ── brain-drain (refine+brainify 자동 — claude -p 헤드리스, concurrency=1) ────
# parser-drain 가 만든 _parse 를 refine→brainify. 상세: docs/2nd-brain-parser-strategy.md.
install-brain-drain:
	install -d $(HOME)/.config/systemd/user
	install -m 0644 brain-drain/brain-drain.service $(HOME)/.config/systemd/user/
	install -m 0644 brain-drain/brain-drain.timer   $(HOME)/.config/systemd/user/
	chmod +x brain-drain/brain-drain.sh
	systemctl --user daemon-reload
	@echo
	@echo "검증(1회 수동): systemctl --user start brain-drain.service && tail -f ~/.local/state/brain-drain.log"
	@echo "활성화:        systemctl --user enable --now brain-drain.timer"
	@echo "부팅영속(1회 sudo): sudo loginctl enable-linger $$USER"
	@echo "일괄 on/off:   Claude Code 슬래시 /cron"
