"""Read-only review of every pending save change, independent of UI filters."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from qt_hud_widgets import HudButton, hud_icon


class ChangesDialog(QDialog):
    def __init__(self,window,save_mode=None):
        super().__init__(window)
        self.setObjectName('changesDialog');self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True);self.setWindowTitle(window.msg('Просмотр изменений','Review changes'))
        self.setModal(True);self.resize(860,520);self.setMinimumSize(650,380)
        self.setStyleSheet(window.styleSheet())
        self.window_editor=window
        t=window.msg;window.edit_changes.refresh(window.core.save)
        source = window.core.source
        data=window.edit_changes;counts=data.counts()
        layout=QVBoxLayout(self);layout.setContentsMargins(22,20,22,18);layout.setSpacing(12)
        self.heading=QLabel(t('ИЗМЕНЕНИЯ ПЕРЕД ЗАПИСЬЮ','CHANGES BEFORE SAVING'))
        self.heading.setObjectName('reviewHeading');layout.addWidget(self.heading)
        self.summary=QLabel(t(
            f'Добавлено: {counts["added"]}   ·   Удалено: {counts["removed"]}   ·   Изменено: {counts["modified"]}',
            f'Added: {counts["added"]}   ·   Removed: {counts["removed"]}   ·   Modified: {counts["modified"]}'))
        layout.addWidget(self.summary)
        if save_mode:
            action=t('Сохранение отдельной копии','Save a separate copy') if save_mode=='copy' else t('Перезапись с резервной копией','Overwrite with a backup')
            self.destination=QLabel(action+' · '+(source.name if source else t('Предпросмотр','Preview')))
            if source:
                self.destination.setToolTip(str(source))
            self.destination.setObjectName('reviewDestination');layout.addWidget(self.destination)
        self.table=QTableWidget(len(data.changes),5);self.table.setObjectName('reviewTable')
        original_label = t('В файле','In file') if source else t('В образце','Original sample')
        self.table.setHorizontalHeaderLabels([t('Предмет','Item'),'ID',original_label,t('После правки','After editing'),t('Действие','Action')])
        self.table.verticalHeader().hide();self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setIconSize(QSize(28,28));self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setShowGrid(False);self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for col,width in [(1,65),(2,85),(3,125),(4,110)]:self.table.setColumnWidth(col,width)
        for row,change in enumerate(data.changes.values()):
            name=window.core.item_name(change.item_id)
            item=QTableWidgetItem(name);item.setToolTip(name)
            item.setData(Qt.ItemDataRole.UserRole,change.item_id)
            item.setIcon(window._icon(change.item_id))
            self.table.setItem(row,0,item)
            action={'added':t('Добавление','Add'),'removed':t('Удаление','Remove'),'modified':t('Количество','Quantity')}[change.kind]
            for col,text in enumerate((str(change.item_id),str(change.before),str(change.after),action),1):
                cell=QTableWidgetItem(text);cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col in (3,4):cell.setForeground(QColor('#F5A8B5') if change.kind=='removed' else QColor('#F0DDE0'))
                self.table.setItem(row,col,cell)
        layout.addWidget(self.table,1)
        if not data.changes:note=t('Несохранённых изменений нет.','No unsaved changes.')
        else:note=t('Показаны все правки, включая предметы за пределами текущего фильтра.','All changes are shown, including items outside the current filter.')
        if save_mode and source is None:
            note += '\n' + t('Запись игровых файлов недоступна в учебном режиме.',
                              'Writing game files is unavailable in sample mode.')
        elif save_mode == 'overwrite':
            note += '\n' + t('Перед записью рядом с файлом будет создана резервная копия .bak.',
                              'A .bak backup will be created next to the file before writing.')
        if window.has_pending_quantity():
            note+='\n'+t(f'Новое количество для предмета «{window.core.item_name(window.active_item_id)}» ещё не применено.',
                         f'The typed quantity for “{window.core.item_name(window.active_item_id)}” has not been applied.')
        self.note=QLabel(note);self.note.setWordWrap(True);self.note.setObjectName('reviewNote');layout.addWidget(self.note)
        buttons=QHBoxLayout();buttons.addStretch(1)
        self.back=HudButton(t('Вернуться','Back'));self.back.setFixedSize(150,46)
        self.back.clicked.connect(self.reject);buttons.addWidget(self.back)
        self.proceed=None
        if save_mode:
            self.proceed=HudButton(t('Сохранить копию…','Save a copy…') if save_mode=='copy' else t('Записать с резервной копией','Save with a backup'))
            self.proceed.setProperty('role','primary');self.proceed.setIcon(hud_icon('check'))
            self.proceed.setFixedSize(240,46)
            self.proceed.setEnabled(bool(source and (save_mode == 'copy' or source.suffix.lower() == '.dat')))
            self.proceed.clicked.connect(self.accept)
            buttons.addWidget(self.proceed)
        layout.addLayout(buttons)
