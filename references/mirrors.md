# 镜像候选与实测延迟

> 实测时间：2026-11-23，本机 Ubuntu 22.04 + 电信出口，直连、无代理。
> 数字是 `xps probe` 的单次最优值（每个源最多 2 次取最快），只代表"当时/该出口"，
> 换网络环境请重新 `xps probe --refresh`。

## 已从候选里删除的（实测不可用）

| 源 | 探测 URL | 结果 | 处理 |
|---|---|---|---|
| 腾讯云 PyPI | `https://mirrors.cloud.tencent.com/pypi/simple/pip/` | **404** | 删除 |
| 阿里云 Anaconda | `https://mirrors.aliyun.com/anaconda/pkgs/main/noarch/current_repodata.json` | **404** | 删除 |
| 腾讯云 npm | `https://mirrors.cloud.tencent.com/npm/` | **404** | 删除（npmmirror 才是正主） |

## 2026-11-23 实测（ms，越小越好）

| 生态 | 源 | 延迟 | 备注 |
|---|---|---|---|
| pip | 阿里云 | 118 | ★ |
| pip | 清华 TUNA | 188 | 本机原来用的就是它 |
| pip | 华为云 | 241 | |
| pip | 中科大 | 322 | |
| npm | npmmirror(淘宝) | 113 | 国内唯一事实标准 |
| conda | 清华 TUNA | 318 | ★ |
| conda | 北外 BFSU | 405 | |
| conda | 中科大 | 527 | |
| cargo | rsproxy.cn | 75 | ★ 字节，sparse index |
| cargo | 阿里云 | 93 | |
| cargo | 清华 TUNA | 118 | |
| go | goproxy.cn | 48 | ★ 七牛 |
| go | 阿里云 | 92 | |
| go | goproxy.io | 4839 | 能用但慢，留作 fallback |
| hf | hf-mirror.com | 583 | 唯一 HF 兼容镜像 |
| github 前缀 | ghproxy.net | 690 | ★ |
| github 前缀 | gh-proxy.com | 709 | |
| github 前缀 | ghfast.top | 1971 | |
| github 前缀 | githubproxy.cc | 5379 | 能用但很慢 |
| docker | DaoCloud | 132（401 = 活着） | ★ `/v2/` 返回 401 是正常鉴权挑战 |
| docker | 1ms.run | 221（401） | |
| docker | dockerproxy.net | 2857 | |
| apt | 北外 BFSU | 130 | ★ |
| apt | 阿里云 | 165 | |
| apt | 清华 TUNA | 256 | |
| apt | 中科大 | 371 | |

## 探测口径

- 用 curl `-L`（跟随重定向），`--max-time 8`，最多 2 次取最快。
- 每个源声明 `accept` 列表：`401` 对 Docker Registry 是"活着"（鉴权挑战），`403` 对 cargo sparse index 也可能是正常。
- `301/302` 一律跟随后再判定。
- 结果缓存 1 小时（`~/.cache/x-proxy-skills/probe.json`），`--refresh` 强制重测。

## 各生态"换源"的准确落点（别搞错文件）

| 工具 | 真正的配置位置 | 本工具是否覆盖 |
|---|---|---|
| pip | `~/.config/pip/pip.conf` `[global] index-url` | ✅ 用户级 |
| **uv** | **不读 pip.conf**：`~/.config/uv/uv.toml` 的 `[[index]]`（或 `UV_DEFAULT_INDEX`、项目 `pyproject.toml` 的 `[[tool.uv.index]]`） | ✅ 用户级 + `--project` 项目级 |
| **poetry** | **没有用户级索引配置**：只能项目 `pyproject.toml` 的 `[[tool.poetry.source]]` | ✅ 仅 `--project DIR` |
| npm / pnpm / yarn / bun | `~/.npmrc` `registry=` | ✅ |
| conda / mamba | `~/.condarc` `default_channels` / `custom_channels` | ✅（已有非托管文件需 `--force`） |
| cargo | `~/.cargo/config.toml` `[source.crates-io] replace-with` | ✅（sparse） |
| go | `go env -w GOPROXY=...`（写 `~/.config/go/env`） | ✅ |
| docker | `/etc/docker/daemon.json` `registry-mirrors`，**重启 docker 才生效** | ✅（sudo + opt-in） |
| apt | `/etc/apt/sources.list`（22.04）或 `/etc/apt/sources.list.d/*.sources`（deb822，24.04+） | 只覆盖前者 |
| huggingface | `HF_ENDPOINT` | ✅（写 env.sh + `hfd`） |
| ModelScope | 默认就在国内，无需换源 | — |
| GitHub | 没有"源"可换，只能走前缀/代理 | ✅（`ghclone` 助手） |
| Playwright | `PLAYWRIGHT_DOWNLOAD_HOST` | ✅（env.sh） |
| Puppeteer | `PUPPETEER_DOWNLOAD_BASE_URL` | ✅（env.sh） |
| Electron | `ELECTRON_MIRROR` | ✅（env.sh） |
| node-gyp 头文件 | `npm_config_disturl` | ✅（env.sh） |
| Flutter | `PUB_HOSTED_URL` / `FLUTTER_STORAGE_BASE_URL` | ✅（env.sh） |

## 二进制下载器镜像（2026-11-23 实测）

| 目标 | 值 | 验证方式 |
|---|---|---|
| Playwright | `PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright` | `HEAD .../builds/chromium/1148/chromium-linux.zip` → 200 application/zip |
| Puppeteer / Chrome for Testing | `PUPPETEER_DOWNLOAD_BASE_URL=https://cdn.npmmirror.com/binaries/chrome-for-testing` | `HEAD .../131.0.6778.204/linux64/chrome-linux64.zip` → 200 application/zip |
| Electron | `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/` | `.../31.0.0/electron-v31.0.0-linux-x64.zip` → 302 |
| node-gyp 头文件 | `npm_config_disturl=https://registry.npmmirror.com/-/binary/node` | `.../v22.11.0/node-v22.11.0-linux-x64.tar.xz` → 302 |
| Flutter pub | `PUB_HOSTED_URL=https://pub.flutter-io.cn` | `.../api/packages/http` → 200（76 KB） |
| Flutter SDK | `FLUTTER_STORAGE_BASE_URL=https://storage.flutter-io.cn` | `.../flutter_infra_release/releases/releases_linux.json` → 200（274 KB） |

注意：`cdn.npmmirror.com/binaries/<x>/` 的**目录列表**会 404，必须用真实文件路径探测，否则会误判成"镜像挂了"。

## 长期维护建议

1. 每月 `xps probe --refresh` 一次，把长期 >3s 的源从 `data/mirrors.json` 里删掉。
2. 新增候选时 `name` 必须唯一且短（会出现在 `--mirror` 参数里）。
3. 公共 Docker 镜像站关停最频繁，别把它写进 Dockerfile 或 CI 的硬编码。
