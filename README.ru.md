<div align="center">

# 📌 AgentCheckpoint

**Проверяемые и восстанавливаемые контрольные точки выполнения для кодинг-агентов**

`agentck` замораживает реальное рабочее состояние сессии кодинг-агента —
состояние git, свидетельства выполненных тестов и собственные утверждения
агента (хранятся *раздельно*) — и сообщает следующему агенту, можно ли ещё
доверять этому состоянию, прежде чем он продолжит работу.

[![CI](https://github.com/hwl668/Agentcheckpoint/actions/workflows/ci.yml/badge.svg)](https://github.com/hwl668/Agentcheckpoint/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agentck)](https://pypi.org/project/agentck/)
[![Python](https://img.shields.io/pypi/pyversions/agentck)](https://pypi.org/project/agentck/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

[Установка](#-установка) · [Быстрый старт](#-быстрый-старт) · [Команды](#-команды) · [Как это работает](#-как-это-работает) · [Дорожная карта](#-дорожная-карта)

[简体中文](README.md) · [English](README.en.md) · [日本語](README.ja.md) · [Español](README.es.md) · **Русский**

<img src="docs/demo.gif" alt="agentck demo" width="820">

</div>

## 💡 Зачем это нужно

Инструменты хендовера «резюмируют». Но резюме не отвечает на три смертельных
вопроса:

- С тех пор как прошли те тесты, **не дрейфовал ли код?**
- У заявления «готово» — **есть доказательства?**
- Можно ли вернуть репозиторий **точно** в то состояние?

AgentCheckpoint отвечает одним железным правилом:

```text
Резюме агента ≠ Истина
```

Каждая информация принадлежит одному из трёх классов, хранится и
помечается отдельно и никогда не смешивается:

```text
CLAIM:      "fixed cache eviction"            ← заявление агента
OBSERVED:   src/cache.py modified             ← собрано машиной (git)
VERIFIED:   pytest tests/test_cache.py → exit 0
STALE:      src/cache.py changed afterwards   ← помечено устаревшим после дрейфа
```

Поэтому `agentck verify` выдаёт вердикт ещё до того, как вы примете работу:

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

Коды выхода пригодны для скриптов: `0` — нет дрейфа · `1` — дрейф · `2` — ошибка.

## ✨ Возможности

|  | Возможность | Что это значит |
|---|---|---|
| 🔖 | **Классы свидетельств** | OBSERVED / VERIFIED / AGENT-REPORTED размечены насквозь; заявления никогда не выдаются за факты |
| 🕵 | **Детекция дрейфа** | HEAD сдвинулся, ветка сменилась, хэши файлов различаются → записанные результаты тестов помечаются STALE |
| 🔐 | **Проверка целостности** | Для каждого артефакта хранится SHA256; verify / restore пересчитывают всё и отказывают при несовпадении — обнаруживает повреждения и посторонние правки, но не остановит решительного злоумышленника |
| 🔁 | **Повтор выполнения** | Перезапускает команды, записанные в checkpoint: consistent / regression / improved |
| 🌳 | **Checkpoint DAG** | Ветвление от любого узла через `--parent`; `log` рисует дерево |
| 🛟 | **Безопасное восстановление** | По умолчанию создаёт новый git worktree и не трогает ваше дерево; in-place требует `--yes` и всегда сперва сохраняет safety checkpoint |
| 🤖 | **Независимость от модели** | Движок не знает ни одного конкретного агента; Claude / Codex / GLM — просто разные renderers |
| 📦 | **Локальность** | Ноль runtime-зависимостей (Python ≥ 3.10 + git); данные живут в проекте; без аккаунтов, без сети, без вызовов LLM |

## 📦 Установка

<details open>
<summary><b>Глобальная установка из исходников (рекомендуется)</b></summary>

```bash
git clone https://github.com/hwl668/Agentcheckpoint.git
cd Agentcheckpoint

# разовая подготовка (если нет pipx):
py -3 -m pip install --user pipx          # POSIX: python3 -m pip install --user pipx

# глобальная установка (editable: изменения кода действуют сразу):
py -3 -m pipx install -e .
py -3 -m pipx ensurepath                  # добавляет ~/.local/bin в PATH, один раз
```

Откройте новый терминал:

```bash
cd ~/projects/any-project
agentck --version
agentck init
```

</details>

<details>
<summary><b>Альтернативы</b></summary>

```bash
pipx install agentck                # после публикации на PyPI
uv tool install agentck             # для пользователей uv
py -3 -m pip install --user .       # обычный pip, без изоляции venv
```

> О названии: дистрибутив на PyPI — **`agentck`** (`agentcheckpoint` занят
> другим проектом); Python-пакет по-прежнему импортируется как
> `agentcheckpoint`, а команда — `agentck`.

</details>

**CLI глобальный, данные — по проектам**: у каждого репозитория свой
`.agentcheckpoint/` (локально исключается через `.git/info/exclude`; ваш
`.gitignore` не трогается), и store'ы друг друга не видят. Вне git-репозитория
любая команда безопасно завершается с кодом 2.

## 🚀 Быстрый старт

```bash
cd my-project
agentck init
```

Поработали с агентом — заморозьте состояние:

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

Команды `--test` **реально выполняются**; их коды выхода и хвост вывода
записываются как машинные свидетельства. Перед передачей работы другому агенту:

```bash
agentck verify            # состоянию ещё можно доверять?
agentck resume codex > HANDOFF.md
```

Хотите вернуться к проверенному checkpoint'у?

```bash
agentck restore cp_20261004_161741      # в свежий worktree; текущее дерево не тронуто
```

## 🧰 Команды

| Команда | Назначение |
|---|---|
| `agentck init` | инициализирует `.agentcheckpoint/` (и локально исключает его) |
| `agentck save [label] [--goal …] [--test cmd] [--parent ref]` | замораживает текущее состояние; `--test` выполняет и записывает свидетельства |
| `agentck list [--json]` | все checkpoints |
| `agentck log` | DAG checkpoint'ов в виде дерева (видны ветвления и разорванные связи) |
| `agentck show [ref] [--json]` | один checkpoint + его handoff-документ |
| `agentck diff <a> <b>` | что изменилось между двумя checkpoint'ами |
| `agentck verify [ref] [--json]` | дрейф / устаревание / целостность / уверенность (exit 1 = дрейф) |
| `agentck replay [ref] [--json]` | перезапускает записанные команды и сравнивает (exit 1 = регрессия) |
| `agentck resume [claude\|codex\|glm\|plain]` | handoff-документ с разметкой свидетельств для следующего агента |
| `agentck restore <ref>` | восстанавливает состояние (по умолчанию worktree; `--in-place --yes` переписывает текущее дерево) |

Ссылки принимают `latest`, точный id, уникальный префикс или label.

## 🧠 Как это работает

Каждый checkpoint — человекочитаемый каталог (схема `agent-checkpoint/v1`):

<details>
<summary><b>Структура checkpoint'а</b></summary>

```text
.agentcheckpoint/checkpoints/cp_20261004_161741/
├── manifest.json        # сам checkpoint (заявления агента + машинные наблюдения)
├── handoff.md           # статический handoff, отрисованный при сохранении
├── integrity.json       # SHA256 каждого артефакта — проверка целостности
├── git/                 # OBSERVED: status.json, staged.patch, tracked.patch, untracked/
├── execution/           # OBSERVED: tests.json (команды, коды выхода, хвосты вывода)
└── semantic/            # AGENT-REPORTED: decisions.md, constraints.md, next-steps.md
```

</details>

Три жёстких правила:

1. **Факты git всегда собираются командами git**, а не LLM — галлюцинация не
   может загрязнить слой истины.
2. **Заявления и наблюдения хранятся раздельно**: goal / completed /
   decisions / blockers попадают только в `agent_claims` и всегда помечены
   «независимо не проверено».
3. **Checkpoint'ы только дописываются**: verify и restore пересчитывают все
   хэши; любое повреждение или постороннее изменение обнаруживается.
   integrity.json не может захэшировать сам себя — против решительного
   злоумышленника нужны подписанные checkpoint'ы (см. дорожную карту).

Точная формула эвристики уверенности, семантика DAG и replay описаны в
[спецификации протокола (англ.)](spec/agent-checkpoint-v1.md).

## 🛡 Безопасность и известные ограничения

- По умолчанию восстановление создаёт новый worktree; `--in-place` требует
  явного `--yes` и всегда сперва пишет автоматический safety checkpoint
  `pre-restore-`.
- При checkout и применении патчей принудительно ставится
  `core.autocrlf=false`, чтобы восстановленные байты бит в бит совпадали с
  хэшами, записанными при сохранении.
- Семантический ввод и записанный вывод **затираются по best-effort** на
  предмет секретов; подозрительные секреты в патчах только вызывают
  предупреждение (перезапись нарушила бы целостность).
- Честные ограничения v1: unmerged (конфликтные) состояния записываются, но
  не восстанавливаются; verify не перезапускает команды (для этого
  `agentck replay`); затирание секретов — best-effort, а не гарантия.

## 🧭 Дорожная карта

- [x] Полный протокол `agent-checkpoint/v1` (save / verify / resume / restore / diff)
- [x] Checkpoint DAG + повтор выполнения
- [ ] Хуки Claude Code для автоматических checkpoint'ов (конец сессии / перед рискованными действиями)
- [ ] Распространяемые Skill-пакеты для платформ агентов
- [ ] Оценка качества checkpoint'а
- [ ] Подписанные checkpoint'ы (корень Меркла + Ed25519/SSH/Sigstore)

## 🤖 Интеграция с агентами

Заставьте Claude / Codex / GLM использовать agentck правильно: установите
[`skills/agent-checkpoint/SKILL.md`](skills/agent-checkpoint/SKILL.md)
в своего агента. Там задано, когда делать checkpoint, что заявления должны
быть конкретными и фальсифицируемыми, и дисциплина свидетельств: *никогда не
заявляй, что тесты проходят, если это не записано через `--test`*.

## 💻 Разработка

```bash
py -3 -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/pytest          # 68 тестов, все на герметичных временных git-репозиториях
.venv/Scripts/ruff check .
```

Подробная документация (англ.): [SPEC.md](SPEC.md) ·
[спецификация протокола](spec/agent-checkpoint-v1.md) · [CHANGELOG](CHANGELOG.md)

---

<div align="center">

**MIT** © AgentCheckpoint contributors

CLI глобальный, данные — по проектам.

</div>
