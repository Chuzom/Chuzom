# Troubleshooting

## `chuzom` command not found

**macOS / Linux:**

```bash
# Confirm the binary is in your PATH
which chuzom || echo "not on PATH"

# If installed via pip into a venv, activate it first:
source .venv/bin/activate
chuzom --version

# Or run directly:
python -m chuzom --version     # works if __main__ is present
~/.local/bin/chuzom --version  # pip --user installs go here

# Permanently add pip's user bin to PATH (add to ~/.zshrc or ~/.bashrc):
export PATH="$HOME/.local/bin:$PATH"
```

**Windows (PowerShell):**

```powershell
python -m pip show chuzom-router | Select-String Location
$env:PATH += ";C:\Users\YOU\AppData\Roaming\Python\Python311\Scripts"
# Or persistently via System Properties → Environment Variables → PATH
```

## Hooks not firing (Claude Code)

```bash
chuzom doctor                                         # check hook registration
cat ~/.claude/settings.json | python -m json.tool | grep -A5 hook
chuzom install                                        # re-install if missing
chuzom install --force                                # force overwrite existing hooks
```

The hook file lives at `~/.claude/hooks/chuzom-auto-route.py`. If it's missing after
install, check that `~/.claude/` is writable and retry.

## Routing not working — Ollama not used

1. Confirm Ollama is running: `ollama list` should show your models.
2. Run `chuzom doctor` — it runs a live health check and populates
   `~/.chuzom/discovery.json`.
3. Set a model explicitly if auto-discovery fails:
   ```bash
   export CHUZOM_OLLAMA_MODEL=llama3.2:latest
   ```
4. Check the Ollama URL if you run it on a non-default port:
   ```bash
   export OLLAMA_BASE_URL=http://localhost:11435
   ```

## Research prompts answering from Ollama (stale data)

Research tasks (news, "latest X", current events) always bypass Ollama and route to
`llm_research` (Perplexity) — Ollama has a training cutoff and cannot fetch live web
data. If you see stale answers, check that `PERPLEXITY_API_KEY` is set:

```bash
chuzom doctor   # will warn if PERPLEXITY_API_KEY is missing
```

## Cursor / Windsurf rules not applying

Pull-routing IDEs require the rule file to be present in the project root:

```bash
chuzom install --host cursor      # or windsurf
# or
chuzom-install-hooks ide

ls .cursor/rules/use-chuzom.mdc
ls .windsurf/rules/use-chuzom.md
```

If the rule file exists but the model still doesn't call Chuzom tools, ensure you're in
**agent mode** (not chat mode). Pull routing only fires where the model can call tools.

## GitHub Copilot not calling Chuzom tools

1. Ensure VS Code ≥ 1.99 (agent mode required).
2. Switch Copilot Chat to **Agent** mode (not "Ask" or "Edit").
3. Verify `.github/copilot-instructions.md` and `.vscode/mcp.json` exist:
   ```bash
   chuzom-install-hooks ide
   ls .vscode/mcp.json
   ls .github/copilot-instructions.md
   ```
4. Restart VS Code — MCP servers load on startup.

## `chuzom doctor` — what it checks

```bash
chuzom doctor
```

Verifies and reports on hook registration in `~/.claude/settings.json`, Python
interpreter path validity (warns if stale venv), Ollama reachability and installed
models, API key presence (Gemini, OpenAI, Perplexity, Anthropic), `~/.chuzom/`
initialization, and provider health (live ping to each configured provider). If a check
fails, `doctor` prints a specific fix command.

---

## Windows-specific setup

**Installation:**

```powershell
pip install chuzom-router
chuzom --version
```

If `chuzom` isn't found after install, add Python's Scripts directory to PATH:

```powershell
pip show chuzom-router                                 # find where pip installed it
$env:PATH += ";$env:APPDATA\Python\Python311\Scripts"  # add in current session
# Or permanently via System Properties → Advanced → Environment Variables
```

**Config file paths (Windows):**

- Claude Desktop: `%APPDATA%\Claude\claude_desktop_config.json`
- VS Code / Copilot MCP: `%APPDATA%\Code\User\mcp.json`

**Environment variables (permanent, any privilege level):**

```powershell
[System.Environment]::SetEnvironmentVariable("OLLAMA_BASE_URL","http://localhost:11434","User")
[System.Environment]::SetEnvironmentVariable("GEMINI_API_KEY","your-key","User")
```

Or add to your PowerShell profile (`$PROFILE`):

```powershell
$env:GEMINI_API_KEY = "your-key"
$env:CHUZOM_CLAUDE_SUBSCRIPTION = "true"
```

**Ollama on Windows:** download from [ollama.com](https://ollama.com) — the installer
sets up the service automatically. Chuzom auto-discovers it at `http://localhost:11434`.

**Hooks on Windows:**

```powershell
chuzom install
# If Git Bash / WSL is not available, the status-bar script is skipped automatically
# (requires bash). All routing hooks install normally.
```
