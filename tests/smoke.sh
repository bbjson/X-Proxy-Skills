#!/usr/bin/env bash
# 端到端冒烟测试：全部在临时 HOME 里跑，不碰真实配置，不依赖网络（--no-probe）。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
XPS="$ROOT/bin/xps"
TMP="$(mktemp -d)"
export HOME="$TMP/home"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy || true
mkdir -p "$HOME/bin"

pass=0; failn=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; failn=$((failn+1)); }
check(){ if eval "$2"; then ok "$1"; else bad "$1"; fi; }

cleanup(){ rm -rf "$TMP"; }
trap cleanup EXIT

echo "== 1. 语法与数据"
check "xps.py 可编译" "python3 -m py_compile '$ROOT/scripts/xps.py'"
check "mirrors.json 合法" "python3 -c 'import json,sys; json.load(open(sys.argv[1]))' '$ROOT/data/mirrors.json'"
check "--version" "'$XPS' --version | grep -q '^xps '"

echo "== 2. doctor（离线）"
printf 'export KEEP=1\n' > "$HOME/.bashrc"
out=$("$XPS" doctor --no-net 2>&1)
check "doctor 输出系统行" "grep -q '^系统' <<<\"\$out\""
check "doctor 不含凭据字段" "! grep -qiE 'token|auth' <<<\"\$out\""
check "doctor --json 可解析" "'$XPS' doctor --no-net --json | python3 -c 'import json,sys; json.load(sys.stdin)'"

echo "== 3. dry-run 不落盘"
"$XPS" apply --only pip,npm,hf --no-probe --dry-run >/dev/null 2>&1
check "dry-run 没创建 pip.conf" "[ ! -e '$HOME/.config/pip/pip.conf' ]"
check "dry-run 没改 .bashrc" "grep -qx 'export KEEP=1' '$HOME/.bashrc' && [ \$(wc -l < '$HOME/.bashrc') -eq 1 ]"

echo "== 4. apply + verify"
"$XPS" apply --only pip,npm,hf --no-probe --yes >/dev/null 2>&1
check "pip.conf 写了 tuna" "grep -q 'index-url = https://pypi.tuna.tsinghua.edu.cn/simple' '$HOME/.config/pip/pip.conf'"
check "npmrc 写了 npmmirror" "grep -q '^registry=https://registry.npmmirror.com' '$HOME/.npmrc'"
check "env.sh 有 HF_ENDPOINT" "grep -q 'HF_ENDPOINT' '$HOME/.config/x-proxy-skills/env.sh'"
check "bashrc 追加托管块且保留原文" "grep -q 'x-proxy-skills' '$HOME/.bashrc' && grep -qx 'export KEEP=1' '$HOME/.bashrc'"
check "hfd 可执行" "[ -x '$HOME/bin/hfd' ]"
check "verify 通过" "'$XPS' verify --only pip,npm,hf --no-probe >/dev/null 2>&1"

echo "== 5. 幂等"
before=$(ls "$HOME/.local/share/x-proxy-skills/backups" | wc -l)
out=$("$XPS" apply --only pip,npm,hf --no-probe --yes 2>&1)
after=$(ls "$HOME/.local/share/x-proxy-skills/backups" | wc -l)
check "第二次不产生新备份" "[ '$before' -eq '$after' ]"
check "第二次提示已是目标状态" "grep -q '已是目标状态' <<<\"\$out\""

echo "== 6. 非托管配置的保护"
printf 'channels:\n  - conda-forge\n' > "$HOME/.condarc"
out=$("$XPS" apply --only conda --no-probe --yes 2>&1)
check "无 --force 时跳过 .condarc" "grep -q '跳过' <<<\"\$out\""
check ".condarc 未被改动" "grep -qx '  - conda-forge' '$HOME/.condarc'"
"$XPS" apply --only conda --no-probe --yes --force >/dev/null 2>&1
check "--force 后 .condarc 带托管标记" "head -1 '$HOME/.condarc' | grep -q 'managed-by: x-proxy-skills'"
check ".condarc 指向 tuna" "grep -q 'mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main' '$HOME/.condarc'"
conda_id=$("$XPS" rollback --list | tail -1 | awk '{print $1}')

echo "== 7. cargo 追加不毁原配置"
mkdir -p "$HOME/.cargo"
printf '[build]\nincremental = true\n' > "$HOME/.cargo/config.toml"
"$XPS" apply --only cargo --no-probe --yes >/dev/null 2>&1
check "保留 [build]" "grep -q '^\[build\]' '$HOME/.cargo/config.toml' && grep -q 'incremental = true' '$HOME/.cargo/config.toml'"
check "加了 replace-with" "grep -q 'replace-with = \"xps\"' '$HOME/.cargo/config.toml'"
cargo_id=$("$XPS" rollback --list | tail -1 | awk '{print $1}')

echo "== 8. rollback"
"$XPS" rollback --to "$cargo_id" --yes >/dev/null 2>&1
check "cargo 回到用户原样" "[ \"\$(cat '$HOME/.cargo/config.toml')\" = \"\$(printf '[build]\nincremental = true')\" ]"
"$XPS" rollback --to "$conda_id" --yes >/dev/null 2>&1
check "condarc 回到用户原样" "grep -qx '  - conda-forge' '$HOME/.condarc' && ! grep -q 'managed-by' '$HOME/.condarc'"

first=$("$XPS" rollback --list | head -1 | awk '{print $1}')
"$XPS" rollback --to "$first" --yes >/dev/null 2>&1
check "pip.conf 被删除（应用前不存在）" "[ ! -e '$HOME/.config/pip/pip.conf' ]"
check "npmrc 被删除" "[ ! -e '$HOME/.npmrc' ]"
check ".bashrc 恢复原文" "[ \"\$(cat '$HOME/.bashrc')\" = 'export KEEP=1' ]"
check "hfd 被删除" "[ ! -e '$HOME/bin/hfd' ]"

echo "== 9. 拒绝带凭据的 URL"
if "$XPS" gh 'https://user:tok@github.com/a/b' >/dev/null 2>&1; then
  bad "带凭据 URL 应被拒绝"
else
  ok "带凭据 URL 被拒绝"
fi

echo
if [ "$failn" -eq 0 ]; then
  printf '\033[32m全部通过\033[0m（%d 项）\n' "$pass"
else
  printf '\033[31m%d 项失败\033[0m（通过 %d）\n' "$failn" "$pass"
  exit 1
fi
