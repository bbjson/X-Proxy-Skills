#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xps — X-Proxy-Skills 主程序.

一个不靠"猜测"的国内网络加速工具：
探测 → 备份 → 应用 → 验证 → 一键回滚。

设计红线（改代码前先读）：
  1. 任何写操作之前先整文件备份；
  2. 不擅自关闭 TLS 校验（sslverify / strict-ssl / NODE_TLS_REJECT_UNAUTHORIZED 一律不碰）；
  3. 不打印任何凭据、token、私有 registry 地址；
  4. 第三方加速前缀只用于公开资源，URL 里出现凭据直接拒绝；
  5. 已有非本工具管理的配置文件，默认拒绝覆盖（除非 --force）。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

UA = "x-proxy-skills/1.0 (+https://github.com/)"
SKILL_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = SKILL_ROOT / "data" / "mirrors.json"
MARK = "x-proxy-skills"
MARK_LINE = f"# managed-by: {MARK}"
MARK_BEGIN = f"# >>> {MARK} >>>"
MARK_END = f"# <<< {MARK} <<<"

STATE_DIR = Path(os.environ.get("XPS_STATE_DIR") or Path.home() / ".local/share/x-proxy-skills")
CACHE_DIR = Path(os.environ.get("XPS_CACHE_DIR") or Path.home() / ".cache/x-proxy-skills")
BACKUP_DIR = STATE_DIR / "backups"
STATE_FILE = STATE_DIR / "state.json"
CACHE_FILE = CACHE_DIR / "probe.json"
CACHE_TTL = 3600


# ---------------------------------------------------------------- 基础工具

class Skip(Exception):
    """可以预期的不执行原因（不是错误）。"""


class Fail(Exception):
    """执行失败。"""


def now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def expand(p: str) -> Path:
    return Path(os.path.expanduser(p))


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None
    except OSError:
        return None


def atomic_write(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.xps.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    if mode is not None:
        os.chmod(tmp, mode)
    os.replace(tmp, path)


def load_data() -> dict:
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    by_id = {e["id"]: e for e in data["ecosystems"]}
    for e in data["ecosystems"]:
        src = e.get("mirrors_from")
        if src and src in by_id:
            e["mirrors"] = [dict(m) for m in by_id[src]["mirrors"]]
            e.setdefault("probe", by_id[src]["probe"])
    return data


PROJECT_FILES = {"npm": ".npmrc", "uv": "uv.toml"}


def eco_path(eco: dict, project: str | None) -> Path | None:
    """返回该生态本次要写/要读的真实路径；没有文件落点（如 go）时返回 None。"""
    raw = eco.get("path")
    if project and eco["id"] in PROJECT_FILES:
        return (Path(project).expanduser().resolve() / PROJECT_FILES[eco["id"]])
    if project and eco.get("project_only") and raw:
        return Path(project).expanduser().resolve() / Path(raw).name
    return expand(raw) if raw else None


def eco_by_id(data: dict) -> dict:
    return {e["id"]: e for e in data["ecosystems"]}


def sel(ecos: list[dict], only: str | None, exclude: str | None, include_optin: bool) -> list[dict]:
    if only:
        want = [x.strip() for x in only.split(",") if x.strip()]
        known = {e["id"] for e in ecos}
        unknown = [x for x in want if x not in known]
        if unknown:
            raise Fail(f"未知生态: {', '.join(unknown)}（可用: {', '.join(sorted(known))}）")
        return [e for e in ecos if e["id"] in want]
    out = []
    ex = {x.strip() for x in (exclude or "").split(",") if x.strip()}
    for e in ecos:
        if e["id"] in ex:
            continue
        if e.get("optin") and not include_optin:
            continue
        out.append(e)
    return out


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"history": []}


def save_state(st: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(STATE_FILE, json.dumps(st, ensure_ascii=False, indent=2) + "\n")


# ---------------------------------------------------------------- 探测

def curl_probe(url: str, timeout: int = 8) -> tuple[str, float | None]:
    cmd = ["curl", "-sS", "-L", "-o", "/dev/null", "-w", "%{http_code} %{time_total}",
           "--max-time", str(timeout), "-A", UA, url]
    code, best = "000", None
    for _ in range(2):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        except subprocess.TimeoutExpired:
            continue
        parts = p.stdout.split()
        if len(parts) == 2:
            c, t = parts[0], float(parts[1])
            if c != "000":
                code = c
                if best is None or t < best:
                    best = t
    return code, best


def probe_eco(eco: dict, timeout: int = 8) -> list[dict]:
    accept = set(eco["probe"].get("accept", [200]))
    tmpl = eco["probe"]["url"]
    fb = eco["probe"].get("fallback_url")
    out = []
    for m in eco["mirrors"]:
        url = tmpl.replace("{base}", m["base"])
        code, ms = curl_probe(url, timeout)
        alive = code.isdigit() and int(code) in accept
        if fb and not alive:
            code2, ms2 = curl_probe(fb.replace("{base}", m["base"]), timeout)
            if code2.isdigit() and int(code2) in accept:
                code, ms = code2, ms2
        ok = code.isdigit() and int(code) in accept
        out.append({"name": m["name"], "label": m.get("label", m["name"]),
                    "code": code, "ms": None if ms is None else round(ms * 1000, 1), "ok": ok})
    return out


def probe_all(ecos: list[dict], timeout: int, refresh: bool, verbose: bool) -> dict:
    cache = {}
    if not refresh:
        try:
            cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if now().timestamp() - cached.get("ts", 0) < CACHE_TTL:
                cache = cached.get("results", {})
        except Exception:
            pass

    todo = [e for e in ecos if e["id"] not in cache]
    if todo and verbose:
        print(f"  探测 {len(todo)} 个生态（并行，每个镜像最多 2 次）…", file=sys.stderr)
    results = dict(cache)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(probe_eco, e, timeout): e["id"] for e in todo}
        for fut in concurrent.futures.as_completed(futs):
            eid = futs[fut]
            try:
                results[eid] = sorted(fut.result(), key=lambda r: (not r["ok"], r["ms"] if r["ms"] is not None else 9e9))
            except Exception as ex:  # pragma: no cover
                results[eid] = []
                if verbose:
                    print(f"  ! {eid} 探测异常: {ex}", file=sys.stderr)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(CACHE_FILE, json.dumps({"ts": now().timestamp(), "results": results}, ensure_ascii=False) + "\n")
    return {e["id"]: sorted(results.get(e["id"], []),
                            key=lambda r: (not r["ok"], r["ms"] if r["ms"] is not None else 9e9))
            for e in ecos}


# ---------------------------------------------------------------- 选择镜像

def choose(eco: dict, args, probes: dict) -> dict:
    ms = eco["mirrors"]
    if getattr(args, "mirror", None):
        for m in ms:
            if m["name"] == args.mirror:
                return m
        raise Fail(f"{eco['id']}: 没有名为 {args.mirror} 的镜像（可选: {', '.join(m['name'] for m in ms)}）")
    if not args.no_probe:
        for r in probes.get(eco["id"], []):
            if r["ok"]:
                for m in ms:
                    if m["name"] == r["name"]:
                        return m
    return ms[0]


# ---------------------------------------------------------------- 渲染（生成新文件内容）

INI_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def ini_set(text: str | None, section: str | None, kv: dict[str, str]) -> str:
    """在 ini/npmrc 里精确改 key，保留注释与其它配置。section=None 表示无节格式。"""
    lines = (text or "").splitlines()
    key_re = re.compile(r"^(\s*)([A-Za-z0-9_.\-]+)(\s*=\s*)(.*)$")

    if section is None:
        ranges = [(0, len(lines))]
        header_needed = False
    else:
        start = next((i for i, ln in enumerate(lines) if (m := INI_RE.match(ln)) and m.group(1) == section), None)
        if start is None:
            new = list(lines) + ([""] if lines and lines[-1].strip() else []) + [f"[{section}]"]
            new += [f"{k} = {v}" for k, v in kv.items()]
            return "\n".join(new) + "\n"
        end = next((i for i in range(start + 1, len(lines)) if INI_RE.match(lines[i])), len(lines))
        ranges = [(start + 1, end)]
        header_needed = True

    pending = dict(kv)
    out: list[str] = []
    seen_sections = 0
    for i, ln in enumerate(lines):
        in_range = any(a <= i < b for a, b in ranges)
        if header_needed and i == ranges[0][0] - 1:
            out.append(ln)
            # 缺失的 key 紧跟 section 头插入
            for k in list(pending):
                out.append(f"{k} = {pending.pop(k)}")
            continue
        m = key_re.match(ln)
        if in_range and m and m.group(2) in kv:
            k = m.group(2)
            if k in pending:
                out.append(f"{k}{m.group(3)}{kv[k]}")
                pending.pop(k)
            else:
                continue  # 删掉重复行
        else:
            out.append(ln)
    if pending and not header_needed:
        for k, v in pending.items():
            out.append(f"{k}={v}")
    if not out:
        out = [f"{k}={v}" for k, v in kv.items()]
    return "\n".join(out) + "\n"


def render_pip(eco, m, force, path) -> tuple[str, str, list[str]]:
    old = read_text(path)
    notes: list[str] = []
    if old and re.search(r"^\s*extra-index-url\s*=", old, re.M):
        notes.append("检测到 extra-index-url，pip 会同时查两个源；如非必要建议注释掉")

    # 旧源留下的 trusted-host 等于对旧域名永久关掉证书校验；换到 https 源后应清掉
    old_index = re.search(r"^\s*index-url\s*=\s*(\S+)", old or "", re.M)
    old_host = urlparse(old_index.group(1)).hostname if old_index else None
    new = ini_set(old, "global", {"index-url": m["index"]})
    if old_host and m["index"].startswith("https://"):
        th = re.search(r"^\s*trusted-host\s*=\s*(\S+)\s*$", new, re.M)
        if th and th.group(1) == old_host and urlparse(m["index"]).hostname != old_host:
            new = re.sub(r"^\s*trusted-host\s*=.*\n?", "", new, flags=re.M)
            notes.append(f"移除随旧源留下的 trusted-host={old_host}（https 源不需要，留着等于对旧域名关闭证书校验）")
    return "file", new, notes


def render_npm(eco, m, force, path) -> tuple[str, str, list[str]]:
    old = read_text(path) or ""
    if not path.parent.exists():
        raise Skip(f"{path.parent} 不存在（--project 要给一个真实项目目录）")
    new = ini_set(old, None, {"registry": m["base"]})
    return "file", new, []


def conda_yaml(m) -> str:
    cloud = m["cloud"]
    return f"""{MARK_LINE}
# 频道名不变，只把 URL 指到国内镜像；`conda install -c conda-forge x` 照常可用
channels:
  - conda-forge

channel_priority: strict
show_channel_urls: true

default_channels:
  - {m['base']}/anaconda/pkgs/main
  - {m['base']}/anaconda/pkgs/r
  - {m['base']}/anaconda/pkgs/msys2

custom_channels:
  conda-forge: {cloud}
  pytorch: {cloud}
  pytorch-lts: {cloud}
  nvidia: {cloud}
  bioconda: {cloud}
  menpo: {cloud}
  simpleitk: {cloud}
  msys2: {cloud}
"""


def render_conda(eco, m, force, path) -> tuple[str, str, list[str]]:
    old = read_text(path)
    if old and MARK_LINE not in old and not force:
        raise Skip(f"已存在非本工具管理的 {path}（{len(old.splitlines())} 行）；"
                   f"要接管请加 --force（会先备份）")
    return "file", conda_yaml(m), []


def cargo_block(m, existing: str = "") -> str:
    body = (f"[source.crates-io]\nreplace-with = \"xps\"\n\n"
            f"[source.xps]\nregistry = \"{m['sparse']}\"\n")
    if not re.search(r"^\s*\[net\]", existing, re.M):
        body += "\n[net]\ngit-fetch-with-cli = true\n"
    return f"{MARK_BEGIN}\n{body}{MARK_END}\n"


def render_cargo(eco, m, force, path) -> tuple[str, str, list[str]]:
    old = read_text(path) or ""
    notes: list[str] = []
    if old and MARK_BEGIN in old and MARK_END in old:
        new = re.sub(rf"{re.escape(MARK_BEGIN)}.*?{re.escape(MARK_END)}\n?",
                     lambda _m: cargo_block(m, old), old, flags=re.S)
    elif old:
        if re.search(r"^\s*\[source\.crates-io\]", old, re.M) and not force:
            raise Skip(f"{path} 里已有 [source.crates-io]，加 --force 才会覆盖（先备份）")
        new = old.rstrip("\n") + "\n\n" + cargo_block(m, old)
    else:
        new = cargo_block(m)
    try:
        import tomllib
        tomllib.loads(new)
    except ImportError:
        pass
    except Exception as ex:
        raise Fail(f"生成的 {path} 不是合法 TOML（{ex}）；已中止，未写入")
    return "file", new, notes


def uv_toml(m) -> str:
    return (f"{MARK_LINE}\n"
            f"# uv 不读 pip.conf；这里用 uv 的默认索引（uv >= 0.4.23 支持 default = true）\n"
            f"[[index]]\nurl = \"{m['index']}\"\ndefault = true\n")


def render_uv(eco, m, force, path) -> tuple[str, str, list[str]]:
    old = read_text(path) or ""
    notes: list[str] = []
    if old and MARK_LINE not in old and not force:
        raise Skip(f"已存在非本工具管理的 {path}；要接管请加 --force（先备份）")
    new = uv_toml(m)
    try:
        import tomllib
        tomllib.loads(new)
    except ImportError:
        pass
    except Exception as ex:
        raise Fail(f"生成的 {path} 不是合法 TOML（{ex}）；已中止")
    if old and "[[index]]" in old and MARK_LINE not in old:
        notes.append("原文件里已有 [[index]] 表，--force 后会被替换")
    return "file", new, notes


def poetry_block(m) -> str:
    return (f"{MARK_BEGIN}\n"
            f"[[tool.poetry.source]]\n"
            f"name = \"xps\"\n"
            f"url = \"{m['index']}\"\n"
            f"priority = \"primary\"\n"
            f"{MARK_END}\n")


def render_poetry(eco, m, force, path) -> tuple[str, str, list[str]]:
    old = read_text(path)
    if old is None:
        raise Skip(f"{path} 不存在：poetry 只能项目级配置，先 `poetry new/init`，再用 --project <dir>")
    if "[tool.poetry]" not in old and "[project]" not in old:
        raise Skip(f"{path} 里没有 [tool.poetry]/[project]，不像 poetry 项目")
    if MARK_BEGIN in old and MARK_END in old:
        new = re.sub(rf"{re.escape(MARK_BEGIN)}.*?{re.escape(MARK_END)}\n?",
                     lambda _m: poetry_block(m), old, flags=re.S)
    else:
        clashes = re.findall(r"^\s*\[\[tool\.poetry\.source\]\]", old, re.M)
        if clashes and not force:
            raise Skip(f"{path} 已有 {len(clashes)} 个 [[tool.poetry.source]]；加 --force 才追加 primary 源")
        new = old.rstrip("\n") + "\n\n" + poetry_block(m)
    try:
        import tomllib
        tomllib.loads(new)
    except ImportError:
        pass
    except Exception as ex:
        raise Fail(f"合并后的 {path} 不是合法 TOML（{ex}）；已中止")
    notes = ["priority=primary 会让 poetry 只查这个源；需要保留官方源请改用 priority=supplemental"]
    return "file", new, notes


HF_ENV = f"""{MARK_LINE} 由 `xps apply --only hf` 生成
# 只要 HF_ENDPOINT 指向 hf-mirror，transformers / diffusers / huggingface-cli 全走镜像
export HF_ENDPOINT="${{HF_ENDPOINT:-https://hf-mirror.com}}"
# 国内直连 HF 的 xet 后端经常超时，关掉更稳
export HF_HUB_DISABLE_XET="${{HF_HUB_DISABLE_XET:-1}}"

# ---- 二进制下载器（npmmirror CDN，2026-11-23 实测可下）----
export PLAYWRIGHT_DOWNLOAD_HOST="${{PLAYWRIGHT_DOWNLOAD_HOST:-https://cdn.npmmirror.com/binaries/playwright}}"
export PUPPETEER_DOWNLOAD_BASE_URL="${{PUPPETEER_DOWNLOAD_BASE_URL:-https://cdn.npmmirror.com/binaries/chrome-for-testing}}"
export ELECTRON_MIRROR="${{ELECTRON_MIRROR:-https://npmmirror.com/mirrors/electron/}}"
export npm_config_disturl="${{npm_config_disturl:-https://registry.npmmirror.com/-/binary/node}}"
# ---- Flutter 中国官方镜像 ----
export PUB_HOSTED_URL="${{PUB_HOSTED_URL:-https://pub.flutter-io.cn}}"
export FLUTTER_STORAGE_BASE_URL="${{FLUTTER_STORAGE_BASE_URL:-https://storage.flutter-io.cn}}"
"""

BASHRC_BLOCK = f"""# >>> {MARK} >>>
[ -f "$HOME/.config/x-proxy-skills/env.sh" ] && . "$HOME/.config/x-proxy-skills/env.sh"
# <<< {MARK} <<<
"""

HFD = """#!/usr/bin/env bash
# hfd —— 走 hf-mirror 的模型下载器（由 x-proxy-skills 安装）
set -euo pipefail
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
if [ $# -eq 0 ]; then
  cat >&2 <<'EOF'
用法:
  hfd <repo_id> [--local-dir 目录] [--include "*.safetensors"]
  hfd --help
说明: 等价于 huggingface-cli download，但强制走 hf-mirror.com
EOF
  exit 2
fi
if command -v hf >/dev/null 2>&1; then
  exec hf download "$@"
elif command -v huggingface-cli >/dev/null 2>&1; then
  exec huggingface-cli download "$@"
else
  echo "未找到 hf / huggingface-cli: pip install -U huggingface_hub" >&2
  exit 1
fi
"""

GHCLONE = """#!/usr/bin/env bash
# ghclone —— GitHub 前缀轮换 + 重试（由 x-proxy-skills 安装）
# 只用于公开资源；URL 里带凭据会直接拒绝。
set -uo pipefail

PREFIXES=(
  "https://ghproxy.net/"
  "https://gh-proxy.com/"
  "https://ghfast.top/"
  "https://githubproxy.cc/"
)
DIRECT_TIMEOUT=25

die() { echo "ghclone: $*" >&2; exit 1; }

case "${1:-}" in
  -h|--help|"")
    cat <<'EOF'
用法:
  ghclone <https://github.com/owner/repo(.git)> [目标目录]   # clone，直连→前缀轮换
  ghclone raw <url>                                          # 取 raw/release 文件到 stdout
  ghclone prefixes                                           # 逐个探测可用前缀
说明: 不改任何 git 全局配置；私有仓库请别用本脚本。
EOF
    exit 0 ;;
  prefixes)
    for p in "${PREFIXES[@]}"; do
      code=$(curl -s -L -o /dev/null -w '%{http_code} %{time_total}s' --max-time 12 \\
        "${p}https://raw.githubusercontent.com/octocat/Hello-World/master/README" || echo "000 -")
      printf '%-32s %s\\n' "$p" "$code"
    done
    exit 0 ;;
  raw)
    shift; url="${1:-}"; [ -n "$url" ] || die "缺少 url"
    key="https://github.com/"
    case "$url" in *"@"*|*"token"*|*"Authorization"*) die "URL 含凭据，拒绝走第三方前缀" ;; esac
    if out=$(curl -fsSL --max-time "$DIRECT_TIMEOUT" "$url" 2>/dev/null); then printf '%s' "$out"; exit 0; fi
    for p in "${PREFIXES[@]}"; do
      if out=$(curl -fsSL --max-time 40 "${p}${url}" 2>/dev/null); then printf '%s' "$out"; exit 0; fi
    done
    die "直连与所有前缀均失败" ;;
esac

url="$1"; dest="${2:-}"
case "$url" in *"@"*|*"token"*'='*) die "URL 含凭据，拒绝走第三方前缀（会泄露 token）" ;; esac
case "$url" in https://github.com/*) ;; *) die "只接受 https://github.com/... 形式" ;; esac

echo "→ 直连尝试（${DIRECT_TIMEOUT}s 上限）" >&2
if timeout "$DIRECT_TIMEOUT" git clone --depth 1 "$url" ${dest:+"$dest"} 2>/dev/null; then
  echo "✓ 直连成功" >&2; exit 0
fi
for p in "${PREFIXES[@]}"; do
  echo "→ 前缀 $p" >&2
  if timeout 90 git clone --depth 1 "${p}${url}" ${dest:+"$dest"} 2>/dev/null; then
    echo "✓ 通过 $p 成功" >&2; exit 0
  fi
  sleep 1
done
die "直连与所有前缀均失败（可先跑 ghclone prefixes 看哪个还活着）"
"""


def github_helpers() -> list[tuple[Path, str, int]]:
    """只装助手脚本，绝不改 git 全局配置。"""
    return [(expand("~/bin/ghclone"), GHCLONE, 0o755)]


# ---------------------------------------------------------------- 计划与执行

class Op:
    def __init__(self, eco: str, kind: str, path: Path | None = None, content: str | None = None,
                 mode: int | None = None, argv: list[str] | None = None, undo: list[str] | None = None,
                 sudo: bool = False):
        self.eco, self.kind, self.path, self.content = eco, kind, path, content
        self.mode, self.argv, self.undo, self.sudo = mode, argv, undo, sudo


APT_OFFICIAL = re.compile(r"https?://(?:archive|security|ports)\.ubuntu\.com|https?://deb\.debian\.org")


def apt_files() -> list[Path]:
    files: list[Path] = []
    classic = Path("/etc/apt/sources.list")
    if classic.exists():
        files.append(classic)
    d = Path("/etc/apt/sources.list.d")
    if d.is_dir():
        files += sorted(d.glob("*.sources"))
    return files


def apt_rewrite(text: str, host: str) -> str | None:
    """只换 host（顺带把 http 升到 https），保留路径 /ubuntu、/debian 与所有其它字段。"""
    if not APT_OFFICIAL.search(text):
        return None
    return APT_OFFICIAL.sub(f"https://{host}", text)


def build_plan(ecos: list[dict], args, probes: dict) -> tuple[list[Op], list[str], dict]:
    ops: list[Op] = []
    notes: list[str] = []
    picks: dict[str, dict] = {}

    for eco in ecos:
        eid = eco["id"]
        try:
            m = choose(eco, args, probes)
            picks[eid] = m
        except Fail as ex:
            notes.append(f"[{eid}] 跳过：{ex}")
            continue

        if eco["type"] == "file":
            if eid in ("apt", "docker"):
                continue  # 单独处理（需要 sudo）
            if eco.get("project_only") and not getattr(args, "project", None):
                notes.append(f"[{eid}] 跳过：{eco['label']} 只能项目级配置，请加 --project <目录>")
                continue
            renderer = {"pip": render_pip, "npm": render_npm, "conda": render_conda,
                        "cargo": render_cargo, "uv": render_uv, "poetry": render_poetry}.get(eid)
            if renderer is None:
                notes.append(f"[{eid}] 跳过：没有 renderer")
                continue
            path = eco_path(eco, getattr(args, "project", None))
            try:
                _, content, en = renderer(eco, m, args.force, path)  # type: ignore[misc]
            except Skip as ex:
                notes.append(f"[{eid}] 跳过：{ex}")
                continue
            notes.extend(f"[{eid}] {n}" for n in en)
            old = read_text(path)
            if old == content and not args.force:
                notes.append(f"[{eid}] 已是目标状态（{m['label']}），无需写入")
                continue
            ops.append(Op(eid, "file", path=path, content=content))

        elif eco["type"] == "env":  # hf
            env_path = expand(eco["path"])
            content = HF_ENV.replace("https://hf-mirror.com", m["base"]) if m["name"] != "hf-mirror" else HF_ENV
            if read_text(env_path) != content or args.force:
                ops.append(Op(eid, "file", path=env_path, content=content))
            bashrc = expand("~/.bashrc")
            cur = read_text(bashrc) or ""
            if (MARK not in cur) or args.force:
                new = (cur.rstrip("\n") + "\n\n" if cur.strip() else "") + BASHRC_BLOCK
                ops.append(Op(eid + ":bashrc", "file", path=bashrc, content=new))
            hfd = expand("~/bin/hfd")
            if read_text(hfd) != HFD or args.force:
                ops.append(Op(eid + ":hfd", "file", path=hfd, content=HFD, mode=0o755))

        elif eco["type"] == "helper":  # github
            for path, content, mode in github_helpers():
                if read_text(path) != content or args.force:
                    ops.append(Op(eid, "file", path=path, content=content, mode=mode))

        elif eco["type"] == "command":  # go
            go = shutil.which("go")
            if not go:
                notes.append(f"[{eid}] 跳过：PATH 里没有 go（装了再跑 --only go）")
                continue
            cur = subprocess.run([go, "env", "GOPROXY"], capture_output=True, text=True).stdout.strip()
            want = m["proxy"]
            if cur == want and not args.force:
                notes.append(f"[{eid}] 已是 {want}，无需写入")
                continue
            ops.append(Op(eid, "command", argv=[go, "env", "-w", f"GOPROXY={want}"],
                          undo=[go, "env", "-u", "GOPROXY"] if cur else None))

    # --- sudo 类：只有 --only 显式点名才做
    if args.only:
        for eid in ("docker", "apt"):
            if eid not in {x.strip() for x in args.only.split(",")}:
                continue
            eco = next(e for e in ecos if e["id"] == eid) if any(e["id"] == eid for e in ecos) else None
            if eco is None:
                continue
            m = choose(eco, args, probes)
            picks[eid] = m
            if eid == "docker":
                path = expand(eco["path"])
                old = read_text(path)
                if old is None:
                    try:
                        old = subprocess.run(["sudo", "-n", "cat", str(path)], capture_output=True,
                                             text=True, check=True).stdout
                    except Exception:
                        old = None
                try:
                    data = json.loads(old) if old else {}
                except json.JSONDecodeError as ex:
                    notes.append(f"[docker] 跳过：{path} 不是合法 JSON（{ex}）")
                    continue
                mirrors = data.get("registry-mirrors") or []
                if m["base"] in mirrors and not args.force:
                    notes.append(f"[docker] 已包含 {m['base']}")
                    continue
                mirrors = [m["base"]] + [x for x in mirrors if x != m["base"]]
                data["registry-mirrors"] = mirrors[:5]
                ops.append(Op(eid, "file", path=path,
                              content=json.dumps(data, ensure_ascii=False, indent=2) + "\n", sudo=True))
            else:  # apt（classic sources.list + deb822 *.sources 都处理）
                host = m["host"]
                files = apt_files()
                if not files:
                    notes.append("[apt] 跳过：没找到 /etc/apt/sources.list 或 sources.list.d/*.sources")
                    continue
                changed = 0
                for path in files:
                    old = read_text(path)
                    if old is None:
                        continue
                    new = apt_rewrite(old, host)
                    if new is None or new == old:
                        continue
                    ops.append(Op(eid, "file", path=path, content=new, sudo=True))
                    changed += 1
                if not changed:
                    notes.append("[apt] 没有可替换的官方源行（可能已经换过源）")
                elif len(files) > 1:
                    notes.append(f"[apt] 会改 {changed}/{len(files)} 个 apt 源文件")
                if any(path.suffix == ".sources" for path in files):
                    notes.append("[apt] 检测到 deb822 *.sources，已按 URIs 行换 host")
    return ops, notes, picks


def make_backup_id() -> str:
    # 微秒级 + pid：保证按目录名字典序 == 时间序（rollback --list 的 tail -1 必须是最近一次）
    return now().strftime("%Y%m%d-%H%M%S-%f") + f"-{os.getpid() % 1000:03d}"


def apply_ops(ops: list[Op], args, picks: dict | None = None) -> dict:
    bid = make_backup_id()
    bdir = BACKUP_DIR / bid
    manifest = {"id": bid, "created_at": now().isoformat(timespec="seconds"),
                "host": os.uname().nodename, "items": []}

    # 先把所有文件读一遍：读不了就在动任何东西之前失败
    prepared: list[tuple[int, Op, str | None, int]] = []
    for i, op in enumerate(ops):
        if op.kind != "file":
            continue
        assert op.path is not None
        path = op.path
        try:
            old = path.read_text(encoding="utf-8") if path.exists() else None
        except PermissionError:
            raise Fail(f"{path} 读不了（需要 sudo）；为免半途而废已中止，未写入任何文件")
        except OSError as ex:
            raise Fail(f"{path} 读不了（{ex}）；未写入任何文件")
        mode = (path.stat().st_mode & 0o777) if path.exists() else (op.mode or 0o644)
        prepared.append((i, op, old, mode))

    done: list[str] = []
    try:
        for i, op, old, mode in prepared:
            path = op.path
            assert path is not None
            item = {"eco": op.eco, "kind": "file", "path": str(path),
                    "existed": old is not None, "mode": mode}
            if args.dry_run:
                if old is not None:
                    item["backup"] = "(dry-run 未写)"
                manifest["items"].append(item)
                diff = difflib.unified_diff((old or "").splitlines(), (op.content or "").splitlines(),
                                            fromfile=f"{path} (当前)", tofile=f"{path} (应用后)", lineterm="")
                print("\n".join(diff) or f"(无内容变化) {path}")
                continue
            if old is not None:
                bdir.mkdir(parents=True, exist_ok=True)
                bf = bdir / f"{i:02d}-{path.name}"
                bf.write_text(old, encoding="utf-8")
                item["backup"] = str(bf.relative_to(bdir))
            manifest["items"].append(item)
            write_file(path, op.content or "", mode)
            done.append(item["path"])

        for op in ops:
            if op.kind != "command" or not op.argv:
                continue
            if args.dry_run:
                print(f"$ {' '.join(op.argv)}")
                continue
            p = subprocess.run(op.argv, capture_output=True, text=True)
            if p.returncode != 0:
                raise Fail(f"命令失败: {' '.join(op.argv)}\n{p.stderr.strip()}")
            manifest["items"].append({"eco": op.eco, "kind": "command",
                                      "argv": op.argv, "undo": op.undo})
            done.append(" ".join(op.argv))
    except Exception as ex:
        if args.dry_run:
            raise
        # 半途失败：先把已经写下去的恢复，再留下 aborted 记录，保证"一条命令回到原样"成立
        manifest["aborted"] = True
        manifest["error"] = str(ex)
        restored = 0
        for item in reversed(manifest["items"]):
            try:
                if item["kind"] == "file":
                    if item.get("existed") and item.get("backup") and item["backup"] != "(dry-run 未写)":
                        write_file(Path(item["path"]), (bdir / item["backup"]).read_text(encoding="utf-8"),
                                   item.get("mode"))
                        restored += 1
                    elif not item.get("existed"):
                        Path(item["path"]).unlink(missing_ok=True)
                        restored += 1
                elif item.get("undo"):
                    subprocess.run(item["undo"], capture_output=True)
            except Exception:
                pass
        bdir.mkdir(parents=True, exist_ok=True)
        atomic_write(bdir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        if isinstance(ex, Fail):
            raise Fail(f"{ex}\n（已自动回滚 {restored} 项；备份 id={bid}，可 `xps rollback --to {bid}` 复查）")
        raise Fail(f"{ex}\n（已自动回滚 {restored} 项；备份 id={bid}）")

    if not args.dry_run and manifest["items"]:
        bdir.mkdir(parents=True, exist_ok=True)
        manifest["applied"] = done
        atomic_write(bdir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        st = load_state()
        st.setdefault("history", []).append({
            "id": bid, "at": manifest["created_at"],
            "items": [x["path"] if x["kind"] == "file" else " ".join(x["argv"])
                      for x in manifest["items"]],
            "picks": {k: v["name"] for k, v in (picks or {}).items()},
            "project": getattr(args, "project", None),
        })
        st["last_backup"] = bid
        st["last_picks"] = {k: v["name"] for k, v in (picks or {}).items()}
        st["last_project"] = getattr(args, "project", None)
        save_state(st)
        prune_backups(keep=int(os.environ.get("XPS_KEEP_BACKUPS", "20")))
    return manifest


def prune_backups(keep: int = 20) -> None:
    """只保留最近 keep 个备份；带 aborted 标记的也照样轮转。"""
    if keep <= 0 or not BACKUP_DIR.exists():
        return
    dirs = sorted((p for p in BACKUP_DIR.iterdir() if (p / "manifest.json").exists()), key=lambda p: p.name)
    for old in dirs[:-keep]:
        shutil.rmtree(old, ignore_errors=True)


def write_file(path: Path, content: str, mode: int | None) -> None:
    """先普通写；权限不够再走 sudo（仅在免密 sudo 可用时）。"""
    try:
        atomic_write(path, content, mode)
        return
    except PermissionError:
        pass
    except OSError as ex:
        raise Fail(f"{path} 写不了（{ex}）；可用 `xps rollback --to <id>` 恢复已写入的项")
    if subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode != 0:
        raise Fail(f"{path} 需要 sudo 且当前无免密 sudo；请用 sudo 手动写，或配好 NOPASSWD 再跑")
    tmp = Path("/tmp") / f"xps-{os.getpid()}-{path.name}"
    tmp.write_text(content, encoding="utf-8")
    p = subprocess.run(["sudo", "-n", "install", "-m", oct(mode or 0o644)[2:], str(tmp), str(path)],
                       capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if p.returncode != 0:
        raise Fail(f"sudo 写 {path} 失败: {p.stderr.strip()}")


# ---------------------------------------------------------------- 验证

def match_any(eco: dict, value: str, key: str) -> dict | None:
    """配置值是否指向本工具已知的任一镜像（而不是必须等于"当前最快"）。"""
    if not value:
        return None
    for m in eco["mirrors"]:
        cand = m.get(key)
        if cand and (cand.rstrip("/") == value.rstrip("/") or cand in value):
            return m
    return None


def verify_eco(eco: dict, picks: dict, project: str | None = None) -> tuple[str, str]:
    eid = eco["id"]
    if not picks.get(eid):
        return "skip", "本次未选择"
    path = eco_path(eco, project)
    try:
        if eid in ("pip", "uv", "poetry", "npm", "conda", "cargo", "hf", "docker"):
            if path is None:
                return "fail", "该生态缺 path 配置"
            if eid != "docker" and not path.exists():
                return "skip", "尚未配置（文件不存在）"
        if eid in ("pip", "uv", "poetry"):
            txt = read_text(path) or ""
            key = "index-url" if eid == "pip" else "url"
            if eid == "poetry":
                got = re.search(r'url\s*=\s*"([^"]+)"', txt)
            elif eid == "uv":
                got = re.search(r'url\s*=\s*"([^"]+)"', txt)
            else:
                got = re.search(r"^\s*index-url\s*=\s*(\S+)", txt, re.M)
            value = got.group(1) if got else ""
            hit = match_any(eco, value, "index")
            if not hit:
                return "fail", (value or "未配置" if value else "未配置")
            if eid == "poetry" and 'priority = "primary"' not in txt:
                return "fail", f"{hit['name']} 但缺 priority=primary"
            if eid == "uv" and "default = true" not in txt:
                return "fail", f"{hit['name']} 但缺 default=true"
            return "ok", f"{hit['name']}  {value}"
        if eid == "npm":
            txt = read_text(path) or ""
            got = re.search(r"^\s*registry\s*=\s*(\S+)", txt, re.M)
            value = got.group(1) if got else ""
            hit = match_any(eco, value, "base")
            return ("ok", f"{hit['name']}  {value}") if hit else ("fail", value or "未配置")
        if eid == "conda":
            txt = read_text(path) or ""
            for m in eco["mirrors"]:
                if m["base"].split("://", 1)[1] in txt:
                    return "ok", f"{m['name']}  {m['base']}"
            return "fail", "未发现已知镜像地址"
        if eid == "cargo":
            txt = read_text(path) or ""
            for m in eco["mirrors"]:
                if m["sparse"] in txt:
                    return "ok", f"{m['name']}  {m['sparse']}"
            return "fail", "未配置已知 replace-with"
        if eid == "go":
            go = shutil.which("go")
            if not go:
                return "skip", "PATH 里没有 go"
            got = subprocess.run([go, "env", "GOPROXY"], capture_output=True, text=True).stdout.strip()
            if not got:
                return "skip", "尚未配置（GOPROXY 为空）"
            for m in eco["mirrors"]:
                if m["proxy"] == got:
                    return "ok", f"{m['name']}  {got}"
            return "fail", got or "未配置"
        if eid == "hf":
            txt = read_text(path) or ""
            rc = read_text(expand("~/.bashrc")) or ""
            need = ("HF_ENDPOINT", "PLAYWRIGHT_DOWNLOAD_HOST", "PUB_HOSTED_URL")
            hit = match_any(eco, txt, "base")
            ok = all(k in txt for k in need) and MARK in rc and expand("~/bin/hfd").exists()
            return ("ok", f"{hit['name'] if hit else '自定义'}  env.sh+hfd") if ok else \
                   ("fail", "env.sh / .bashrc / hfd 不完整")
        if eid == "github":
            p = expand("~/bin/ghclone")
            if not p.exists():
                return "skip", "尚未安装 ghclone"
            return ("ok", str(p)) if os.access(p, os.X_OK) else ("fail", "ghclone 不可执行")
        if eid == "docker":
            txt = read_text(path) or ""
            for m in eco["mirrors"]:
                if m["base"] in txt:
                    return "ok", f"{m['name']}  {m['base']}"
            return "fail", "daemon.json 里没有已知镜像"
        if eid == "apt":
            files = apt_files()
            if not files:
                return "skip", "没有 apt 源文件"
            texts = {f: read_text(f) or "" for f in files}
            left = sum(len(APT_OFFICIAL.findall(t)) for t in texts.values())
            hit = next((m for m in eco["mirrors"]
                        if any(m["host"] in t for t in texts.values())), None)
            if left:
                return "fail", f"仍有 {left} 处官方源"
            return ("ok", f"{hit['name']}  {hit['host']}") if hit else ("fail", "没有发现已知镜像 host")
    except Exception as ex:
        return "fail", f"验证异常: {ex}"
    return "skip", "无验证器"


# ---------------------------------------------------------------- 回滚

def rollback(bid: str | None, yes: bool, dry: bool) -> None:
    if not BACKUP_DIR.exists():
        raise Fail("没有任何备份记录")
    ids = sorted(p.name for p in BACKUP_DIR.iterdir() if (p / "manifest.json").exists())
    if not ids:
        raise Fail("没有任何备份记录")
    bid = bid or ids[-1]
    if bid not in ids:
        raise Fail(f"找不到备份 {bid}（可用: {', '.join(ids[-5:])}）")
    bdir = BACKUP_DIR / bid
    man = json.loads((bdir / "manifest.json").read_text(encoding="utf-8"))
    print(f"回滚 {bid}（{len(man['items'])} 项）")
    for item in reversed(man["items"]):
        if item["kind"] == "file":
            p = Path(item["path"])
            if dry:
                print(f"  会{'恢复' if item.get('existed') else '删除'} {p}")
                continue
            if item.get("existed") and item.get("backup"):
                if not yes:
                    ans = input(f"  恢复 {p} ? [y/N] ").strip().lower()
                    if ans != "y":
                        print("  跳过"); continue
                content = (bdir / item["backup"]).read_text(encoding="utf-8")
                write_file(p, content, item.get("mode"))
                print(f"  ✓ 恢复 {p}")
            else:
                if not yes:
                    ans = input(f"  删除 {p}（应用前不存在）? [y/N] ").strip().lower()
                    if ans != "y":
                        print("  跳过"); continue
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass
                print(f"  ✓ 删除 {p}")
        else:
            undo = item.get("undo")
            if not undo:
                print(f"  - {item['argv']}（无自动回滚，请手工处理）")
                continue
            if dry:
                print(f"  会执行: {' '.join(undo)}")
                continue
            p = subprocess.run(undo, capture_output=True, text=True)
            print(f"  {'✓' if p.returncode == 0 else '✗'} {' '.join(undo)}")
    print("提醒：已开着的 shell 需要 `source ~/.bashrc` 或重开才生效")


# ---------------------------------------------------------------- doctor / status

def cmd_doctor(args) -> int:
    info = {
        "os": f"{os.uname().sysname} {os.uname().release}",
        "distro": "",
        "shell": os.environ.get("SHELL", ""),
        "python": sys.version.split()[0],
        "curl": shutil.which("curl") or "",
        "proxies": {k: ("已设置" if os.environ.get(k) else "") for k in
                    ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY") if k in os.environ},
        "tools": {t: bool(shutil.which(t)) for t in ("node", "go", "cargo", "docker", "conda", "pip", "git")},
        "sudo_nopasswd": subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0,
    }
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                info["distro"] = line.split("=", 1)[1].strip('"')
    except Exception:
        pass

    data = load_data()
    ecos = data["ecosystems"]
    info["config"] = {}
    for eco in ecos:
        if eco["type"] in ("file", "env"):
            p = expand(eco["path"])
            txt = read_text(p)
            info["config"][eco["id"]] = {
                "path": str(p),
                "exists": txt is not None,
                "managed": bool(txt and MARK_LINE in txt),
                "lines": len(txt.splitlines()) if txt else 0,
            }
        elif eco["type"] == "command":
            go = shutil.which("go")
            info["config"][eco["id"]] = {"path": "go env", "exists": bool(go),
                                         "value": subprocess.run([go, "env", "GOPROXY"], capture_output=True,
                                                                 text=True).stdout.strip() if go else ""}
        else:
            info["config"][eco["id"]] = {"path": str(expand(eco["path"])),
                                         "exists": expand(eco["path"]).exists()}

    net = {}
    if not getattr(args, "no_net", False):
        for label, url in [("baidu", "https://www.baidu.com"), ("pypi", "https://pypi.org/simple/"),
                           ("github", "https://github.com"), ("hf", "https://huggingface.co")]:
            code, ms = curl_probe(url, timeout=6)
            net[label] = {"code": code, "ms": None if ms is None else round(ms * 1000, 1)}
    info["net"] = net

    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    print(f"系统      : {info['distro'] or info['os']}")
    print(f"shell     : {info['shell']}   python {info['python']}   curl {info['curl'] or '缺失!'}")
    prox = [k for k, v in info["proxies"].items() if v]
    print(f"代理变量  : {', '.join(prox) if prox else '未设置（直连）'}")
    print(f"工具      : " + "  ".join(f"{k}{'✓' if v else '✗'}" for k, v in info["tools"].items()))
    print(f"免密 sudo : {'是' if info['sudo_nopasswd'] else '否'}")
    if net:
        print("\n连通性  : " + "  ".join(f"{k}={v['code']}/{v['ms']}ms" if v["ms"] else f"{k}={v['code']}"
                                        for k, v in net.items()))
    print("\n配置现状：")
    for eid, c in info["config"].items():
        state = "已配置" if c.get("exists") else "无"
        if c.get("managed"):
            state += "(本工具管理)"
        print(f"  {eid:<8} {state:<16} {c['path']}")
    print("\n下一步：xps probe      看哪个镜像站现在最快")
    print("        xps apply --dry-run  看会改哪些文件")
    return 0


def cmd_status(args) -> int:
    st = load_state()
    hist = st.get("history", [])
    data = load_data()
    ecos = data["ecosystems"]
    by_name = {(e["id"], m["name"]): m for e in ecos for m in e["mirrors"]}
    picks = {eid: by_name[(eid, name)] for eid, name in (st.get("last_picks") or {}).items()
             if (eid, name) in by_name}
    rows = []
    for eco in ecos:
        status, detail = verify_eco(eco, picks, st.get("last_project")) if picks else ("?", "未记录本次选择")
        rows.append({"eco": eco["id"], "status": status, "detail": detail})
    bks = sorted(p.name for p in BACKUP_DIR.iterdir() if (p / "manifest.json").exists()) \
        if BACKUP_DIR.exists() else []
    out = {"history": hist[-5:], "backups": bks[-5:], "verify": rows}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print("最近应用：")
    for h in hist[-5:]:
        print(f"  {h['id']}  {h['at']}  {len(h['items'])} 项")
    print("备份：" + (", ".join(out["backups"]) or "无"))
    if not picks:
        print("（还没有 apply 记录；先跑 `xps apply --dry-run`）")
    else:
        print("上次选择的实际状态：")
        icon = {"ok": "✓", "fail": "✗", "skip": "-", "?": "?"}
        for r in rows:
            if r["status"] in ("ok", "fail"):
                print(f"  {icon[r['status']]} {r['eco']:<9} {r['detail']}")
    print("提示：重新探测并验证用 `xps verify --only pip,npm`")
    return 0


# ---------------------------------------------------------------- 子命令

def cmd_probe(args) -> int:
    data = load_data()
    ecos = sel(data["ecosystems"], args.only, None, include_optin=True)
    probes = probe_all(ecos, args.timeout, args.refresh, verbose=not args.json)
    if args.json:
        print(json.dumps(probes, ensure_ascii=False, indent=2))
        return 0
    for eco in ecos:
        rows = probes.get(eco["id"], [])
        best = next((r for r in rows if r["ok"]), None)
        print(f"\n{eco['id']:<9} {eco['label']}")
        for r in rows:
            if r["ok"]:
                flag = "★" if best and r["name"] == best["name"] else " "
                print(f"  {flag} {r['name']:<13} {r['code']:<4} {r['ms']:>8.1f} ms  {r['label']}")
            else:
                print(f"    {r['name']:<13} {r['code']:<4} {'--':>8}     {r['label']}  (不可用)")
        if not best:
            print("  ! 全部不可用：将回退到默认 #{0}（{1}）".format(1, eco["mirrors"][0]["label"]))
    return 0


def cmd_list(args) -> int:
    data = load_data()
    ecos = sel(data["ecosystems"], args.only, None, include_optin=True)
    if args.json:
        print(json.dumps(ecos, ensure_ascii=False, indent=2))
        return 0
    for e in ecos:
        flags = []
        if e.get("optin"):
            flags.append("需显式 --only 且可能要 sudo")
        print(f"\n{e['id']:<9} {e['label']}  {' '.join(flags)}")
        print(f"  目标: {e.get('path', '(命令)')}")
        for m in e["mirrors"]:
            print(f"    {m['name']:<13} {m.get('label','')}")
    return 0


def cmd_apply(args) -> int:
    data = load_data()
    ecos = sel(data["ecosystems"], args.only, args.exclude, include_optin=bool(args.only))
    probes = {} if args.no_probe else probe_all(ecos, args.timeout, args.refresh, verbose=not args.json)
    ops, notes, picks = build_plan(ecos, args, probes)

    if args.json and not args.dry_run and not args.yes:
        raise Fail("--json 模式不能等待交互确认，请加 --yes（或先 --dry-run）")

    if not args.json:
        for n in notes:
            print(f"  · {n}")
        if not ops:
            print("\n没有需要写入的项。")
            picks_ok = {k: v for k, v in picks.items()}
            if picks_ok:
                print("当前选择的镜像：")
                for k, v in picks_ok.items():
                    print(f"  {k:<9} {v['label']}")
            return 0
        print(f"\n计划写入 {len(ops)} 个文件/命令：")
        for op in ops:
            what = op.path if op.kind == "file" else " ".join(op.argv or [])
            print(f"  {op.eco:<14} {what}")
        if args.dry_run:
            print("\n—— dry-run 差异 ——")
        elif not args.yes:
            ans = input("\n确认执行？[y/N] ").strip().lower()
            if ans != "y":
                print("已取消")
                return 1

    manifest = apply_ops(ops, args, picks)
    if args.json:
        print(json.dumps({"backup_id": manifest["id"],
                          "applied": [i.get("path") or " ".join(i.get("argv", [])) for i in manifest["items"]],
                          "dry_run": args.dry_run}, ensure_ascii=False, indent=2))
        return 0
    if args.dry_run:
        print(f"\n(dry-run 结束，没有写入任何文件)")
        return 0
    print(f"\n✓ 写入完成，备份 id = {manifest['id']}（回滚: xps rollback）")
    for k, v in picks.items():
        print(f"  {k:<9} → {v['label']}  {v.get('base') or v.get('index') or v.get('proxy') or ''}")
    print("提示：已开着的 shell 请 `source ~/.bashrc`（或重开终端）；Docker 需重启服务才生效")
    return 0


def cmd_verify(args) -> int:
    data = load_data()
    ecos = sel(data["ecosystems"], args.only, args.exclude, include_optin=bool(args.only))
    probes = {} if args.no_probe else probe_all(ecos, args.timeout, args.refresh, verbose=False)
    picks = {e["id"]: choose(e, args, probes) for e in ecos}
    rows = []
    for eco in ecos:
        status, detail = verify_eco(eco, picks, getattr(args, "project", None))
        rows.append((eco["id"], eco["label"], status, detail))
    if args.json:
        print(json.dumps([{"eco": a, "label": b, "status": c, "detail": d} for a, b, c, d in rows],
                         ensure_ascii=False, indent=2))
    else:
        icon = {"ok": "✓", "fail": "✗", "skip": "-"}
        for a, b, c, d in rows:
            print(f"  {icon.get(c,'?')} {a:<9} {d}")
    return 0 if all(r[2] != "fail" for r in rows) else 1


def cmd_rollback(args) -> int:
    if args.list:
        if not BACKUP_DIR.exists():
            print("无备份")
            return 0
        for p in sorted(BACKUP_DIR.iterdir()):
            mf = p / "manifest.json"
            if mf.exists():
                man = json.loads(mf.read_text(encoding="utf-8"))
                print(f"{p.name}  {man['created_at']}  {len(man['items'])} 项")
        return 0
    rollback(args.to, args.yes, args.dry_run)
    return 0


def cmd_gh(args) -> int:
    url = args.url
    if not re.match(r"^https://github\.com/[\w.-]+/[\w.-]+", url):
        raise Fail("只接受 https://github.com/owner/repo 形式")
    if "://" in url and "@" in url.split("://", 1)[1]:
        raise Fail("URL 含凭据，拒绝走第三方前缀")
    data = load_data()
    eco = next(e for e in data["ecosystems"] if e["id"] == "github")
    mirrors = eco["mirrors"]
    direct_ok = False
    print(f"→ 直连 git clone {url}", file=sys.stderr)
    try:
        p = subprocess.run(["git", "clone", "--depth", "1", url] + ([args.dest] if args.dest else []),
                           timeout=30)
        direct_ok = p.returncode == 0
    except subprocess.TimeoutExpired:
        pass
    if direct_ok:
        print("✓ 直连成功", file=sys.stderr)
        return 0
    for m in mirrors:
        target = m["prefix"] + url
        print(f"→ 前缀 {m['label']} …", file=sys.stderr)
        try:
            p = subprocess.run(["git", "clone", "--depth", "1", target] + ([args.dest] if args.dest else []),
                               timeout=120)
        except subprocess.TimeoutExpired:
            continue
        if p.returncode == 0:
            print(f"✓ 通过 {m['label']} 成功", file=sys.stderr)
            return 0
    raise Fail("直连与所有前缀都失败；先跑 `xps probe --only github` 看哪个前缀活着")


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="xps", description="X-Proxy-Skills: 探测→备份→应用→验证→回滚 的国内网络加速工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  xps doctor                        环境体检
  xps probe                         测所有镜像站延迟
  xps apply --dry-run               看会改什么
  xps apply --only pip,npm          只配 pip + npm（自动选最快）
  xps apply --only conda --force    接管已有 .condarc
  xps apply --only docker           需要 sudo；重启 docker 才生效
  xps verify --only pip,npm         验证
  xps rollback --list               看备份
  xps rollback                      回滚最近一次""")
    ap.add_argument("-V", "--version", action="version", version="xps 1.1.0")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="环境与连通性体检")
    d.add_argument("--json", action="store_true")
    d.add_argument("--no-net", action="store_true")
    d.set_defaults(func=cmd_doctor)

    l = sub.add_parser("list", help="列出生态与镜像候选")
    l.add_argument("eco", nargs="?", help="只看某个生态")
    l.add_argument("--only")
    l.add_argument("--json", action="store_true")
    l.set_defaults(func=cmd_list)

    p = sub.add_parser("probe", help="并行探测镜像站")
    p.add_argument("--only")
    p.add_argument("--timeout", type=int, default=8)
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_probe)

    def add_auto(a):
        a.add_argument("--only", help="逗号分隔，例如 pip,npm")
        a.add_argument("--exclude")
        a.add_argument("--mirror", help="强制指定镜像名（xps list 查看）")
        a.add_argument("--no-probe", action="store_true", help="不探测，直接用默认候选")
        a.add_argument("--timeout", type=int, default=8)
        a.add_argument("--refresh", action="store_true")
        a.add_argument("--force", action="store_true", help="允许接管已有配置")
        a.add_argument("--project", metavar="DIR",
                       help="项目级落点：把 .npmrc / uv.toml / pyproject.toml 写进该项目而不是用户目录")
        a.add_argument("--json", action="store_true")

    a = sub.add_parser("apply", help="应用镜像配置")
    add_auto(a)
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--yes", "-y", action="store_true")
    a.set_defaults(func=cmd_apply)

    v = sub.add_parser("verify", help="验证当前配置")
    add_auto(v)
    v.set_defaults(func=cmd_verify)

    s = sub.add_parser("status", help="历史与备份")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)

    r = sub.add_parser("rollback", help="回滚")
    r.add_argument("--to")
    r.add_argument("--list", action="store_true")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--yes", "-y", action="store_true")
    r.set_defaults(func=cmd_rollback)

    g = sub.add_parser("gh", help="前缀轮换方式 clone GitHub（不改 git 全局配置）")
    g.add_argument("url")
    g.add_argument("dest", nargs="?")
    g.set_defaults(func=cmd_gh)

    args = ap.parse_args(argv)
    if args.cmd in ("probe", "apply", "verify", "gh") and not shutil.which("curl"):
        print("错误: 需要 curl（探测用）。请先安装 curl。", file=sys.stderr)
        return 2
    if args.cmd == "list" and args.eco and not args.only:
        args.only = args.eco
    try:
        return args.func(args)
    except Skip as ex:
        print(f"跳过: {ex}", file=sys.stderr)
        return 1
    except Fail as ex:
        print(f"错误: {ex}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130
    except Exception as ex:  # 兜底：不把 traceback 甩给用户
        if os.environ.get("XPS_DEBUG"):
            raise
        print(f"错误: {type(ex).__name__}: {ex}", file=sys.stderr)
        print("提示: XPS_DEBUG=1 可看完整 traceback", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
