"""Two non-blocking first-launch steps, driven by the editor's real state."""
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QProgressBar, QSizePolicy, QLayout,
)
from qt_hud_widgets import GlassPanel, HudButton, hud_icon, ElideLabel


class FirstLaunchPage(QScrollArea):
    find_game=Signal()
    choose_game=Signal()
    open_save=Signal()
    browse=Signal()

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('firstLaunchScroller');self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)
        self.inner=QWidget();self.inner.setObjectName('firstLaunchInner')
        self.setWidget(self.inner);self.inner.setAutoFillBackground(False)
        self.inner.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        outer=QVBoxLayout(self.inner);outer.setContentsMargins(28,10,28,10);outer.setSpacing(0)
        outer.addStretch(1)
        self.content=QWidget();self.content.setObjectName('firstLaunchContent');self.content.setMaximumWidth(1030)
        layout=QVBoxLayout(self.content);layout.setContentsMargins(0,0,0,0);layout.setSpacing(14)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.kicker=QLabel();self.kicker.setObjectName('setupKicker');layout.addWidget(self.kicker)
        self.heading=QLabel();self.heading.setObjectName('setupHeading');self.heading.setWordWrap(True)
        layout.addWidget(self.heading)
        self.intro=QLabel();self.intro.setObjectName('setupIntro');self.intro.setWordWrap(True);layout.addWidget(self.intro)
        cards=QHBoxLayout();cards.setSpacing(16)
        self.catalog_card=GlassPanel(kind='dark');self.save_card=GlassPanel(kind='dark')
        for card in (self.catalog_card,self.save_card):
            card.setMinimumHeight(232)
            card.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        cards.addWidget(self.catalog_card,1);cards.addWidget(self.save_card,1);layout.addLayout(cards)
        left=QVBoxLayout(self.catalog_card);left.setContentsMargins(20,17,20,18);left.setSpacing(9)
        right=QVBoxLayout(self.save_card);right.setContentsMargins(20,17,20,18);right.setSpacing(9)
        self.catalog_title=self._step_title(left,'01','catalog')
        self.save_title=self._step_title(right,'02','open')
        self.catalog_text=QLabel();self.catalog_text.setWordWrap(True);self.catalog_text.setObjectName('setupCardText')
        self.save_text=QLabel();self.save_text.setWordWrap(True);self.save_text.setObjectName('setupCardText')
        left.addWidget(self.catalog_text);right.addWidget(self.save_text)
        self.catalog_status=QLabel();self.catalog_status.setObjectName('setupStatus');self.catalog_status.setWordWrap(True)
        self.save_status=ElideLabel();self.save_status.setObjectName('setupStatus')
        self.save_status.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        left.addWidget(self.catalog_status);right.addWidget(self.save_status)
        self.progress=QProgressBar();self.progress.setObjectName('setupProgress')
        self.progress.setRange(0,0);self.progress.setTextVisible(False);self.progress.setFixedHeight(8)
        left.addWidget(self.progress);self.progress.hide()
        left.addStretch(1);right.addStretch(1)
        actions=QHBoxLayout();actions.setSpacing(8)
        self.auto_button=HudButton();self.auto_button.setProperty('role','primary')
        self.folder_button=HudButton();self.open_button=HudButton();self.open_button.setProperty('role','primary')
        self.open_button.setIcon(hud_icon('open',36));self.open_button.setIconSize(QSize(28,28))
        for button in (self.auto_button,self.folder_button,self.open_button):button.setFixedHeight(47)
        self.auto_button.clicked.connect(self.find_game.emit);self.folder_button.clicked.connect(self.choose_game.emit)
        self.open_button.clicked.connect(self.open_save.emit)
        actions.addWidget(self.auto_button,1);actions.addWidget(self.folder_button,1)
        left.addLayout(actions);right.addWidget(self.open_button)
        foot=QHBoxLayout();foot.setSpacing(12)
        self.later=QLabel();self.later.setObjectName('setupLater');self.later.setWordWrap(True)
        foot.addWidget(self.later,1)
        self.browse_button=HudButton();self.browse_button.setFixedSize(216,43)
        self.browse_button.clicked.connect(self.browse.emit);foot.addWidget(self.browse_button)
        layout.addLayout(foot)
        outer.addWidget(self.content,0,Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)

    def resizeEvent(self,event):
        super().resizeEvent(event);self._fit_content()

    def _fit_content(self):
        if not hasattr(self,'content'):return
        width=min(1030,max(300,self.viewport().width()-56))
        self.content.setFixedWidth(width)
        layout=self.content.layout();layout.invalidate()
        height=max(layout.minimumSize().height(),layout.heightForWidth(width))
        self.content.setFixedHeight(height)
        layout.activate();self.content.updateGeometry()

    def _step_title(self,layout,number,kind):
        row=QHBoxLayout();row.setSpacing(10)
        badge=QLabel(number);badge.setObjectName('setupStep');badge.setFixedSize(33,31)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter);row.addWidget(badge)
        icon=QLabel();icon.setPixmap(hud_icon(kind,36).pixmap(30,30));icon.setFixedSize(31,31);row.addWidget(icon)
        title=QLabel();title.setObjectName('setupCardTitle');row.addWidget(title,1)
        layout.addLayout(row);return title

    def render_state(self,*,language,catalog_count,demo=True,save_name='',busy=False,stage='',error='',error_details='',warning_count=0):
        t=lambda ru,en:ru if language=='ru' else en
        self.kicker.setText(t('ПЕРВЫЙ ЗАПУСК · COLD STEEL I','GETTING STARTED · COLD STEEL I'))
        self.heading.setText(t('Начнём с двух шагов','Two steps to get started'))
        self.intro.setText(t('Загрузите каталог предметов и откройте учебный инвентарь.',
                             'Load the item catalog, then open the sample inventory.') if demo else
                           t('Загрузите каталог предметов и откройте сохранение Cold Steel I.',
                             'Load the item catalog, then open a Cold Steel I save.'))
        self.catalog_title.setText(t('Каталог предметов','Item catalog'))
        self.save_title.setText(t('Учебный инвентарь','Sample inventory') if demo else t('Сохранение Steam','Steam save'))
        self.catalog_text.setText(t('Названия и описания будут прочитаны из установленной игры.',
                                    'Item names and descriptions are read from your installed game.'))
        self.save_text.setText(t('Образец использует предметы из установленной игры. Правки хранятся в памяти.',
                                 'The sample uses items from your installed game. Edits are kept in memory.') if demo else
                               t('Выберите слот .dat. При перезаписи редактор сохранит резервную копию рядом с файлом.',
                                 'Select a .dat slot. The editor creates a backup next to the file before overwriting it.'))
        if busy:
            message=t('Ищем установленную игру…','Locating your installed game…')
            if stage=='reading':message=t('Читаем таблицу предметов Cold Steel I…','Reading the Cold Steel I item table…')
            elif stage=='saving':message=t('Подготавливаем каталог…','Preparing the catalog…')
            state='busy'
        elif catalog_count:
            message=t(f'Каталог загружен · Предметов: {catalog_count}',f'Catalog ready · Items: {catalog_count}')
            state='ready'
            if warning_count:
                message+=t(f'\nНекоторые таблицы пропущены: {warning_count}',f'\nSome tables were skipped: {warning_count}')
                state='warning'
            if error:message+=t('\nНовое сканирование не завершено. Используется загруженный каталог.',
                                '\nThe new scan did not finish. Your existing catalog is available.')
        elif error=='not_found':
            message=t('Автопоиск не нашёл игру. Выберите её папку вручную.',
                       'The game was not found automatically. Choose its folder.')
            state='error'
        elif error:
            message=t('Каталог не удалось прочитать. Выберите корневую папку игры с каталогом data.',
                       'The catalog could not be read. Choose the game folder containing data.')
            state='error'
        else:
            message=t('Папка игры пока не выбрана','Choose your game folder to begin')
            state='waiting'
        self.catalog_status.setText(message);self.catalog_status.setToolTip(error_details or message)
        if self.catalog_status.property('state')!=state:
            self.catalog_status.setProperty('state',state)
            self.catalog_status.style().unpolish(self.catalog_status);self.catalog_status.style().polish(self.catalog_status)
        self.progress.setVisible(busy)
        self.auto_button.setText(t('Найти игру автоматически','Find game automatically'))
        self.folder_button.setText(t('Выбрать папку игры','Choose game folder'))
        self.folder_button.setToolTip(t('Выберите папку Cold Steel I, в которой находится каталог data.',
                                       'Choose the Cold Steel I folder containing the data directory.'))
        self.auto_button.setEnabled(not busy);self.folder_button.setEnabled(not busy)
        roles=[(self.auto_button,'primary' if not catalog_count and not error else 'normal'),
               (self.folder_button,'primary' if error and not catalog_count else 'normal'),
               (self.open_button,'normal' if save_name else 'primary'),
               (self.browse_button,'primary' if catalog_count and save_name and not busy else 'normal')]
        for button,role in roles:
            if button.property('role')!=role:button.setProperty('role',role);button.update()
        if demo:
            self.open_button.setText(t('Заново загрузить образец','Reload sample') if save_name else t('Открыть образец','Open sample'))
        else:
            self.open_button.setText(t('Выбрать другое сохранение','Choose another save') if save_name else
                                     t('Открыть сохранение','Open save'))
        self.open_button.setEnabled(bool(catalog_count) and not busy)
        if save_name:self.save_status.setText(t('Открыто: ','Opened: ')+save_name)
        elif busy:self.save_status.setText(t('Дождитесь загрузки каталога','Waiting for the catalog'))
        elif catalog_count:self.save_status.setText(t('Готово — можно открыть образец','Ready to open the sample') if demo else
                                                    t('Каталог готов к открытию слота','Ready to open a save'))
        else:self.save_status.setText(t('Сначала загрузите каталог','Load the catalog first'))
        self.browse_button.setText(t('Открыть редактор','Open the editor'))
        self.later.setText(t('На этом этапе можно проверить интерфейс и редактирование образца.',
                             'Use this preview to test the interface and edit the sample.') if demo else
                           t('F5 открывает последнее совместимое сохранение.','F5 opens the latest compatible save.'))
        self._fit_content()
