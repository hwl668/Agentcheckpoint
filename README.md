<div align="center">

# 📌 AgentCheckpoint

**给 coding agent 的可验证、可恢复的执行检查点**

`agentck` 冻结 coding agent 会话的真实工作状态——git 状态、测试执行证据、
agent 自述（三者分开存储）——并在下一个 agent 动手之前，告诉它这份状态是否仍然可信。

[![CI](https://github.com/hwl668/Agentcheckpoint/actions/workflows/ci.yml/badge.svg)](https://github.com/hwl668/Agentcheckpoint/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agentck)](https://pypi.org/project/agentck/)
[![Python](https://img.shields.io/pypi/pyversions/agentck)](https://pypi.org/project/agentck/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

[安装](#-安装) · [快速上手](#-快速上手) · [命令一览](#-命令一览) · [工作原理](#-工作原理) · [路线图](#-路线图)

**简体中文** · [English](README.en.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Русский](README.ru.md)

<img src="docs/demo.gif" alt="agentck demo" width="820">

</div>

## 💡 为什么需要它

交接工具都在"总结"。但总结回答不了三个致命问题：

- 自从那些测试通过之后，**代码漂移了吗？**
- 那句"做完了"，**有证据吗？**
- 仓库还能**精确回到**当时的状态吗？

AgentCheckpoint 用一条铁律回答：

```text
Agent 的总结 ≠ 事实
```

所有信息分三类，分开存储、分开标注，从不混淆：

```text
CLAIM:      "fixed cache eviction"            ← agent 自述
OBSERVED:   src/cache.py modified             ← 机器采集（git）
VERIFIED:   pytest tests/test_cache.py → exit 0
STALE:      src/cache.py changed afterwards   ← 漂移后标记过期
```

于是 `agentck verify` 能在你接手之前给出这样的判断：

```text
Files
! src_cache.py changed since checkpoint
Tests
! git rev-parse --verify HEAD
  PASS at checkpoint — result is now STALE
Claims
? "switched eviction policy to LRU"
  agent-reported, not independently verified

Resume confidence: 75%
```

退出码可脚本化：`0` 无漂移 · `1` 有漂移 · `2` 出错。

## ✨ 特性亮点

|  | 特性 | 说明 |
|---|---|---|
| 🔖 | **证据分层** | OBSERVED / VERIFIED / AGENT-REPORTED 全链路标注，agent 的声明永远不会被渲染成事实 |
| 🕵 | **漂移检测** | HEAD 移动、分支变化、文件哈希变化 → 当时的测试结果标记 STALE |
| 🔐 | **防篡改** | 每个产物记录 SHA256；verify / restore 全量重哈希，不匹配即拒绝 |
| 🔁 | **执行重放** | 重跑 checkpoint 里记录的验证命令，判定 consistent / regression / improved |
| 🌳 | **Checkpoint DAG** | `--parent` 从任意节点分叉，`log` 渲染树状历史 |
| 🛟 | **安全恢复** | 默认开新 git worktree，绝不碰当前目录；in-place 需 `--yes` 且自动先存安全检查点 |
| 🤖 | **模型无关** | 引擎不认识任何具体 agent；Claude / Codex / GLM 只是不同 renderer |
| 📦 | **本地优先** | 运行时零依赖（Python ≥ 3.10 + git），数据全在项目里，无账号、无网络、无 LLM 调用 |

## 📦 安装

<details open>
<summary><b>从源码全局安装一次（推荐）</b></summary>

```bash
git clone https://github.com/hwl668/Agentcheckpoint.git
cd Agentcheckpoint

# 一次性准备（若尚未安装 pipx）：
py -3 -m pip install --user pipx          # POSIX: python3 -m pip install --user pipx

# 全局安装（可编辑模式，改源码立即生效）：
py -3 -m pipx install -e .
py -3 -m pipx ensurepath                  # 把 ~/.local/bin 加入 PATH，只需一次
```

开新终端后：

```bash
cd ~/projects/any-project
agentck --version
agentck init
```

</details>

<details>
<summary><b>其他方式</b></summary>

```bash
pipx install agentck                # PyPI 发布后可用
uv tool install agentck             # uv 用户
py -3 -m pip install --user .       # 普通 pip，无 venv 隔离
```

> 命名说明：PyPI 分发名是 **`agentck`**（`agentcheckpoint` 已被无关项目占用）；
> Python 包仍为 `agentcheckpoint`，命令行仍是 `agentck`。

</details>

**CLI 全局，数据项目局部**：每个仓库有自己的 `.agentcheckpoint/`
（`init` 会通过 `.git/info/exclude` 本地排除，不碰你的 `.gitignore`），
不同项目的 checkpoint 互不可见。非 git 目录里所有命令安全失败（exit 2）。

## 🚀 快速上手

```bash
cd my-project
agentck init
```

和 agent 干完一段活，冻结状态：

```bash
agentck save glm-cache-refactor \
    --agent glm \
    --goal "Fix CUDA memory leak" \
    --completed "switched eviction policy to LRU" \
    --decision "preserve public Cache API" \
    --blocker "test_large_batch fails" \
    --next "inspect Cache.evict() around line 184" \
    --do-not "modify allocator.cpp" \
    --test "git rev-parse --verify HEAD"
```

`--test` 的命令会**当场执行**，退出码和输出尾部作为机器证据记录。
准备切换到另一个 agent 时：

```bash
agentck verify            # 状态还可信吗？
agentck resume codex > HANDOFF.md
```

某个 checkpoint 特别可靠、想回去？

```bash
agentck restore cp_20261004_161741      # 恢复到全新 worktree，当前目录毫发无损
```

## 🧰 命令一览

| 命令 | 用途 |
|---|---|
| `agentck init` | 初始化 `.agentcheckpoint/`（并本地排除该目录） |
| `agentck save [label] [--goal …] [--test cmd] [--parent ref]` | 冻结当前状态；`--test` 现场执行并记录证据 |
| `agentck list [--json]` | 全部 checkpoint |
| `agentck log` | checkpoint DAG 树状图（分叉、断链可见） |
| `agentck show [ref] [--json]` | 单个 checkpoint 详情 + handoff 文档 |
| `agentck diff <a> <b>` | 两个 checkpoint 之间的差异 |
| `agentck verify [ref] [--json]` | 漂移 / 过期 / 防篡改 / 置信度（exit 1 = 有漂移） |
| `agentck replay [ref] [--json]` | 重放记录的验证命令并比对结果（exit 1 = 出现回归） |
| `agentck resume [claude\|codex\|glm\|plain]` | 给下一个 agent 的证据标注型交接文档 |
| `agentck restore <ref>` | 恢复状态（默认 worktree；`--in-place --yes` 覆写当前目录） |

引用方式支持 `latest`、完整 ID、唯一前缀、label。

## 🧠 工作原理

每个 checkpoint 是一个人类可读的目录（`agent-checkpoint/v1` schema）：

<details>
<summary><b>checkpoint 目录结构</b></summary>

```text
.agentcheckpoint/checkpoints/cp_20261004_161741/
├── manifest.json        # 检查点本体（含 agent claims 与机器观测）
├── handoff.md           # save 时渲染的静态交接文档
├── integrity.json       # 所有产物的 SHA256 —— 防篡改
├── git/                 # OBSERVED：status.json、staged.patch、tracked.patch、untracked/
├── execution/           # OBSERVED：tests.json（命令、退出码、输出尾部）
└── semantic/            # AGENT-REPORTED：decisions.md、constraints.md、next-steps.md
```

</details>

三条硬规则：

1. **git 事实永远由 git 命令采集**，绝不让 LLM 生成——幻觉污染不了底层状态。
2. **claims 与观测分层存储**：goal / completed / decisions / blockers 只进
   `agent_claims`，永远带"未独立验证"标注。
3. **checkpoint 只增不改**：verify 与 restore 都会全量重哈希，任何篡改都会被抓住。

置信度启发式的精确公式、DAG 与 replay 语义，见
[协议规范（英文）](spec/agent-checkpoint-v1.md)。

## 🛡 安全设计与已知边界

- 恢复默认走新 worktree；`--in-place` 必须显式 `--yes`，且总是先自动写一个
  `pre-restore-` 安全检查点。
- 检出与打补丁强制 `core.autocrlf=false`，保证恢复字节与保存时哈希逐位一致。
- 语义输入与命令输出会做**尽力而为的秘密脱敏**；patch 里的疑似秘密只警告不改写
  （改写会破坏完整性）。
- 诚实声明 v1 的边界：unmerged（冲突）状态可记录但不可恢复；verify 不重跑命令
  （要重放请用 `agentck replay`）；脱敏是尽力而为，不是保证。

## 🧭 路线图

- [x] `agent-checkpoint/v1` 全量协议（save / verify / resume / restore / diff）
- [x] Checkpoint DAG + execution replay
- [ ] Claude Code hooks 自动 checkpoint（会话结束/危险操作前自动 save）
- [ ] 各 agent 平台的 Skill 分发包
- [ ] Checkpoint 质量评分

## 🤖 Agent 集成

让 Claude / Codex / GLM 直接按规矩使用 agentck：把
[`skills/agent-checkpoint/SKILL.md`](skills/agent-checkpoint/SKILL.md)
装进你的 agent。它规定了何时该 save、claims 必须具体可证伪、以及
"没通过 `--test` 记录就不许声称 tests pass" 的证据纪律。

## 💻 开发

```bash
py -3 -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/pytest          # 68 个测试，全部运行在密封的临时 git 仓库里
.venv/Scripts/ruff check .
```

深入文档（英文）：[SPEC.md](SPEC.md) · [协议规范](spec/agent-checkpoint-v1.md) ·
[CHANGELOG](CHANGELOG.md)

---

<div align="center">

**MIT** © AgentCheckpoint contributors

CLI 全局，数据项目局部。

</div>
