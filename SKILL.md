---
name: x-proxy-skills
description: >
  中国大陆网络环境下的开发环境加速器：自动探测最快的国内镜像站，配置 pip/uv、npm/pnpm/yarn、
  conda、cargo、Go、Docker Registry、GitHub 加速前缀、HuggingFace(hf-mirror)、apt 源，
  并为每次改动做整文件备份与一键回滚。当用户说「下载慢」「装不上」「超时」「连接被重置」
  「ECONNRESET」「ETIMEDOUT」「SSL 握手失败」「换源」「换镜像」「镜像加速」「docker 拉不动」
  「pip 拉不动」「npm 装不动」「git clone 卡住」「github 打不开」「hf 下不动」「clash/代理配好了还是慢」
  时使用。也用于写 Dockerfile/CI 前的镜像源规划与排障。
license: MIT
compatibility: >
  Linux / macOS / WSL 优先（Ubuntu 22.04 实测）。依赖 bash、curl、python3(>=3.9)、git。
  需要 sudo 的项（docker、apt）只在显式 --only 指定时才会执行。
allowed-tools: Bash Read Write Edit Glob Grep
metadata:
  version: "1.0.0"
  category: devtools
  region: china-mainland
  verified: "2026-11-23"
  repo: https://github.com/<you>/X-Proxy-Skills
---

# X-Proxy-Skills

> **铁律：先探测，再备份，再写入，再验证；任何一步失败都能一条命令回到原样。**
> 不做「先跑起来再说」的检查 —— 不关 TLS 校验、不猜镜像、不改 git 全局配置。

## 什么时候用它

| 症状 | 动作 |
|---|---|
| `npm install` / `pip install` 卡在 0% 或超时 | `xps apply --only npm,pip` |
| `docker pull` 卡住 / TLS handshake timeout | `xps apply --only docker`（需 sudo，之后要重启 docker） |
| `git clone https://github.com/...` 卡住 / reset | `xps gh <url>` 或 `xps apply --only github` |
| `huggingface-cli download` 下不动 | `xps apply --only hf`，然后 `hfd <repo>` |
| conda solve 慢 / 下包慢 | `xps apply --only conda --force`（接管已有 .condarc） |
| 不知道问题在哪 | `xps doctor` → `xps probe` → `xps verify` |

## 30 秒上手

```bash
# 0. 体检（本机配置现状 + 连通性 + 是否有免密 sudo）
./bin/xps doctor

# 1. 看谁最快（并行探测，结果缓存 1 小时）
./bin/xps probe

# 2. 看会改什么（不写任何文件）
./bin/xps apply --dry-run

# 3. 应用（默认跳过需要 sudo 的 docker/apt）
./bin/xps apply --yes

# 4. 验证
./bin/xps verify

# 5. 不满意就回滚
./bin/xps rollback --list
./bin/xps rollback --yes
```

装到 pi / Claude Code：

```bash
# pi: ~/.agents/skills/（用户级）或 .agents/skills/（项目级）
ln -s "$PWD" ~/.agents/skills/x-proxy-skills
# 或者直接放 ~/bin 当普通命令用
ln -s "$PWD/bin/xps" ~/.local/bin/xps
```

## 决策流程（agent 必须按这个顺序）

1. **先 `xps doctor`**：确认 OS、有没有 curl、`HTTP(S)_PROXY` 是否设了、各配置文件的现状、有没有免密 sudo。
   - 如果 `HTTP_PROXY` 已经指向一个**活着的**本地代理（7890/7891/1080），先别换源 —— 先判断是代理本身的问题还是源的问题（`xps probe` 里直连延迟 vs 代理延迟）。
2. **`xps probe`**：只看 `★` 那行。全部 `不可用` 说明当前网络对镜像站也不通（更可能是 DNS/出口问题，不是换源能解决的），此时不要乱写配置。
3. **`xps apply --dry-run`**：把 diff 给用户看，特别是有 `extra-index-url`、已有 `[source.crates-io]`、已有 `.condarc` 的情况。
4. **`xps apply --only <需要的>`**：不要默认 `apply` 全量 —— 只改用户抱怨的那几个生态。
5. **`xps verify`**：必须回读配置、证明改对了，不要只看命令退出码。
6. 告诉用户：**已开的 shell 要 `source ~/.bashrc`**；docker/apt 要重启服务；npm/pip 建议顺手跑一次真实安装验证。

## 支持矩阵

| 生态 | 目标 | 探测 | 自动选最快 | 备份 | 说明 |
|---|---|---|---|---|---|
| `pip` | `~/.config/pip/pip.conf` | ✅ | ✅ | ✅ | 覆盖 uv/poetry（它们读同一个 index 配置需另配，见 references） |
| `npm` | `~/.npmrc` | ✅ | ✅ | ✅ | pnpm/yarn/bun 共用 registry |
| `conda` | `~/.condarc` | ✅ | ✅ | ✅ | 已有非托管 .condarc 时必须 `--force` |
| `cargo` | `~/.cargo/config.toml` | ✅ | ✅ | ✅ | sparse index |
| `go` | `go env -w GOPROXY` | ✅ | ✅ | ✅（命令级 undo） | 没装 go 自动跳过 |
| `hf` | `~/.config/x-proxy-skills/env.sh` + `~/bin/hfd` | ✅ | ✅ | ✅ | `HF_ENDPOINT=hf-mirror.com` |
| `github` | `~/bin/ghclone` | ✅ | ✅ | ✅ | **只装助手，不改 git 配置** |
| `docker` | `/etc/docker/daemon.json` | ✅ | ✅ | ✅ | opt-in + sudo |
| `apt` | `/etc/apt/sources.list` | ✅ | ✅ | ✅ | opt-in + sudo；deb822 系统需手工 |

## 安全红线

1. **第三方加速前缀 = 中间人**。`xps gh` / `ghclone` 只用于**公开**仓库；URL 含 `@`、token、`Authorization` 会直接拒绝。
2. **不关 TLS**。任何 `sslverify=false` / `strict-ssl=false` / `NODE_TLS_REJECT_UNAUTHORIZED=0` 都不做，用户明确要求也不代劳，只给出风险说明。
3. **不打印凭据**。`doctor`/`apply` 输出里不出现 `_authToken`、`//registry/:_auth`、私有 URL。
4. **托管标记**：本工具写的文件都带 `# managed-by: x-proxy-skills`（或 npmrc 里 `registry=` 单键）。看到标记才敢覆盖；没有标记一律 `--force`。
5. **备份先行**：每次 apply 生成 `~/.local/share/x-proxy-skills/backups/<id>/`（原文件逐份拷贝 + manifest.json），`rollback` 按 manifest 逆序恢复，应用前不存在的文件会被删掉。
6. 项目级 skill 里的脚本会以你的身份执行 —— 只在信任的仓库开 project trust。

## 常见误区

- **"换源就能解决一切"**：DNS 污染、出口限速、TLS 被插队不会因为换源变好。`xps probe` 全灭时先查网络（`references/troubleshooting.md`）。
- **"镜像越多越好"**：pip 同时配 `index-url` + `extra-index-url` 会出现依赖混淆（dependency confusion）风险，本工具只写一个主源。
- **"改完立刻生效"**：`~/.bashrc` 里的 env 要重新 source；docker 要 `systemctl restart docker`；已运行的进程不会继承新变量。
- **"镜像站是永久的"**：2024 年后大量公共 Docker 镜像站关停。`data/mirrors.json` 里每个源都带 `probe`，用 `xps probe --refresh` 定期复查。

## 扩展方式

新增一个镜像候选：只改 `data/mirrors.json` 里对应生态的 `mirrors` 数组（`name` 唯一即可），不需要改代码。
新增一个生态：`mirrors.json` 加一项 + `scripts/xps.py` 里加一个 renderer + 一个 verifier。
