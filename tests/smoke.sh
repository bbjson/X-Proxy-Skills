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

echo "== 9. cargo 不产出重复 [net]"
mkdir -p "$HOME/.cargo2"
printf '[build]\nincremental = true\n\n[net]\nretry = 3\n' > "$HOME/.cargo2/config.toml"
XPS_CARGO_TEST=1 python3 - "$ROOT" "$HOME/.cargo2/config.toml" <<'PYEOF'
import sys, pathlib
root, target = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
sys.path.insert(0, str(root / "scripts"))
import xps
eco = {"id": "cargo", "path": str(target)}
m = {"sparse": "sparse+https://rsproxy.cn/index/"}
_, new, _ = xps.render_cargo(eco, m, force=False)
out = pathlib.Path(str(target) + ".new")
out.write_text(new, encoding="utf-8")
import tomllib
d = tomllib.loads(new)
assert d["net"]["retry"] == 3, "原 [net] 内容应保留"
assert d["source"]["crates-io"]["replace-with"] == "xps"
PYEOF
check "cargo 合并后 TOML 合法且不重复 [net]" "[ $? -eq 0 ]"

echo "== 10. --json 不允许隐式交互"
"$XPS" apply --only pip --no-probe --json >/dev/null 2>&1
check "--json 缺 --yes 时返回非零" "[ $? -ne 0 ]"
check "--json 失败时没写 pip.conf" "[ ! -e '$HOME/.config/pip/pip.conf' ]"

echo "== 11. 写失败自动回滚"
mkdir -p "$HOME/blocked"
printf 'export KEEP=1\n' > "$HOME/blocked/.bashrc"
printf '' > "$HOME/blocked/bin"                # 父路径是普通文件：root 也写不进去
XPS_STATE_DIR="$TMP/state2" HOME="$HOME/blocked" \
  "$XPS" apply --only hf --no-probe --yes >/dev/null 2>&1
rc=$?
check "写失败返回非零" "[ $rc -ne 0 ]"
check "已写入的 .bashrc 被自动还原" "[ \"\$(cat '$HOME/blocked/.bashrc')\" = 'export KEEP=1' ]"
check "已写入的 env.sh 被自动删除" "[ ! -e '$HOME/blocked/.config/x-proxy-skills/env.sh' ]"
check "留下 aborted 备份记录" "grep -rq '\"aborted\": true' '$TMP/state2/backups' 2>/dev/null"
rm -rf "$HOME/blocked" "$TMP/state2" "$HOME/.cargo2"

echo "== 12. 拒绝带凭据的 URL"
if "$XPS" gh 'https://user:tok@github.com/a/b' >/dev/null 2>&1; then
  bad "带凭据 URL 应被拒绝"
else
  ok "带凭据 URL 被拒绝"
fi

echo "== 13. 符号链接安装可用"
mkdir -p "$TMP/links"
ln -sfn "$ROOT/bin/xps" "$TMP/links/xps"
check "经符号链接 --version 可用" "'$TMP/links/xps' --version | grep -q '^xps '"
check "经符号链接 doctor 可用" "'$TMP/links/xps' doctor --no-net | grep -q '^系统'"

echo
if [ "$failn" -eq 0 ]; then
  printf '\033[32m全部通过\033[0m（%d 项）\n' "$pass"
else
  printf '\033[31m%d 项失败\033[0m（通过 %d）\n' "$failn" "$pass"
  exit 1
fi
