"""Cold Steel I Qt window, separated from the save engine.

All widgets are real Qt controls. Background/glow effects are painted on panels;
mouse movement never causes catalog re-population or wallpaper rescaling.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize, QRectF, QRect, QPoint, QPointF, Signal, Slot, QObject, QThread, QSignalBlocker
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics, QPolygonF, QPixmap, QIcon, QPainterPath, QLinearGradient, QBrush, QRadialGradient
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QLineEdit,
    QSpinBox, QComboBox, QCheckBox, QTreeWidget, QTreeWidgetItem, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QHBoxLayout, QVBoxLayout,
    QGridLayout, QStackedWidget, QMessageBox, QFileDialog, QScrollArea,
    QPlainTextEdit, QSizePolicy, QStyle, QStatusBar, QSizeGrip
)

from categories import GROUPS, CATEGORY_NAMES, category_of, item_in_category
from qt_backend import EditorCore, find_game_install, scan_game_tables
from game_art import ASSETS, GameArt
from edit_changes import EditChanges
from qt_first_launch import FirstLaunchPage
from qt_errors import error_text
VERSION = "0.1.0"
APP_NAME = "Cold Steel I Inventory Editor"


from qt_hud_widgets import (hud_icon, HudButton, Backdrop, GlassPanel, AngularTab,
                            HudTableDelegate, HudTitleBar, ItemTitle, ElideLabel)


def glass_label(text='',role='default',font=10):
    lab=QLabel(text)
    lab.setProperty('role',role)
    f=lab.font();f.setPointSize(font)
    lab.setFont(f)
    return lab


def add_button(text,slot=None,role='normal'):
    btn=HudButton(text)
    btn.setProperty('role',role)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setMinimumHeight(44)
    if slot:btn.clicked.connect(lambda _checked=False: slot())
    return btn


class HudSectionHeader(QWidget):
    """Compact angular HUD caption; native Qt painting, fully DPI-scalable."""
    def __init__(self, title='', serial='01', parent=None):
        super().__init__(parent)
        self.caption=title
        self.serial=serial
        self.setFixedHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def setCaption(self, title):
        self.caption=title
        self.update()

    def paintEvent(self, event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        width=self.width();height=self.height()
        if width < 80:
            p.end();return
        edge=QPainterPath()
        edge.moveTo(1,1);edge.lineTo(width-21,1)
        edge.lineTo(width-2,17);edge.lineTo(width-2,height-2)
        edge.lineTo(1,height-2);edge.closeSubpath()
        grad=QLinearGradient(0,0,width,0)
        grad.setColorAt(0,QColor(167,33,45,196))
        grad.setColorAt(.55,QColor(67,54,61,118))
        grad.setColorAt(1,QColor(39,31,36,28))
        p.fillPath(edge,QBrush(grad))
        p.setPen(QPen(QColor(229,118,128,188),1.2))
        p.drawPath(edge)
        p.setPen(QPen(QColor(255,237,240,175),2.4))
        p.drawLine(5,4,66,4)
        p.setFont(QFont('Segoe UI',9,QFont.Weight.Bold))
        p.setPen(QColor('#FFEDF0'))
        p.drawText(QRect(11,5,31,23),Qt.AlignmentFlag.AlignVCenter,self.serial)
        p.setPen(QColor('#F7FCFF'))
        label_area=QRect(46,5,max(8,width-68),23)
        text=p.fontMetrics().elidedText(self.caption,Qt.TextElideMode.ElideRight,label_area.width())
        p.drawText(label_area,Qt.AlignmentFlag.AlignVCenter,text)
        p.end()


class ScanWorker(QObject):
    stage=Signal(str)
    result=Signal(object)
    error=Signal(str)
    finished=Signal()
    def __init__(self,controller,path=None):
        super().__init__();self.preferred_root=controller.settings.get('game_root','');self.path=path
    @Slot()
    def run(self):
        try:
            self.stage.emit('locating')
            root=Path(self.path) if self.path is not None else find_game_install(self.preferred_root)
            if root is None: raise FileNotFoundError('Game directory not found')
            self.stage.emit('reading')
            self.result.emit(scan_game_tables(root))
        except Exception as exc:self.error.emit(str(exc))
        finally:self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self,core=None):
        super().__init__()
        self.core=core if core is not None else EditorCore()
        self.setWindowTitle(f'{APP_NAME} v{VERSION}')
        self.art = GameArt()
        self.setWindowIcon(self.art.menu_icon('inventory'))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.resize(1536,864);self.setMinimumSize(1280,720)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors,True)
        self.active_item_id=None
        self.filter_group='all'
        self.inv_filter_group='all'
        self.sort_keys={'catalog':(1,False),'inventory':(1,False)}
        self.scan_thread=None
        self.scan_worker=None
        self._startup_dismissed=False
        self._startup_forced=False
        self._scan_busy=False
        self._scan_stage=''
        self._scan_error=''
        self._scan_error_details=''
        self._scan_warning_count=0
        self._scan_succeeded=False
        self._scan_started_in_setup=False
        self._scan_silent=False
        self._icon_pixmaps={}
        self._category_icons={}
        self._category_nodes={'catalog':{},'inventory':{}}
        self._table_rows={}
        self._view_catalog=None
        self._view_english=None
        self._view_language=None
        self._visible_catalog={}
        self._search_details={}
        self._row_names={}
        self.edit_changes=EditChanges()
        self.cat_favorites_only=False
        self.inv_favorites_only=False
        self._quantity_user_edited=False
        self.language=self.core.language
        self._qt_setup()
        self.make_ui()
        self.retranslate()
        self.populate_categories()
        self.update_tables()
        self.show_section('catalog')
        self.resize_grip=QSizeGrip(self);self.resize_grip.setFixedSize(16,16)
        self.resize_grip.setToolTip('Потяни для изменения размера / Drag to resize')
        self.initial_load_timer=QTimer(self)
        self.initial_load_timer.setSingleShot(True)
        self.initial_load_timer.timeout.connect(self.initial_load)
        self.initial_load_timer.start(360)

    def _qt_setup(self):
        from qt_hud_theme import HUD_STYLESHEET
        self.setStyleSheet(HUD_STYLESHEET)

    def _toolbar_icons(self):
        """Provide supported Qt icons instead of missing-font square glyphs."""
        icons=(
            (self.btn_latest,'latest'),(self.btn_open,'open'),
            (self.btn_compare,'compare'),(self.btn_overwrite,'backup'),
            (self.btn_savecopy,'save'),
        )
        for btn,kind in icons:
            btn.setIcon(hud_icon(kind,64))
            btn.setIconSize(QSize(31,31))


    def msg(self,ru,en):return ru if self.language=='ru' else en

    def make_ui(self):
        canvas=Backdrop(self);canvas.setObjectName('canvas');self.setCentralWidget(canvas)
        entire=QVBoxLayout(canvas);entire.setContentsMargins(16,0,16,16);entire.setSpacing(0)
        self.header=HudTitleBar();self.header.setObjectName('titleBar');self.header.setFixedHeight(96)
        self.header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        hl=QHBoxLayout(self.header);hl.setContentsMargins(16,8,0,8)
        crest = glass_label()
        crest.setFixedSize(125, 78)
        crest.setAlignment(Qt.AlignmentFlag.AlignCenter)
        crest.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        emblem = QPixmap(str(ASSETS / 'thors.png'))
        if not emblem.isNull():
            crest.setPixmap(emblem.scaled(74, 74, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            crest.setText('THORS')
        crest.setAccessibleName('Thors Military Academy')
        hl.addWidget(crest)
        branding=QVBoxLayout();branding.setSpacing(0)
        self.title=glass_label('Редактор сохранений','title',30)
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.subtitle=glass_label('COLD STEEL I · ИНВЕНТАРЬ','subtitle',12)
        self.subtitle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        branding.addWidget(self.title);branding.addWidget(self.subtitle)
        hl.addLayout(branding,1)
        logo = QPixmap(str(ASSETS / 'logo.png'))
        if not logo.isNull():
            from PySide6.QtGui import QRegion
            visible = QRegion(logo.mask()).boundingRect()
            if not visible.isEmpty():
                logo = logo.copy(visible)
            mark = glass_label()
            mark.setPixmap(logo.scaled(151, 62, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            hl.addWidget(mark)
        controls=QVBoxLayout();controls.setSpacing(6)
        window_controls=QHBoxLayout();window_controls.setSpacing(1)
        self.window_buttons={}
        for symbol,slot in [('minimize',self.showMinimized),('maximize',self.toggle_maximized),('close',self.close)]:
            b=add_button('',slot,'window');b.setProperty('symbol',symbol)
            b.setText({'minimize':'−','maximize':'□','close':'×'}[symbol]);b.setFixedSize(46,30)
            b.setToolTip({'minimize':'Свернуть','maximize':'Развернуть','close':'Закрыть'}[symbol])
            window_controls.addWidget(b)
            self.window_buttons[symbol]=b
        controls.addLayout(window_controls)
        self.lang=QComboBox();self.lang.addItems(['Русский','English']);self.lang.setFixedSize(112,28)
        self.lang.setObjectName('languageSwitch')
        self.lang.setCurrentIndex(1 if self.language=='en' else 0)
        self.lang.currentIndexChanged.connect(lambda _i:self.switch_language())
        controls.addWidget(self.lang,0,Qt.AlignmentFlag.AlignRight)
        hl.addLayout(controls);entire.addWidget(self.header)
        # The toolbar and save path align with the catalog, as in the reference.
        self.actions=QWidget();self.actions.setFixedHeight(112)
        bar=QVBoxLayout(self.actions);bar.setContentsMargins(191,10,16,4);bar.setSpacing(4)
        self.actions_layout=bar
        buttons=QHBoxLayout();buttons.setSpacing(7)
        self.btn_latest=add_button('',lambda:self.load_latest(),'toolbarPrimary')
        self.btn_open=add_button('',self.open_save_dialog,'toolbar')
        self.btn_compare=add_button('',self.compare_dialog,'toolbar')
        self.btn_overwrite=add_button('',self.overwrite_dialog,'toolbar')
        self.btn_savecopy=add_button('',self.save_copy_dialog,'toolbar')
        for btn in (self.btn_latest,self.btn_open,self.btn_compare,self.btn_overwrite,self.btn_savecopy):
            btn.setFixedHeight(64);btn.setMinimumWidth(130)
        for btn in (self.btn_latest,self.btn_open,self.btn_compare):buttons.addWidget(btn)
        buttons.addStretch(1)
        for btn in (self.btn_overwrite,self.btn_savecopy):buttons.addWidget(btn)
        self._toolbar_icons();bar.addLayout(buttons)
        status=QHBoxLayout();status.setContentsMargins(8,0,4,0);status.setSpacing(8)
        self.save_line=ElideLabel();self.save_line.setProperty('role','muted')
        self.save_line.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        status.addWidget(self.save_line,1)
        self.dirty_chip=QLabel('');self.dirty_chip.setObjectName('saveStateChip')
        self.dirty_chip.setAlignment(Qt.AlignmentFlag.AlignCenter);self.dirty_chip.setFixedHeight(23)
        self.review_button=add_button('',self.show_changes,'filter')
        self.review_button.setFixedSize(122,27);self.review_button.hide()
        status.addWidget(self.review_button);status.addWidget(self.dirty_chip);bar.addLayout(status)
        entire.addWidget(self.actions)
        body=QHBoxLayout();body.setSpacing(8)
        rail=GlassPanel(kind='rail');rail.setFixedWidth(195);self.rail_panel=rail
        rl=QVBoxLayout(rail);rl.setContentsMargins(0,14,0,5);rl.setSpacing(1)
        self.rail_header=HudSectionHeader('НАВИГАЦИЯ','00');self.rail_header.hide()
        self.navigation={}
        for key in ('inventory','catalog','tools'):
            b=add_button('',role='nav');b.setCheckable(True);b.setFixedHeight(67)
            b.setIcon(hud_icon(key,38));b.setIconSize(QSize(38,38))
            b.clicked.connect(lambda checked=False,k=key:self.navigate_section(k))
            self.navigation[key]=b;rl.addWidget(b)
        rl.addStretch(1)
        self.rail_file=glass_label('saveXXX.dat','muted',10)
        self.rail_folder=glass_label('','muted',10)
        self.rail_folder.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.rail_date=glass_label('--.--.----','muted',10)
        self.rail_state=glass_label('','muted',10)
        for widget,icon in [(self.rail_file,'save'),(self.rail_folder,'open'),(self.rail_date,'clock'),(self.rail_state,'check')]:
            row=QHBoxLayout();row.setContentsMargins(12,0,0,0);row.setSpacing(10)
            pict=QLabel();pict.setPixmap(hud_icon(icon,22).pixmap(22,22));pict.setFixedSize(23,28)
            row.addWidget(pict);row.addWidget(widget,1);rl.addLayout(row)
        body.addWidget(rail)
        center=QWidget();self.center_shell=center;cl=QVBoxLayout(center)
        cl.setContentsMargins(0,0,0,0);cl.setSpacing(0)
        self.main_header=HudSectionHeader('КАТАЛОГ ПРЕДМЕТОВ','01');self.main_header.hide()
        self.tabs=QWidget();self.tabs.setFixedHeight(51)
        tabs=QHBoxLayout(self.tabs);tabs.setContentsMargins(0,0,0,0);tabs.setSpacing(-1)
        self.tabcat=AngularTab('Каталог предметов');self.tabinv=AngularTab('Мой инвентарь')
        self.tabcat.setFixedWidth(224);self.tabinv.setFixedWidth(202)
        self.tabcat.clicked.connect(lambda _checked=False:self.navigate_section('catalog'))
        self.tabinv.clicked.connect(lambda _checked=False:self.navigate_section('inventory'))
        tabs.addWidget(self.tabcat);tabs.addWidget(self.tabinv);tabs.addStretch(1);cl.addWidget(self.tabs)
        center_panel=GlassPanel();self.center_panel=center_panel
        pl=QVBoxLayout(center_panel);pl.setContentsMargins(14,18,13,16);pl.setSpacing(0)
        self.pages=QStackedWidget();pl.addWidget(self.pages,1);cl.addWidget(center_panel,1)
        self.catpage=self._make_catalog();self.invpage=self._make_inventory();self.toolspage=self._make_tools()
        for page in (self.catpage,self.invpage,self.toolspage):self.pages.addWidget(page)
        self.startup_page=FirstLaunchPage()
        self.startup_page.find_game.connect(lambda:self.scan_game(None))
        self.startup_page.choose_game.connect(self.choose_game)
        self.startup_page.open_save.connect(self.open_save_from_startup)
        self.startup_page.browse.connect(self.dismiss_startup)
        self.pages.addWidget(self.startup_page)
        body.addWidget(center,1)
        self.detail_shell=QWidget();dl=QVBoxLayout(self.detail_shell);dl.setContentsMargins(0,14,0,0);dl.setSpacing(0)
        self.detail=GlassPanel(kind='dark');self.detail.setFixedWidth(410);self._make_detail();dl.addWidget(self.detail,1)
        body.addWidget(self.detail_shell);entire.addLayout(body,1)
        self.footer_row=QWidget();self.footer_row.setObjectName('footerRow');self.footer_row.setFixedHeight(44)
        fl=QHBoxLayout(self.footer_row);fl.setContentsMargins(202,2,4,0);fl.setSpacing(12)
        self.footer=glass_label(f'CS1 v{VERSION}','muted',10)
        self.footer.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.footer_aux=glass_label('','muted',10)
        fl.addWidget(self.footer,1);fl.addWidget(self.footer_aux)
        self.help_button=add_button('',lambda:self.show_report(self.msg('Клавиши и работа с редактором','Editor help'),[
            'F5 — '+self.msg('учебный инвентарь','sample inventory'),
            'Ctrl+O — '+self.msg('диалог открытия','open dialog'),
            'Ctrl+S — '+self.msg('предпросмотр сохранения копии','preview saving a copy'),
            'Ctrl+Z — '+self.msg('отменить изменение','undo edit'),
            'Ctrl+F — '+self.msg('поиск в каталоге','catalog search'),
            self.msg('Правый клик по количеству — 1 / 10 / 50 / 99.','Right-click quantity for 1 / 10 / 50 / 99.'),
        ],count=False),'window')
        self.help_button.setIcon(hud_icon('help'));self.help_button.setFixedSize(32,32)
        self.help_button.setToolTip('Справка');fl.addWidget(self.help_button)
        entire.addWidget(self.footer_row)
        self.search_debounce=QTimer(self);self.search_debounce.setSingleShot(True);self.search_debounce.setInterval(140)
        self.search_debounce.timeout.connect(self.update_tables)
        self.notice=QLabel(canvas);self.notice.setObjectName('toastNotice')
        self.notice.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        self.notice.setWordWrap(True);self.notice.hide()
        self.notice_timer=QTimer(self);self.notice_timer.setSingleShot(True)
        self.notice_timer.timeout.connect(self.notice.hide)
        self._notice_text=None

    def toggle_maximized(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'cat_tree'):self.resizeEvent_as_layout()
        if hasattr(self,'notice') and self.notice.isVisible():self._position_notice()
        if hasattr(self,'resize_grip'):
            self.resize_grip.move(self.width()-18,self.height()-18);self.resize_grip.raise_()

    def _make_categories(self,kind='catalog'):
        tree=QTreeWidget();tree.setHeaderHidden(True);tree.setFixedWidth(240)
        tree.setColumnCount(2)
        # Native Windows styles can otherwise reserve most of a narrow tree for
        # the first section, pushing the count column outside the viewport.
        tree.header().setMinimumSectionSize(24)
        tree.header().setStretchLastSection(False)
        tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        tree.header().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tree.setIndentation(10);tree.setRootIsDecorated(False)
        tree.setUniformRowHeights(False);tree.setIconSize(QSize(24,24))
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tree.itemSelectionChanged.connect(lambda:self.on_category(tree,kind))
        if kind=='catalog':self.cat_tree=tree
        else:self.inv_tree=tree
        return tree

    def _make_table(self,kind):
        headers=['Предмет','ID','Категория','В инвентаре']
        table=QTableWidget(0,4)
        table.setHorizontalHeaderLabels(headers)
        table.setSortingEnabled(False)
        table.verticalHeader().hide()
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for c,w in [(1,64),(2,147 if kind=='catalog' else 65),(3,82)]:
            table.horizontalHeader().setSectionResizeMode(c,QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(c,w)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setAlternatingRowColors(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setDefaultSectionSize(37)
        table.setIconSize(QSize(25,25))
        table.setShowGrid(False)
        table.setItemDelegate(HudTableDelegate(table))
        table.horizontalHeader().setFixedHeight(38)
        table.horizontalHeader().setSortIndicatorShown(True)
        table.horizontalHeader().setSortIndicator(1,Qt.SortOrder.AscendingOrder)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setWordWrap(False)
        table.itemSelectionChanged.connect(lambda:self.selection_changed(table))
        table.horizontalHeader().sectionClicked.connect(lambda col:self.sort_rows(kind,col))
        table.model().layoutChanged.connect(lambda:self._table_rows.pop(kind,None))
        return table

    def _searchbar(self,placeholder):
        inp=QLineEdit();inp.setPlaceholderText(placeholder)
        inp.addAction(hud_icon('search',22),QLineEdit.ActionPosition.LeadingPosition)
        inp.setClearButtonEnabled(True)
        inp.setFixedHeight(37)
        inp.textChanged.connect(lambda _text:self.search_debounce.start())
        return inp

    def _make_catalog(self):
        page=QWidget();row=QHBoxLayout(page);row.setContentsMargins(0,0,0,0);row.setSpacing(10)
        row.addWidget(self._make_categories())
        content=QVBoxLayout();content.setSpacing(5)
        self.cat_search=self._searchbar('Поиск по названию, ID или описанию…')
        search_row=QHBoxLayout();search_row.setSpacing(5);search_row.addWidget(self.cat_search,1)
        self.cat_quick_favorite=add_button('★',lambda:self.toggle_quick_favorites('catalog'),'quick')
        self.cat_quick_favorite.setCheckable(True);self.cat_quick_favorite.setFixedSize(39,37)
        search_row.addWidget(self.cat_quick_favorite);content.addLayout(search_row)
        filters=QHBoxLayout();filters.setSpacing(8)
        self.missing=QCheckBox('Только отсутствующие');self.present=QCheckBox('Только имеющиеся')
        self.missing.toggled.connect(self._only_missing);self.present.toggled.connect(self._only_present)
        filters.addWidget(self.missing);filters.addStretch(1)
        from PySide6.QtWidgets import QMenu
        self.filter_button=add_button('Фильтры ▾',role='filter');self.filter_button.setFixedSize(106,28)
        menu=QMenu(self.filter_button)
        owned=menu.addAction('Только имеющиеся');owned.setCheckable(True)
        self.owned_action=owned
        owned.toggled.connect(self.present.setChecked);self.present.toggled.connect(owned.setChecked)
        self.source=QComboBox();self.source.addItems(['Все источники','Основная игра','DLC']);self.source.hide()
        from PySide6.QtGui import QActionGroup
        source_group=QActionGroup(menu);source_group.setExclusive(True)
        self.source_actions=[]
        menu.addSeparator()
        for index,text in enumerate(['Все источники','Основная игра','DLC']):
            action=menu.addAction(text);action.setCheckable(True);source_group.addAction(action)
            self.source_actions.append(action)
            action.setChecked(index==0);action.triggered.connect(lambda checked=False,i=index:self.source.setCurrentIndex(i))
        self.source.currentIndexChanged.connect(lambda _i:self.update_tables())
        self.filter_button.setMenu(menu);filters.addWidget(self.filter_button);content.addLayout(filters)
        self.catalog_counter=glass_label('','muted',9);self.catalog_counter.setObjectName('catalogCounter');self.catalog_counter.hide()
        self.cat_table=self._make_table('catalog');content.addWidget(self.cat_table,1)
        self.bulk_bar=QWidget();bulk=QHBoxLayout(self.bulk_bar);bulk.setContentsMargins(0,1,0,0);bulk.setSpacing(5)
        self.selection_info=glass_label('Выбрано: 0','muted',10);bulk.addWidget(self.selection_info);bulk.addStretch(1)
        self.add_one=add_button('+1 каждому',lambda:self.apply_bulk(1))
        self.add_bulk=add_button('Добавить выбранные',lambda:self.apply_bulk(),'primary')
        self.add_one.setFixedHeight(39);self.add_bulk.setFixedHeight(39)
        bulk.addWidget(self.add_one);bulk.addWidget(self.add_bulk);self.bulk_bar.hide();content.addWidget(self.bulk_bar)
        row.addLayout(content,1);return page

    def _make_inventory(self):
        page=QWidget();row=QHBoxLayout(page);row.setContentsMargins(0,0,0,0);row.setSpacing(10)
        row.addWidget(self._make_categories('inventory'))
        l=QVBoxLayout();l.setContentsMargins(0,0,0,0);l.setSpacing(5)
        self.inv_search=self._searchbar('Поиск по названию, ID или описанию…')
        search_row=QHBoxLayout();search_row.setSpacing(5);search_row.addWidget(self.inv_search,1)
        self.inv_quick_favorite=add_button('★',lambda:self.toggle_quick_favorites('inventory'),'quick')
        self.inv_quick_favorite.setCheckable(True);self.inv_quick_favorite.setFixedSize(39,37)
        search_row.addWidget(self.inv_quick_favorite);l.addLayout(search_row)
        self.inventory_hint=glass_label('Предметы в загруженном сохранении','muted',10)
        self.inventory_hint.setFixedHeight(30)
        self.inventory_hint.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        l.addWidget(self.inventory_hint)
        self.inv_table=self._make_table('inventory');l.addWidget(self.inv_table,1)
        self.inv_bulk_bar=QWidget();bulk=QHBoxLayout(self.inv_bulk_bar);bulk.setContentsMargins(0,0,0,0)
        self.inv_selection_info=glass_label('','muted',10);bulk.addWidget(self.inv_selection_info,1)
        self.del_bulk=add_button('Удалить выбранные',self.delete_bulk,'danger');self.del_bulk.setFixedHeight(39)
        self.del_bulk.setIcon(hud_icon('remove',20));bulk.addWidget(self.del_bulk);l.addWidget(self.inv_bulk_bar)
        self.inv_bulk_bar.hide();row.addLayout(l,1);return page

    def _make_tools(self):
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName('toolsScroller');scroll.viewport().setAutoFillBackground(False)
        inside=QWidget();inside.setObjectName('toolsInner');grid=QGridLayout(inside);grid.setSpacing(12)
        specs=[
          ('Сохранения', [('Учебный инвентарь',self.load_latest),('Открыть вручную',self.open_save_dialog),
             ('Папка сохранений',self.open_save_dir),('Просмотр правок',self.show_changes),('Сравнить два файла',self.compare_dialog)]),
          ('Игра и DLC',[('Сканировать папку игры',self.choose_game),('Автопоиск игры',lambda:self.scan_game(None)),('Начало работы',self.show_startup)]),
          ('Каталог и диагностика',[('Импорт английского каталога',self.import_english_dialog),('Отчёт: отсутствующие переводы',self.translation_report),
                                   ('Отчёт: отсутствующие иконки',self.icon_report),
                                   ('Экспорт инвентаря в CSV',self.export_csv)]),
          ('Настройки',[('Отменить изменение',self.undo),('Сбросить изменения',self.reset),
                        ('Избранное: выбранный предмет',self.favorite)])
        ]
        self.tools_title=glass_label('ИНСТРУМЕНТЫ И ДИАГНОСТИКА','section',14)
        grid.addWidget(self.tools_title,0,0,1,2)
        self.tool_groups=[]
        self.tool_btns=[]
        for i,(name,items) in enumerate(specs):
            pane=GlassPanel();pl=QVBoxLayout(pane);pl.setContentsMargins(15,12,15,14)
            lbl=glass_label(name,'section',12);pl.addWidget(lbl)
            for title,fn in items:
                b=add_button(title,fn)
                b.setMinimumHeight(40);b.setMaximumHeight(42)
                pl.addWidget(b)
                self.tool_btns.append((title,b))
            pl.addStretch();grid.addWidget(pane,1+i//2,i%2)
            self.tool_groups.append((lbl,items))
        self.scan_state=glass_label('Сканирование ещё не выполнялось','muted',11)
        grid.addWidget(self.scan_state,3,0,1,2)
        scroll.setWidget(inside)
        inside.setAutoFillBackground(False)
        inside.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        return scroll

    def _make_detail(self):
        l=QVBoxLayout(self.detail);l.setContentsMargins(22,15,22,25);l.setSpacing(7)
        self.detail_header=HudSectionHeader('ИНФОРМАЦИЯ О ПРЕДМЕТЕ','02');self.detail_header.hide()
        heading=QHBoxLayout();heading.setSpacing(0)
        self.detail_title=glass_label('ВЫБРАННЫЙ ПРЕДМЕТ','section',12)
        heading.addWidget(self.detail_title,1)
        self.favorite_btn=add_button('☆',self.favorite,'window');self.favorite_btn.setFixedSize(26,28)
        self.favorite_btn.setToolTip('В избранное');heading.addWidget(self.favorite_btn)
        l.addLayout(heading)
        top=QHBoxLayout();top.setSpacing(14)
        self.big_icon=QLabel('◇');self.big_icon.setFixedSize(92,112)
        self.big_icon.setAlignment(Qt.AlignmentFlag.AlignCenter);self.big_icon.setObjectName('heroIcon');top.addWidget(self.big_icon)
        identity=QVBoxLayout();identity.setSpacing(2)
        self.item_name=ItemTitle();self.item_name.setProperty('role','itemName');self.item_name.setText('Выберите предмет')
        self.item_name.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        identity.addWidget(self.item_name,1)
        self.item_category=ElideLabel();self.item_category.setObjectName('itemCategoryBadge')
        self.item_category.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.item_category.setFixedHeight(19);identity.addWidget(self.item_category)
        self.owned_note=glass_label('','muted',10);self.owned_note.hide()
        labels=QHBoxLayout();labels.setSpacing(8)
        self.id_caption=glass_label('ID предмета','muted',10);self.qty_caption=glass_label('Количество (0–99)','muted',10)
        self.id_caption.setObjectName('fieldCaption');self.qty_caption.setObjectName('fieldCaption')
        self.id_caption.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.qty_caption.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        labels.addWidget(self.id_caption,1);labels.addWidget(self.qty_caption,1);identity.addLayout(labels)
        nums=QHBoxLayout();nums.setSpacing(8)
        self.id_field=QLineEdit();self.id_field.setReadOnly(True);self.id_field.setFixedHeight(36)
        self.qty=QSpinBox();self.qty.setRange(0,99);self.qty.setFixedHeight(36)
        # Native spin-box size hints must not consume the adjacent ID field.
        for field in (self.id_field,self.qty):
            field.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.qty.valueChanged.connect(self._quantity_edited)
        nums.addWidget(self.id_field,1);nums.addWidget(self.qty,1);identity.addLayout(nums);top.addLayout(identity,1);l.addLayout(top)
        self.quantity_note=glass_label('','muted',10);self.quantity_note.setObjectName('quantityChange')
        self.quantity_note.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.quantity_note.setFixedHeight(21);l.addWidget(self.quantity_note)
        self.quantity_presets=QHBoxLayout();self.preset_buttons={}
        self.qty_preset_caption=glass_label('БЫСТРОЕ КОЛИЧЕСТВО','muted',9);self.qty_preset_caption.hide()
        from PySide6.QtWidgets import QMenu
        self.qty.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        def quick_menu(pos):
            menu=QMenu(self.qty)
            for amount in (1,10,50,99):
                a=menu.addAction(str(amount));a.triggered.connect(lambda checked=False,v=amount:self.qty.setValue(v))
            try:menu.exec(self.qty.mapToGlobal(pos))
            finally:menu.deleteLater()
        self.qty.customContextMenuRequested.connect(quick_menu)
        for amount in (1,10,50,99):
            b=add_button(str(amount),lambda value=amount:self.qty.setValue(value),'preset');b.setParent(self.detail);b.hide()
            self.preset_buttons[amount]=b
        def separator():
            line=QFrame();line.setObjectName('hudSeparator');line.setFixedHeight(1);l.addWidget(line)
        separator()
        self.apply_btn=add_button('Применить количество',self.apply_single,'primary')
        self.delete_btn=add_button('Удалить предмет из сохранения',self.delete_single,'danger')
        self.apply_btn.setIcon(hud_icon('check'));self.delete_btn.setIcon(hud_icon('remove'))
        for b in (self.apply_btn,self.delete_btn):b.setFixedHeight(48);l.addWidget(b)
        secondary=QHBoxLayout();secondary.setSpacing(3)
        self.undo_btn=add_button('Отменить',self.undo);self.undo_btn.setIcon(hud_icon('undo'))
        self.reset_btn=add_button('Сбросить правки',self.reset);self.reset_btn.setIcon(hud_icon('reset'))
        for b in (self.undo_btn,self.reset_btn):b.setFixedHeight(48);secondary.addWidget(b)
        l.addLayout(secondary);separator()
        self.description_title=glass_label('Описание и характеристики','descriptionTitle',12);l.addWidget(self.description_title)
        self.description=QPlainTextEdit();self.description.setReadOnly(True);self.description.setObjectName('itemDescription')
        self.description.setMinimumHeight(110);l.addWidget(self.description,1)
        self.safe_note=glass_label('','muted',9);self.safe_note.hide()

    def _only_missing(self,v):
        if v:
            with QSignalBlocker(self.present):self.present.setChecked(False)
            self.owned_action.setChecked(False)
        self.update_tables()
    def _only_present(self,v):
        if v:
            with QSignalBlocker(self.missing):self.missing.setChecked(False)
        self.update_tables()

    def initial_load(self):
        if not self.core.catalog:
            self.scan_game(None,silent=True)
        else:self.update_tables()

    def navigate_section(self,section):
        if section in ('catalog','inventory'):
            self._startup_dismissed=True;self._startup_forced=False
        self.show_section(section)

    def show_startup(self):
        self._startup_dismissed=False;self._startup_forced=True
        self.show_section('catalog')

    def dismiss_startup(self):
        self._startup_dismissed=True;self._startup_forced=False
        self.show_section('catalog')

    def open_save_from_startup(self):
        previous=self.core.save
        self.load_latest()
        if self.core.save is not None and self.core.save is not previous:
            self._startup_forced=False;self._startup_dismissed=False
            self.show_section('inventory')

    def refresh_startup(self,catalog_count=None):
        if not hasattr(self,'startup_page'):return
        count=len(self._catalog_view()) if catalog_count is None else catalog_count
        section=getattr(self,'current_section','catalog')
        needed=not count or self.core.save is None
        showing=section!='tools' and not self._startup_dismissed and (needed or self._startup_forced)
        self.startup_page.render_state(language=self.language,catalog_count=count,
            save_name=self.msg('Учебный инвентарь','Sample inventory') if self.core.save else '',busy=self._scan_busy,
            stage=self._scan_stage,error=self._scan_error,error_details=error_text(self._scan_error_details,self.language),
            warning_count=self._scan_warning_count)
        self.pages.setCurrentWidget(self.startup_page if showing else {'catalog':self.catpage,'inventory':self.invpage,'tools':self.toolspage}[section])
        self.tabs.setVisible(section!='tools' and not showing)
        self.detail_shell.setVisible(section!='tools' and not showing)
        self.detail.setVisible(section!='tools' and not showing)
        if showing:
            self.footer.setText(self.msg('Начало работы · Каталог → Образец → Редактор',
                                         'Getting started · Catalog → Sample → Editor'))

    def show_section(self,section):
        self.current_section=section
        self._refresh_section_headers()
        self.pages.setCurrentIndex({'catalog':0,'inventory':1,'tools':2}[section])
        self.detail_shell.setVisible(section!='tools')
        self.detail.setVisible(section!='tools')
        self.tabs.setVisible(section!='tools')
        self.tabcat.setVisible(section!='tools');self.tabinv.setVisible(section!='tools')
        self.tabcat.setChecked(section=='catalog');self.tabinv.setChecked(section=='inventory')
        for k,b in self.navigation.items():b.setChecked(k==section)
        self.update_tables()
        if section in ('catalog','inventory'):
            selected=self.selected_ids(self.cat_table if section=='catalog' else self.inv_table)
            if selected and self.active_item_id not in selected:self.show_item(selected[-1])

    def switch_language(self):
        # UI translation must not discard a quantity typed but not yet applied.
        pending_quantity = self.qty.value()
        quantity_edited = self._quantity_user_edited
        self.language='en' if self.lang.currentIndex()==1 else 'ru'
        self.core.set_language(self.language)
        self.retranslate();self.populate_categories();self.update_tables()
        self.show_item(self.active_item_id)
        if self.active_item_id is not None:
            self.qty.setValue(pending_quantity)
            self._quantity_user_edited=quantity_edited

    def retranslate(self):
        t=self.msg
        self.title.setText(t('Редактор сохранений','Save editor'))
        self.subtitle.setText(t('COLD STEEL I · АКАДЕМИЯ ТОРС · КЛАСС VII','COLD STEEL I · THORS ACADEMY · CLASS VII'))
        for key,ru,en in [('inventory','Инвентарь','Inventory'),
                          ('catalog','Каталог','Catalog'),('tools','Инструменты','Tools')]:
            self.navigation[key].setText(t(ru,en))
        self.btn_latest.setText(t('Последнее\nсохранение   F5','Latest\nsave   F5'))
        self.btn_open.setText(t('Открыть вручную\nCtrl+O','Open manually\nCtrl+O'))
        self.btn_compare.setText(t('Сравнить\nфайлы','Compare\nsaves'))
        self.btn_overwrite.setText(t('Записать с резервной\nкопией','Overwrite with\nbackup'))
        self.btn_savecopy.setText(t('Сохранить\nкопию…','Save a\ncopy…'))
        self.tabcat.setText(t('Каталог предметов','Item catalog'));self.tabinv.setText(t('Мой инвентарь','My inventory'))
        self.cat_search.setPlaceholderText(t('Поиск по названию, ID или описанию…','Search by name, ID or description…'))
        self.inv_search.setPlaceholderText(t('Поиск по названию, ID или описанию…','Search by name, ID or description…'))
        self.inventory_hint.setText(t('Предметы в учебном инвентаре','Items in the sample inventory'))
        self.missing.setText(t('Показывать только отсутствующие','Show missing only'))
        self.present.setText(t('Только имеющиеся','Owned only'))
        self.filter_button.setText(t('Фильтры ▾','Filters ▾'))
        self.owned_action.setText(t('Только имеющиеся','Owned only'))
        for action,ru,en in zip(self.source_actions,['Все источники','Основная игра','DLC'],['All sources','Base game','DLC']):action.setText(t(ru,en))
        for symbol,ru,en in [('minimize','Свернуть','Minimize'),('maximize','Развернуть / восстановить','Maximize / restore'),('close','Закрыть','Close')]:
            self.window_buttons[symbol].setToolTip(t(ru,en))
        self.help_button.setToolTip(t('Справка','Help'))
        selected_source=self.source.currentIndex()
        self.source.blockSignals(True);self.source.clear();self.source.addItems([
            t('Все источники','All sources'),t('Основная игра','Base game'),'DLC'])
        self.source.setCurrentIndex(max(0,selected_source));self.source.blockSignals(False)
        self.cat_table.setHorizontalHeaderLabels([t('Предмет','Item'),'ID',t('Категория','Category'),t('В инвентаре','Owned')])
        self.inv_table.setHorizontalHeaderLabels([t('Предмет','Item'),'ID',t('Категория','Category'),t('В инвентаре','Owned')])
        self.add_one.setText(t('По 1 каждому','Set 1 each'))
        self.add_bulk.setText(t('Добавить выбранные','Apply to selected'))
        self.del_bulk.setText(t('Удалить выбранные','Remove selected'))
        self.detail_title.setText(t('ВЫБРАННЫЙ ПРЕДМЕТ','SELECTED ITEM'))
        self.id_caption.setText(t('ID предмета','Item ID'))
        self.qty_caption.setText(t('Количество (0–99)','Quantity (0–99)'))
        self.apply_btn.setText(t('Применить количество','Apply quantity'))
        self.delete_btn.setText(t('Удалить предмет из сохранения','Delete from save'))
        self.undo_btn.setText(t('Отменить','Undo'))
        self.reset_btn.setText(t('Сбросить правки','Reset edits'))
        self.favorite_btn.setText('☆')
        self.favorite_btn.setToolTip(t('Добавить или убрать из избранного','Add or remove favorite'))
        self.description_title.setText(t('Описание и характеристики','Description & details'))
        self.qty_preset_caption.setText(t('БЫСТРОЕ КОЛИЧЕСТВО','QUICK QUANTITY'))
        self.safe_note.setText(t('Правки демонстрационного инвентаря хранятся в памяти.','Sample inventory edits are kept in memory.'))
        self.tools_title.setText(t('ИНСТРУМЕНТЫ И ДИАГНОСТИКА','TOOLS & DIAGNOSTICS'))
        if self._scan_busy:
            self.scan_state.setText(t('Загрузка каталога…','Loading the catalog…'))
        elif self._scan_error:
            self.scan_state.setText(t('Каталог не удалось загрузить. Выберите папку игры.','The catalog could not be loaded. Choose the game folder.'))
        elif self.core.last_scan is not None:
            r=self.core.last_scan
            self.scan_state.setText(self.scan_summary(r))
        else:
            self.scan_state.setText(t('Сканирование ещё не выполнялось','Game has not been scanned yet'))
        for label,(ru,en) in zip([x[0] for x in self.tool_groups],[
             ('Сохранения','Saves'),('Игра и DLC','Game & DLC'),('Каталог и диагностика','Catalog & diagnostics'),('Настройки','Settings')]):
             label.setText(t(ru,en))
        for ru,btn in self.tool_btns:
            btn.setText(t(ru, TOOL_EN.get(ru,ru)))
        self._refresh_section_headers()
        if getattr(self,'_notice_text',None):self.notice.setText(self.msg(*self._notice_text))
        self.resizeEvent_as_layout()
        self.refresh_save_labels()

    def resizeEvent_as_layout(self):
        if not hasattr(self,'cat_tree'):return
        width=self.width();compact=width<1460
        short=self.height()<800
        self.header.setFixedHeight(86 if short else 96)
        self.actions.setFixedHeight(102 if short else 112)
        self.footer_row.setFixedHeight(36 if short else 44)
        if width<1460:rail,detail,categories=177,326,205
        elif width<1600:rail,detail,categories=195,410,240
        else:rail,detail,categories=208,416,255
        self.rail_panel.setFixedWidth(rail);self.detail.setFixedWidth(detail)
        self.detail_shell.setFixedWidth(detail)
        self.cat_tree.setFixedWidth(categories)
        self.inv_tree.setFixedWidth(categories)
        self.actions_layout.setContentsMargins(rail-4,10,16,4)
        widths=(178,182,161,223,185) if compact else (211,219,211,274,223)
        pairs=(
          (self.btn_latest,('Образец\nF5','Sample\nF5'),('Учебный\nинвентарь   F5','Sample\ninventory   F5')),
          (self.btn_open,('Открыть\nCtrl+O','Open\nCtrl+O'),('Открыть вручную\nCtrl+O','Open manually\nCtrl+O')),
          (self.btn_compare,('Сравнить','Compare'),('Сравнить файлы','Compare files')),
          (self.btn_overwrite,('Записать + копия','Backup + save'),('Записать с резервной копией','Save with backup')),
          (self.btn_savecopy,('Копия…','Save copy'),('Сохранить копию…','Save a copy…')),
        )
        for (btn,short,long),button_width in zip(pairs,widths):
            btn.setFixedWidth(button_width);btn.setText(self.msg(*(short if compact else long)))
        for i,value in enumerate((62,109,82) if compact else (70,133,108),start=1):self.cat_table.setColumnWidth(i,value)
        for i,value in enumerate((62,109,82) if compact else (70,133,108),start=1):self.inv_table.setColumnWidth(i,value)
        for table in (self.cat_table,self.inv_table):table.verticalHeader().setDefaultSectionSize(30)
        self.footer_row.layout().setContentsMargins(rail+8,2,4,0)
        self.qty_caption.setToolTip(self.msg('Допустимое количество: от 0 до 99','Allowed quantity: 0 to 99'))
        self.btn_latest.setToolTip(self.msg('Загрузить учебный инвентарь (F5)','Load sample inventory (F5)'))
        self.btn_open.setToolTip(self.msg('Открыть окно загрузки образца (Ctrl+O)','Open sample loading dialog (Ctrl+O)'))
        self.btn_compare.setToolTip(self.msg('Сравнить правки с исходным образцом','Compare edits with the original sample'))
        self.btn_overwrite.setToolTip(self.msg('Предпросмотр записи с резервной копией','Preview saving with a backup'))
        self.btn_savecopy.setToolTip(self.msg('Предпросмотр сохранения копии (Ctrl+S)','Preview saving a copy (Ctrl+S)'))
        self.big_icon.setFixedSize(74 if compact else 92,104 if compact else 112)
        self.detail.layout().setSpacing(3 if self.height()<800 else 7)
        self.detail.layout().setContentsMargins(18 if self.height()<800 else 22,10 if self.height()<800 else 15,18 if self.height()<800 else 22,16 if self.height()<800 else 25)
        margins=self.detail.layout().contentsMargins()
        field_width=(detail-margins.left()-margins.right()-self.big_icon.width()-14-8)//2
        for field,text,padding in ((self.id_field,'65535',18),(self.qty,'99',36)):
            field.ensurePolished()
            field.setMinimumWidth(field.fontMetrics().horizontalAdvance(text)+padding)
        for caption,full,brief in (
                (self.id_caption,self.msg('ID предмета','Item ID'),'ID'),
                (self.qty_caption,self.msg('Количество (0–99)','Quantity (0–99)'),self.msg('Кол-во','Qty'))):
            caption.ensurePolished()
            caption.setText(brief if compact or caption.fontMetrics().horizontalAdvance(full)>field_width else full)
        for button in (self.apply_btn,self.delete_btn,self.undo_btn,self.reset_btn):
            button.setFixedHeight(40 if self.height()<800 else 48)
        self.reset_btn.setText(self.msg('Сбросить','Reset') if compact else self.msg('Сбросить правки','Reset edits'))
        self.delete_btn.setText(self.msg('Удалить из сохранения','Delete from save') if compact else self.msg('Удалить предмет из сохранения','Delete from save'))
        if self.active_item_id is not None:
            ico=self._icon(self.active_item_id,self.core.catalog.get(self.active_item_id,{}))
            self._set_big_icon(ico,72 if compact else 90)

    def _refresh_section_headers(self):
        self.rail_header.setCaption(self.msg('НАВИГАЦИЯ','NAVIGATION'))
        self.detail_header.setCaption(self.msg('ИНФОРМАЦИЯ О ПРЕДМЕТЕ','ITEM DETAILS'))
        sections={'catalog':self.msg('КАТАЛОГ ПРЕДМЕТОВ','ITEM CATALOG'),
                  'inventory':self.msg('ТЕКУЩИЙ ИНВЕНТАРЬ','CURRENT INVENTORY'),
                  'tools':self.msg('ИНСТРУМЕНТЫ И ДИАГНОСТИКА','TOOLS & DIAGNOSTICS')}
        current=getattr(self,'current_section','catalog')
        self.main_header.setCaption(sections[current])
        self.main_header.serial={'catalog':'01','inventory':'02','tools':'03'}[current]
        self.main_header.update()

    def populate_categories(self):
        visible=self._catalog_view()
        counts=Counter(category_of(record) for record in visible.values())
        quantities={entry.item_id:entry.quantity for entry in self.core.save.items()} if self.core.save else {}
        owned={i:self.core.catalog.get(i,{'id':i,'category':'other'}) for i in quantities}
        owned_counts=Counter(category_of(record) for record in owned.values())
        def entry(tree,kind,key,title,count,parent=None):
            nodes=self._category_nodes[kind]
            item=nodes.get(key)
            if item is None:
                item=QTreeWidgetItem();nodes[key]=item
                item.setTextAlignment(1,Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
                item.setData(0,Qt.ItemDataRole.UserRole,key)
                item.setSizeHint(0,QSize(0,32 if parent else 39))
                if parent:parent.addChild(item)
                else:tree.addTopLevelItem(item)
            if key not in self._category_icons:
                category=key if key in CATEGORY_NAMES else GROUPS[key][1][0][0] if key in GROUPS else None
                if key == 'quartz_master':
                    self._category_icons[key] = self.art.item_icon(2000, self.core.native[2000]) if 2000 in self.core.native else hud_icon('quartz', 25)
                else:
                    self._category_icons[key] = hud_icon(category or key, 25)
            icon=self._category_icons[key]
            if item.icon(0).cacheKey()!=icon.cacheKey():item.setIcon(0,icon)
            for column,text in enumerate((title,str(count))):
                if item.text(column)!=text:item.setText(column,text)
                tip=f'{title} ({count})'
                if item.toolTip(column)!=tip:item.setToolTip(column,tip)
            return item
        for kind,tree,totals,total,previous,favorites in (
                ('catalog',self.cat_tree,counts,len(visible),self.filter_group,self.cat_favorites_only),
                ('inventory',self.inv_tree,owned_counts,len(owned),self.inv_filter_group,self.inv_favorites_only)):
            updates_enabled=tree.updatesEnabled()
            with QSignalBlocker(tree):
                tree.setUpdatesEnabled(False)
                try:
                    entry(tree,kind,'all',self.msg('Все предметы','All items'),total)
                    for group,(ru,subs) in GROUPS.items():
                        parent=entry(tree,kind,group,ru if self.language=='ru' else GROUP_EN.get(group,ru),sum(totals[k] for k,_ in subs))
                        for key,label in subs:
                            entry(tree,kind,key,label if self.language=='ru' else CATEGORY_EN.get(key,key.title()),totals[key],parent)
                        parent.setExpanded(True)
                    if kind=='catalog':
                        entry(tree,kind,'favorites',self.msg('Избранное','Favorites'),len(self.core.favorites & visible.keys()))
                        entry(tree,kind,'recent',self.msg('Недавно добавленные','Recently added'),sum(i in visible for i in self.core.recent))
                    selection=self._category_nodes[kind].get(previous)
                    if selection:tree.setCurrentItem(selection)
                    if favorites:tree.clearSelection()
                finally:tree.setUpdatesEnabled(updates_enabled)

    def on_category(self,tree=None,kind='catalog'):
        tree=tree or self.cat_tree;item=tree.currentItem()
        if item is not None:
            value=item.data(0,Qt.ItemDataRole.UserRole)
            if kind=='catalog':
                self.filter_group=value;self.cat_favorites_only=False;self.cat_quick_favorite.setChecked(False)
            else:
                self.inv_filter_group=value;self.inv_favorites_only=False;self.inv_quick_favorite.setChecked(False)
            self.update_tables()

    def sort_rows(self,kind,column):
        previous_column,descending=self.sort_keys[kind]
        self.sort_keys[kind]=(column,not descending if column==previous_column else False)
        self.update_tables()

    def _icon(self,item_id,record):
        if item_id in self._icon_pixmaps:return self._icon_pixmaps[item_id]
        item = self.core.native.get(item_id)
        icon = self.art.item_icon(item_id, item) if item is not None else QIcon()
        self._icon_pixmaps[item_id] = icon
        return icon

    def _set_big_icon(self,icon,side):
        dpr=max(2.0,self.devicePixelRatioF())
        px=icon.pixmap(QSize(side,side),dpr)
        if px.isNull():
            self.big_icon.clear();self.big_icon.setText(self.msg('Нет иконки','No icon'))
        else:
            if max(px.width(),px.height())<round(side*dpr):
                px=px.scaled(round(side*dpr),round(side*dpr),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
                px.setDevicePixelRatio(dpr)
            self.big_icon.setPixmap(px)

    def toggle_quick_favorites(self,kind):
        if kind=='catalog':
            self.cat_favorites_only=self.cat_quick_favorite.isChecked();tree=self.cat_tree
        else:
            self.inv_favorites_only=self.inv_quick_favorite.isChecked();tree=self.inv_tree
        active=self.cat_favorites_only if kind=='catalog' else self.inv_favorites_only
        tree.blockSignals(True)
        if active:tree.clearSelection()
        elif tree.currentItem():tree.setCurrentItem(tree.currentItem())
        tree.blockSignals(False);self.update_tables()
        if active and not self.core.favorites:
            self.show_toast('В избранном пока пусто. Добавь предмет звездочкой в карточке.',
                            'No favorites yet. Use the star on an item card to add one.')

    def _catalog_view(self):
        if self._view_catalog is not self.core.catalog:
            self._view_catalog=self.core.catalog
            self._visible_catalog=self.core.visible()
            self._search_details.clear()
            self._row_names.clear()
            self._icon_pixmaps.clear()
            self._category_icons.clear();self._table_rows.clear()
        if self._view_english is not self.core.english or self._view_language!=self.language:
            self._view_english=self.core.english;self._view_language=self.language
            self._search_details.clear()
            self._row_names.clear()
        return self._visible_catalog

    def _matches_search(self,needle,iid,name):
        if not needle or needle in str(iid) or needle in name.casefold():return True
        if iid not in self._search_details:
            self._search_details[iid]=self.core.details_text(iid).casefold()
        return needle in self._search_details[iid]

    def _row_name(self,iid):
        if iid not in self._row_names:self._row_names[iid]=self.core.item_name(iid)
        return self._row_names[iid]

    def _rows_for(self,kind,entries=None):
        visible=self._catalog_view()
        if entries is None:entries=self.core.save.items() if self.core.save else []
        if kind=='inventory':
            if not self.core.save:return []
            rows=[]
            needle=self.inv_search.text().casefold().strip()
            for ent in entries:
                record=self.core.catalog.get(ent.item_id)
                if record is None:
                    record={'id':ent.item_id,'name':f'ID {ent.item_id}','description':'','category':'other'}
                if self.inv_favorites_only:
                    if ent.item_id not in self.core.favorites:continue
                elif not item_in_category(record,self.inv_filter_group):continue
                name=self._row_name(ent.item_id)
                if not self._matches_search(needle,ent.item_id,name):continue
                rows.append((ent.item_id,name,ent.slot+1,ent.quantity,record))
            return rows
        rows=[]
        needle=self.cat_search.text().strip().casefold()
        quantities={entry.item_id:entry.quantity for entry in entries}
        source_filter=self.source.currentIndex()
        missing=self.missing.isChecked();present=self.present.isChecked()
        for i,record in visible.items():
            if self.cat_favorites_only:
                if i not in self.core.favorites:continue
            elif self.filter_group=='favorites' and i not in self.core.favorites:continue
            elif self.filter_group=='recent' and i not in self.core.recent:continue
            elif not self.cat_favorites_only and self.filter_group not in ('favorites','recent') and not item_in_category(record,self.filter_group):continue
            qty=quantities.get(i,0)
            if missing and qty:continue
            if present and not qty:continue
            source=record.get('_source','base')
            if source_filter==1 and source=='dlc':continue
            if source_filter==2 and source!='dlc':continue
            name=self._row_name(i)
            if not self._matches_search(needle,i,name):continue
            rows.append((i,name,category_of(record),qty,record))
        return rows

    def update_tables(self):
        self.edit_changes.refresh(self.core.save)
        entries=self.core.save.items() if self.core.save else []
        for kind,table in [('catalog',self.cat_table),('inventory',self.inv_table)]:
            rows=self._rows_for(kind,entries)
            col,rev=self.sort_keys[kind]
            def sortrow(r):
                if col==0:return r[1].casefold()
                if col==1:return r[0]
                if col==2:return self.category_label(category_of(r[4])).casefold()
                return r[3]
            rows.sort(key=sortrow,reverse=rev)
            table.horizontalHeader().setSortIndicator(col,Qt.SortOrder.DescendingOrder if rev else Qt.SortOrder.AscendingOrder)
            signatures=[]
            for iid,name,sub,qty,rec in rows:
                change=self.edit_changes.changes.get(iid)
                signatures.append((iid,name,self.category_label(category_of(rec)),qty,
                                   (change.before,change.after) if change else None,self.language))
            old=self._table_rows.get(kind,[])
            if signatures!=old or table.rowCount()!=len(rows):
                self._table_rows.pop(kind,None)
                previous=set(self.selected_ids(table))
                current=table.currentItem()
                current_id=table.item(current.row(),0).data(Qt.ItemDataRole.UserRole) if current else None
                reordered=([r[0] for r in old]!=[r[0] for r in signatures])
                updates_enabled=table.updatesEnabled()
                with QSignalBlocker(table):
                    table.setUpdatesEnabled(False)
                    try:
                        if reordered:table.clearSelection();table.setCurrentItem(None)
                        table.setRowCount(len(rows))
                        for ix,(row,signature) in enumerate(zip(rows,signatures)):
                            if ix<len(old) and signature==old[ix]:continue
                            iid,name,category,qty,change,language=signature
                            tip=name
                            if change:tip+=self.msg(f'\nИзменено: {change[0]} → {change[1]}',f'\nChanged: {change[0]} → {change[1]}')
                            for column,text in enumerate((name,str(iid),category,str(qty))):
                                cell=table.item(ix,column)
                                if cell is None:
                                    cell=QTableWidgetItem();table.setItem(ix,column,cell)
                                    if column:cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                                cell.setText(text)
                                cell.setToolTip(tip if column==0 or (column==3 and change) else text)
                                cell.setData(Qt.ItemDataRole.UserRole+1,change)
                                if column==0:
                                    cell.setData(Qt.ItemDataRole.UserRole,iid)
                                    cell.setIcon(self._icon(iid,row[4]))
                        if reordered:
                            from PySide6.QtCore import QItemSelectionModel
                            sel=table.selectionModel()
                            for ix,signature in enumerate(signatures):
                                iid=signature[0]
                                if iid in previous:
                                    sel.select(table.model().index(ix,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
                                if iid==current_id:
                                    sel.setCurrentIndex(table.model().index(ix,0),QItemSelectionModel.SelectionFlag.NoUpdate)
                        self._table_rows[kind]=signatures
                    finally:table.setUpdatesEnabled(updates_enabled)
            if kind=='catalog':
                self.catalog_counter.setText(self.msg(f'НАЙДЕНО ПРЕДМЕТОВ: {len(rows)}',f'ITEMS FOUND: {len(rows)}'))
        self.selection_info.setText(self.msg('Выделено: ','Selected: ')+str(len(self.cat_table.selectionModel().selectedRows())))
        self.bulk_bar.setVisible(len(self.cat_table.selectionModel().selectedRows())>1)
        self.inv_selection_info.setText(self.msg('Выделено: ','Selected: ')+str(len(self.selected_ids(self.inv_table))))
        self.inv_bulk_bar.setVisible(len(self.selected_ids(self.inv_table))>1)
        section = getattr(self, 'current_section', 'catalog')
        if self.active_item_id is not None and section in ('catalog', 'inventory'):
            active = self.cat_table if section == 'catalog' else self.inv_table
            selected = self.selected_ids(active)
            if self.active_item_id not in selected:
                self.show_item(selected[-1] if selected else None)
        self.refresh_save_labels()

    def category_label(self,key):
        if self.language=='ru':return CATEGORY_NAMES.get(key,key)
        return CATEGORY_EN.get(key,key.title())

    def selected_ids(self,table):
        ids=[]
        for idx in table.selectionModel().selectedRows():
            item=table.item(idx.row(),0)
            if item:ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return list(dict.fromkeys(ids))

    def selection_changed(self,table):
        ids=self.selected_ids(table)
        active_table=self.cat_table if getattr(self,'current_section','catalog')=='catalog' else self.inv_table
        if table is active_table:self.show_item(ids[-1] if ids else None)
        self.selection_info.setText(self.msg('Выделено: ','Selected: ')+str(len(self.selected_ids(self.cat_table))))
        self.bulk_bar.setVisible(len(self.selected_ids(self.cat_table))>1)
        self.inv_bulk_bar.setVisible(len(self.selected_ids(self.inv_table))>1)
        self.inv_selection_info.setText(self.msg('Выделено: ','Selected: ')+str(len(self.selected_ids(self.inv_table))))

    def show_item(self,iid):
        self.active_item_id=iid
        self._quantity_user_edited=False
        self.apply_btn.setEnabled(self.core.can_edit(iid))
        self.qty.setEnabled(self.core.can_edit(iid))
        self.delete_btn.setEnabled(self.core.can_delete(iid))
        if iid is None:
            with QSignalBlocker(self.qty):
                self.qty.setMaximum(99)
                self.qty.setValue(1)
            self.item_name.setText(self.msg('Выберите предмет','Select an item'))
            self.item_category.setText('');self.owned_note.setText('');self.id_field.clear()
            self.description.clear();self.big_icon.clear();self.big_icon.setText('');self.favorite_btn.setText('☆');self.quantity_note.clear();return
        record=self.core.catalog.get(iid,{})
        self.item_name.setText(self.core.item_name(iid))
        source=self.msg('DLC','DLC') if record.get('_source')=='dlc' else self.msg('Основная игра','Base game')
        self.item_category.setText(self.category_label(category_of(record))+' · '+source)
        self.item_category.setToolTip(self.category_label(category_of(record))+' · '+source)
        self.id_field.setText(str(iid))
        owned=self.core.quantity(iid)
        change=self.edit_changes.changes.get(iid)
        with QSignalBlocker(self.qty):
            self.qty.setMaximum(max(0, min(99, record.get('limit', 99))))
            self.qty.setValue(0 if change and change.after == 0 else owned or 1)
        self.owned_note.setText(self.msg(f'В сумке: {owned}',f'Owned: {owned}'))
        self.description.setPlainText(self.core.details_text(iid))
        self.favorite_btn.setText('★' if iid in self.core.favorites else '☆')
        ico=self._icon(iid,record);self._set_big_icon(ico,72 if self.width()<1460 else 90)
        self.big_icon.setToolTip(self.msg('Оригинальная иконка Cold Steel I', 'Original Cold Steel I artwork')
                                 if not ico.isNull() else self.msg('Оригинальная иконка недоступна', 'Original icon unavailable'))
        self.refresh_quantity_note()

    def _quantity_edited(self,_value):
        self._quantity_user_edited=True
        self.refresh_quantity_note()

    def has_pending_quantity(self):
        return bool(self.core.save and self._quantity_user_edited and self.active_item_id is not None and self.qty.value()!=self.core.quantity(self.active_item_id))

    def refresh_quantity_note(self):
        if not hasattr(self,'quantity_note'):return
        iid=self.active_item_id
        if iid is None:self.quantity_note.clear();return
        self.edit_changes.refresh(self.core.save)
        current=self.core.quantity(iid);before=self.edit_changes.before.get(iid,0);pending=self.qty.value()
        if pending!=current:
            text=self.msg(f'Сейчас: {current}  →  После применения: {pending}',f'Current: {current}  →  After applying: {pending}')
        elif before!=current:
            text=self.msg(f'В образце: {before}  →  После правки: {current}',f'Sample: {before}  →  After editing: {current}')
        else:text=self.msg(f'В образце и редакторе: {current}',f'Original and current: {current}')
        self.quantity_note.setText(text);self.quantity_note.setToolTip(text)
        self.quantity_note.setProperty('changed',before!=current or pending!=current)

    def show_changes(self,save_mode=None):
        from qt_changes_dialog import ChangesDialog
        from PySide6.QtWidgets import QDialog
        dialog=ChangesDialog(self,save_mode)
        try:return dialog.exec()==QDialog.DialogCode.Accepted
        finally:dialog.deleteLater()

    def _position_notice(self):
        width=min(600,max(250,self.center_shell.width()-40))
        self.notice.setFixedWidth(width);self.notice.adjustSize()
        pos=self.center_shell.mapTo(self.centralWidget(),QPoint(20,0))
        self.notice.move(pos.x(),self.height()-self.footer_row.height()-self.notice.height()-23)

    def show_toast(self,ru,en):
        self._notice_text=(ru,en);self.notice.setText(self.msg(ru,en))
        self._position_notice();self.notice.show();self.notice.raise_();self.notice_timer.start(3600)

    def _handle(self,action):
        try:
            result=action()
            if getattr(self.core,'persistence_warning',''):
                self.show_toast('Действие выполнено. Настройки не удалось сохранить для следующего запуска.',
                                'Action completed. Preferences could not be saved for the next session.')
                self.notice.setToolTip(error_text(self.core.persistence_warning,self.language))
            return result
        except Exception as exc:
            QMessageBox.warning(self,self.msg('Ошибка','Error'),error_text(exc,self.language))
            return None

    def _apply(self,changes):
        def run():
            before=self.core.save.quantities if self.core.save else None
            self.core.change(changes)
            self.populate_categories();self.update_tables();self.show_item(self.active_item_id)
            if self.core.save and self.core.save.quantities is not before:
                self.show_toast('Правки применены к образцу. Их можно просмотреть.', 'Changes applied to the sample. You can review them.')
        return self._handle(run)

    def apply_single(self):
        if self.active_item_id is None:return
        self._apply({self.active_item_id:self.qty.value()})

    def apply_bulk(self,qty=None):
        ids=self.selected_ids(self.cat_table)
        if not ids:
            QMessageBox.information(self,'CS1',self.msg('Выбери предметы в каталоге','Select items in the catalog'));return
        amount=self.qty.value() if qty is None else qty
        self._apply({i:amount for i in ids})

    def delete_single(self):
        if self.active_item_id is not None:self._apply({self.active_item_id:0})

    def delete_bulk(self):
        ids=self.selected_ids(self.inv_table)
        if ids and QMessageBox.question(self,'CS1',self.msg(f'Удалить выбранные предметы: {len(ids)}?',f'Remove {len(ids)} selected items?'))==QMessageBox.StandardButton.Yes:
            self._apply({i:0 for i in ids})

    def undo(self):
        changed=self._handle(lambda:self.core.undo())
        self.populate_categories();self.update_tables();self.show_item(self.active_item_id)
        if changed:self.show_toast('Последнее изменение отменено','Last change undone')

    def reset(self):
        if self.core.save and QMessageBox.question(self,'CS1',self.msg('Сбросить несохранённые изменения?', 'Discard unsaved changes?'))==QMessageBox.StandardButton.Yes:
            self.core.reset();self.populate_categories();self.update_tables();self.show_item(self.active_item_id)
            self.show_toast('Правки сброшены к исходному файлу','Edits reset to the original file')

    def favorite(self):
        if self.active_item_id is None:return
        self._handle(lambda:self.core.toggle_favorite(self.active_item_id))
        self.populate_categories();self.update_tables()
        if self.active_item_id is not None:
            self.favorite_btn.setText('★' if self.active_item_id in self.core.favorites else '☆')
            if self.active_item_id in self.core.favorites:self.show_toast('Предмет добавлен в избранное','Item added to favorites')
            else:self.show_toast('Предмет удалён из избранного','Item removed from favorites')

    def confirm_dirty(self):
        if (self.core.save and self.core.save.changed) or self.has_pending_quantity():
            return QMessageBox.question(self,'CS1',self.msg('Несохранённые изменения будут потеряны. Продолжить?',
                'Unsaved changes will be lost. Continue?')) == QMessageBox.StandardButton.Yes
        return True

    def open_save_dialog(self):
        choice = QMessageBox.question(
            self, APP_NAME,
            self.msg('Открытие игровых файлов будет добавлено позже. Загрузить демонстрационный инвентарь?',
                     'Opening game files is planned for a later stage. Load the sample inventory?'),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice == QMessageBox.StandardButton.Yes:
            self.load_latest()

    def load_latest(self, silent=False):
        if not silent and not self.confirm_dirty():
            return
        if not self.core.load_demo():
            if not silent:
                self.show_toast('Сначала загрузите каталог игры.', 'Load the game catalog first.')
            return
        self.active_item_id = None
        self.populate_categories()
        self.update_tables()
        self.navigate_section('inventory')
        self.show_toast('Учебный инвентарь загружен.', 'Sample inventory loaded.')

    def save_copy_dialog(self):
        if self.core.save:
            self.show_changes('copy')

    def overwrite_dialog(self):
        if self.core.save and self.core.save.changed:
            self.show_changes('overwrite')

    def compare_dialog(self):
        if self.core.save is None:
            return
        self.edit_changes.refresh(self.core.save)
        counts = self.edit_changes.counts()
        added, removed, modified = (counts[key] for key in ('added', 'removed', 'modified'))
        summary = self.msg(
            f'Сравнение с исходным учебным инвентарём.\n\nДобавлено: {added}\nУдалено: {removed}\nИзменено: {modified}',
            f'Comparison with the original sample inventory.\n\nAdded: {added}\nRemoved: {removed}\nModified: {modified}',
        )
        QMessageBox.information(self, self.msg('Сравнение инвентаря','Compare inventory'), summary)

    def choose_game(self):
        folder=QFileDialog.getExistingDirectory(self,self.msg('Папка игры','Game directory'),self.core.settings.get('game_root',''))
        if folder:self.scan_game(Path(folder))

    def scan_game(self,path=None,silent=False):
        if self.scan_thread is not None:return
        self._scan_started_in_setup=self.pages.currentWidget() is self.startup_page
        self._scan_busy=True;self._scan_stage='locating';self._scan_error='';self._scan_error_details=''
        self._scan_warning_count=0;self._scan_succeeded=False;self._scan_silent=silent
        self.scan_state.setText(self.msg('Ищем игру и загружаем каталог…','Locating the game and loading the catalog…'))
        self.refresh_startup()
        self.scan_thread=QThread(self)
        self.scan_worker=ScanWorker(self.core,path)
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.stage.connect(self.on_scan_stage)
        self.scan_worker.result.connect(self.on_scan_result)
        self.scan_worker.error.connect(self.on_scan_error)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_worker.finished.connect(self.scan_worker.deleteLater)
        self.scan_thread.finished.connect(self.scan_thread.deleteLater)
        self.scan_thread.finished.connect(self.on_scan_finished)
        self.scan_thread.start()

    @Slot(str)
    def on_scan_stage(self,stage):
        self._scan_stage=stage;self.refresh_startup()

    @Slot(object)
    def on_scan_result(self,result):
        self._scan_stage='saving';self.refresh_startup()
        try:self.core.apply_scan_result(result)
        except Exception as exc:
            self.on_scan_error(str(exc),self._scan_silent);return
        self._scan_succeeded=True;self._scan_error=''
        self._scan_warning_count=len(result.errors)
        self._scan_error_details='\n'.join(result.errors[:6])
        self.refresh_catalog()
        self.scan_state.setText(self.scan_summary(result))
        if result.errors and not self._scan_started_in_setup and not self._scan_silent:
            QMessageBox.warning(self,'TBL',error_text('\n'.join(result.errors[:6]),self.language))

    def scan_summary(self,result):
        n=len(result.files);m=len(result.items)
        return self.msg(f'Сканировано таблиц: {n}, предметов: {m}',
                        f'Scanned {n} '+('table' if n==1 else 'tables')+f'; {m} '+('item' if m==1 else 'items'))

    @Slot(str)
    def on_scan_error(self,error,silent=False):
        silent=silent or self._scan_silent
        self._scan_succeeded=False
        self._scan_error='not_found' if error=='Game directory not found' else 'unreadable'
        self._scan_error_details=error
        self.scan_state.setText(self.msg('Каталог не удалось загрузить. Выберите папку игры.',
                                        'The catalog could not be loaded. Choose the game folder.'))
        self.refresh_startup()
        if not silent and not self._scan_started_in_setup and self.pages.currentWidget() is not self.startup_page:
            QMessageBox.warning(self,'TBL',error_text(error,self.language))

    @Slot()
    def on_scan_finished(self):
        self.scan_thread=None;self.scan_worker=None;self._scan_busy=False
        self.refresh_startup()
        if self._scan_succeeded:
            count=len(self.core.visible())
            self.show_toast(f'Каталог загружен. Предметов: {count}',f'Catalog loaded. Items: {count}')

    def open_save_dir(self):
        self.show_toast('Папка сохранений будет подключена вместе с поддержкой игровых файлов.',
                        'The save folder will be available when game files are supported.')

    def translation_report(self):
        missing = [f'{item_id}: {name}' for item_id, name in self.core.missing_translations()]
        self.show_report(self.msg('Непереведённые записи','Untranslated records'),missing)

    def import_english_dialog(self):
        path,_=QFileDialog.getOpenFileName(self,self.msg('Импорт оригинального английского каталога','Import an original English catalog'),'',
                                          'Cold Steel I catalog (*.tbl)')
        if not path:return
        count=self._handle(lambda:self.core.import_english_catalog(path))
        if count:
            self.refresh_catalog()
            self.show_toast(f'Английский каталог загружен: {count} предметов',f'English catalog loaded: {count} items')

    def refresh_catalog(self):
        pending=self.qty.value();edited=self._quantity_user_edited;active=self.active_item_id
        self._icon_pixmaps.clear();self._table_rows.clear()
        self._category_icons.clear()
        self._view_catalog=None
        self.populate_categories();self.update_tables()
        self.show_item(active)
        if edited and active is not None:
            self.qty.setValue(pending);self._quantity_user_edited=True

    def icon_report(self):
        missing=[]
        for i,record in self.core.visible().items():
            if self._icon(i,record).isNull():missing.append(f'{i}: {self.core.item_name(i)}')
        self.show_report(self.msg('Отсутствующие оригинальные иконки','Missing original icons'),missing)

    def show_report(self,title,lines,count=True):
        prefix=(self.msg('Найдено: ','Found: ')+str(len(lines))+'\n') if count else ''
        QMessageBox.information(self,title,prefix+'\n'.join(lines[:60]))

    def export_csv(self):
        if not self.core.save:return
        filename,_=QFileDialog.getSaveFileName(self,'CSV','CS1_inventory.csv','CSV (*.csv)')
        if not filename:return
        destination=self._handle(lambda:self.core.export_csv(filename))
        if destination:self.show_toast('CSV сохранён: '+destination.name,'CSV exported: '+destination.name)

    def refresh_save_labels(self):
        self.edit_changes.refresh(self.core.save)
        loaded = self.core.save is not None
        self.rail_file.setText(self.msg('Учебный инвентарь','Sample inventory') if loaded else '—')
        self.rail_folder.setText(self.msg('В памяти','In memory') if loaded else '—')
        self.rail_date.setText('—')
        self.rail_state.setText(self.msg('Образец загружен','Sample loaded') if loaded else self.msg('Нет данных','No data'))
        self.save_line.setText(self.msg('Предпросмотр интерфейса · игровой каталог и учебный инвентарь',
                                        'Interface preview · game catalog and sample inventory') if loaded else
                               self.msg('Для начала загрузите каталог игры.', 'Load the game catalog to start.'))
        if self.core.save and self.core.save.changed:
            state='dirty'
            status=self.msg('● ЕСТЬ ПРАВКИ','● UNSAVED EDITS')
        elif self.core.save:
            state='clean'
            status=self.msg('ДЕМО · В ПАМЯТИ','DEMO · IN MEMORY')
        else:
            state='empty'
            status=self.msg('○ НЕТ ДАННЫХ','○ NO DATA')
        self.dirty_chip.setText(status)
        if self.dirty_chip.property('state')!=state:
            self.dirty_chip.setProperty('state',state)
            self.dirty_chip.style().unpolish(self.dirty_chip)
            self.dirty_chip.style().polish(self.dirty_chip)
        self.dirty_chip.setToolTip(self.msg('Правки образца хранятся в памяти.', 'Sample edits are kept in memory.'))
        visible=self._catalog_view();n=self.core.save.occupied_count if self.core.save else 0
        rows=self.cat_table.rowCount() if getattr(self,'current_section','catalog')=='catalog' else self.inv_table.rowCount()
        favorite_view=self.cat_favorites_only if getattr(self,'current_section','catalog')=='catalog' else self.inv_favorites_only
        caption=self.msg('Избранное','Favorites') if favorite_view else self.msg('В выбранной группе','In this view')
        self.footer.setText(self.msg(f'Каталог: {len(visible)} предметов',f'Catalog: {len(visible)} items')+f'   |   {caption}: {rows}')
        self.footer_aux.setText(self.msg(f'Инвентарь: {n}   ·   Правок: {len(self.edit_changes.changes)}',f'Inventory: {n}   ·   Edits: {len(self.edit_changes.changes)}'))
        self.review_button.setText(self.msg(f'Правки: {len(self.edit_changes.changes)}',f'Edits: {len(self.edit_changes.changes)}'))
        self.review_button.setVisible(bool(self.core.save and self.core.save.changed))
        self.review_button.setToolTip(self.msg('Просмотреть все изменения перед записью','Review every change before saving'))
        for button in (self.cat_quick_favorite,self.inv_quick_favorite):
            button.setToolTip(self.msg(f'Избранное: {len(self.core.favorites)} · нажми для фильтра',f'Favorites: {len(self.core.favorites)} · click to filter'))
        self.refresh_quantity_note()
        self.apply_btn.setEnabled(self.core.can_edit(self.active_item_id))
        self.delete_btn.setEnabled(self.core.can_delete(self.active_item_id))
        self.undo_btn.setEnabled(bool(self.core.undo_stack))
        self.reset_btn.setEnabled(bool(self.core.save and self.core.save.changed))
        self.btn_compare.setEnabled(self.core.save is not None)
        self.btn_savecopy.setEnabled(self.core.save is not None)
        self.btn_overwrite.setEnabled(bool(self.core.save and self.core.save.changed))
        self.refresh_startup(len(visible))

    def keyPressEvent(self,event):
        k=event.key();mods=event.modifiers()
        if k==Qt.Key.Key_F5:self.load_latest()
        elif mods & Qt.KeyboardModifier.ControlModifier and k==Qt.Key.Key_O:self.open_save_dialog()
        elif mods & Qt.KeyboardModifier.ControlModifier and k==Qt.Key.Key_S:self.save_copy_dialog()
        elif mods & Qt.KeyboardModifier.ControlModifier and k==Qt.Key.Key_Z:self.undo()
        elif mods & Qt.KeyboardModifier.ControlModifier and k==Qt.Key.Key_F:
            self.navigate_section('catalog');self.cat_search.setFocus()
        else:super().keyPressEvent(event)

    def closeEvent(self,event):
        if not self.confirm_dirty():event.ignore();return
        if self.scan_thread and self.scan_thread.isRunning():
            QMessageBox.information(self,'CS1',self.msg('Дождись завершения сканирования игры.',
                                                   'Please wait until game scanning finishes.'))
            event.ignore();return
        super().closeEvent(event)


TOOL_EN={
 'Учебный инвентарь':'Sample inventory', 'Открыть вручную':'Open manually',
 'Просмотр правок':'Review changes','Папка сохранений':'Save directory','Резервная копия':'Create backup',
 'Сравнить два файла':'Compare saves','Сканировать папку игры':'Scan game folder',
 'Автопоиск игры':'Detect game automatically','Начало работы':'Getting started',
 'Отчёт: отсутствующие переводы':'Report: missing translations',
 'Импорт английского каталога':'Import English catalog',
 'Отчёт: отсутствующие иконки':'Report: missing icons',
 'Экспорт инвентаря в CSV':'Export inventory to CSV',
 'Отменить изменение':'Undo edit','Сбросить изменения':'Reset edits',
 'Избранное: выбранный предмет':'Favorite selected item'}

GROUP_EN={'quartz':'Quartz','equipment':'Equipment','consumables':'Consumables',
 'library':'Books & recipes','cosmetics':'Cosmetics','fishing':'Fishing','special':'Other items'}
CATEGORY_EN={'quartz_normal':'Standard quartz','quartz_master':'Master quartz',
 'weapon':'Weapons','armor':'Armor','shoes':'Footwear','accessory':'Accessories',
 'consumable':'Healing & combat','food':'Prepared dishes','ingredient':'Ingredients',
 'recipe':'Recipes','book':'Books & magazines','costume':'Outfits','face':'Cosmetic accessories',
 'hair':'Hairstyles','decoration':'Decorations','fish':'Fish','fishing_gear':'Fishing gear',
 'quest':'Quest & key items','material':'Materials & sepith','card':'Cards & minigames',
 'orbment':'EX Orbs & upgrades','other':'Other'}
