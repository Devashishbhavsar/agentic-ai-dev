# Enterprise Agent — Claude Code Instructions

## Project
Multi-agent enterprise BI → Software Delivery platform.
FastAPI on port 8000, OpenClaw gateway on 18789, Discord bot via MCP.

## Skills (installed in .agents/skills/)

Always apply these skills when relevant:

| Skill | When to use |
|-------|------------|
| `systematic-debugging` | Any time an agent, test, or pipeline fails |
| `verification-before-completion` | Before marking any pipeline step "success" |
| `test-driven-development` | Adding new agents or pipeline steps |
| `dispatching-parallel-agents` | Designing new swarm phases |
| `writing-plans` | Before implementing multi-file changes |
| `webapp-testing` | Testing FastAPI endpoints |
| `xlsx` / `pdf` | Exporting BI pipeline results |
| `mcp-builder` | Adding new MCP tools |

## Architecture layers
```
L1  api/gateway.py          FastAPI REST entry point
L2  core/orchestrator.py    Intent classification + pipeline routing
L3  core/swarm.py           Parallel agent execution (ThreadPoolExecutor)
L4  agents/*/               35 Hermes agents across 7 swarms
L5  core/model_router.py    LLM routing via OpenRouter
L6  core/memory/            Session + semantic cache
L7  data/connectors/        Postgres, Snowflake, BigQuery, CSV, DuckDB
L8  data/unified_layer.py   Single query interface
L9  pipelines/bi_pipeline.py       5-phase parallel BI pipeline
L10 pipelines/sw_delivery_pipeline.py  5-phase parallel SW pipeline
L11 mcp_server.py           OpenClaw/Discord MCP bridge
```

## Key rules

- Model tiers are loaded from `config/settings.yaml` and route through OpenRouter with provider-prefixed IDs. Planning: `anthropic/claude-opus-4`, balanced/code: `anthropic/claude-sonnet-4-5` or `openai/gpt-4.1`, fast: `anthropic/claude-haiku-4-5`, long-context: `google/gemini-2.5-pro`, cost-optimized: `deepseek/deepseek-chat`. `max_tokens=512` for agents, `700` for JSON.
- All parallel phases use `ThreadPoolExecutor` — max 2 concurrent API calls (semaphore in ModelRouter).
- Agent results always return `AgentResult` with `status`, `results` dict, `confidence_score`.
- Cache lives in `data/cache/` (SHA256-keyed, 24h TTL).
- Systemd user services: `enterprise-agent` and `openclaw-gateway`.
- OPENROUTER_API_KEY in `.env` — never hard-code.

## Common commands
```bash
systemctl --user status enterprise-agent     # check service
systemctl --user restart enterprise-agent    # restart after code change
curl http://localhost:8000/v1/health         # verify API
```
