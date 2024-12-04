from pathlib import Path
from typing import Dict, List


def read_netscape_cookies(cookie_path: str | Path) -> List[Dict]:
    """读取 Netscape 格式的 cookie 文件

    Args:
        cookie_path: cookie 文件路径

    Returns:
        List[Dict]: cookie 列表
    """
    cookies = []
    with open(cookie_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                fields = line.strip().split("\t")
                if len(fields) >= 7:
                    cookie = {
                        "domain": fields[0],
                        "name": fields[5],
                        "value": fields[6],
                        "path": fields[2],
                        "expires": float(fields[4]) if fields[4].isdigit() else 0,
                        "secure": "TRUE" in fields[3],
                        "httpOnly": False,
                        "sameSite": "Lax",
                    }
                    cookies.append(cookie)
    return cookies


def get_cookie_value(cookies: List[Dict], name: str) -> str:
    """从 cookie 列表中获取指定名称的 cookie 值

    Args:
        cookies: cookie 列表
        name: cookie 名称

    Returns:
        str: cookie 值
    """
    for cookie in cookies:
        if cookie["name"] == name:
            return cookie["value"]
    return ""
