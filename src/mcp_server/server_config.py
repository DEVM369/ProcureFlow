import os
from urllib.parse import urlsplit

# This local application is not configured for production ERP use.
# Never let the optional live FastMCP tools point at a production ERP.
JAVA_API_BASE_URL = os.environ["PROCUREFLOW_JAVA_API_BASE_URL"]
_target = urlsplit(JAVA_API_BASE_URL)
if (_target.scheme != "http" or _target.hostname != "127.0.0.1"
        or _target.port != 18881 or _target.path.rstrip("/") != "/api"
        or _target.username or _target.password or _target.query or _target.fragment):
    raise RuntimeError("Local MCP adapter only permits http://127.0.0.1:18881/api")

# MCP 服务监听配置
MCP_HOST = "127.0.0.1"
# Keep the local MCP port distinct from common application service ports.
# An opt-in adapter is bound to a separate port by default.
MCP_PORT = int(os.environ.get("PROCUREFLOW_MCP_PORT", "18880"))
if MCP_PORT in (8000, 8001, 18080, 18881) or not 1024 <= MCP_PORT <= 65535:
    raise RuntimeError("Choose an unused demo MCP port, normally 18880")
MCP_PATH = "/mcp"
