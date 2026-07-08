# Run in InstaVM badge kit

## Markdown snippet

```md
[![Run in InstaVM](https://instavm.io/badge.svg)](https://run.instavm.io/<slug>)
```

`<slug>` is assigned per tool.

Hosted names:

- `badge.svg` serves `run-in-instavm.svg`
- `badge-dark.svg` serves `run-in-instavm-dark.svg`

## HTML with dark mode

```html
<a href="https://run.instavm.io/<slug>">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://instavm.io/badge-dark.svg">
    <img alt="Run in InstaVM" src="https://instavm.io/badge.svg">
  </picture>
</a>
```

## PR body template

```text
This adds a Run in InstaVM badge to the README.
The badge is a plain link to https://run.instavm.io/<slug>.
InstaVM hosts the badge asset and the sandbox setup.
It lets readers try the CLI without installing it locally.
Please tell us if you want this removed or adjusted.
```

## Initial targets

| Slug | Repository |
| --- | --- |
| opencode | anomalyco/opencode |
| aider | Aider-AI/aider |
| cline | cline/cline |
| gemini-cli | google-gemini/gemini-cli |
| codex | openai/codex |
| goose | aaif-goose/goose |
| code-server | coder/code-server |
| jupyter | jupyterlab/jupyterlab |
| hermes | nousresearch/hermes-agent |

Deferred or coming soon:

| Slug | Repository |
| --- | --- |
| librechat | danny-avila/LibreChat |

License review first:

| Slug | Repository |
| --- | --- |
| crush | charmbracelet/crush |
| open-webui | open-webui/open-webui |

Skip core repo:

| Tool | Repository |
| --- | --- |
| claude-code | core repo |
