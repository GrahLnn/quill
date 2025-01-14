import random
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


def random_insert_substring(input_string, times=1):
    result = input_string
    for _ in range(times):
        length = len(result)
        if not result or length < 20:
            break

        # 计算连续 20% 的长度
        segment_length = max(1, length // 20)  # 至少取 1 个字符

        # 计算起始位置的上限，确保子串不超过 [5:-5] 范围
        max_start = length - segment_length - 5
        if max_start < 5:
            max_start = 5  # 避免 randint 抛出错误

        # 随机选择起始位置，保证子串在 [5:-5] 范围内
        start_index = random.randint(5, max_start)
        end_index = start_index + segment_length

        # 提取子串
        substring = result[start_index:end_index]

        # 从原字符串中移除子串
        remaining_string = result[:start_index] + result[end_index:]

        # 随机选择插入位置
        insert_index = random.randint(0, len(remaining_string))

        # 插入子串到新位置
        result = remaining_string[:insert_index] + substring + remaining_string[insert_index:]

    return result
