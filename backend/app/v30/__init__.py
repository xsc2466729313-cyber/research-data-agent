"""V3.0 旁路智能层：科研助手入口，不进入医学数据处理主链。"""

from backend.app.v30.api import mount_v30_routes

__all__ = ["mount_v30_routes"]
