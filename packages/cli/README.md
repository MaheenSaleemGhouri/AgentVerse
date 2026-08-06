# @agentverse/cli

```bash
npx @agentverse/cli templates
```

```
export AGENTVERSE_API_KEY=...
export AGENTVERSE_WORKSPACE_ID=...

agentverse templates                       # the first-party library
agentverse install research-assistant      # one-click install
agentverse run <agent-id> "Summarise this"
agentverse agents list --json
```

Every command takes `--json`, because a CLI whose output only a human can
read is a CLI nobody can script.

Built and tested in this repository; **not yet published to npm**.
