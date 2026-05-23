# Egress 프록시 하드닝 — 컨테이너 OpenClaw 보안 강화 (참고 조사)

> **상태: 조사·참고용. 아직 미채택·미구현.** OpenClaw 를 Docker 컨테이너로 운영하는 위에, *아웃바운드(egress) 트래픽을 allowlist 로 제한*하는 프록시 계층을 더하면 보안이 한층 강화된다. 컨테이너화된 AI 에이전트는 임의 코드·도구를 실행하므로, 나가는 트래픽을 통제해 **데이터 유출·공급망 공격**을 방어하는 것이 핵심.

## 두 가지 아키텍처 패턴 (먼저 고를 것)

| | **A. 컨테이너 내부 방화벽** | **B. egress 프록시 사이드카** |
|---|---|---|
| 구현 | agent 컨테이너 안에서 `iptables`+`ipset`, default-DROP, IP allowlist | 별도 `squid` 컨테이너 + agent 를 `internal` 네트워크에 가둠 |
| 대표 | `anthropics/claude-code` devcontainer | 본 시스템의 옛 `2nd-brain-docker/images/squid/` + shaharia 블로그 |
| 신뢰경계 | 약함 — agent 가 root+caps 면 룰 변경 가능 | **강함** — agent 가 프록시를 못 건드림 (별 컨테이너) |
| 필요 권한 | `NET_ADMIN`·`NET_RAW` (컨테이너 특권↑) | agent 컨테이너 특권 불필요 |
| 필터 단위 | IP (도메인→IP 해석, 동적 IP 까다로움) | **도메인** (`dstdomain`, CONNECT) |
| 모든 프로토콜 | TCP/UDP/DNS 다 잡음 | HTTP(S)만 — 나머지는 *네트워크 격리*로 막아야 |

→ **패턴 B** 가 본 시스템의 기존 squid 설계와 일치하고, 신뢰경계가 더 깨끗하다(에이전트가 자기 통제 장치를 못 건드림).

## 공개 GitHub 사례

**AI 에이전트 샌드박스 (가장 관련)**
- [anthropics/claude-code `init-firewall.sh`](https://github.com/anthropics/claude-code/blob/main/.devcontainer/init-firewall.sh) — 패턴 A의 canonical. iptables+ipset default-DROP, `dig` 도메인 해석 + GitHub `/meta` API 동적 IP 대역, `NET_ADMIN`/`NET_RAW`.
- [shaharia.com — Claude Code Docker 네트워크 격리](https://shaharia.com/blog/run-claude-code-docker-network-isolation/) ⭐ 패턴 B 청사진(아래 토폴로지).
- [kydycode/claude-code-secure-container](https://github.com/kydycode/claude-code-secure-container) · [IVIJL/devbox](https://github.com/IVIJL/devbox)(default-deny + rootless DinD) · [centminmod/claude-code-devcontainers](https://github.com/centminmod/claude-code-devcontainers)

**Squid egress 프록시 구현 (패턴 B)**
- [jlandowner/docker-squid-allowlist](https://github.com/jlandowner/docker-squid-allowlist) — allowlist 를 configmap 으로 관리하는 forward proxy.
- [seznam/jailoc](https://github.com/seznam/jailoc) — squid forward proxy + SSL bump + **도메인 + HTTP method** allowlist (한 단계 더 강한 하드닝).
- [salrashid123/squid_proxy](https://github.com/salrashid123/squid_proxy)(SSL intercept) · [sameersbn/docker-squid](https://github.com/sameersbn/docker-squid)(범용 이미지) · [theonemule/docker-proxy-server](https://github.com/theonemule/docker-proxy-server)(Squid+SquidGuard 콘텐츠필터)

**베스트프랙티스 가이드**
- [Northflank — AI 에이전트 샌드박싱](https://northflank.com/blog/how-to-sandbox-ai-agents) · [MintMCP — Sandbox Claude Code](https://www.mintmcp.com/blog/sandbox-claude-code) · [ikangai 종합 가이드](https://www.ikangai.com/the-complete-guide-to-sandboxing-autonomous-agents-tools-frameworks-and-safety-essentials/)

## 직접 적용 청사진 (패턴 B — shaharia 토폴로지)

```yaml
networks:
  isolated:  { internal: true }     # ← 인터넷 직통 없음 (enforcement 지점)
  internet:  {}                     # 표준 bridge

services:
  proxy:   # ubuntu/squid
    networks: [isolated, internet]  # 유일한 egress 출구
  agent:   # openclaw 컨테이너
    networks: [isolated]            # internal 만!
    environment:                    # 대·소문자 둘 다
      - HTTP_PROXY=http://proxy:3128
      - HTTPS_PROXY=http://proxy:3128
      - http_proxy=http://proxy:3128
      - https_proxy=http://proxy:3128
```

핵심 3가지:
1. **네트워크가 enforcement** — agent 를 `internal: true` 에 가두면 프록시가 *유일한* 인터넷 경로.
2. squid 은 `dstdomain` allowlist + `http_access deny all` (fail-closed).
3. **`HTTP_PROXY` env 를 빼면 노출** — `internal:true` 는 bridge route 만 막지, 잘못 설정 시 우회 가능.

## 기존 prior art 와의 갭 (= 추가할 한 조각)

본 시스템의 옛 `2nd-brain-docker/images/squid/squid.conf` 는 **allowlist·deny-all·no-TLS-intercept·점진확대 로깅까지 완성형**이다(아래 발췌). 빠진 것은 squid.conf 가 아니라 **compose 토폴로지** — OpenClaw 컨테이너를 `internal: true` 네트워크에 넣어 *squid 가 유일 경로*가 되게 묶는 부분. squid.conf 만 있고 agent 가 직통 가능하면 무력화된다.

```
# 발췌: 도메인 allowlist via CONNECT, no TLS intercept, fail-closed
acl whitelist dstdomain .anthropic.com .github.com ...
acl CONNECT method CONNECT
http_access deny CONNECT !SSL_ports
http_access allow whitelist
http_access deny all
forwarded_for off   # upstream 에 client 정보 누설 금지
via off
```

## OpenClaw 적용 시 메모

- **allowlist 후보**: `.anthropic.com`·`.claude.ai`(모델) / `.telegram.org`(봇 long-polling) / `.googleapis.com`·`.google.com`(gog) / `.github.com`·`.npmjs.org`(스킬 설치 시).
- **함정**:
  - **DNS/ICMP exfil** — squid 은 HTTP(S)만 본다. DNS 는 안 막으므로, `internal` 네트워크에서 DNS 도 지정 resolver/프록시만 거치게 하거나 egress DNS 를 차단해야 진짜 격리.
  - **클라우드 메타데이터·내부대역** — `169.254.169.254`·`10.x`·`192.168.x` 차단(B는 internal network 가 자연 차단).
  - **squid 중복 도메인 거부** — `.anthropic.com` 과 `api.anthropic.com` 동시 등록 금지(넓은 쪽만).
  - OpenClaw 은 Telegram **long-polling**(outbound)이라 egress-only 로 충분 — webhook 모드면 inbound 처리 별도.

## 채택 시 다음 작업 (보류)

`docker-compose.proxy.yml` 오버레이 초안 = 옛 squid.conf 재활용 + 위 `internal` 네트워크 토폴로지 + OpenClaw allowlist. (현재 미진행 — 본 노트는 조사 기록.)
