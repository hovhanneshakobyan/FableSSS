"""MCP server exposing the corpus to every teammate's Claude Code.

Why this exists: during the build, all 5 of us can ask our own agent
"how many reviews mention X?" and get a real answer instead of the agent
writing a throwaway script and re-reading 7MB of JSON. That is the cost saving.

Run:      python3 mcp_server.py
Register: claude mcp add silent-stakeholder -- python3 /ABS/PATH/mcp_server.py
"""
from mcp.server.fastmcp import FastMCP
import tools

mcp = FastMCP("silent-stakeholder")

mcp.tool()(tools.search_reviews)
mcp.tool()(tools.search_issues)
mcp.tool()(tools.polarity)
mcp.tool()(tools.bridge)
mcp.tool()(tools.get_review)
mcp.tool()(tools.get_issue)
mcp.tool()(tools.resolution_lag)

if __name__ == "__main__":
    mcp.run()
