# Open Source Leverage Strategy

When building brokerage or portfolio analysis capabilities:

1. **Always survey first** — Check for mature open source clients and MCP servers before writing new code.
2. **Preferred projects (as of 2026-05)**:
   - `jkoelker/schwab-mcp` + its `schwab-py` fork (strong transaction + position support, already MCP-ready)
   - `tylerebowers/Schwabdev` (clean, popular, lightweight)
3. **Decision rule**: If an existing project already solves authentication, transactions, or MCP exposure well, extend or contribute to it rather than building a parallel implementation.

This approach was validated during the initial portfolio-analysis skill development.