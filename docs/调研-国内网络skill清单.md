# 国内网络环境问题 · Agent Skill 全网清单

> 调研时间：2026-11-23
> 方法：GitHub Code Search（`filename:SKILL.md` × 16 组关键词）+ GitHub Repo Search + skills.sh 注册表 API（`/api/search`）
> 命中口径：**专门**（或主要）解决中国大陆网络/镜像/代理问题的 skill，不是"某个部署文档里顺带提了一句镜像源"

## 0. 结论先说

- **没有一个官方"大全包"**。这个方向目前是散落的个人项目，绝大多数 0–10 star，更新到 2026 年 10–11 月的只有少数几个。
- 真正**成体系、可安装、带脚本和回滚**的只有 3 个：`loredunk/china-mirror-skills`、`routefox/cn-dev-network-skills`、`CacinieP/network-troubleshoot-skill`。
- 按用途分成 6 类共 **42 个已核实** + 4 个未核实（见 §7）。
- 生态里"镜像类" skill 高度同质化：都是 npm/pip/cargo/go/conda/apt/docker 换源命令的集合，差异在**是否有探活、是否有备份回滚、是否覆盖 Docker/HF/GitHub**。

---

## 1. A 类 · 综合镜像源加速（最值得装的一类）

| # | 仓库 / skill 路径 | 覆盖 | 关键特点 | 核实 |
|---|---|---|---|---|
| 1 | `loredunk/china-mirror-skills` → `china-mirror/skills/china-mirror/SKILL.md` | pip/uv/poetry、npm/pnpm/yarn、Docker Hub、Cargo、Homebrew、Conda、Go、Flutter、Docker CE 安装源、Python/Node 本体安装、HuggingFace（含 `hfd.sh`） | **脚本化最完整**：每个生态一个脚本目录 + `backup_config.sh` / `restore_config.sh` / `diagnose.sh`；带 `.claude-plugin` 插件清单 | ✅ 2026-11-22 更新（最新） |
| 2 | `routefox/cn-dev-network-skills` → `SKILL.md` | pip/uv/poetry/pdm、conda/mamba、npm/pnpm/yarn/corepack、Docker CE + Registry Mirror、GitHub、HuggingFace/hf-mirror/ModelScope、Go/Rust/Maven/Gradle、apt、Playwright/Puppeteer 二进制、HTTP(S)_PROXY | **覆盖面最广**（文档型）：`references/` 知识库 + 只读诊断脚本；流程固定为「先收集本机上下文 → 探测候选 → 选最快 → 生成命令 → 验证 → 给回滚」 | ✅ |
| 3 | `CacinieP/network-troubleshoot-skill` → `skills/network-troubleshoot/SKILL.md` | 通用网络排障（DNS/代理/SSL/HTTP/防火墙/包管理器）+ 国内/GFW 工作流 + 多进程应用的"代理层错配"检测 | **17+ 种 agent 适配器**（`.claude`/`.cursor`/`.codex`/`.windsurf`/`aider`/…），`install.sh <agent>` 一键装；安全边界写得很硬（只读优先、不擅自关 TLS 校验、不打印密钥） | ✅ |
| 4 | `LeoYeAI/agent-master-skills` → `skills/china-mirror-resolver/SKILL.md`（另有独立镜像 `The-Ladder-of-Rrogress/china-mirror-resolver`） | pip/npm/yarn/pnpm/conda/Docker/Go/Rust/Maven/Gradle/Homebrew/apt/yum/GitHub/HF | yaml 里声明 `last-verified: 2026-03-08`，自带 `scripts/*` + `references/*`，含 Cursor/Windsurf 适配 | ✅ |
| 5 | `itech001/fast-mirror-skill` → `SKILL.md` | npm/yarn/pnpm、pip/pip3/uv、brew、apt、gem、cargo、go、Docker、git clone | 触发面写得很宽（"用户抱怨下载慢"就触发），带 `evals/` | ✅ |
| 6 | `normdist-ai/china-mirrors` → `SKILL.md` | pip/npm/yarn/pnpm/cargo/go/NuGet/RubyGems/conda/brew/Gradle | **不带预置脚本**，让 agent 现写命令执行；会主动检测 `package.json`/`requirements.txt`/`go.mod` 等再建议 | ✅ |
| 7 | `diegosouzapw/awesome-omni-skill` → `skills/devops/mirror-optimizer/SKILL.md` | Docker/Python/Node/Go/Java/Ruby/Rust | "铁律：任何部署前先确认镜像源配置"；有明确的**不适用**边界 | ✅ |
| 8 | `Lord1Egypt/awesome-skill-forge` → `community/clawhub/c/china-dev-environment/SKILL.md` | npm/pip/Docker/GitHub 加速 + Google API 替代 + 开发工具代理 | 触发词最全（中英双语）；偏知识库 | ✅ |
| 9 | `HWMAT4-R6/mirror-switch` → `SKILL.md` | Linux 的 apt/pip/docker/npm/cargo/go | 纯 bash 引擎，`--mirror auto` **测速选站**，支持 cernet/tuna/ustc/阿里/hust/bfsu/nju/sjtu；自带 dry-run + 备份 + 回滚；可对远程 ssh / 容器执行 | ✅ |
| 10 | `ysyx2008/SailFish` → `skills/china-mirror-config/SKILL.md` | npm/pnpm/yarn、pip、Docker、apt/yum、Go、Maven、brew、Rust | 最薄的一档，就是命令速查表，好处是无脑照抄 | ✅ |
| 11 | `seed-forge/harness-ai-kit` → `skills/base-cn-registry-mirror-strategy/SKILL.md` | Dockerfile/CI 场景：Docker/Debian/Alpine/Node/Python/Maven/Gradle/Go | **唯一面向 Dockerfile 与 CI 的"分层策略"**（谁负责加速：宿主机 / CI 注入 / Dockerfile 内显式换源） | ✅ |
| 12 | `monkingame/flutter_lib` → `.agents/skills/cn-mirror/SKILL.md` | 项目级镜像记录 | 把项目用到的国内镜像写进 `docs/cn-mirror.md` 并在 `CLAUDE.md` 建引用；支持去重、标记失效 | ✅ |
| 13 | `jnMetaCode/superpowers-zh` → `skills/chinese-git-workflow/SKILL.md` | 中文开发工作流（含 npmmirror、镜像相关） | 偏"中文本土化"，不是纯网络 skill | ✅ |
| 14 | `skills.volces.com/china-mirrors`、`skills.volces.com/bootstrap-china-network` | 未知（页面 JS 渲染，正文取不到） | 火山引擎 SkillHub 收录，可在 skills.sh 检索到 | ⚠️ 未核实 |

---

## 2. B 类 · GitHub 专项加速

| # | 仓库 / skill 路径 | 干什么 | 核实 |
|---|---|---|---|
| 15 | `youbuwei/github-accelerator` → `SKILL.md` | **直连优先、镜像兜底、用前探测**；只读（明确禁止 push、禁止私有仓库/token 走第三方镜像、禁止改全局 git config） | ✅ v1.3.0 |
| 16 | `lg0219/github-ghclone` → `SKILL.md` | 加速前缀**自动轮换 + 重试**（单前缀挂死不卡死），配 `~/bin/ghclone` 别名 | ✅ |
| 17 | `Lucas-1u/git-push-cn` → `SKILL.md` | Windows + GFW 下 `git push/pull/clone` 排障（schannel / TLS 握手 / `Connection was reset` / 静默失败 / 梯子开着也推不上去）+ **推送前密钥泄露扫描** | ✅ v1.2.0 |
| 18 | `volcengine/OpenViking` → `bot/workspace/skills/github-proxy/SKILL.md` | 用 `githubproxy.cc` 前缀加速 clone/raw/release，备用 `ghfast.top`；skills.sh 上 185 次安装，是该类最"官方"的一个 | ✅ |
| 19 | `angri450/Nong.Dev.Net` → `ghproxy/SKILL.md` | `/ghproxy` 斜杠命令 + 链接自动改写 | ✅ |
| 20 | `neko233-com/AgentTeamWiki233` → `skill/SKILL.md` | 公司内网 GitHub 加速服务器（ghaccel233）+ 多 agent 接入 | ✅ |
| 21 | `SHYXIN/cn-skills-cli` | 不是 skill，是**给国内用的 skill 安装器**：Gitee/GitHub 双源 + 镜像加速 + 中文索引 | ✅ |

---

## 3. C 类 · Docker 镜像

| # | 仓库 / skill 路径 | 干什么 | 核实 |
|---|---|---|---|
| 22 | `full-stack-skills/devops-skills` → `skills/linuxmirrors-docker/SKILL.md`（配套 `linuxmirrors-os`） | LinuxMirrors 的 Docker CE 换源 + Registry Mirror 规划：版本选择、已有安装、`--only-registry`、多镜像地址、`daemon.json` 合并、验证与回滚 | ✅ |
| 23 | `typ431127/ddn-docker-mirror` → `SKILL.md` | 渡渡鸟镜像站 `docker.aityp.com` 的查询 CLI：镜像是否已同步、按平台（amd64/arm64）筛、队列/错误记录 | ✅ |
| 24 | `hellolukeding/docker-mirror-helper` → `docker-mirror-helper/SKILL.md` | 同上镜像站，偏"改写"：把 `docker pull`、Dockerfile/docker-compose/K8s YAML 里的镜像引用换成可用地址 | ✅ |
| 25 | `ccwq/ccwq-skill-list` → `skills/dockerhub-mirror/SKILL.md` | Docker Hub 拉取慢/registry 报错的分诊（网络/TLS/token/限流），并测速排序、刷新、发现镜像站 | ✅ |
| 26 | `hugogu/skills` → `skills/dockerhub-to-aliyun-acr-sync/SKILL.md` | 把 Docker Hub 某 tag 同步进阿里云 ACR 个人版；含 **GFW 双侧网络两阶段切换**流程 | ✅ |
| 27 | `zhaochongjie666-cyber/cjxdd` → `skills/xdd-docker-helper/SKILL.md` | Docker 镜像地址助手 | ✅ |
| 28 | `shanyou/skills` → `skills/docker-mirror-lookup/SKILL.md` | 镜像可用性查询 | ⚠️ 路径未核实 |
| 29 | `skills.volces.com/docker-mirror` | 火山 SkillHub 收录 | ⚠️ 未核实 |

---

## 4. D 类 · 代理 / 翻墙 / 抗封锁（"搭梯子"与"被墙后怎么办"）

| # | 仓库 / skill 路径 | 干什么 | 核实 |
|---|---|---|---|
| 30 | `1126misakp/proxy-expert` → `SKILL.md` | **端到端搭梯子专家**：VLESS+Reality+sing-box，部署 VPS 服务端 → 生成客户端配置 → 验收测试，全程带 `references/` | ✅ |
| 31 | `ielym/xray-easy` → `SKILL.md` | 一条命令装 Xray + Reality 服务端，一条命令生成 vless 链接/二维码；含"WireGuard 51820 被端口级封锁，换 8443 即通"的实测结论 | ✅ |
| 32 | `ystyleb/claude-vpn-skill` → `skills/x-ui-deploy/SKILL.md` | 3X-UI + VLESS+XHTTP+TLS+Cloudflare CDN，v4.2；明确写了"比 SS/Trojan/WireGuard/sing-box 更难被识别"的取舍 | ✅ |
| 33 | `riverscn/singbox-confgen` → `skills/sing-box-best-practice/SKILL.md` | **改分区/分流配置不踩坑**：sing-box 1.14+ 的 DNS、IPv6、geosite-cn/gfwlist 规则相互依赖，改一条会静默出错 | ✅ |
| 34 | `surgioproject/surgio` → `skills/migrate-v3-config/SKILL.md` | surgio 配置 v2→v3 迁移（机场/规则生成） | ✅ |
| 35 | `lanyz1/TGSEC-KB` → `hermes-skills/security/gfw-proxy-downloads/SKILL.md` | 走本机代理通道下载被墙官网文件/APK 的固定 work flow | ✅ |
| 36 | `Asura-2010/gemini-cli-skills` → `SKILL.md` | 把 Gemini CLI 当第二意见工具，**专为"需要代理的网络环境"配好代理**再调 | ✅ |
| 37 | `SorarinX/claude-web-fetch-proxy-skill` → `SKILL.md` | Claude Code `WebFetch` 失败诊断三板斧：preflight 拦截 / GFW / 代理错配 | ✅ |
| 38 | `daymade/claude-code-skills` → `tunnel-doctor/SKILL.md` | **Tailscale 与代理/VPN 共存**的冲突排查：TUN、DNS 劫持、SSH 到 WSL、curl 通但浏览器 503 | ✅ |
| 39 | `oaustegard/claude-skills` → `fetching-blocked-urls/SKILL.md` | 用 `r.jina.ai` 兜底取 403/付费墙/JS SPA 页面（非中国专属，但国内高频用） | ✅ |
| 40 | `manmonthW/termux-openclaw-android` | Android Termux 上装 OpenClaw + GFW 绕过 | ⚠️ 路径未核实 |
| 41 | `SHAOBUZHI/hermes-webui-deployment` | WSL2 + GFW 约束下部署 hermes-web-ui | ⚠️ 路径未核实 |

---

## 5. E 类 · 模型 / 数据集下载（HF 被墙的替代路径）

| # | 仓库 / skill 路径 | 干什么 | 核实 |
|---|---|---|---|
| 42 | `Ascend/agent-skills` → `skills/modelscope-cli/SKILL.md` | ModelScope CLI：模型/数据集批量下载、完整性校验、参数量统计、网络诊断 | ✅ |
| 43 | `renyiming25/InferBenchSkills` → `model-download/SKILL.md` | ModelScope / HuggingFace 多级下载策略：指定源、大小预估、后台下载 | ✅ |
| 44 | `openJiuwen-ai/relay` → `office-claw-skills/openai-whisper-cn/SKILL.md` | whisper 模型的国内源版本 | ✅ |
| 45 | （`loredunk/china-mirror-skills` 内置）`scripts/huggingface/` + `hfd.sh` | `huggingface-cli` 走 `hf-mirror.com` 的一次性/持久化写法 | ✅ 见 #1 |

---

## 6. F 类 · 找 skill 的基础设施（用于持续追踪新增）

- `majiayu000/claude-skill-registry-data` —— 全量 skill 注册表数据快照（可直接 grep，比一个个搜快）
- `aiskillstore/marketplace` —— 市场式收录
- **skills.sh 有公开搜索 API**（本次调研的主力）：
  ```bash
  curl -s "https://skills.sh/api/search?q=china+network&limit=12" | jq -r '.skills[] | "\(.id) | \(.installs)"'
  ```
- awesome 列表：`lingxling/awesome-skills-cn`、`hackerFish/awesome-dsh-skills`、`ComposioHQ/awesome-claude-skills`

---

## 7. 未核实 / 只算"沾边"的

以下命中但正文没取到（路径 404 或页面 JS 渲染），要装之前务必先看仓库：
`shanyou/skills`(docker-mirror-lookup)、`skills.volces.com/{china-mirrors,docker-mirror,bootstrap-china-network}`、
`manmonthW/termux-openclaw-android`、`SHAOBUZHI/hermes-webui-deployment`。

只算沾边（镜像源只是部署步骤之一，不是 skill 主体）：
`labring/FastGPT`、`apache/rocketmq-dashboard`、`modelscope/AgentJet`、`openJiuwen-ai/jiuwenswarm`、
`qusong0627/QuantMind`、`shaomang/mtnode-aio`（多个 *-install skill 里都用了 ghproxy）、`xiaonuobase/Snowy` 等。

---

## 8. 怎么装（本机 pi 环境）

pi 的 skill 目录（`SKILL.md` 会被递归发现）：

```bash
# 用户级（推荐，跨项目）
mkdir -p ~/.agents/skills && git clone --depth 1 <repo> ~/.agents/skills/<name>
# 项目级
mkdir -p .agents/skills && git clone --depth 1 <repo> .agents/skills/<name>
# Claude Code 通用位置
mkdir -p ~/.claude/skills && git clone --depth 1 <repo> ~/.claude/skills/<name>
```

装了之后用 `/skill:<name>` 直接调用（pi 支持 skill 命令），改完 `/reload`。

skills.sh 上架的可以用 `npx skills add https://github.com/<owner>/<repo> --skill <skill-name>`，
但注意它默认装到 `~/.claude/skills`。

---

## 9. 推荐组合（按场景）

| 场景 | 装什么 |
|---|---|
| **只想要一个"换源"技能** | #1 `loredunk/china-mirror-skills`（脚本最全 + 有备份回滚）或 #2 `routefox`（覆盖最广、纯文档、无副作用） |
| **日常排障（"为什么装不上"）** | #3 `CacinieP/network-troubleshoot-skill`（17+ agent 适配、只读优先） |
| **CI / Dockerfile / 容器构建** | #11 `seed-forge/base-cn-registry-mirror-strategy` + #22 `linuxmirrors-docker` |
| **GitHub 拉不动** | #15 `youbuwei/github-accelerator`（只读、有探测）+ #17 `Lucas-1u/git-push-cn`（Windows 推送排障） |
| **Docker 拉不动** | #23 `ddn-docker-mirror` / #24 `docker-mirror-helper`（同一个镜像站的查询与改写） |
| **要自己搭节点** | #30 `proxy-expert`（端到端）或 #31 `xray-easy`（最快）；节点已有、要调分流 → #33 `sing-box-best-practice` |
| **HF 模型下载** | #42 `modelscope-cli` + `hf-mirror.com`（本机已有 8005/8000 的 vLLM 栈，模型下载走这条） |

---

## 10. 风险提示

1. **国内镜像/第三方加速前缀能看全你传过去的东西** —— 拿它们 clone/pull **私有仓库、带 token 的 URL、Docker push 凭据** 等于把凭据交给第三方。`youbuwei/github-accelerator` 是把这条写进 `prohibited` 的少数派，照它做。
2. **`--insecure-registry` / `strict-ssl false` / `NODE_TLS_REJECT_UNAUTHORIZED=0`** 这类"先跑起来再说"的配置，`CacinieP` 明确要求先征求同意 —— 值得抄这个习惯。
3. **star 数不可信**：本清单里绝大多数仓库 0–10 star（本次 API 返回的部分"高星"仓库星数明显异常）。装之前 `grep -r "curl .*| *sh"` 和 `grep -r "rm -rf"` 过一遍脚本。
4. **镜像站会死**：2024 年后大量公开 Docker 镜像站关停。所有"写死镜像地址"的 skill 都会过期，优先选**带探活/测速**的（#9 `mirror-switch`、#15 `github-accelerator`）。
5. **skill 自带脚本 = 以你的身份执行**。project 级 skill 只在信任的仓库里开。
