# NoemaForge 0.32.1 — Admin Chat, locales, artifacts

0.32.1 changes the default GUI direction from an engineering dashboard to a chat-first Admin console.

## Layout contract

- One main chat with the user.
- Active persona portrait in the top-left area.
- Persona switch line in the chat, for example: `-- смена персоны с Admin на Dev Team --`.
- One separate internal chat/panel for model/team handoffs.
- Raw JSON hidden under details/raw.
- Created files, patches, model-selection plans and evolution artifacts are shown as artifact cards.

## Dev Team flow

1. User says hello.
2. Admin replies in the selected locale.
3. User asks to improve code through Dev Team.
4. Admin asks what to change, where the project/file is, and whether to apply immediately or show patch first.
5. Admin checks file visibility and write mode.
6. Admin passes details to Dev Team.
7. GUI shows the persona switch line.
8. Dev Team writes/changes files.
9. Context, architecture and QA notes are saved as artifacts.

## Locales

Supported locales:

```text
en ru uk es de pt it zh-CN ja ko
```

Aliases:

```text
pt-PT -> pt
pt-BR -> pt
zh -> zh-CN
```

Machine keys stay English. User-facing chat strings are localized.
