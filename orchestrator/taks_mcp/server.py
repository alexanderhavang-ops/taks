"""Independent TAKS business MCP server; DevOps tools are never imported."""
import os
from mcp.server.fastmcp import FastMCP
from taks_mcp.business import register_taks_tools

mcp = FastMCP("TAKS Business", host=os.environ.get("TAKS_MCP_HOST", "127.0.0.1"),
              port=int(os.environ.get("TAKS_MCP_PORT", "8766")),
              stateless_http=True, json_response=True)
register_taks_tools(mcp)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
