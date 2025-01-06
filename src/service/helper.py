from typing import Dict, List, Union

from returns.result import Success


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


def remove_none_values(
    data: Union[Dict, List, str, int],
) -> Success[Union[Dict, List, str, int]]:
    """
    递归移除值为 None 的键值对，返回 Success 包裹的清洗后结果。
    """
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                nested = remove_none_values(v).unwrap()
                if nested:
                    cleaned[k] = nested
            elif v is not None:
                cleaned[k] = v
        return Success(cleaned)
    elif isinstance(data, list):
        cleaned_list = [
            remove_none_values(item).unwrap() for item in data if item is not None
        ]
        return Success(cleaned_list)
    else:
        return Success(data)
