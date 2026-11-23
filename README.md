# X-Proxy-Skills (xps)

> 国内网络环境下的开发环境加速器：**探测 → 备份 → 应用 → 验证 → 回滚**。
> 一个 Agent Skill，也是一条命令行工具。不猜镜像、不关 TLS、不改 git 全局配置。

```bash
xps doctor                 # 体检：系统 / 代理 / 配置现状 / 连通性 / 免密 sudo
xps probe                  # 并行测 9 类镜像站，★ 标最快（结果缓存 1h）
xps apply --dry-run        # 看 diff，不写任何文件
xps apply --only pip,npm   # 只配你抱怨的那几个
xps verify                 # 回读配置证明改对了
xps rollback --yes         # 不满意一条命令回原样
```

## 为什么不是"再写一份换源命令清单"

网上这类 skill 已经很多（见 `docs/调研-国内网络skill清单.md`），但绝大多数是「把 npm/pip 的换源命令抄一遍」。问题在于：

| 常见做法 | 实际后果 |
|---|---|
| 写死一个镜像地址 | 镜像站关停后配置变成毒药，且没人知道要改 |
| 直接覆盖 `.condarc` / `.cargo/config.toml` | 用户原有的 channels / build 配置消失 |
| 没有备份 | 出问题只能凭记忆手改回来 |
| 换完不验证 | 项目级 `.npmrc` 覆盖了全局，用户以为配好了其实没生效 |
| 为了"能跑"关掉 TLS 校验 | 中间人从此无法被发现 |
| 全局 `insteadOf` 劫持 github.com | 私有仓库和 `git push` 一起走第三方，token 泄漏 |

`xps` 针对每一条都做了对应设计：

- **探测驱动**：`data/mirrors.json` 里每个源都带探测 URL，`apply` 默认选当前最快的；镜像死了 `probe` 一眼能看出来。
- **最小改动**：只动目标键（`index-url` / `registry` / `registry-mirrors`），注释和其它配置原样保留。
- **托管标记**：本工具写的文件带 `# managed-by: x-proxy-skills`；已有非托管配置一律要求 `--force`。
- **整文件备份 + 逆序回滚**：`~/.local/share/x-proxy-skills/backups/<id>/`，应用前不存在过的文件回滚时会被删除。
- **验证器**：每个生态都有回读校验，`verify` 失败会返回非零退出码（可直接进 CI）。
- **安全红线**：不关 TLS、不打印凭据、带凭据的 URL 拒绝走第三方前缀。

## 支持矩阵

| 生态 | 配置落点 | 探测 | 自动选最快 | 备份 | 需要 sudo |
|---|---|---|---|---|---|
| pip（+ uv 说明） | `~/.config/pip/pip.conf` | ✅ | ✅ | ✅ | — |
| npm / pnpm / yarn / bun | `~/.npmrc` | ✅ | ✅ | ✅ | — |
| conda / mamba | `~/.condarc` | ✅ | ✅ | ✅ | — |
| cargo | `~/.cargo/config.toml`（sparse） | ✅ | ✅ | ✅ | — |
| go modules | `go env -w GOPROXY` | ✅ | ✅ | ✅ | — |
| HuggingFace | `HF_ENDPOINT` + `~/bin/hfd` | ✅ | ✅ | ✅ | — |
| GitHub | `~/bin/ghclone`（前缀轮换） | ✅ | ✅ | ✅ | — |
| Docker Registry | `/etc/docker/daemon.json` | ✅ | ✅ | ✅ | 是（opt-in） |
| apt（22.04 sources.list） | `/etc/apt/sources.list` | ✅ | ✅ | ✅ | 是（opt-in） |

## 安装

```bash
git clone <repo> ~/src/X-Proxy-Skills && cd ~/src/X-Proxy-Skills

# 命令 + skill 一起装（只建符号链接，不改任何配置）
bash install.sh --skills-dir ~/.agents/skills

# 或分开手工
ln -s "$PWD/bin/xps" ~/.local/bin/xps
ln -s "$PWD" ~/.claude/skills/x-proxy-skills
```

依赖：`bash`、`curl`、`python3 >= 3.9`、`git`。没有第三方 Python 包。

## 用法要点

```bash
# 强制指定源（跳过探测）
xps apply --only conda --mirror ustc

# 接管已有的非托管配置（会先备份）
xps apply --only conda --force

# 需要 sudo 的项必须显式点名，且不会自动重启服务
xps apply --only docker      # 之后手动 systemctl restart docker

# 机器可读输出（给 agent / CI 用）
xps probe --json
xps verify --json
xps doctor --json

# GitHub：直连失败自动试 4 个前缀，绝不改 git 全局配置
xps gh https://github.com/owner/repo /tmp/repo
```

退出码：`0` 成功 / `1` 有项目被跳过或验证失败 / `2` 错误 / `130` 中断。

## 目录结构

```
X-Proxy-Skills/
├── SKILL.md                 # Agent 读的入口（决策流程 + 红线）
├── README.md
├── bin/xps                  # 入口（找 python3 后调 scripts/xps.py）
├── scripts/xps.py           # 全部逻辑，约 900 行，无第三方依赖
├── data/mirrors.json        # 镜像候选 + 探测 URL（唯一需要经常维护的文件）
├── references/
│   ├── mirrors.md           # 各源实测延迟 + 每个工具真正的配置落点
│   ├── troubleshooting.md   # 症状 → 判据 → 处理（DNS/代理/TLS/各包管理器）
│   └── safety.md            # 威胁模型、红线、备份语义
├── tests/smoke.sh           # 沙箱 HOME 下的端到端测试（离线可跑）
└── docs/调研-国内网络skill清单.md
```

## 设计取舍

- **为什么用 Python 而不是纯 bash**：要改 ini / toml / json 三种格式还保留注释，bash 做不干净；Python 无三方依赖即可。
- **为什么不直接 `npm config set` / `pip config set`**：它们是各自工具的实现细节，版本间行为不同，且失败时只写一半。直接编辑目标文件 + 回读校验更可控。
- **为什么默认不改 apt/docker**：两者要 sudo、会中断服务（docker 重启停容器、apt 换源影响整个系统），必须显式点名。
- **为什么保留 `goproxy.io` 这种 4.8s 的源**：测速失败和源下线是两件事，留着能区分"全灭"和"慢"。

## 测试

```bash
bash tests/smoke.sh          # 在临时 HOME 里跑，不碰真实配置，不需要网络
```

## 完整度（如实说明）

已闭环：

- 9 类生态的探测 / 备份 / 应用 / 验证 / 回滚，29+ 项离线测试
- 写失败自动回滚、`--dry-run` 零落盘、托管标记保护、备份轮转（保留 20 份）
- `--json` 全命令机读输出；`--json` 下拒绝隐式交互
- cargo 生成结果用 `tomllib` 校验（不会产出非法 TOML，也不会重复 `[net]`）

还没做（`references/troubleshooting.md` 里给的是手工命令）：

- `uv` / `poetry` 的 renderer（它们不读 pip.conf）
- Ubuntu 24.04+ 的 deb822 `.sources`
- Maven / Gradle / gem / Flutter
- `--scope project`：项目级落点
- 代理本身的配置（本工具只探测和提示，不写 clash/v2ray 配置）

## 路线图

- [ ] `--scope project`：把镜像写进项目本地（`.npmrc` / `pip.conf` / `pyproject.toml`）而不是用户全局
- [ ] deb822（Ubuntu 24.04+ `/etc/apt/sources.list.d/*.sources`）支持
- [ ] uv / poetry 专用 renderer（目前只在 references 里给命令）
- [ ] Maven `settings.xml` / Gradle `init.gradle`
- [ ] `xps explain <错误文本>`：把报错映射到 troubleshooting.md 的条目
- [ ] 镜像站健康度趋势（多次 probe 存历史，画退化曲线）

## License

MIT
