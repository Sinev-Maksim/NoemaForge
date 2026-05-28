# NoemaForge stateful Admin GUI shell

Version: `0.32.1`

## Scope

The GUI is a local operator shell, not only a web form. It must restore backend state after page refresh and prevent duplicate long-running jobs.

## Required state

- conversation history;
- active persona and portrait;
- artifacts;
- SR/SSR review records;
- epoch/model-selection state;
- active jobs and locks;
- task queue and inactivity timer;
- telemetry cards;
- pipeline catalog filters and selected pipeline.

## Safety

Browser clicks must not perform hidden privileged actions. They may create plan-first jobs, audited apply requests or fallback commands that the operator runs explicitly.
