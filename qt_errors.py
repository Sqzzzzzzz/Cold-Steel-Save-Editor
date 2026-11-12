"""Localized messages from the Cold Steel I preview controller."""

import re


RU = {
    "Choose a .csv file for inventory export.": "Для экспорта инвентаря выберите файл .csv.",
    "Open a compatible save first": "Сначала загрузите учебный инвентарь.",
    "No save loaded": "Учебный инвентарь не загружен.",
    "Game directory not found": "Папка игры не найдена.",
    "No readable item tables found": "Выберите папку Cold Steel I с таблицей data/text/dat_us/t_item.tbl.",
    "Select an original English catalog. This file contains Russian or another language.":
        "Выберите оригинальную английскую таблицу предметов Cold Steel I.",
    "Expected a Cold Steel I t_item.tbl.": "Ожидается таблица предметов t_item.tbl из Cold Steel I.",
    "Invalid Cold Steel I item table.": "Таблица предметов Cold Steel I повреждена.",
    "Invalid t_item.tbl size.": "Некорректный размер таблицы t_item.tbl.",
    "This item cannot be edited.": "Этот предмет недоступен для редактирования.",
    "Unable to save preferences.": "Не удалось сохранить настройки.",
}


def error_text(error, language: str) -> str:
    message = str(error)
    if language != "ru":
        return message
    limit = re.fullmatch(r"Quantity must be between 0 and (\d+)\.", message)
    if limit:
        return f"Количество должно быть от 0 до {limit[1]}."
    if isinstance(error, FileExistsError):
        return "Файл уже существует. Выберите другое имя."
    return RU.get(message, message)
