"""MCP stdio server skeleton for Schwab portfolio tools.

Implements basic MCP protocol over stdio for native-mcp integration.
Exposes tools: authenticate, get_accounts, get_transactions, etc.
Ready for extension with analysis tools.
"""

import json
import sys
from typing import Any, Dict, List

from .auth import SchwabAuth, SchwabAuthError
from .client import SchwabClient


class SchwabMCPServer:
    """Minimal MCP server exposing Schwab capabilities over stdio."""

    def __init__(self):
        self.auth = SchwabAuth()
        self.client = SchwabClient(self.auth)
        self.tools = {
            "schwab_auth_start": self._tool_auth_start,
            "schwab_auth_complete": self._tool_auth_complete,
            "schwab_get_accounts": self._tool_get_accounts,
            "schwab_get_transactions": self._tool_get_transactions,
            "schwab_get_account_numbers": self._tool_get_account_numbers,
        }

    def _send(self, message: Dict[str, Any]) -> None:
        """Send JSON-RPC response."""
        sys.stdout.write(json.dumps(message) + "\n")
        sys.stdout.flush()

    def _error(self, request_id: Any, code: int, message: str) -> None:
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": code, "message": message},
            }
        )

    def _result(self, request_id: Any, result: Any) -> None:
        self._send({"jsonrpc": "2.0", "id": request_id, "result": result})

    # Tool implementations
    def _tool_auth_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            url, verifier = self.auth.get_authorization_url()
            # Store verifier temporarily (in real impl use session/state)
            return {"authorization_url": url, "code_verifier": verifier}
        except Exception as e:
            raise SchwabAuthError(str(e))

    def _tool_auth_complete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        code = params.get("code")
        verifier = params.get("code_verifier")
        if not code or not verifier:
            raise ValueError("Missing code or code_verifier")
        tokens = self.auth.exchange_code_for_tokens(code, verifier)
        return {"status": "authenticated", "expires_in": tokens.get("expires_in")}

    def _tool_get_accounts(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        include_positions = params.get("include_positions", True)
        return self.client.get_accounts(include_positions=include_positions)

    def _tool_get_transactions(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        account_hash = params["account_hash"]
        return self.client.get_transactions(
            account_hash,
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
            limit=params.get("limit", 50),
        )

    def _tool_get_account_numbers(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        return self.client.get_account_numbers()

    def handle_request(self, request: Dict[str, Any]) -> None:
        """Process one JSON-RPC request."""
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if method == "initialize":
            self._result(
                req_id,
                {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "schwab-mcp", "version": "0.1.0"},
                    "capabilities": {"tools": {"listChanged": False}},
                },
            )
            return

        if method == "tools/list":
            tools = [
                {
                    "name": name,
                    "description": f"Schwab {name.split('_')[-1]}",
                    "inputSchema": {},
                }
                for name in self.tools
            ]
            self._result(req_id, {"tools": tools})
            return

        if method == "tools/call":
            tool_name = params.get("name")
            tool_params = params.get("arguments", {})
            if tool_name not in self.tools:
                self._error(req_id, -32601, f"Unknown tool: {tool_name}")
                return
            try:
                result = self.tools[tool_name](tool_params)
                self._result(
                    req_id, {"content": [{"type": "text", "text": json.dumps(result)}]}
                )
            except Exception as e:
                self._error(req_id, -32603, str(e))
            return

        self._error(req_id, -32601, f"Method not found: {method}")

    def run(self) -> None:
        """Main stdio loop."""
        for line in sys.stdin:
            try:
                request = json.loads(line.strip())
                self.handle_request(request)
            except json.JSONDecodeError:
                self._error(None, -32700, "Parse error")
            except Exception as e:
                self._error(None, -32603, str(e))


def main():
    """Entry point for MCP server."""
    server = SchwabMCPServer()
    server.run()


if __name__ == "__main__":
    main()
