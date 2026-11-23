# 安全模型与红线

这个工具会改你的开发环境配置文件，也会往 shell 里注入 env。威胁模型必须说清楚。

## 1. 谁会看到你的流量

| 通道 | 对方能看到 | 能篡改 | 什么时候可以接受 |
|---|---|---|---|
| 国内镜像站（tuna/ustc/aliyun…） | 你 **下载了什么包**（包名、版本、时间） | 理论上可以（HTTPS + 包签名/哈希部分缓解） | 公开依赖，且对比过官方源哈希 |
| 第三方 GitHub 前缀（ghproxy/gh-proxy/ghfast…） | 完整 URL、仓库名、`Authorization` 头（如果你带了） | 可以 | **只用于公开仓库** |
| 自建代理 / VPS | 全部流量 | 可以 | 你自己的机器 |
| 公司 TLS 中间盒 | 全部明文 | 可以 | 公司政策允许时 |

**结论**：镜像 = 中间人。对公开依赖这是可接受的工程取舍；对私有仓库、内部包、带凭据的 URL，绝对不行。

## 2. 本工具明确不做的事

1. 不设置 `git config --global http.sslVerify false`
2. 不设置 `npm config set strict-ssl false`
3. 不设置 `NODE_TLS_REJECT_UNAUTHORIZED=0` / `PYTHONHTTPSVERIFY=0` / `SSL_CERT_FILE` 指向可疑证书
4. 不使用 `--insecure-registry`
5. 不把私有 registry / `_authToken` / `//host/:_auth` 写进任何配置或输出
6. 不把 `url.<proxy>.insteadOf` 写进 git 全局配置（会连 push 一起劫持）
7. 不在 URL 含 `@` / `token=` / `Authorization` 时走第三方前缀
8. 不 `sudo` 提权去改 `docker`/`apt`，除非用户用 `--only docker` / `--only apt` 明确点名

如果你需要 1–3 中的任何一条，请自己执行并理解后果：那等于关掉了唯一能发现中间人的机制。

## 3. 配置文件的信任边界

| 文件 | 谁能写 | 本工具的策略 |
|---|---|---|
| `~/.config/pip/pip.conf` | 你 | 只改 `[global] index-url`，保留其它键与注释 |
| `~/.npmrc` | 你 / 项目 | 只改 `registry=`，**不碰** `_authToken` 等凭据行 |
| `~/.condarc` | 你 | 有内容且无托管标记 → 拒绝，除非 `--force`（先备份） |
| `~/.cargo/config.toml` | 你 | 无 `[source.crates-io]` → 追加托管块；有 → 需 `--force` |
| `~/.bashrc` | 你 / 各种安装脚本 | 只追加带 `# >>> x-proxy-skills >>>` 标记的块，不重排原文 |
| `~/bin/ghclone`、`~/bin/hfd` | 你 | 覆盖前备份，文件头写明来源 |
| `/etc/docker/daemon.json` | root | opt-in；只合并 `registry-mirrors`（最多 5 个），其它键保留；JSON 非法则不动 |
| `/etc/apt/sources.list` | root | opt-in；只替换 `archive/security/ports.ubuntu.com` 与 `deb.debian.org` 的 host |

## 4. 依赖混淆（dependency confusion）提醒

**不要**同时配 `index-url` 和 `extra-index-url` 指向两个不同的源。pip 会在所有源里挑"版本号最高"的那个，攻击者只要在内网源/公网源放一个高版本同名包就能投毒。本工具刻意只写一个主源；发现你的 pip.conf 里有 `extra-index-url` 时会在输出里警告。

## 5. 备份与回滚的语义

- 每次 `apply` 生成一个备份 id：`~/.local/share/x-proxy-skills/backups/<id>/`
  - `files/NN-<basename>`：每个被改动文件的**原文**（按序号，避免同名覆盖）
  - `manifest.json`：路径、是否存在过、权限位、备份文件名、命令级 undo
- `rollback` 逆序恢复：**应用前存在 → 恢复原文；应用前不存在 → 删除文件**。
- 命令级改动（`go env -w`）会记录 undo（`go env -u GOPROXY`）；如果原来没有设置，则**不会**凭空 `-u`（保留原状）。
- 备份是明文、权限 0600 目录（继承 umask）。里面可能有你自己的源地址，别把 `backups/` 提交进 Git。
- 回滚不会重启 docker、不会 `source` shell —— 需要你自己做。

## 6. 给 agent 的硬约束

当用户让你"帮我配好国内源"时：

1. 先 `xps doctor`，把现状贴给用户；**不要**在没有读取现状的情况下直接写文件。
2. 只改用户明确抱怨的生态（`--only`），不要"顺手全配一遍"。
3. `--dry-run` 的 diff 必须给用户看过再 `--yes`。
4. 用户说"跳过证书校验吧" → 解释风险，**不代劳**。
5. 用户给的是私有仓库/带 token 的 URL → 不走镜像/前缀。
6. 改完必须 `xps verify`，并提示"已开的 shell 要重新 source"。
