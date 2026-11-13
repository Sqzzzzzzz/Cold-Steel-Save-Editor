"""Categories used by the Cold Steel I catalog and inventory."""
from __future__ import annotations
from collections import OrderedDict

# Ordered display groups and subcategories. Entries are stable internal identifiers.
GROUPS = OrderedDict([
    ('quartz', ('Кварцы', [('quartz_normal','Обычные кварцы'),('quartz_master','Мастер-кварцы')])),
    ('equipment', ('Снаряжение', [('weapon','Оружие'),('armor','Броня'),('shoes','Обувь'),('accessory','Аксессуары')])),
    ('consumables', ('Расходники и еда', [('consumable','Лечение и бой'),('food','Готовые блюда'),('ingredient','Ингредиенты')])),
    ('library', ('Книги и рецепты', [('recipe','Рецепты'),('book','Книги и журналы')])),
    ('cosmetics', ('Внешний вид', [('costume','Костюмы'),('face','Аксессуары образа'),('decoration','Корпуса АРКУСа')])),
    ('fishing', ('Рыбалка', [('fish','Рыба'),('fishing_gear','Удочки и снасти'),('fish_book','Журналы рыбалки')])),
    ('special', ('Другие предметы', [('quest','Ключевые предметы'),('material','Материалы и сепит'),('card','Предметы мини-игр'),('orbment','Сюжетные сферы'),('dlc_pack','Наборы дополнений'),('other','Прочее')])),
])

CATEGORY_TO_GROUP = {
    cat: group for group, (_, subcategories) in GROUPS.items()
    for cat, _ in subcategories
}
CATEGORY_NAMES = {
    cat: label for _, (_, subcategories) in GROUPS.items()
    for cat, label in subcategories
}

def category_of(item: dict) -> str:
    category = item.get('category')
    if category in CATEGORY_TO_GROUP:
        return category
    return 'quartz_normal' if item.get('kind') == 'quartz' else 'other'


def item_in_category(item: dict, filter_id: str) -> bool:
    if filter_id == 'all':
        return True
    category = category_of(item)
    return (category == filter_id or CATEGORY_TO_GROUP[category] == filter_id)
