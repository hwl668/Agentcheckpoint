<div align="center">

# 📌 AgentCheckpoint

**Checkpoints de ejecución verificables y restaurables para agentes de código**

`agentck` congela el estado real de trabajo de una sesión de agente de
programación — estado de git, evidencia de pruebas ejecutadas y las
declaraciones del propio agente (guardadas *por separado*) — y le dice al
siguiente agente si ese estado sigue siendo fiable antes de continuar.

[![CI](https://github.com/hwl668/Agentcheckpoint/actions/workflows/ci.yml/badge.svg)](https://github.com/hwl668/Agentcheckpoint/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agentck)](https://pypi.org/project/agentck/)
[![Python](https://img.shields.io/pypi/pyversions/agentck)](https://pypi.org/project/agentck/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

[Instalación](#-instalación) · [Inicio rápido](#-inicio-rápido) · [Comandos](#-comandos) · [Cómo funciona](#-cómo-funciona) · [Hoja de ruta](#-hoja-de-ruta)

[简体中文](README.md) · [English](README.en.md) · [日本語](README.ja.md) · **Español** · [Русский](README.ru.md)

<img src="docs/demo.gif" alt="agentck demo" width="820">

</div>

## 💡 Por qué

Las herramientas de handoff resumen. Pero un resumen no responde tres
preguntas letales:

- Desde que esas pruebas pasaron, **¿ha derivado el código?**
- Ese "ya está hecho" — **¿hay evidencia?**
- ¿Se puede devolver el repositorio **exactamente** a como estaba?

AgentCheckpoint responde con una regla de hierro:

```text
Resumen del agente ≠ Verdad
```

Cada información pertenece a una de tres clases, guardadas y etiquetadas por
separado, nunca mezcladas:

```text
CLAIM:      "fixed cache eviction"            ← declarado por el agente
OBSERVED:   src/cache.py modified             ← recolectado por la máquina (git)
VERIFIED:   pytest tests/test_cache.py → exit 0
STALE:      src/cache.py changed afterwards   ← marcado como obsoleto tras la deriva
```

Así, `agentck verify` te da un veredicto antes de tomar el relevo:

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

Códigos de salida scriptables: `0` sin deriva · `1` deriva · `2` error.

## ✨ Lo más destacado

|  | Característica | Qué significa |
|---|---|---|
| 🔖 | **Clases de evidencia** | OBSERVED / VERIFIED / AGENT-REPORTED etiquetadas de extremo a extremo; las declaraciones nunca se presentan como hechos |
| 🕵 | **Detección de deriva** | HEAD movido, rama cambiada, hashes distintos → resultados de pruebas marcados STALE |
| 🔐 | **Verificación de integridad** | Cada artefacto con SHA256; verify / restore re-hashean todo y rechazan cualquier discrepancia — detecta corrupción y ediciones ajenas, no necesariamente a un atacante decidido |
| 🔁 | **Replay de ejecución** | Reejecuta los comandos grabados en un checkpoint: consistent / regression / improved |
| 🌳 | **Checkpoint DAG** | Bifurca desde cualquier nodo con `--parent`; `log` dibuja el árbol |
| 🛟 | **Restauración segura** | Crea un git worktree nuevo por defecto, nunca toca tu árbol; in-place exige `--yes` y siempre guarda antes un checkpoint de seguridad |
| 🤖 | **Agnóstico del modelo** | El motor no conoce ningún agente concreto; Claude / Codex / GLM son solo renderers distintos |
| 📦 | **Local primero** | Cero dependencias en runtime (Python ≥ 3.10 + git); los datos viven en el proyecto; sin cuentas, sin red, sin llamadas a LLM |

## 📦 Instalación

<details open>
<summary><b>Instalación global desde el código (recomendada)</b></summary>

```bash
git clone https://github.com/hwl668/Agentcheckpoint.git
cd Agentcheckpoint

# ayuda única (si aún no tienes pipx):
py -3 -m pip install --user pipx          # POSIX: python3 -m pip install --user pipx

# instalación global (editable: los cambios de código aplican al instante):
py -3 -m pipx install -e .
py -3 -m pipx ensurepath                  # añade ~/.local/bin al PATH, una sola vez
```

Abre una terminal nueva:

```bash
cd ~/projects/any-project
agentck --version
agentck init
```

</details>

<details>
<summary><b>Alternativas</b></summary>

```bash
pipx install agentck                # cuando se publique en PyPI
uv tool install agentck             # usuarios de uv
py -3 -m pip install --user .       # pip normal, sin aislamiento de venv
```

> Nota de nombres: la distribución en PyPI es **`agentck`**
> (`agentcheckpoint` está ocupado por otro proyecto); el paquete Python sigue
> importándose como `agentcheckpoint` y el comando es `agentck`.

</details>

**CLI global, datos por proyecto**: cada repositorio tiene su propio
`.agentcheckpoint/` (excluido localmente vía `.git/info/exclude`; tu
`.gitignore` nunca se toca) y los stores nunca se ven entre sí. Fuera de un
repositorio git, todo comando falla de forma segura con exit code 2.

## 🚀 Inicio rápido

```bash
cd my-project
agentck init
```

Trabaja con tu agente y congela el estado:

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

Los comandos `--test` se **ejecutan de verdad**; sus códigos de salida y el
final de su salida se graban como evidencia de máquina. Al entregar a otro
agente:

```bash
agentck verify            # ¿el estado sigue siendo fiable?
agentck resume codex > HANDOFF.md
```

¿Quieres volver a un checkpoint de confianza?

```bash
agentck restore cp_20261004_161741      # en un worktree nuevo; tu árbol intacto
```

## 🧰 Comandos

| Comando | Propósito |
|---|---|
| `agentck init` | inicializa `.agentcheckpoint/` (y lo excluye localmente) |
| `agentck save [label] [--goal …] [--test cmd] [--parent ref]` | congela el estado actual; `--test` ejecuta y graba evidencia |
| `agentck list [--json]` | todos los checkpoints |
| `agentck log` | el DAG de checkpoints como árbol (bifurcaciones y enlaces rotos visibles) |
| `agentck show [ref] [--json]` | un checkpoint + su documento de handoff |
| `agentck diff <a> <b>` | qué cambió entre dos checkpoints |
| `agentck verify [ref] [--json]` | deriva / obsolescencia / integridad / confianza (exit 1 = deriva) |
| `agentck replay [ref] [--json]` | reejecuta los comandos grabados y compara (exit 1 = regresión) |
| `agentck resume [claude\|codex\|glm\|plain]` | documento de handoff etiquetado con evidencia para el siguiente agente |
| `agentck restore <ref>` | restaura el estado (worktree por defecto; `--in-place --yes` reescribe el árbol actual) |

Las referencias aceptan `latest`, un id exacto, un prefijo único o una etiqueta.

## 🧠 Cómo funciona

Cada checkpoint es un directorio legible por humanos (esquema
`agent-checkpoint/v1`):

<details>
<summary><b>Estructura de un checkpoint</b></summary>

```text
.agentcheckpoint/checkpoints/cp_20261004_161741/
├── manifest.json        # el checkpoint (declaraciones del agente + observaciones de máquina)
├── handoff.md           # handoff estático renderizado al guardar
├── integrity.json       # SHA256 de cada artefacto — verificación de integridad
├── git/                 # OBSERVED: status.json, staged.patch, tracked.patch, untracked/
├── execution/           # OBSERVED: tests.json (comandos, códigos de salida, colas)
└── semantic/            # AGENT-REPORTED: decisions.md, constraints.md, next-steps.md
```

</details>

Tres reglas duras:

1. **Los hechos de git siempre provienen de comandos git**, nunca de un LLM:
   la alucinación no puede contaminar la capa de verdad.
2. **Declaraciones y observaciones se guardan por separado**: goal /
   completed / decisions / blockers solo van a `agent_claims`, siempre
   etiquetadas "no verificado de forma independiente".
3. **Los checkpoints son de solo anexado**: verify y restore re-hashean todo;
   cualquier corrupción o modificación no anticipada se detecta. integrity.json
   no puede hashearse a sí mismo — resistir a un atacante decidido requiere
   checkpoints firmados (ver hoja de ruta).

La fórmula exacta de la heurística de confianza y la semántica de DAG y
replay están en la [especificación del protocolo (inglés)](spec/agent-checkpoint-v1.md).

## 🛡 Diseño de seguridad y límites conocidos

- La restauración crea un worktree nuevo por defecto; `--in-place` exige un
  `--yes` explícito y siempre escribe primero un checkpoint de seguridad
  `pre-restore-`.
- El checkout y la aplicación de parches fuerzan `core.autocrlf=false`, de
  modo que los bytes restaurados coinciden bit a bit con los hashes guardados.
- La entrada semántica y la salida grabada se **sanitizan mejor-esfuerzo**
  buscando secretos; los secretos sospechosos en parches solo generan
  advertencia (reescribirlos rompería la integridad).
- Límites honestos de v1: los estados unmerged (conflicto) se graban pero no
  se restauran; verify no reejecuta comandos (usa `agentck replay`); la
  sanitización es mejor-esfuerzo, no una garantía.

## 🧭 Hoja de ruta

- [x] Protocolo `agent-checkpoint/v1` completo (save / verify / resume / restore / diff)
- [x] Checkpoint DAG + replay de ejecución
- [ ] Hooks de Claude Code para checkpoints automáticos (fin de sesión / antes de acciones riesgosas)
- [ ] Paquetes de Skill distribuibles por plataforma de agente
- [ ] Puntuación de calidad del checkpoint
- [ ] Checkpoints firmados (raíz Merkle + Ed25519/SSH/Sigstore)

## 🤖 Integración con agentes

Haz que Claude / Codex / GLM usen agentck correctamente: instala
[`skills/agent-checkpoint/SKILL.md`](skills/agent-checkpoint/SKILL.md)
en tu agente. Define cuándo hacer checkpoint, que las declaraciones sean
concretas y falsables, y la disciplina de evidencia: *nunca afirmes que las
pruebas pasan si no se grabaron con `--test`*.

## 💻 Desarrollo

```bash
py -3 -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/pytest          # 68 pruebas, todas sobre repositorios git temporales herméticos
.venv/Scripts/ruff check .
```

Documentación profunda (inglés): [SPEC.md](SPEC.md) ·
[especificación del protocolo](spec/agent-checkpoint-v1.md) · [CHANGELOG](CHANGELOG.md)

---

<div align="center">

**MIT** © AgentCheckpoint contributors

CLI global, datos por proyecto.

</div>
