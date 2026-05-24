# Syncthing 셋업 — 2nd-brain-vault 동기

새 머신에 vault 동기를 셋업할 때 따라가는 실행 가이드.

## 목적·범위

- **무엇을 다루는가**: WSL2 ↔ Windows Syncthing 페어링 + Drive for Desktop 연계 + 표준 .stignore 적용
- **무엇을 안 다루는가**: 왜 이 아키텍처를 채택했는지의 결정 근거 — `2nd-brain-vault/knowledge/02_areas/brain-system/research/2026-05-04_sync-architecture-roadmap.md` 참조

## 전제

- 머신: Windows + WSL2 (Ubuntu 또는 Debian 계열)
- vault 정본 위치: `~/projects/2nd-brain-vault/` (WSL2 ext4 native)
- Windows 동기 사본 위치: `D:\Gdrive\2nd-brain-vault\` (Drive for Desktop 미러링 영역)
- Google Drive 계정 + Drive for Desktop 설치 (file 미러링 모드)
- 인터넷 outbound HTTPS 허용 (Syncthing global discovery 용)

## Port Convention

| 컨텍스트 | GUI 포트 | Sync 포트 | Discovery |
|---|---|---|---|
| WSL2 (Linux) | **8384** | 22000 (기본) | 21027 (기본) |
| Windows | **8385** | 22000 (기본) | 21027 (기본) |

**원칙**: GUI 포트만 명시 통일. Sync/Discovery 는 기본값 유지 (mirrored mode 충돌은 SyncTrayzor 가 자동 처리).

## 새 머신 셋업 순서

### 1. 사전 준비

**WSL2 네트워킹 모드 확인** (분기 결정용):
```bash
hostname -I                                      # WSL2 자신의 IP
ip route show default | awk '/default/ {print $3}'  # Windows 호스트 IP
```
- 두 IP 가 다른 대역 → **NAT mode** (포트 충돌 없음, 단순)
- 두 IP 가 같은 대역 → **mirrored mode** (포트 충돌 가능, SyncTrayzor 자동 처리)

**vault 디렉토리 확인**:
```bash
ls -la ~/projects/2nd-brain-vault 2>/dev/null
```
- 비어있거나 부재 → 신규 머신, Windows 측에서 받아옴 (예: hospital PC)
- 내용 있음 → 정본 보유 머신, Windows 측으로 보냄 (예: laptop)

### 2. Syncthing 설치

**WSL2 측**:
```bash
sudo apt update && sudo apt install -y syncthing
syncthing --version
```
또는 [공식 바이너리](https://syncthing.net/downloads/) 다운로드.

systemd-user 서비스로 자동 시작:
```bash
systemctl --user enable syncthing
systemctl --user start syncthing
loginctl enable-linger $USER  # 로그아웃 후에도 유지
```

**Windows 측**: [GermanCoding/SyncTrayzor v2](https://github.com/GermanCoding/SyncTrayzor/releases) 의 `SyncTrayzorSetup-x64.exe` 다운로드 + 설치. 설치 시 자동 시작 등록 + 방화벽 규칙 자동 추가.

> **참고**: 원본 `canton7/SyncTrayzor` 는 2025-08 아카이브. GermanCoding fork 가 공식 후속. 자세한 배경은 vault 의 [research notes](../../../2nd-brain-vault/knowledge/02_areas/brain-system/research/) 참조.

### 3. GUI 포트 설정 (양쪽)

**WSL2 측 Web UI** (`http://127.0.0.1:8384`):
- 기본값 그대로 유지 (8384) — 별도 설정 불필요

**Windows 측 Web UI**:
1. 첫 실행 시 SyncTrayzor 가 mirrored mode 에서 자동 override 한 random 포트로 떠 있을 수 있음
2. SyncTrayzor → File → Settings → "Syncthing" 탭 → "Override Syncthing's listen address" **체크 해제**
3. Web UI → Actions → Settings → GUI → **GUI Listen Address: `127.0.0.1:8385`** → Save → "Restart Syncthing"
4. 트레이에서 Web UI 가 8385 로 정상 열리는지 확인

검증:
```bash
# WSL2 에서
curl -I http://127.0.0.1:8384

# Windows PowerShell 에서
curl.exe -I http://127.0.0.1:8385
```

### 4. 페어링

**Device 이름 명확화** (양쪽):
- ⚙ → Settings → General → **Device Name**: `<위치>-<OS>` 패턴
  - 예: `laptop-wsl2`, `laptop-win`, `hospital-wsl2`, `hospital-win`, `nas-linux`

**Device ID 교환**:
1. WSL2 Web UI → ⚙ → **Show ID** → 복사
2. Windows Web UI → 우하단 **+ Add Remote Device** → Device ID 붙여넣기 → Name 입력 → Save
3. WSL2 Web UI 상단 알림 배너 → **Add Device** → 승인

**페어링 검증**: 양쪽 device 카드가 **녹색 + "Connected"** 또는 **"Up to Date"**.

NAT mode 에서 2분 이상 "Disconnected" 가 지속되면 → 명시적 address 추가:
- Windows 측에서 WSL2 device 의 Address 에 `tcp://<WSL_IP>:22000, dynamic`
- WSL2 측에서 Windows device 의 Address 에 `tcp://<WIN_HOST>:22000, dynamic`
- WSL_IP 가 재부팅마다 바뀌면 portproxy 사용:
  ```powershell
  netsh interface portproxy add v4tov4 listenaddress=127.0.0.1 listenport=22001 connectaddress=<WSL_IP> connectport=22000
  ```

### 5. 임시 폴더 sync 검증 (필수 권장)

vault 본 등록 전, 더미 폴더로 양방향 동기 작동 확인:

WSL2:
```bash
mkdir -p ~/sync-test
```
WSL2 Web UI → + Add Folder → `~/sync-test` → Sharing 탭에서 Windows device 체크 → Save.

Windows 측 알림 → Add → 적당한 임시 위치 (예: `C:\Users\<USER>\sync-test`).

양방향 파일 생성 테스트:
```bash
# WSL2 → Windows
echo "test $(date)" > ~/sync-test/from-wsl.txt
# Windows → WSL2 (PowerShell)
"test $(Get-Date)" | Out-File C:\Users\<USER>\sync-test\from-win.txt
```
양쪽 모두 5~10초 내 도달하면 통과.

### 6. vault 폴더 본 등록

**중요**: 본 등록 전 백업:
```bash
cd ~/projects
tar -czf 2nd-brain-vault-backup-$(date +%Y%m%d).tar.gz 2nd-brain-vault/
```

**Drive for Desktop 일시정지** (초기 복제 race 방지):
- Windows 트레이 → Google Drive 아이콘 → 동기화 일시정지

**정본 보유 머신** (예: laptop): WSL2 측에서 vault 폴더 추가:
- WSL2 Web UI → + Add Folder
- Folder Path: `~/projects/2nd-brain-vault`
- **Folder ID**: `2nd-brain-vault` (모든 머신에서 동일하게 입력 — 중요!)
- Sharing 탭: Windows device 체크
- **Advanced 탭**:
  - Folder Type: Send & Receive
  - File Versioning: **Staggered**
  - **Ignore Permissions: ✅ 체크** (ext4 ↔ NTFS 호환)
  - Watch for Changes: ✅ 체크
- **Ignore Patterns 탭**: 아래 표준 패턴 입력 (초기 복제 전에 등록 — 노이즈 사전 차단)
- Save

Windows 측 알림 → Add:
- Folder Path: `D:\Gdrive\2nd-brain-vault\` 명시 입력 (기본값 그대로 두지 말 것)
- Advanced 탭: Ignore Permissions ✅, Watch for Changes ✅
- Ignore Patterns 탭: 동일 패턴 입력
- Save

**받기 머신** (예: hospital PC): Windows 측이 이미 채워져 있으므로 반대 방향:
- Windows 측에서 vault 폴더 먼저 등록 (D:\Gdrive\2nd-brain-vault\)
- Sharing 탭에서 WSL2 device 체크
- Folder ID 는 정본 머신과 **반드시 동일**
- WSL2 측은 빈 디렉토리(`mkdir -p ~/projects/2nd-brain-vault`) 준비 후 알림 수신

**초기 복제 대기**: 양쪽 모두 "Up to Date" 녹색 + "Out of Sync Items: 0" 까지.

### 7. Drive for Desktop 재개

위 6 단계 완료 후:
- 트레이 → Drive 아이콘 → 일시정지 해제
- D:\Gdrive\2nd-brain-vault\ 의 모든 파일 클라우드 업로드 시작

업로드 진행 확인:
- 트레이 메뉴 → 활동 패널
- 또는 https://drive.google.com → `2nd-brain-vault` 폴더 등장

## .stignore 표준 패턴

양쪽 (WSL2·Windows) Folder → ⋮ → Edit → Ignore Patterns 탭에 동일 입력:

```
.stversions
.stfolder
*.sync-conflict-*
.syncthing.*
desktop.ini
.tmp.driveupload
*.tmp
.~*
.obsidian/workspace.json
.obsidian/workspaces.json
.obsidian/workspace
.obsidian/cache
.obsidian/cache/**
.trash/
__pycache__/
*.pyc
.git/index.lock
.DS_Store
Thumbs.db
```

## 검증 체크리스트

```bash
# WSL2 측 vault 파일 수
find ~/projects/2nd-brain-vault -type f ! -path '*/.stfolder/*' | wc -l

# Windows 측 vault 파일 수 (PowerShell)
(Get-ChildItem D:\Gdrive\2nd-brain-vault -Recurse -File).Count

# 충돌 파일 0 확인
find ~/projects/2nd-brain-vault -name ".sync-conflict-*"

# 핵심 파일 spot check
ls ~/projects/2nd-brain-vault/CLAUDE.md
```

End-to-end 양방향 round-trip:
```bash
echo "from $(hostname) $(date)" > ~/projects/2nd-brain-vault/00_inbox/sync-roundtrip-test.md
# 다른 머신에서 수 분 후 (Drive for Desktop polling 대기)
ls ~/projects/2nd-brain-vault/00_inbox/sync-roundtrip-test.md
```

## 트러블슈팅

### SyncTrayzor 가 의도와 다른 GUI 포트로 뜸

증상: Web UI Settings 에 "시작옵션이 GUI 주소를 덮어쓰고 있습니다" 표시.

원인: SyncTrayzor 가 mirrored mode 의 포트 충돌 감지 → 자동 random 포트 override.

조치:
1. SyncTrayzor → File → Settings → Syncthing 탭 → "Override Syncthing's listen address" 체크 해제
2. Web UI → Settings → GUI → GUI Listen Address 명시 입력 (`127.0.0.1:8385`) → Save → Restart
3. SyncTrayzor 가 다시 자동 override 시도하면, WSL2 측 GUI 포트가 정말 8384 인지 확인 (충돌 시 SyncTrayzor 가 비킨 것이라면 정상)

### 페어링이 "Connecting..." 에서 멈춤

체크 순서:
1. 같은 머신 내라면 명시적 address 추가 (`tcp://127.0.0.1:22000` 또는 WSL_IP·WIN_HOST)
2. 다른 머신 간이면 outbound TCP 22000 + HTTPS 443 (discovery) 방화벽 확인
3. Device ID 가 정확한지 (오타 한 글자에도 페어링 실패)
4. 양쪽 모두 device 등록 + 승인 완료됐는지

### 파일 권한 에러

증상: Windows → WSL2 방향 파일이 root 소유로 생성됨.

조치:
- 양쪽 폴더 Advanced 탭 → **Ignore Permissions: ✅ 체크** 확인
- 이미 잘못 생성된 파일은 `sudo chown -R $USER:$USER ~/projects/2nd-brain-vault/`

### `.sync-conflict-*` 파일 누적

원인: 양쪽에서 같은 파일 동시 편집 또는 시계 차이.

조치:
1. 충돌 파일 내용 확인 (`diff` 로 원본과 비교)
2. 어느 쪽을 살릴지 결정 → 한쪽 삭제
3. 빈번하면 Obsidian/편집기 사용 패턴 점검 (한 머신에서만 편집하는 규약)

### Drive for Desktop 이 수상한 파일을 클라우드로 올림

원인: `.stignore` 가 Syncthing 만 가르치고, Drive for Desktop 은 별도. Drive for Desktop 은 Windows 폴더의 모든 파일을 클라우드에 보낸다.

조치:
- `.stignore` 패턴이 의도대로 작동해서 Windows 측에 노이즈가 안 가도록 — Syncthing 측 ignore 가 첫 방어선
- 이미 클라우드에 올라간 노이즈는 Drive 웹에서 직접 삭제

### 연결됐지만 type=relay-server (mirrored mode 특수)

증상: 페어링은 성공, 두 device 가 connected, 동기는 작동. 그러나 device 카드 또는 REST API 의 `connections` 가 `type: relay-server`, `address: <외부 IP>:22067` (Syncthing 공용 relay). 외부 트래픽 + 지연 + 처리량 한계 발생.

원인: WSL2 mirrored mode 에서 WSL2·Windows 가 동일 LAN IP 공유 → 양쪽 Syncthing 이 같은 sync 포트(22000) 두고 경쟁 → 한쪽이 random 포트(예: 57534) 로 fallback (SyncTrayzor 자동 처리) → Windows Defender Firewall 이 random 포트의 LAN inbound 를 차단 → discovery 가 LAN candidate(`tcp://<LAN-IP>:<random>`) 를 알려도 inbound 도달 불가 → Syncthing 이 relay 로 fallback. NAT mode 에선 발생 안 함 (다른 LAN 대역이라 포트 경쟁 없음).

해결 (mirrored mode 의 localhost 양방향 포워딩 활용):

1. **Windows Syncthing 의 sync 포트 명시 핀** — Web UI → Actions → Settings → Connections → Sync Protocol Listen Addresses:
   ```
   tcp://0.0.0.0:22001, dynamic+https://relays.syncthing.net/endpoint, quic://0.0.0.0:22001
   ```
   포트 값은 WSL2 측 22000 과 다른 값이면 자유. Save → Restart Syncthing.

2. **양 peer 의 Address 를 localhost 로 명시** — 양쪽 Web UI → Remote Devices → 상대 device 편집 → Addresses:
   - Windows 측 → WSL2 device → `tcp://127.0.0.1:22000, dynamic`
   - WSL2 측 → Windows device → `tcp://127.0.0.1:22001, dynamic`

3. **검증** — REST API 또는 Web UI 의 connections 보기:
   ```bash
   APIKEY=$(grep -oP '<apikey>\K[^<]+' ~/.local/state/syncthing/config.xml | head -1)
   curl -ksS -H "X-API-Key: $APIKEY" "https://127.0.0.1:8384/rest/system/connections"
   ```
   `type: tcp-server` (또는 `tcp-client`), `address: 127.0.0.1:<port>`, `isLocal: True` 로 떨어지면 직결 성공.

본 케이스는 mirrored mode 전용. NAT mode 의 LAN 직결 문제는 step 4 의 portproxy 단계로 별도 해결.

## 운영 사례 — 첫 적용 (2026-05-04 ~)

| 머신 | 셋업 일자 | 비고 |
|---|---|---|
| laptop (mirrored mode) | 2026-05-04 | SyncTrayzor 자동 GUI 포트 override 경험. 명시적 8385 로 통일 |
| hospital PC (NAT mode) | 2026-05-04 진행 중 | 정본 보유 머신이 아니라 받기 머신 (Windows D:\ 가 cloud 에서 먼저 채워짐) |
| desktop (NAT mode) | 2026-05-04 | Windows 측 GUI 가 SyncTrayzor override 로 8384 에 바인딩 (XML 은 8385). NAT mode 라 무해 — 그대로 운영 |

새 머신 추가 시 본 문서 업데이트.

## 관련 문서

- 결정 근거·아키텍처: `2nd-brain-vault/knowledge/02_areas/brain-system/research/2026-05-04_sync-architecture-roadmap.md`
- Obsidian × WSL2 9P 한계: `2nd-brain-vault/knowledge/02_areas/brain-system/research/2026-05-04_obsidian-wsl2-limitation.md`
- vault 시스템 운영 규약: `2nd-brain-vault/CLAUDE.md`
