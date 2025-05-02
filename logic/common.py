"""Общие функции для контроллеров"""
from typing import Dict


def get_minmax(data: Dict[int, int]):
    """Возвращает минимальное и максимальное из списка значений словаря"""
    return (
        data.get(-1 if len(data) == 0 else min(data, key=data.get), 0),
        data.get(-1 if len(data) == 0 else max(data, key=data.get), 0),
    )
