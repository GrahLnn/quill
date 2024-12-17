def get(data, path: str):
    """从嵌套数据中根据路径获取字段值"""
    keys = path.split(".")
    for key in keys:
        if isinstance(data, dict) and key in data:
            data = data[key]
        elif isinstance(data, list):
            try:
                index = int(key)
                data = data[index] if abs(index) < len(data) else None
            except ValueError:
                return None
        else:
            return None
    return data
