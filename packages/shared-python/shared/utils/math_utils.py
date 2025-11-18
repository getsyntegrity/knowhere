"""
数学工具函数
这些函数被多个服务使用，保留在 shared-python 中
"""


def min_max_normalize(value, min_val, max_val):
    """
    最小-最大归一化
    
    Args:
        value: 待归一化的值
        min_val: 最小值
        max_val: 最大值
    
    Returns:
        归一化后的值（范围 [0, 1]）
    """
    if max_val == min_val:
        return 0  # Avoid division by zero
    normalized = (value - min_val) / (max_val - min_val)
    return max(0, min(1, normalized))  # Clip to [0, 1]

