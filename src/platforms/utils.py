from pathlib import Path
from typing import Dict, List


def read_netscape_cookies(cookie_path: str | Path) -> Dict[str, str]:
    """读取 Netscape 格式的 cookie 文件，转换为简单的key-value字典

    Args:
        cookie_path: cookie 文件路径

    Returns:
        Dict[str, str]: cookie字典，key为cookie名称，value为cookie值
    """
    cookies = {}
    with open(cookie_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                fields = line.strip().split("\t")
                if len(fields) >= 7:
                    cookies[fields[5]] = fields[6]
    return cookies


def get_cookie_value(cookies: Dict[str, str], name: str) -> str:
    """从cookie字典中获取指定名称的cookie值

    Args:
        cookies: cookie字典
        name: cookie名称

    Returns:
        str: cookie值
    """
    return cookies.get(name, "")
