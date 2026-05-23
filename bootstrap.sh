#!/usr/bin/env bash
# 2nd-brain vault 부트스트랩
# 빈 PARA 골격(knowledge/ + sources/) + 운영 가이드를 @-import 하는 얇은 CLAUDE.md 로더를
# 새 vault 디렉토리에 생성한다. 데이터(vault)와 운영(이 repo)을 분리하는 3-tier 모델의 진입점.
#
# 사용:  ./bootstrap.sh [대상_vault_경로]
#   기본 대상: ~/projects/2nd-brain-vault
#
# 안전: 대상이 이미 존재하고 비어있지 않으면 덮어쓰지 않고 중단(멱등).
set -euo pipefail

# --- 경로 결정 -------------------------------------------------------------
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # = 이 공개 repo(2nd-brain)
SKELETON="$REPO_DIR/templates/vault-skeleton"
VAULT_DIR="${1:-$HOME/projects/2nd-brain-vault}"

# vault 의 CLAUDE.md 가 @-import 할 가이드 경로. 공개 repo 를 관례 위치
# (~/projects/2nd-brain)에 clone 했다고 가정. 다른 곳이면 생성된 CLAUDE.md 를 직접 수정.
GUIDE_REF="~/projects/2nd-brain"

echo "▶ 공개 가이드 repo : $REPO_DIR"
echo "▶ 대상 vault       : $VAULT_DIR"
echo

# --- 사전 점검 -------------------------------------------------------------
[ -d "$SKELETON" ] || { echo "✋ 골격을 찾을 수 없습니다: $SKELETON" >&2; exit 1; }
if [ -e "$VAULT_DIR" ] && [ -n "$(ls -A "$VAULT_DIR" 2>/dev/null)" ]; then
  echo "✋ '$VAULT_DIR' 가 이미 존재하고 비어있지 않습니다. 덮어쓰지 않고 중단합니다." >&2
  echo "   (다른 경로를 인자로 주거나, 기존 vault 를 직접 확인하세요.)" >&2
  exit 1
fi

# --- 1) PARA 골격 복사 -----------------------------------------------------
mkdir -p "$VAULT_DIR"
cp -r "$SKELETON/." "$VAULT_DIR/"
echo "✅ PARA 골격 복사 (knowledge/ + sources/ × 00_inbox..04_archive)"

# --- 2) 얇은 CLAUDE.md 로더 생성 (없을 때만) -------------------------------
if [ ! -f "$VAULT_DIR/CLAUDE.md" ]; then
  cat > "$VAULT_DIR/CLAUDE.md" <<EOF
# (개인) 2nd-brain vault — 데이터 전용

> 이 저장소는 **데이터(knowledge + sources)** 만 담습니다.
> 운영 방법론은 공개 가이드를 \`@\`-import 해서 가져옵니다.
> 공개 repo 를 \`$GUIDE_REF\` 가 아닌 다른 곳에 두었다면 아래 경로를 맞춰 수정하세요.

@$GUIDE_REF/methodology/brain-system/README.md
@$GUIDE_REF/methodology/brain-system/claude-instruction-layers.md

## 내 개인 설정 (직접 채우기)

- 호칭:
- 개인 운영 규칙·계정·도구 스택 등 *이 머신/사람에 한정된* 내용을 여기에 추가합니다.
- (개인 가정이 큰 운영 자산은 별도 비공개 repo 로 분리 권장 — 가이드 참조)
EOF
  echo "✅ 얇은 CLAUDE.md 로더 생성 (가이드 @-import + 개인설정 자리)"
else
  echo "↷ CLAUDE.md 가 이미 있어 건너뜀"
fi

# --- 3) 로컬 git 버전관리 (vault 본동기는 SyncThing 이지만 로컬 history 권장) ---
if [ ! -d "$VAULT_DIR/.git" ]; then
  git -C "$VAULT_DIR" init -q
  git -C "$VAULT_DIR" add -A
  git -C "$VAULT_DIR" commit -q -m "초기 vault 골격 (2nd-brain bootstrap)" || true
  echo "✅ git init + 초기 커밋"
else
  echo "↷ .git 이 이미 있어 건너뜀"
fi

echo
echo "🎉 완료. 다음 단계:"
echo "  1) $VAULT_DIR/CLAUDE.md 의 '내 개인 설정' 채우기"
echo "  2) sources/00_inbox/ 에 자료를 떨구고 brainify 로 흡수"
echo "  3) 다중기기 동기는 SyncThing 설정 (가이드 참조)"
