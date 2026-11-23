# NW_CONTEXT — Night Watch × NoemaForge

> **Назначение:** накопительный, проверяемый контекст части NoemaForge, связанной с Night Watch (NW), его автономным циклом разработки (NWEV), интеграцией с NF и текущими ограничениями. Читать перед продолжением работ по NW.  
> **Последняя содержательная сверка:** 2026-11-23. **Статус документа:** working context / не release-evidence и не замена канонических NF-политик.  
> **Область:** NoemaForge / Night Watch. **Видимость:** репозиторий GitHub публичный; не помещать в этот документ приватные логи, секреты, персональные данные, содержимое локальных закрытых каталогов и непроверенные утверждения.
>
> Этот файл создан по прямому требованию владельца проекта: **после обработки каждого пользовательского запроса проверять, требуется ли обновить контекст Night Watch**. Если есть значимое изменение, обновлять файл с датой, основанием и оценкой достоверности. Если изменений нет — не делать пустой commit. В отсутствие доступа к GitHub подготовить patch/полный текст и явно обозначить, что репозиторий ещё не обновлён. Новые утверждения не должны превращать PENDING/BLOCKED в PASS без новых evidence.

## 0. Межчатовый протокол проекта «ОС_ИИ» (обязательный)

**Требование владельца, 2026-11-23:** этот документ — **хранитель контекста Night Watch между всеми чатами ChatGPT Project «ОС_ИИ»**, а не только README или журнал GitHub. Его надо использовать для восстановления рабочего состояния при переходе между чатами, после длинных диалогов или потери части истории.

### 0.1 Две поверхности и единый источник истины

- **Основная версия (authoritative):** корневой `NW_CONTEXT.md` в репозитории `Sinev-Maksim/NoemaForge`. До принятия [draft PR #355](https://github.com/Sinev-Maksim/NoemaForge/pull/355) она живёт в ветке `codex/task-nw-context-20261123`:
  `https://github.com/Sinev-Maksim/NoemaForge/blob/codex/task-nw-context-20261123/NW_CONTEXT.md`.
  После merge источником становится **только явно согласованная принимающая ветка/новая maintenance-ветка**, а не угадываемый `main`.
- **Project «ОС_ИИ»:** файл **обнаружен среди Project sources/files при проверке 2026-11-23**. Перед тестовыми GitHub-записями он совпадал с GitHub-версией по содержанию, за исключением завершающего LF. После GitHub-обновлений этот снимок **устарел** и его нужно обновить отдельно. Он остаётся fallback при недоступности GitHub. Загруженный файл **не синхронизируется автоматически** с GitHub. Факт его присутствия/актуальности необходимо проверять отдельно. Если Project-снимок и GitHub расходятся, сообщить о drift, прочитать новый GitHub SHA и использовать доказанный более свежий источник; не объединять конфликтующие изменения молча.
- **Project Instructions:** чтобы правило действовало в *новых чатах*, его текст должен быть добавлен пользователем в настройки самого ChatGPT Project. Одного `AGENTS.md` из GitHub недостаточно: он действует для репозиторных агентов, но не устанавливает Project Instructions в интерфейсе ChatGPT.
- **Project memory и история чатов:** вспомогательные источники для восстановления деталей, не заменяют проверяемых HEAD/checkpoint/gates. Нельзя обещать автоматическую фоновую синхронизацию или выполнение при отсутствии доступа к репозиторию.

### 0.2 На старте каждого нового чата проекта

1. Если запрос касается Night Watch, NWEV, self-heal, Dev Team, NW-Git/Claude/Codex, интеграции NF, сначала открыть **последнюю подтверждённую** версию `NW_CONTEXT.md` через GitHub connector/доступный источник. Если доступ невозможен, читать Project-снимок, явно отметить его provenance и возможную устарелость. Если нет ни того ни другого, не восстанавливать точные значения из догадок.
2. Прочитать разделы §1 «Краткий текущий статус», §7 «Текущие задачи», §8 «Как продолжать», §10 «Правило обслуживания» и **последние записи журнала**. По требованию задачи развернуть остальные разделы, ссылки/исходники и Project-чаты.
3. Держать различными `VERIFIED_OPERATOR_OUTPUT`, `VERIFIED_OFFLINE_ARTIFACT`, `SOURCE_PRESENT`, `DOCUMENTED_POLICY`, `PROPOSED`, `BLOCKED/UNKNOWN`. При противоречии не подменять значение более удобной версией; запросить/собрать независимые доказательства.
4. Начать с текущего незавершённого шага. Не запускать повторно уже завершённый `prepare` и не повторять 9/9, не менять dirty main checkout, не снимать `RELEASE_BLOCKED` или model-call gates.

### 0.3 После обработки каждого пользовательского запроса в «ОС_ИИ»

1. **Проверить затронут ли Night Watch**: появилось ли подтверждённое решение, новый run/SHA, результат команды, тест, review/CI, статус gate, новая спецификация, blocker, изменённый план или next action.
2. Если изменился — **обновить этот же файл**: верхний статус, необходимый тематический раздел, §10 журнал с датой и типом evidence. Обновление осуществлять на отдельной разрешённой ветке и через PR. Нет изменения — нет пустого коммита.
3. Перед записью перечитать последнюю версию (blob SHA) и проверить отсутствие конкурирующего обновления. При конфликте — diff/rebase содержимого, не перезаписывать вслепую.
4. После записи выполнить read-back и сообщить пользователю **фактический GitHub commit/ref/PR**. Если запись недоступна — дать полный актуализированный файл или patch, написать `NOT_PERSISTED` и не заявлять об успехе. Восстановить синхронизацию Project-снимка отдельно; **не говорить, что Project-файл автоматически обновился**.
5. Запреты на секреты, автоматические model calls, approve/merge/release и target evidence действуют независимо от необходимости обновить контекст.

### 0.4 Рекомендуемая Project Instruction (копировать в настройки проекта «ОС_ИИ»)

> Для всех чатов проекта «ОС_ИИ»: `NW_CONTEXT.md` — межчатовый хранитель контекста Night Watch/NWEV. Перед работой по Night Watch сначала найди и прочитай актуальную GitHub-версию `Sinev-Maksim/NoemaForge` → `NW_CONTEXT.md` (до merge PR #355: ветка `codex/task-nw-context-20261123`); при недоступности используй прикреплённую к Project копию, отмечая её дату и возможную устарелость. После каждого запроса проверяй, изменился ли NW-контекст. Если изменился, обновляй тот же файл с точными SHA/run/evidence на отдельной ветке/PR; после записи проверяй read-back. Если доступ к записи отсутствует, выдавай patch и честно отмечай `NOT_PERSISTED`. Не повторяй завершённые циклы, не обходи review, ToolProxy, epoch, sandbox и release gates; `BLOCKED` не превращай в PASS без доказательств. Для нерелевантных запросов не делай пустых commits.

## 1. Краткий текущий статус (2026-11-23)

| Слой | Состояние и evidence |
|---|---|
| Основной NF checkout пользователя | Dirty, не трогать; на Windows существует отдельная клонированная лабораторная копия. |
| База лаборатории NF | `release/0.33.0-dev` @ `ab12cb61959066fe3f5b7ad12360e497441fabd1`. Это **approved exact SHA только для EXTERNAL_OPERATOR_LAB**, не production integration approval. |
| Родительский цикл NWEVX | `NWEVX-20261115T145907-9bcd6f2eb0`; стадия `NINE_COMPLETED_CHECKPOINTED`, DEV-003…011 = 9 принятых advisory-итераций; 32/32 модельных вызова. |
| Родительский checkpoint | Git HEAD `5306d41a92f7c35ba38def068ab4ce8e70efa6a2`; checkpoint SHA256 `c42c2fc2bb985a5f7015881f04db6e617220bc07f4116a7b927ae0ac7cebd756`. |
| Подготовленный NWEV v2.1 run | `NWEV21-20261123T130839Z-2100f6c96`, `PREPARED_INTEGRATION_BLOCKED`; native Git ancestry сохранена, workspace CLEAN, freeze verified: **574 файла тестов по SHA**, а **не 574 выполненных теста**. |
| Разрешение модельных вызовов в NWEV21 | `model_calls_authorized=0`. Новые Claude/Codex-вызовы не разрешены этим preflight. |
| Реальный NF-native runtime | `native_runtime_connected=false`. Нет подтверждённых ToolProxy/epoch/lease, независимого review, CodeRabbit и sandbox. |
| Release и публикация | `release=BLOCKED`, `publication=false`. Debian target acceptance = `BLOCKED_TARGET_UNAVAILABLE`. |
| Текущая ближайшая задача | `NWEV-INFRA-01`: read-only native contract/review probe на подготовленном run; после него — настоящая интеграция, а не повторный `prepare`. |

**Не путать три типа успеха:** (1) пакет прошёл offline self-test; (2) лабораторная итерация получила advisory review; (3) код прошёл NF-native gates и target acceptance. Ни (1), ни (2) не означают (3).

## 2. Назначение и границы системы

**NoemaForge (NF)** — local-first, privacy-first AI OS. Night Watch — существующий контур работы с кодом, независимым review, управлением ошибками и evidence. NWEV — дополнительный лабораторный цикл развития NW/NF, который должен **переиспользовать**, а не дублировать, NF-native механизмы.

Ответственности различаются:

- **NF architecture/control plane:** `AGENTS.md`, `noemaforge/docs/reference/PROJECT_CONTEXT.md`, `noemaforge/docs/architecture/ARCHITECTURE.md`, ToolProxy, Contract Epochs, Resource Lease, Dev Team, Worktree Manager, Code Evolution, Evolution contracts, Code QA.
- **Native Night Watch:** самостоятельный Windows self-heal harness, provider routing и транспорт, recovery, patch proposal, immutable regression, independent review routing, history continuity.
- **NWEV laboratory orchestration:** девятиитерационные окна, бухгалтерия вызовов/попыток, checkpoint, provenance, scratch Git history, bounded interruption/replay; не подменяет authority NF.
- **Owner/operator:** выбирает точный Git SHA и режим, разрешает новые модельные вызовы и опасные действия отдельно. Архитектурный review и release — отдельные решения.

Для NF-native действий запрещён обход ToolProxy/capability-token/Contract Epoch. Внешний лабораторный режим допускается только при явной метке `EXTERNAL_OPERATOR_LAB` и не вправе называться native, production-ready или release-approved.

## 3. Неизменяемые правила и критерии качества

1. **План существует с первого шага.** Девять — число **различных принятых DEV-итераций** между накопительными ревизиями, не лимит модельных вызовов и не девять уровней root-cause extrapolation NW.
2. После каждых 9 принятых итераций: summary, точные SHA и evidence, architecture delta, regression и отрицательные тесты, независимый review, невыполненные риски, следующая очередь до 9, новый run/authorization. Старые шаги автоматически не повторяются.
3. Считать отдельно: `development_iterations_accepted`, `model_calls` / reservations, `product_attempts`, `control_plane_retries` и `review_calls`. Ошибка транспорта/провайдера не равна PRODUCT repair attempt.
4. `SUCCESS_FIRST_MAX_EVIDENCE`: сохранять доказательства и продолжать независимые безопасные задачи, если отдельная задача заблокирована; не обходить hard-stop, бюджет, reviewer и release gate.
5. Exact candidate SHA, от какого HEAD получен diff, зафиксированные тесты, trust provenance и reviewer identity — обязательны. Старый review не переносится на новый SHA.
6. В Native Night Watch regression-тесты self-heal защищены от изменения самим циклом исправления. Новые тесты добавляются отдельно и проверяются; тесты, изменённые при операторской разработке, нельзя автоматически приписывать self-heal.
7. Любой unknown/incomplete evidence => BLOCKED/PENDING, а не предполагаемый PASS. Локальный Codex PASS — **advisory**, если нет полного NF-native review gate.
8. Никаких `reset` / `clean` / `stash` в dirty main checkout, скрытого `push` / `merge` / `release` / переключения epoch. Lab-run и истории прежних циклов должны оставаться нетронутыми.
9. Один активный тяжёлый/model worker, если явно утверждённая epoch/policy не разрешает иначе; тяжелые runtime-действия требуют operator approval и ресурса/lease.
10. Тесты, написанные/изменённые моделью, нельзя запускать как произвольный Python под учётной записью пользователя с секретами: требуется непривилегированная песочница, минимум прав, ограничение egress.
11. Архитектурные источники проверять по **фактически выбранному Git SHA**, не по названию файла из более старого архива. `AGENTS.md` содержит исторические сведения про ветку `release/0.32.2-hardening`; это не подтверждает актуальный integration target.
12. Нельзя утверждать Linux/Debian target acceptance по Windows unit/self-test и нельзя использовать sealed archive как аттестацию активной установленной версии.

## 4. Что уже есть в Native Night Watch

Пользователь предоставил архив `NoemaForge-NightWatch.rar` (проверка 2026-11-17): около 46 005 записей. Содержит каталог `current/`, историю и отдельный исправленный routing-кандидат. Архив не равнозначен запущенному runtime на машине.

- В `CURRENT_RELEASE.json` каталог `current/` обозначен как Night Watch Self-Heal **v3.8.5** с `deployedAt=2026-09-21T10:30:39.7824061Z`, `exactBase=a3c172f5d60113876f0c103010de411fc30b8c38`. Это утверждение **манифеста архива**, не независимое подтверждение deployment в ноябре.
- Хеш-проверка `current/SHA256SUMS.json`: **34/34** доступных файлов совпали. В более позднем sealed-пакете NWEV21 отдельно закреплены 32 reference-файла: это **другой показатель**, не противоречие.
- Исходные routing-тесты `current/payload/`: **21/21 PASS**. Исправленный `corrected/`: **35/35 PASS** в изоляции. `candidate-review-result.json` имеет `HARNESS_ERROR` / `reconstruction=NOT_RUN`: нельзя считать corrected-кандидат внедрённым.
- `HARNESS_REGRESSION_SELFTEST.py`, `PROVIDER_ROLE_DEGRADATION_SELFTEST.py`, `WINDOWS_STARTUP_HARDENING_SELFTEST.py` в архивном офлайн-аудите дали PASS; это не аттестация живого хоста.
- В историческом self-heal log: `IMPLEMENTATION=PASS` при `ACCEPTANCE=PENDING` и недоступном отличном reviewer; не маркировать как полноценный independent PASS.

Реализованные механизмы (переиспользовать):

| Native компонент / контракт | Назначение |
|---|---|
| `RUN_AGENT_SELF_HEAL.ps1` | Существующий bounded self-heal loop и safety state machine; не заменять новым независимым контроллером. |
| `INVOKE_CLAUDE_AGENT.ps1`, `INVOKE_CODEX_AGENT.ps1`, `PROVIDER_ROLE_POLICY.json`, `AGENT_PROTOCOL.json` | Provider capability, availability, CLI transport/failover, роли implementer/reviewer, структурированные результаты. |
| `RUN_LOCAL_ROUTING_CONTRACT_INNER.ps1`, `SELF_HEAL_POLICY.json` | Exact-base Git isolation, попытки/обрывы, repair bounds, degradation, rollback. |
| `NIGHT_WATCH_DEVELOPMENT_RULES.md`, `ENGINEERING_GUARDRAILS.json` | Immutable regression, scope, evidence-first, rollback, запрет обхода hard-stop. |
| `HISTORY_CONTINUITY_POLICY.json`, `MERGE_HANDOFF_HISTORY.py` | Накопительная история и handoff без потери lineage. |
| `BUILD_VALIDATION.json`, `FAILURE_RESOLUTION_MATRIX.json`, `PRE_SEND_DRY_RUN.py` | Типизированная диагностика и pre-send/fault-injection проверки. |

**Источник:** архив пользователя и `NWEV_Native_NightWatch_Audit_2026-11-17.md`. Для актуального поведения установленного NW необходим новый read-only runtime probe.

## 5. Реальные NF-native модули и ограничения

GitHub: `https://github.com/Sinev-Maksim/NoemaForge`. Файлы присутствуют в определённых ветках/коммитах, но **не обязаны присутствовать все в одной рабочей базе**.

| Файл / поверхность | Роль |
|---|---|
| `noemaforge/src/code_evolution_loop.py` | TODO/task → propose → (explicit apply) → tests → (explicit commit) → outcome. |
| `noemaforge/src/dev_team_runtime.py` и `dev_bounded_loop_runtime.py` | Dev Team и bounded checkpoint/stop. `dev-bounded-loop-policy.json` имел `status=shadow`, `forbid_auto_apply=true`, `require_admin_approval=true`. |
| `noemaforge/src/code_qa_runtime.py` | Последовательные review/test-gap sub-team, разнообразие моделей; offline scaffolding по умолчанию. |
| `noemaforge/src/safe_worktree_evolution_runtime.py` и `worktree_manager.py` | Safe worktree policy и Git boundary. |
| `noemaforge/src/evolution_execution_contracts_runtime.py` | Проверка типов `noemaforge.evolution-execution/v1` (см. ниже). |
| `noemaforge/src/toolproxy.py`, `epoch.py` | Capability boundary, привязка токена к immutable Contract Epoch, операторское переключение epoch. |
| `noemaforge/src/night_watch_routing_runtime.py` | Reviewer/provider readiness, independent identity, exact SHA, CodeRabbit gating; найден в GitHub ветке `night-watch`, **отсутствует** в выбранной лабораторной `release/0.33.0-dev`. |
| `noemaforge/src/evolution_adapters/night_watch_readonly.py` | Старый read-only legacy-NW observer; найден в `night-watch`, **отсутствует** в выбранной лабораторной базе. Не умеет автоматически интерпретировать новые NWEVX/NWEV21 события. |

**Девять типов NF Evolution:** `EvolutionRun`, `EvolutionWorkItem`, `EvolutionEvent`, `EvolutionAgentRequest`, `EvolutionAgentResult`, `EvolutionResourceLease`, `EvolutionMutationEvidence`, `EvolutionIndependentReviewEvidence`, `EvolutionReleaseGateResult`. Канонические схемы — `noemaforge/contracts/evolution_*.schema.json`, не JSON, придуманный исполнителем.

Важные требования валидатора: независимый producer/reviewer, точное совпадение `reviewed_head == target_head` и неистёкший review; тяжёлый resource lease exclusive/approved/one-active; manual gate PASS требует `manual_marker` и `operator_approved=true`; `EvolutionRun` требует инвариантов ToolProxy, epoch, one-worker, explicit approval и no-hidden-autostart. Схема может подтверждать **формат**, но не происхождение provider proof: это отдельная trust boundary.

Night Watch router в `night-watch` требует CodeRabbit при scope `code`, `config` и `infra`; для `markdown` — когда затронут prior reviewer CodeRabbit. Ненаблюдаемый provider или отсутствующий live PR review ведёт к BLOCKED/YIELD, не PASS.

## 6. История разработки и доказательства

### До первого полноценного девятиитерационного окна

- Исторический `NWEVQ-20261112T082827-553f7b0` завершился на **9/9 модельных вызовах**, не 9 DEV-задачах. Не переиспользовать его счётчик и не replay уже выполненное.
- DEV-001: candidate `38003924d98f2c3a9989dbdf31d2c2f300279f5e`, локальный advisory review.
- DEV-002: первоначальный candidate `3e345ba82d582fa6eccd97941fe3a5546f8ec03b`; исправленный `47d8b69a9efffb052821c2ce0719c92190e334ea`. **25/25 unit tests PASS** на локальных источниках; независимое подтверждение исправленного SHA и authoritative исходный task spec не установлены.
- Реконструкция старого контракта DEV-002 и trust-boundary cases — материал для дальнейшей работы, не автоматически утверждённая исходная спецификация.

### NWEVX: DEV-003…DEV-011 (завершённый лабораторный этап)

Run `NWEVX-20261115T145907-9bcd6f2eb0`; `NINE_COMPLETED_CHECKPOINTED`; **9/9 distinct DEV iterations, 32/32 model calls**. Итоговый HEAD и checkpoint SHA — в `1.

Реализованные девять вспомогательных модулей и соответствующие тесты:

1. `nwev_call_accounting.py` — учёт вызовов.
2. `nwev_review_outcome_contract.py` — review outcome.
3. `nwev_provenance_payload.py` — provenance.
4. `nwev_trusted_evidence_gate.py` — trust/evidence checks.
5. `nwev_iteration_ledger.py` — ledger итераций.
6. `nwev_architecture_gate.py` — architecture gate.
7. `nwev_batch_checkpoint_gate.py` — checkpoint после окна.
8. `nwev_cycle_replay_policy.py` — replay.
9. `nwev_evidence_rollup.py` — сводка evidence.

Экспорт `NWEV_9of9_Code_Review.zip`: 18 source/test файлов; SHA256 архива `cc9ae3b5cf60d4c0d161eb8f581b26db045f7d1a5fe58b9b839b34279cae97f1`; 139 локальных unit-тестов PASS + 7 дополнительных boundary probes. Они подтверждают модули, **не сквозную интеграцию NF**. Финальный DEV-010 имел `DONE_ADVISORY` после зафиксированных repair failures; финальное состояние сохранять без переписывания истории. Архитектурное approval = PENDING, Debian = BLOCKED.

### Bridge v2 Candidate (не запускать)

`NWEV_ExecutionBridge_v2_Candidate` проходил 16/16 локальных offline tests и mock 9/9, но **отвергнут как NF-native исполнитель**: использовал собственный `git init` вместо настоящей NF ancestry, параллельный review/ledger, прямой CLI Claude/Codex, допускал изменения защищённых тестов, не подключал ToolProxy/epoch/lease/sandbox и не менял настоящие NF touchpoints. **Статус: SUPERSEDED_DESIGN_REFERENCE / NO-GO.** Не вызывать `review_executor.py --cloud-ok` / `nwev_v2.py resume`.

### NWEV v2.1 foundation (последнее подтверждённое пользователем)

Подготовительный пакет `NWEV21_NF_Native_Execution_Pack`: проверка 42 файлов, sealed 32 NW reference-файлов, **12/12 offline fixture tests PASS**. На Windows пользователь успешно выполнил:
- независимый `git clone` от `release/0.33.0-dev` @ `ab12cb61959066fe3f5b7ad12360e497441fabd1`; исходный main checkout не менялся;
- `nwev21.py inspect` → пакеты/родительский checkpoint/9 schemas подтверждены, оба модуля NW в source отсутствуют;
- `nwev21.py prepare` → `NWEV21-20261123T130839Z-2100f6c96`;
- `nwev21.py status` → `PREPARED_INTEGRATION_BLOCKED`, workspace_clean=true, frozen_tests_verified=574, native_runtime_connected=false, model_calls_authorized=0, release=BLOCKED.

**Не выполнять повторно** `clone` или `prepare` в уже созданных каталогах. Лабораторная база одобрена только для prep, а не для live NF-native execution.

## 7. Текущие задачи, блокеры и следующий безопасный шаг

### NWEV-INFRA-01 (идёт)

Read-only contract/review probe `NWEV21_INFRA01_Probe.py` (v0.1) подготовлен, в отдельной среде **9/9 offline-тестов PASS**, но **Windows-выполнение пользователем ещё не подтверждено**. Probe читает existing run, сверяет manifest/parent/frozen tests, вызывает sealed Night Watch router с **ненаблюдаемым набором провайдеров** и строит два preview-документа (`EvolutionWorkItem`, `EvolutionReleaseGateResult`) по схемам из выбранного NF SHA. Preview не сохраняются как фактический runtime event и не являются полным NF-native acceptance.

Ожидаемо: `ok=true` и **`review_gate_pass=false`**, `coderabbit_required=true`, `native_runtime_connected=false`, `release=BLOCKED`. Положительный статус этого probe не открывает модельные вызовы.

Для завершения INFRA-01 потребуются: настоящий ToolProxy/epoch-bound capability, общий exclusive resource lease, production-relevant reviewer/CodeRabbit evidence, полноценная схема Evolution events с trust provenance, изоляция тестового runner, crash/reboot recovery и отдельный independent architecture review.

### DEV-012–DEV-020 — пересмотренный **план**, не выполненные задачи

| DEV | Предлагаемая цель | Минимальный gate |
|---|---|---|
| 012 | Exact NF source anchor и явный selector EXTERNAL_OPERATOR_LAB / NF_NATIVE | Approved SHA + policy pins; без native-claims в lab |
| 013 | Legacy Night Watch + NWEVX → NF Evolution event projection | Типизированные события, дедупликация, только read-only legacy |
| 014 | Native provider/review routing и CodeRabbit | Same-SHA независимость, quality, no-self-review, blocked≠pass |
| 015 | Раздельные call/product/control/iteration ledgers | Monotonic accounting, crash-safe, no double count |
| 016 | Native Dev Team / ToolProxy execution adapter | Capability+epoch, operator approval, exclusive lease |
| 017 | Git worktree + immutable regression policy | Ancestry, frozen SHA, отрицательные scope tests |
| 018 | NF-native evidence и batch checkpoint | 9 kinds schema, trusted provenance, release blocked |
| 019 | Interrupted-run replay + cumulative handoff | No stale review, unknown outcome reserved, old history unchanged |
| 020 | Native integration E2E / fault injection / target blocker | Cross-module tests, truthful Debian/PR status, no publish |

План в файле `NWEV_DEV012_020_NF_NATIVE_RESCOPED.json` имел `PROPOSED_NOT_AUTHORIZED`. Выполнение не начинается до действительного прохождения gate A0–A6 и отдельного бюджета новых модельных вызовов.

### Текущая матрица gates

| Gate | Состояние на 2026-11-23 |
|---|---|
| A0 Exact Git base | **PASS для EXTERNAL_OPERATOR_LAB**, не NF-native/production |
| A1 Real Git ancestry / clean lab workspace | PASS на созданном NWEV21 |
| A2 Девять NF Evolution schema kinds | AVAILABLE; пока нет полного native end-to-end evidence |
| A3 Native reviewer/CodeRabbit | PENDING / BLOCKED |
| A4 ToolProxy + immutable epoch + exclusive lease | BLOCKED_NOT_CONNECTED |
| A5 Sandbox for model-written tests | BLOCKED_NOT_PROVEN |
| A6 Native E2E / acceptance | PENDING |
| A7 Release/publish | BLOCKED / false |

## 8. Как продолжать работу из нового чата/сессии

1. Читать `NW_CONTEXT.md`, затем актуальные `AGENTS.md`, `PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, policy и run state. **Этот файл — handoff, не substitute для исходных доказательств**.
2. Уточнять, на какой поверхности находится изменение: архив `current/`, исправленный candidate, `night-watch` branch, `release/0.33.0-dev`, внешний лабораторный NWEVX/NWEV21 или установленный Debian runtime. Не смешивать их.
3. Проверять актуальный SHA/состояние через read-only команды; не предполагать, что GitHub ref всё ещё соответствует записанному SHA. Принимаемый commit pin неизменен, имя ветки может сдвигаться.
4. Для следующего шага запросить/проанализировать результат запуска `NWEV21_INFRA01_Probe.py` **в существующем NWEV21**, не повторяя prepare.
5. После этого проектировать **минимальные NF-native adapters**, переиспользуя существующие механизмы и записывая FAIL/BLOCKED честно; не запускать модельный цикл без отдельного разрешения.
6. На каждом следующем цикле проверять freeze/architecture/review/trust boundary, точную Git ancestry и global worker ограничение.

## 9. Индекс источников (не равно live-аттестации)

**GitHub (каноническая читаемая база):**
- `AGENTS.md`; `noemaforge/docs/reference/PROJECT_CONTEXT.md`; `noemaforge/docs/architecture/ARCHITECTURE.md`.
- `noemaforge/src/code_evolution_loop.py`, `dev_team_runtime.py`, `dev_bounded_loop_runtime.py`, `code_qa_runtime.py`, `safe_worktree_evolution_runtime.py`, `evolution_execution_contracts_runtime.py`, `toolproxy.py`, `epoch.py`.
- `noemaforge/contracts/evolution_*.schema.json`; `noemaforge/configs/docs-hygiene-policy.json`.
- Branch `night-watch`: `noemaforge/src/night_watch_routing_runtime.py` и `noemaforge/src/evolution_adapters/night_watch_readonly.py`. На дату аудита 2026-11-17 ветка была `02d601419340e2bc681725324f57c38d3de07573`.

**Локальные пользовательские evidence/artifacts (не коммитить их содержимое в публичный репозиторий):**
- `NoemaForge-NightWatch.rar`; `NWEV_Native_NightWatch_Audit_2026-11-17.md`; `NWEV_NF_NightWatch_BridgeV2_Compatibility_Audit_2026-11-17.md`.
- `NWEV_9of9_Code_Review.zip`; `NWEV_CYCLE_001_EXTENDED_CHECKPOINT_2026-11-13.md`; `NWEV_DEV012_020_NF_NATIVE_RESCOPED.json`.
- `NWEV21_NF_Native_Execution_Pack.tar` / `.zip`; `NWEV21_INFRA01_Probe.py`; их манифесты/QA и соответствующий локальный run state.

**Степени достоверности:**
- `VERIFIED_OPERATOR_OUTPUT` — дословный вывод оператора о реально выполненной команде;
- `VERIFIED_OFFLINE_ARTIFACT` — локально сверенная копия файла/хеш/тест;
- `SOURCE_PRESENT` — код существует в конкретной ветке/SHA, **не** доказано его подключение или deployment;
- `DOCUMENTED_POLICY` — требование из политики; не равно runtime enforcement;
- `PROPOSED` — проектное решение/следующая задача;
- `BLOCKED` / `UNKNOWN` — не подменять выводом PASS.

## 10. Правило обслуживания NW_CONTEXT.md

**После каждого запроса пользователя** в части Night Watch выполнить короткую контрольную проверку: появились ли новые факты (вывод команд, SHA, run/stage, test/review results), согласованные решения, изменения архитектуры, новые блокеры или изменился следующий шаг? При необходимости **обновить этот же документ**, а не создавать отдельный контекстный файл.

- Изменять верхнее «Краткий текущий статус», соответствующий тематический раздел и журнал изменений ниже.
- Для каждого нового утверждения указать дату, конкретный run/SHA/evidence и статус проверки; результаты model-generated mock не объявлять live.
- В случае конфликта старой и новой информации сохранять историю с пометкой `SUPERSEDED`, а не бесследно переписывать предыдущий verdict.
- Избегать дублирования: новые алгоритмы/контракты должны ссылаться на канонические NF-файлы, а не копировать их целиком. Не коммитить токены, сырые логи, списки секретов, приватные имена/адреса.
- Изменения создавать на отдельной ветке и проводить через review/PR. Не коммитить напрямую в `main` или защищённые release-ветки, не делать automatic merge. Поддержка контекста **не даёт разрешения** на cloud calls, публикацию или release.
- Если запрос не касается Night Watch и не меняет связанный контекст, достаточно проверки без пустого коммита.

### Журнал контекста

| Дата | Изменение | Evidence / решение |
|---|---|---|
| 2026-11-23 | NWCTX-SMOKE-20261123-01: WRITE/UPDATE persistence smoke test; защита от устаревшей версии PASS. | Первый write commit `81c0bb255bf7a6459a312ff668e3bcb08fb81217` подтверждён read-back (blob `30394c09a73cb831d0c70a181c4c82d5d7b4c678`). Повторная запись с устаревшим blob `9cd962a6a18109769d88fb68ad81a1140785784e` отклонена GitHub HTTP 409, состояние осталось неизменным. Второе обновление — этот commit; резервный Project-снимок требует обновления отдельно. |
| 2026-11-23 | Уточнено назначение: межчатовый хранитель контекста ChatGPT Project «ОС_ИИ», а не только GitHub-файл. Добавлен протокол start-of-chat/end-of-turn, Source of Truth, Project Instructions и контроль drift снимков. | Прямое решение пользователя; на момент первоначальной проверки Project-файл не был обнаружен; позднее подтверждена его доступность. |
| 2026-11-23 | Инициализирован единый `NW_CONTEXT.md`. Сведены Native NW, NF contracts, DEV-001..011, v2 NO-GO, NWEV21 run и INFRA-01. | Пользователь явно потребовал вести файл; исходники и выводы перечислены выше. |

---
**Контроль перед любыми следующими действиями:** реальный run `NWEV21-20261123T130839Z-2100f6c96` остаётся `PREPARED_INTEGRATION_BLOCKED`; `model_calls_authorized=0`; `release=BLOCKED`. Это не ошибка, а корректное состояние безопасности.
