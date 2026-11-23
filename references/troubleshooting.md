# 排障手册（国内网络）

先跑 `xps doctor`，把"事实"拿全再动手。下面每条都按「症状 → 判据 → 处理」写。

---

## 1. 分清三类问题

| 类别 | 典型判据 | 换源有用吗 |
|---|---|---|
| **A. 源慢/源不对** | 直连 `pypi.org` 通但 1.8s，镜像站 120ms；只有某个包管理器慢，`curl` 正常 | ✅ 有用 |
| **B. 网络本身坏** | `xps probe` 全灭；`curl -I https://www.baidu.com` 也超时；DNS 解析到 0.0.0.0 | ❌ 换源无用，先修网络/DNS |
| **C. 配置错位** | 换源了还是慢；只有某个进程慢（IDE 里的 npm、Docker Desktop、VS Code 扩展） | ❌ 要改对进程读的那份配置 |

C 类最常被误判成 A 类：**代理是分进程生效的**。`curl` 走 `HTTP_PROXY`，但 Docker daemon 是 systemd 拉起的、不继承你的 shell 环境；VS Code 的扩展进程可能不读你终端里的 `npm_config_registry`。

---

## 2. DNS 被污染 / 解析异常

```bash
getent hosts registry.npmjs.org
dig +short registry.npmjs.org @223.5.5.5
curl -sI --max-time 5 https://registry.npmjs.org/-/ping | head -1
```

- 返回 `0.0.0.0` / `127.0.0.1` / 明显错误 IP → DNS 被污染。
- 换 `223.5.5.5`（阿里）/ `119.29.29.29`（腾讯）/ `1.1.1.1` 对比：
  ```bash
  dig +short pypi.org @119.29.29.29
  ```
- 只影响某个域名时，用 hosts 兜底（注意 IP 会变，别长期写死）。
- **systemd-resolved 的 stub（127.0.0.53）** 会把你的 `/etc/resolv.conf` 覆盖掉，改完要 `resolvectl flush-caches`。

---

## 3. 有代理但某些工具不走

```bash
env | grep -iE 'http_proxy|https_proxy|all_proxy|no_proxy'
git config --get-regexp '^http\..*proxy$'
npm config get proxy; npm config get https-proxy
docker info | sed -n '/Proxy/,+3p'
```

- **git**：只认 `http.proxy` / 环境变量，不认系统代理设置。
- **Docker daemon**：要写 `/etc/systemd/system/docker.service.d/*.conf` 的 `Environment=HTTPS_PROXY=...`，然后 `systemctl daemon-reload && systemctl restart docker`。
- **pip**：认 `HTTP_PROXY`/`HTTPS_PROXY`，不认 `~/.config/pip/pip.conf` 里的 proxy（pip 支持 `proxy =` 但只对 http 生效，https 走 CONNECT）。
- **NO_PROXY 写错**：`NO_PROXY=localhost,127.0.0.1` 只匹配这些；内网 registry 要显式加后缀（`.corp.example.com`）。

---

## 4. pip / uv / poetry

### `ReadTimeoutError` / `Connection broken`

```bash
xps apply --only pip                  # 选最快源
pip config list                       # 确认 index-url
pip install -v <pkg> 2>&1 | tail -30   # 看卡在哪个域名
```

- 报 `SSL: CERTIFICATE_VERIFY_FAILED` → **不要** `trusted-host` 一把梭；先确认是不是公司 TLS 中间盒（`openssl s_client -connect host:443 -showcerts`）。确实需要时由用户自己决定，本工具不代劳。
- `trusted-host` 只对 http 有意义；https 源写了也没用（本机 pip.conf 里那条属于历史遗留，无害）。

### uv 不读 pip.conf

```bash
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple   # uv >= 0.4.23
export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple       # 旧版
# 或写进项目 pyproject.toml:
# [[tool.uv.index]]
# url = "https://pypi.tuna.tsinghua.edu.cn/simple"
# default = true
```

### poetry

```bash
poetry source add --priority=primary tuna https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 5. npm / pnpm / yarn

### `ERR_SOCKET_TIMEOUT` / `ETIMEDOUT` / `ECONNRESET`

```bash
npm config get registry         # 应该是 https://registry.npmmirror.com
npm ping
npm install --loglevel=http     # 看是哪个 host 慢
```

- `npm ERR! network request to https://registry.npmjs.org failed` → 你的 registry 没生效（可能项目里有 `.npmrc` 覆盖了全局）。项目级 `.npmrc` 优先。
- `pnpm` / `yarn` / `bun` 都读 `~/.npmrc` 的 `registry`，但**各自的缓存目录不同**，换源后旧缓存仍可能报错：`npm cache verify` / `pnpm store prune`。
- 原生模块（`node-gyp`）走的是 `nodejs.org` 的 headers 下载，跟 registry 无关：
  ```bash
  npm config set disturl https://registry.npmmirror.com/-/binary/node
  npm config set electron_mirror https://registry.npmmirror.com/-/binary/electron/
  ```
  Playwright / Puppeteer 的浏览器二进制同理（`PLAYWRIGHT_DOWNLOAD_HOST` / `PUPPETEER_DOWNLOAD_BASE_URL`）。

---

## 6. conda

- `CondaHTTPError: HTTP 000 CONNECTION FAILED` → `xps apply --only conda --force`，或 `conda config --show channels` 看是不是还在用 `defaults`。
- `channel_priority: strict` 会导致 `conda-forge` 和 `defaults` 混用时报 `PackagesNotFoundError`，这是策略问题不是网络问题。
- 换源后第一条命令仍慢：`conda clean -i` 清索引缓存。
- **别同时** 配 `.condarc` 和镜像站文档里的 `conda config --add channels`（会重复/冲突）。

---

## 7. Docker

```bash
docker info | sed -n '/Registry Mirrors/,+3p'
docker pull hello-world
```

- 改完 `daemon.json` **必须** `systemctl restart docker`（`reload` 不生效）；restart 会停掉所有容器。
- `x509: certificate signed by unknown authority` → 镜像站证书问题，换一个源，别加 `insecure-registries`。
- `toomanyrequests` → Docker Hub 限流，镜像站也限流，换源或登录。
- 私有仓库（Harbor/ACR）**不要**配到 `registry-mirrors`（mirror 只对 docker.io 生效），走 `docker login`。
- Docker Desktop（macOS/Windows）的 daemon 在虚拟机里，改 `~/.docker/daemon.json` 或 GUI 设置，不是 `/etc/docker/daemon.json`。

---

## 8. GitHub / git

```bash
git ls-remote https://github.com/octocat/Hello-World 2>&1 | head -3
xps probe --only github
xps gh https://github.com/owner/repo /tmp/repo
```

- `Recv failure: Connection reset` / `GnuTLS recv error` → 直连被重置，用前缀。
- `schannel` / `SEC_E_...`（Windows）→ 见 `Lucas-1u/git-push-cn` 那份 skill，本工具不碰 `http.sslBackend`。
- **push 不要走第三方前缀**（会带凭据）。push 只能直连/自己的代理。
- `git config --global url."https://ghproxy.net/https://github.com/".insteadOf` 这种全局改写**有害**：私有仓库和 push 都会被打到第三方。本工具只装 `ghclone` 助手，不改全局。

---

## 9. HuggingFace

```bash
xps apply --only hf
source ~/.bashrc
hfd Qwen/Qwen2.5-7B-Instruct --local-dir /data/models/qwen
```

- `HF_HUB_DISABLE_XET=1` 很重要：xet 后端（CAS）在国内经常 TLS 超时，关掉走普通 HTTP。
- 已经下了一半：加 `--resume-download`（老版本）或直接重跑（新版本默认断点续传）。
- `huggingface-cli` 已改名为 `hf`，两者本脚本都支持。
- **ModelScope 不是 HF 兼容端点**，别把 `HF_ENDPOINT` 指向它；用 `modelscope download --model <id> --local_dir <dir>`。

---

## 10. 什么时候该停手

- `xps probe` 全灭且 `curl https://www.baidu.com` 也失败 → 网络断了，不是镜像问题。
- 只有 https 失败、http 正常 → 大概率 TLS 中间盒，需要用户确认（企业环境）。
- 报错里出现 `401/403` 且是私有源 → 凭据问题，与换源无关。
- 换了源仍然只有某个包失败 → 看包本身（jar/npm 包的 postinstall 下载的二进制、git 依赖 `git+https://`）。
