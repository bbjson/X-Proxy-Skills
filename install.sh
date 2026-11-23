#!/usr/bin/env bash
# X-Proxy-Skills 安装脚本：把 bin/xps 链到 PATH，并可把 skill 装进 agent 的 skills 目录。
# 只创建符号链接，不改任何系统配置、不改你的镜像源。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${XPS_BIN_DIR:-$HOME/.local/bin}"
SKILLS_DIR="${XPS_SKILLS_DIR:-}"
UNINSTALL=0

usage() {
  cat <<'EOF'
用法: bash install.sh [--bin-dir DIR] [--skills-dir DIR] [--uninstall]

  --bin-dir DIR     把 xps 链到这里（默认 ~/.local/bin）
  --skills-dir DIR  额外把整个 skill 目录链到这里（例如 ~/.agents/skills 或 ~/.claude/skills）
  --uninstall       删除上面两个符号链接（不碰备份与配置）

环境变量: XPS_BIN_DIR / XPS_SKILLS_DIR 等同对应参数
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --bin-dir) BIN_DIR="${2:?}"; shift 2 ;;
    --skills-dir) SKILLS_DIR="${2:?}"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage; exit 2 ;;
  esac
done

link="$BIN_DIR/xps"
skill_link="${SKILLS_DIR:+$SKILLS_DIR/x-proxy-skills}"

if [ "$UNINSTALL" -eq 1 ]; then
  for p in "$link" "$skill_link"; do
    [ -n "$p" ] || continue
    if [ -L "$p" ]; then rm -f "$p" && echo "已删除 $p"; fi
  done
  exit 0
fi

for c in curl git python3; do
  command -v "$c" >/dev/null 2>&1 || { echo "缺少依赖: $c" >&2; exit 1; }
done
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
  || { echo "需要 python3 >= 3.9" >&2; exit 1; }

chmod +x "$ROOT/bin/xps" "$ROOT/scripts/xps.py"
mkdir -p "$BIN_DIR"
ln -sfn "$ROOT/bin/xps" "$link"
echo "✓ 命令   $link -> $ROOT/bin/xps"

if [ -n "$SKILLS_DIR" ]; then
  mkdir -p "$SKILLS_DIR"
  ln -sfn "$ROOT" "$skill_link"
  echo "✓ skill  $skill_link -> $ROOT"
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "! $BIN_DIR 不在 PATH 里，加一行： export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

echo
echo "下一步："
echo "  xps doctor              # 体检"
echo "  xps probe               # 测速"
echo "  xps apply --dry-run     # 看会改什么"
