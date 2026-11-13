"""Cold Steel I Qt window, separated from the save engine.

All widgets are real Qt controls. Background/glow effects are painted on panels;
mouse movement never causes catalog re-population or wallpaper rescaling.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from itertools import groupby
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize, QRectF, QRect, QPoint, QPointF, Signal, Slot, QObject, QThread, QSignalBlocker, QUrl, QEvent, QItemSelection, QItemSelectionModel, QLibraryInfo, QTranslator
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics, QPolygonF, QPixmap, QIcon, QPainterPath, QLinearGradient, QBrush, QRadialGradient, QDesktopServices, QPixmapCache
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QLineEdit,
    QSpinBox, QComboBox, QCheckBox, QTreeWidget, QTreeWidgetItem, QTableView,
    QHeaderView, QAbstractItemView, QHBoxLayout, QVBoxLayout,
    QGridLayout, QStackedWidget, QMessageBox, QFileDialog, QScrollArea,
    QPlainTextEdit, QSizePolicy, QStyle, QStatusBar, QSizeGrip
)

from categories import GROUPS, CATEGORY_NAMES, category_of, item_in_category
from qt_backend import EditorCore, find_game_install, read_english_catalog, scan_game_tables, write_csv
from game_art import ASSETS, SHINING_POM_BAIT_ID, shared_game_art
from edit_changes import EditChanges
from qt_inventory_model import InventoryModel, ItemRow
from qt_first_launch import FirstLaunchPage
from qt_errors import error_text
from save_storage import SteamSaveStorage
from item_catalog import NOTEBOOK_IDS, STAT_NAMES
from version import VERSION
APP_NAME = "Cold Steel I Inventory Editor"
SAVE_FILTER = "Cold Steel I (*.dat *.bak)"
STAT_NAMES_RU = ("СИЛ", "ЗАЩ", "СА", "ЗА", "ТЧН", "УКЛ", "СКР", "ХОД", "ОЗ", "ОЭ")


from qt_hud_widgets import (hud_icon, HudButton, HudCheckBox, Backdrop, RailWatermark, GlassPanel, AngularTab,
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
    error=Signal(object)
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
        except Exception as exc:self.error.emit(exc)
        finally:self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self,core=None):
        super().__init__()
        self.core=core if core is not None else EditorCore(storage=SteamSaveStorage())
        self.setWindowTitle(f'{APP_NAME} v{VERSION}')
        self.art = shared_game_art()
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
        self._file_pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='cs1-file')
        self._file_job=None
        self._file_complete=None
        self._close_after_work=False
        self._startup_dismissed=False
        self._startup_forced=False
        self._scan_busy=False
        self._scan_stage=''
        self._scan_error=''
        self._scan_error_details=('','')
        self._scan_warning_count=0
        self._scan_succeeded=False
        self._scan_started_in_setup=False
        self._scan_silent=False
        self._icon_pixmaps={}
        self._category_icons={}
        self._category_nodes={'catalog':{},'inventory':{}}
        self._view_catalog=None
        self._view_english=None
        self._view_language=None
        self._startup_state=None
        self._visible_catalog={}
        self._search_details={}
        self._row_names={}
        self._search_names={}
        self._item_rows={}
        self.search_debounce={}
        self.edit_changes=EditChanges()
        self.cat_favorites_only=False
        self.inv_favorites_only=False
        self._quantity_user_edited=False
        self.language=self.core.language
        self._qt_translation=QTranslator(self)
        self._apply_qt_language()
        self._qt_setup()
        self.make_ui()
        self.retranslate()
        self.populate_categories()
        self.update_tables()
        self.show_item(None)
        self.show_section('catalog')
        self.resize_grip=QSizeGrip(self);self.resize_grip.setFixedSize(16,16)
        self.resize_grip.setToolTip(self.msg('Потяните, чтобы изменить размер окна','Drag to resize the window'))
        self.file_timer=QTimer(self)
        self.file_timer.setInterval(16)
        self.file_timer.timeout.connect(self._finish_file_job)
        self.initial_load_timer=QTimer(self)
        self.initial_load_timer.setSingleShot(True)
        self.initial_load_timer.timeout.connect(self.initial_load)
        self.initial_load_timer.start(0)

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
        self.crest = glass_label()
        self.crest.setFixedSize(125, 78)
        self.crest.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crest.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.crest.setAccessibleName('Thors Military Academy')
        self.emblem_art = QPixmap(str(ASSETS / 'thors.png'))
        if self.emblem_art.isNull():
            self.crest.setText('THORS')
        hl.addWidget(self.crest)
        branding=QVBoxLayout();branding.setSpacing(0)
        self.title=glass_label('Редактор сохранений','title',30)
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.subtitle=glass_label('COLD STEEL I · ИНВЕНТАРЬ','subtitle',12)
        self.subtitle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        branding.addWidget(self.title);branding.addWidget(self.subtitle)
        hl.addLayout(branding,1)
        self.logo_art = QPixmap(str(ASSETS / 'logo.png'))
        if not self.logo_art.isNull():
            from PySide6.QtGui import QRegion
            visible = QRegion(self.logo_art.mask()).boundingRect()
            if not visible.isEmpty():
                self.logo_art = self.logo_art.copy(visible)
            self.logo = glass_label()
            self.logo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            hl.addWidget(self.logo)
        self._refresh_branding_art()
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
        self.rail_watermark=RailWatermark()
        rl.addWidget(self.rail_watermark,1)
        self.rail_file=ElideLabel()
        self.rail_folder=ElideLabel(mode=Qt.TextElideMode.ElideMiddle)
        for label in (self.rail_file,self.rail_folder):
            label.setProperty('role','muted')
            label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
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
            'F5 — '+(self.msg('последнее сохранение','latest save') if self.core.storage else
                       self.msg('учебный инвентарь','sample inventory')),
            'Ctrl+O — '+self.msg('открыть сохранение','open a save'),
            'Ctrl+S — '+self.msg('сохранить копию','save a copy'),
            'Ctrl+Z — '+self.msg('отменить изменение','undo edit'),
            'Ctrl+F — '+self.msg('поиск в каталоге','catalog search'),
            self.msg('Щёлкните правой кнопкой по полю количества, чтобы выбрать значение.',
                     'Right-click the quantity field to choose a preset.'),
        ],count=False),'window')
        self.help_button.setIcon(hud_icon('help'));self.help_button.setFixedSize(32,32)
        self.help_button.setToolTip('Справка');fl.addWidget(self.help_button)
        entire.addWidget(self.footer_row)
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
        table=QTableView()
        table.setObjectName('inventoryTable')
        table.setModel(InventoryModel(self._icon, self.msg, table))
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
        selection = table.selectionModel()
        selection.selectionChanged.connect(lambda *_: self.selection_changed(table))
        selection.currentRowChanged.connect(lambda *_: self._sync_selection(table))
        table.horizontalHeader().sectionClicked.connect(lambda col:self.sort_rows(kind,col))
        return table

    def _searchbar(self,kind):
        inp=QLineEdit()
        inp.addAction(hud_icon('search',22),QLineEdit.ActionPosition.LeadingPosition)
        inp.setClearButtonEnabled(True)
        inp.setFixedHeight(37)
        timer=QTimer(inp);timer.setSingleShot(True);timer.setInterval(100)
        timer.timeout.connect(lambda:self.update_tables(kind))
        inp.textChanged.connect(lambda _text:timer.start())
        self.search_debounce[kind]=timer
        return inp

    def _make_catalog(self):
        page=QWidget();row=QHBoxLayout(page);row.setContentsMargins(0,0,0,0);row.setSpacing(10)
        row.addWidget(self._make_categories())
        content=QVBoxLayout();content.setSpacing(5)
        self.cat_search=self._searchbar('catalog')
        search_row=QHBoxLayout();search_row.setSpacing(5);search_row.addWidget(self.cat_search,1)
        self.cat_quick_favorite=add_button('★',lambda:self.toggle_quick_favorites('catalog'),'quick')
        self.cat_quick_favorite.setCheckable(True);self.cat_quick_favorite.setFixedSize(39,37)
        search_row.addWidget(self.cat_quick_favorite);content.addLayout(search_row)
        filters=QHBoxLayout();filters.setSpacing(8)
        self.missing=HudCheckBox('Только отсутствующие');self.present=QCheckBox('Только имеющиеся')
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
        self.source.currentIndexChanged.connect(lambda _i:self.update_tables('catalog'))
        self.filter_button.setMenu(menu);filters.addWidget(self.filter_button);content.addLayout(filters)
        self.catalog_counter=glass_label('','muted',9);self.catalog_counter.setObjectName('catalogCounter');self.catalog_counter.hide()
        self.cat_table=self._make_table('catalog');content.addWidget(self.cat_table,1)
        self.catalog_empty=glass_label('','muted',10)
        self.catalog_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.catalog_empty.setWordWrap(True)
        self.catalog_empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        empty_layout=QVBoxLayout(self.cat_table.viewport())
        empty_layout.setContentsMargins(16,12,16,12)
        empty_layout.addWidget(self.catalog_empty)
        self.catalog_empty.hide()
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
        self.inv_search=self._searchbar('inventory')
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
          ('Сохранения', [('Последнее сохранение' if self.core.storage else 'Учебный инвентарь',self.load_latest),
             ('Открыть вручную',self.open_save_dialog),
             ('Папка сохранений',self.open_save_dir),('Просмотр правок',self.show_changes),('Сравнить два файла',self.compare_dialog)]),
          ('Игра и дополнения',[('Сканировать папку игры',self.choose_game),('Автопоиск игры',lambda:self.scan_game(None)),('Начало работы',self.show_startup)]),
          ('Каталог и диагностика',[('Импорт английского каталога',self.import_english_dialog),('Отчёт: отсутствующие переводы',self.translation_report),
                                   ('Отчёт: отсутствующие иконки',self.icon_report),
                                   ('Экспорт инвентаря в CSV',self.export_csv)]),
          ('Настройки',[('Отменить изменение',self.undo),('Сбросить изменения',self.reset),
                        ('Избранное: выбранный предмет',self.favorite)])
        ]
        self.tools_title=glass_label('ИНСТРУМЕНТЫ И ДИАГНОСТИКА','section',14)
        grid.addWidget(self.tools_title,0,0,1,2)
        self.tool_groups=[]
        self.tool_btns={}
        for i,(name,items) in enumerate(specs):
            pane=GlassPanel();pl=QVBoxLayout(pane);pl.setContentsMargins(15,12,15,14)
            lbl=glass_label(name,'section',12);pl.addWidget(lbl)
            for title,fn in items:
                b=add_button(title,fn)
                b.setMinimumHeight(40);b.setMaximumHeight(42)
                pl.addWidget(b)
                self.tool_btns[title]=b
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
        labels=QHBoxLayout();labels.setSpacing(8)
        self.id_caption=glass_label('ID предмета','muted',10);self.qty_caption=ElideLabel();self.qty_caption.setProperty('role','muted')
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
        self.quantity_note=ElideLabel();self.quantity_note.setObjectName('quantityChange')
        self.quantity_note.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.quantity_note.setFixedHeight(21);l.addWidget(self.quantity_note)
        self.quantity_presets=QHBoxLayout();self.preset_buttons={}
        self.qty_preset_caption=glass_label('БЫСТРОЕ КОЛИЧЕСТВО','muted',9);self.qty_preset_caption.hide()
        from PySide6.QtWidgets import QMenu
        self.qty.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        def quick_menu(pos):
            menu=QMenu(self.qty)
            for amount in (1,10,50,99):
                a=menu.addAction(str(amount));a.setEnabled(amount<=self.qty.maximum())
                a.triggered.connect(lambda checked=False,v=amount:self.qty.setValue(v))
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
        self.update_tables('catalog')
    def _only_present(self,v):
        if v:
            with QSignalBlocker(self.missing):self.missing.setChecked(False)
        self.update_tables('catalog')

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
        if self.core.storage:
            self.open_save_dialog()
        else:
            self.load_latest()

    def refresh_startup(self,catalog_count=None):
        if not hasattr(self,'startup_page'):return
        count=len(self._catalog_view()) if catalog_count is None else catalog_count
        section=getattr(self,'current_section','catalog')
        needed=not count or self.core.save is None
        showing=section!='tools' and not self._startup_dismissed and (needed or self._startup_forced)
        source = self.core.source
        save_name = source.name if source else self.msg('Учебный инвентарь','Sample inventory') if self.core.save else ''
        state=dict(language=self.language,catalog_count=count,demo=self.core.storage is None,
                   save_name=save_name,busy=self._scan_busy,stage=self._scan_stage,error=self._scan_error,
                   error_details=self.msg(*self._scan_error_details),
                   warning_count=self._scan_warning_count)
        if state!=self._startup_state:
            self.startup_page.render_state(**state)
            self._startup_state=state
        self.startup_page.open_button.setEnabled(bool(count) and not self._scan_busy and self._file_job is None)
        self.pages.setCurrentWidget(self.startup_page if showing else {'catalog':self.catpage,'inventory':self.invpage,'tools':self.toolspage}[section])
        self.tabs.setVisible(section!='tools' and not showing)
        self.detail_shell.setVisible(section!='tools' and not showing)
        self.detail.setVisible(section!='tools' and not showing)
        self._refresh_view_footer()

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
        self._sync_selection(self.cat_table if section=='catalog' else self.inv_table)
        self.refresh_save_labels()

    def _apply_qt_language(self):
        app=QApplication.instance()
        app.removeTranslator(self._qt_translation)
        if self.language=='ru' and self._qt_translation.load(
                'qtbase_ru',QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
            app.installTranslator(self._qt_translation)

    def switch_language(self):
        self.language='en' if self.lang.currentIndex()==1 else 'ru'
        self.core.set_language(self.language)
        self._apply_qt_language()
        self.retranslate()
        self.refresh_catalog()

    def retranslate(self):
        t=self.msg
        self.crest.setAccessibleName(t('Военная академия Торс','Thors Military Academy'))
        if hasattr(self,'resize_grip'):
            self.resize_grip.setToolTip(t('Потяните, чтобы изменить размер окна','Drag to resize the window'))
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
        self.inventory_hint.setText(t('Предметы в загруженном сохранении','Items in the opened save') if self.core.storage else
                                    t('Предметы в учебном инвентаре','Items in the sample inventory'))
        self.missing.setText(t('Показывать только отсутствующие','Show missing only'))
        self.present.setText(t('Только имеющиеся','Owned only'))
        self.filter_button.setText(t('Фильтры ▾','Filters ▾'))
        self.owned_action.setText(t('Только имеющиеся','Owned only'))
        sources=(t('Все источники','All sources'),t('Основная игра','Base game'),t('Дополнения','DLC'))
        for action,text in zip(self.source_actions,sources):action.setText(text)
        for symbol,ru,en in [('minimize','Свернуть','Minimize'),('maximize','Развернуть / восстановить','Maximize / restore'),('close','Закрыть','Close')]:
            self.window_buttons[symbol].setToolTip(t(ru,en))
        self.help_button.setToolTip(t('Справка','Help'))
        selected_source=self.source.currentIndex()
        self.source.blockSignals(True);self.source.clear();self.source.addItems(sources)
        self.source.setCurrentIndex(max(0,selected_source));self.source.blockSignals(False)
        headers=(t('Предмет','Item'),'ID',t('Категория','Category'),t('В инвентаре','Owned'))
        for table in (self.cat_table,self.inv_table):
            table.model().set_headers(headers)
        self.add_one.setText(t('Установить по 1','Set 1 each'))
        self.add_bulk.setText(t('Задать количество','Apply to selected'))
        self.del_bulk.setText(t('Удалить выбранные','Remove selected'))
        self.detail_title.setText(t('ВЫБРАННЫЙ ПРЕДМЕТ','SELECTED ITEM'))
        self.id_caption.setText(t('ID предмета','Item ID'))
        self.apply_btn.setText(t('Применить количество','Apply quantity'))
        self.delete_btn.setText(t('Удалить предмет из сохранения','Delete from save'))
        self.undo_btn.setText(t('Отменить','Undo'))
        self.reset_btn.setText(t('Сбросить правки','Reset edits'))
        self.favorite_btn.setText('☆')
        self.favorite_btn.setToolTip(t('Добавить в избранное или удалить из него','Add to or remove from favorites'))
        self.description_title.setText(t('Описание и характеристики','Description & stats'))
        self.qty_preset_caption.setText(t('БЫСТРОЕ КОЛИЧЕСТВО','QUICK QUANTITY'))
        self.safe_note.setText(t('При перезаписи слота редактор создаёт резервную копию.',
                                 'Overwriting a slot creates a backup.') if self.core.storage else
                               t('Правки демонстрационного инвентаря хранятся в памяти.','Sample inventory edits are kept in memory.'))
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
             ('Сохранения','Saves'),('Игра и дополнения','Game & DLC'),('Каталог и диагностика','Catalog & diagnostics'),('Настройки','Settings')]):
             label.setText(t(ru,en))
        for ru,btn in self.tool_btns.items():
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
        latest = (('Последнее\nF5','Latest\nF5'), ('Последнее\nсохранение   F5','Latest\nsave   F5')) if self.core.storage else (
            ('Образец\nF5','Sample\nF5'), ('Учебный\nинвентарь   F5','Sample\ninventory   F5'))
        pairs=(
          (self.btn_latest,*latest),
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
        self.btn_latest.setToolTip(self.msg('Открыть последнее сохранение (F5)','Open latest save (F5)') if self.core.storage else
                                   self.msg('Загрузить учебный инвентарь (F5)','Load sample inventory (F5)'))
        self.btn_open.setToolTip(self.msg('Открыть сохранение (Ctrl+O)','Open save (Ctrl+O)'))
        self.btn_compare.setToolTip(self.msg('Сравнить инвентарь с другим файлом','Compare inventory with another file'))
        self.btn_overwrite.setToolTip(self.msg('Записать с резервной копией','Save with a backup'))
        self.btn_savecopy.setToolTip(self.msg('Сохранить отдельную копию (Ctrl+S)','Save a separate copy (Ctrl+S)'))
        self.big_icon.setFixedSize(74 if compact else 92,104 if compact else 112)
        self.detail.layout().setSpacing(3 if self.height()<800 else 7)
        self.detail.layout().setContentsMargins(18 if self.height()<800 else 22,10 if self.height()<800 else 15,18 if self.height()<800 else 22,16 if self.height()<800 else 25)
        margins=self.detail.layout().contentsMargins()
        field_width=(detail-margins.left()-margins.right()-self.big_icon.width()-14-8)//2
        for field,text,padding in ((self.id_field,'65535',18),(self.qty,'99',36)):
            field.ensurePolished()
            field.setMinimumWidth(field.fontMetrics().horizontalAdvance(text)+padding)
        id_caption=self.msg('ID предмета','Item ID')
        self.id_caption.ensurePolished()
        self.id_caption.setText('ID' if compact or self.id_caption.fontMetrics().horizontalAdvance(id_caption)>field_width else id_caption)
        self._refresh_quantity_caption()
        for button in (self.apply_btn,self.delete_btn,self.undo_btn,self.reset_btn):
            button.setFixedHeight(40 if self.height()<800 else 48)
        self.reset_btn.setText(self.msg('Сбросить','Reset') if compact else self.msg('Сбросить правки','Reset edits'))
        self.delete_btn.setText(self.msg('Удалить из сохранения','Delete from save') if compact else self.msg('Удалить предмет из сохранения','Delete from save'))
        if self.active_item_id is not None:
            self._set_big_icon(self.active_item_id,72 if compact else 90)

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
        quantities=self.core.save.quantities if self.core.save else {}
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
                        new_group=group not in self._category_nodes[kind]
                        count=sum(totals[k] for k,_ in subs)
                        parent=entry(tree,kind,group,ru if self.language=='ru' else GROUP_EN.get(group,ru),count)
                        parent.setHidden(kind=='catalog' and not count)
                        for key,label in subs:
                            child=entry(tree,kind,key,label if self.language=='ru' else CATEGORY_EN.get(key,key.title()),totals[key],parent)
                            child.setHidden(kind=='catalog' and not totals[key])
                        if new_group:parent.setExpanded(True)
                    if kind=='catalog':
                        entry(tree,kind,'favorites',self.msg('Избранное','Favorites'),len(self.core.favorites & visible.keys()))
                        entry(tree,kind,'recent',self.msg('Недавно добавленные','Recently added'),sum(i in visible for i in self.core.recent))
                    selection=self._category_nodes[kind].get(previous)
                    if kind=='catalog' and (selection is None or selection.isHidden()):
                        self.filter_group='all'
                        selection=self._category_nodes[kind]['all']
                    if not favorites and selection and not selection.isSelected():
                        tree.setCurrentItem(selection)
                finally:tree.setUpdatesEnabled(updates_enabled)

    def on_category(self,tree=None,kind='catalog'):
        tree=tree or self.cat_tree;item=tree.currentItem()
        if item is not None:
            value=item.data(0,Qt.ItemDataRole.UserRole)
            if kind=='catalog':
                self.filter_group=value;self.cat_favorites_only=False;self.cat_quick_favorite.setChecked(False)
            else:
                self.inv_filter_group=value;self.inv_favorites_only=False;self.inv_quick_favorite.setChecked(False)
            self.update_tables(kind)

    def sort_rows(self,kind,column):
        previous_column,descending=self.sort_keys[kind]
        self.sort_keys[kind]=(column,not descending if column==previous_column else False)
        if self.search_debounce[kind].isActive():
            self.update_tables(kind)
        else:
            table=self.cat_table if kind=='catalog' else self.inv_table
            self._present_rows(kind,table,list(table.model().rows))

    def _icon(self,item_id):
        if item_id in self._icon_pixmaps:return self._icon_pixmaps[item_id]
        item = self.core.native.get(item_id)
        if isinstance(item_id,str):
            icon=self.art.tile_icon(self.art.reference_tile(item_id))
        else:
            icon=self.art.item_icon(item_id,item) if item is not None else QIcon()
        self._icon_pixmaps[item_id] = icon
        return icon

    def _set_big_icon(self,item_id,side):
        item=self.core.native.get(item_id)
        if item is not None:
            picture=self.art.item_picture(item_id,item)
        elif isinstance(item_id,str) and item_id.startswith('fish:'):
            picture=self.art.fish_picture(int(item_id.removeprefix('fish:')))
        elif isinstance(item_id,str) and item_id.startswith('dlc:'):
            picture=self.art.tile(self.art.reference_tile(item_id))
        else:
            picture=QPixmap()
        if picture.isNull():
            self.big_icon.setText(self.msg('Нет иконки','No icon'))
            return
        dpr=self.devicePixelRatioF()
        pixels=round(side*dpr)
        key=f'cs1-item-{picture.cacheKey()}-{pixels}-{dpr}'
        px=QPixmapCache.find(key)
        if px is None:
            native=max(picture.width(),picture.height())
            # Whole-pixel enlargement keeps the original inventory sprites sharp.
            if native<=pixels:
                factor=pixels//native
                px=picture.scaled(picture.size()*factor,Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.FastTransformation) if factor>1 else QPixmap(picture)
            else:
                px=picture.scaled(pixels,pixels,Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
            px.setDevicePixelRatio(dpr)
            QPixmapCache.insert(key,px)
        self.big_icon.setPixmap(px)

    def event(self,event):
        result=super().event(event)
        if event.type()==QEvent.Type.DevicePixelRatioChange and hasattr(self,'logo_art'):
            self._refresh_branding_art()
            if self.active_item_id is not None:
                self._set_big_icon(self.active_item_id,72 if self.width()<1460 else 90)
        return result

    def _refresh_branding_art(self):
        dpr=self.devicePixelRatioF()
        for art,label,size in ((self.emblem_art,self.crest,QSize(74,74)),
                               (self.logo_art,getattr(self,'logo',None),QSize(151,62))):
            if art.isNull():
                continue
            pixmap=art.scaled(size*dpr,Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
            pixmap.setDevicePixelRatio(dpr)
            label.setPixmap(pixmap)

    def toggle_quick_favorites(self,kind):
        if kind=='catalog':
            self.cat_favorites_only=self.cat_quick_favorite.isChecked();tree=self.cat_tree
        else:
            self.inv_favorites_only=self.inv_quick_favorite.isChecked();tree=self.inv_tree
        active=self.cat_favorites_only if kind=='catalog' else self.inv_favorites_only
        with QSignalBlocker(tree):
            if active:
                tree.setCurrentItem(None)
            else:
                group=self.filter_group if kind=='catalog' else self.inv_filter_group
                tree.setCurrentItem(self._category_nodes[kind][group])
        self.update_tables(kind)
        if active and not self.core.favorites:
            self.show_toast('В избранном пока пусто. Нажмите на звёздочку в карточке предмета.',
                            'No favorites yet. Use the star on an item card to add one.')

    def _catalog_view(self):
        if self._view_catalog is not self.core.catalog:
            self._view_catalog=self.core.catalog
            self._visible_catalog=self.core.visible()
            self._search_details.clear()
            self._row_names.clear()
            self._search_names.clear()
            self._item_rows.clear()
            self._icon_pixmaps.clear()
            self._category_icons.clear()
        if self._view_english is not self.core.english or self._view_language!=self.language:
            self._view_english=self.core.english;self._view_language=self.language
            self._search_details.clear()
            self._row_names.clear()
            self._search_names.clear()
            self._item_rows.clear()
        return self._visible_catalog

    def _name_folded(self,iid):
        if iid not in self._search_names:
            self._search_names[iid]=self._row_name(iid).casefold()
        return self._search_names[iid]

    def _matches_search(self,needle,iid):
        if not needle or (isinstance(iid,int) and needle in str(iid)) or needle in self._name_folded(iid):
            return True
        if iid not in self._search_details:
            self._search_details[iid]=self.core.details_text(iid).casefold()
        return needle in self._search_details[iid]

    def _row_name(self,iid):
        if iid not in self._row_names:self._row_names[iid]=self.core.item_name(iid)
        return self._row_names[iid]

    def _rows_for(self,kind,quantities):
        visible=self._catalog_view()
        if kind=='inventory':
            rows=[]
            needle=self.inv_search.text().casefold().strip()
            for iid,quantity in quantities.items():
                record=self.core.catalog.get(iid,{})
                if self.inv_favorites_only:
                    if iid not in self.core.favorites:continue
                elif not item_in_category(record,self.inv_filter_group):continue
                if self._matches_search(needle,iid):
                    rows.append(self._item_row(iid,record,quantity))
            return rows
        rows=[]
        needle=self.cat_search.text().strip().casefold()
        source_filter=self.source.currentIndex()
        missing=self.missing.isChecked();present=self.present.isChecked()
        group='favorites' if self.cat_favorites_only else self.filter_group
        recent=set(self.core.recent) if group=='recent' else ()
        for iid,record in visible.items():
            if group=='favorites':
                if iid not in self.core.favorites:continue
            elif group=='recent':
                if iid not in recent:continue
            elif group!='all' and not item_in_category(record,group):continue
            qty=quantities.get(iid,0) if record['track_quantity'] else None
            if qty is None and (missing or present):continue
            if (missing and qty) or (present and not qty):continue
            if source_filter==1 and record['_source']=='dlc':continue
            if source_filter==2 and record['_source']=='base':continue
            if self._matches_search(needle,iid):
                rows.append(self._item_row(iid,record,qty))
        return rows

    def _item_row(self, item_id, record, quantity):
        change=self.edit_changes.changes.get(item_id)
        row=self._item_rows.get(item_id)
        if row is None or row.quantity!=quantity or row.change!=change:
            row=ItemRow(item_id,self._row_name(item_id),self.category_label(category_of(record)),quantity,change)
            if record:
                self._item_rows[item_id]=row
        return row

    def update_tables(self, only=None):
        self.edit_changes.refresh(self.core.save)
        quantities=self.core.save.quantities if self.core.save else {}
        for kind,table in (('catalog',self.cat_table),('inventory',self.inv_table)):
            if only and kind!=only:
                continue
            self.search_debounce[kind].stop()
            rows=self._rows_for(kind,quantities)
            self._present_rows(kind,table,rows)
            if kind=='catalog':
                self.catalog_counter.setText(self.msg(f'НАЙДЕНО ПРЕДМЕТОВ: {len(rows)}',f'ITEMS FOUND: {len(rows)}'))
                self._show_catalog_empty(not rows)
        if only:
            self._refresh_view_footer()
        else:
            self.refresh_save_labels()

    def _present_rows(self,kind,table,rows):
        col,reverse=self.sort_keys[kind]
        keys=(lambda row:self._name_folded(row.item_id),lambda row:row.item_id if isinstance(row.item_id,int) else 0,
              lambda row:row.category.casefold(),lambda row:row.quantity if row.quantity is not None else 0)
        rows.sort(key=keys[col],reverse=reverse)
        if col==1:
            rows.sort(key=lambda row:isinstance(row.item_id,str))
        elif col==3:
            rows.sort(key=lambda row:row.quantity is None)
        header=table.horizontalHeader()
        order=Qt.SortOrder.DescendingOrder if reverse else Qt.SortOrder.AscendingOrder
        if header.sortIndicatorSection()!=col or header.sortIndicatorOrder()!=order:
            header.setSortIndicator(col,order)
        self._set_table_rows(table,rows)
        self.selection_changed(table)

    def _show_catalog_empty(self,empty):
        self.catalog_empty.setVisible(empty)
        if not empty:return
        if not self.core.catalog:
            text=self.msg('Загрузите каталог из папки игры.','Load the catalog from the game folder.')
        elif self.cat_favorites_only or self.filter_group=='favorites':
            text=self.msg('В избранном пока нет предметов по текущим фильтрам.',
                          'No favorites match the current filters.')
        elif self.filter_group=='recent' and not self.core.recent:
            text=self.msg('Недавно добавленных предметов пока нет.','No recently added items yet.')
        else:
            text=self.msg('Предметы не найдены. Проверьте поиск и фильтры.',
                          'No items found. Check the search and filters.')
        self.catalog_empty.setText(text)

    def _set_table_rows(self, table, rows):
        model=table.model()
        selection=table.selectionModel()
        selected=self.selected_ids(table)
        old_current=table.currentIndex()
        current=old_current.data(Qt.ItemDataRole.UserRole)
        current_column=max(0,old_current.column())
        top=model.index(table.rowAt(0),0).data(Qt.ItemDataRole.UserRole)
        with QSignalBlocker(selection):
            if not model.replace_rows(rows):
                return
            restored=QItemSelection()
            positions=sorted(model.positions[item_id] for item_id in selected if item_id in model.positions)
            for _,run in groupby(enumerate(positions),key=lambda entry:entry[1]-entry[0]):
                first=last=next(run)[1]
                for _,last in run:
                    pass
                restored.select(model.index(first,0),model.index(last,0))
            selection.select(restored,QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
            current_index=model.index_for_id(current)
            selection.setCurrentIndex(current_index.siblingAtColumn(current_column),QItemSelectionModel.SelectionFlag.NoUpdate)
        top_index=model.index_for_id(top)
        if top_index.isValid():
            table.scrollTo(top_index,QAbstractItemView.ScrollHint.PositionAtTop)
        elif current_index.isValid() and current in selected:
            table.scrollTo(current_index)
        else:
            table.scrollToTop()

    def category_label(self,key):
        if self.language=='ru':return CATEGORY_NAMES.get(key,key)
        return CATEGORY_EN.get(key,key.title())

    def selected_ids(self,table):
        return [index.data(Qt.ItemDataRole.UserRole) for index in table.selectionModel().selectedRows()]

    def _sync_selection(self,table,ids=None):
        section=getattr(self,'current_section','catalog')
        if section=='tools' or table is not (self.cat_table if section=='catalog' else self.inv_table):
            return
        if ids is None:
            ids=self.selected_ids(table)
        current=table.currentIndex().data(Qt.ItemDataRole.UserRole)
        item_id=current if current in ids else self.active_item_id if self.active_item_id in ids else (ids[-1] if ids else None)
        if self.active_item_id!=item_id:
            self.show_item(item_id)

    def selection_changed(self,table):
        ids=self.selected_ids(table)
        self._sync_selection(table,ids)
        bar,label=(self.bulk_bar,self.selection_info) if table is self.cat_table else (self.inv_bulk_bar,self.inv_selection_info)
        label.setText(self.msg('Выделено: ','Selected: ')+str(len(ids)))
        bar.setVisible(len(ids)>1)
        self._refresh_bulk_controls(table,ids)

    def _refresh_quantity_caption(self):
        item=self.core.native.get(self.active_item_id)
        tracked=self.core.catalog.get(self.active_item_id,{}).get('track_quantity',True)
        limit=item.limit if tracked and item and 1<=item.limit<=99 else None
        if limit is None:
            self.qty_caption.setText(self.msg('Количество','Quantity'))
            self.qty_caption.setToolTip('')
            self.qty.setAccessibleName(self.qty_caption.text())
        else:
            self.qty_caption.setText(self.msg(f'Макс. {limit}',f'Max {limit}'))
            tip=self.msg(f'Допустимое количество: 0–{limit}',f'Allowed quantity: 0–{limit}')
            self.qty_caption.setToolTip(tip)
            self.qty.setAccessibleName(tip)

    def _set_description(self,text):
        if self.description.toPlainText()!=text:
            self.description.setPlainText(text)

    def show_item(self,iid):
        self.active_item_id=iid
        self._quantity_user_edited=False
        editable=self.core.can_edit(iid)
        self.favorite_btn.setEnabled(isinstance(iid,int))
        self._refresh_quantity_caption()
        if iid is None:
            with QSignalBlocker(self.qty):
                self.qty.setSpecialValueText('')
                self.qty.setMaximum(99)
                self.qty.setValue(0)
            self.item_name.setText(self.msg('Выберите предмет','Select an item'))
            self.item_category.setText('');self.id_field.clear()
            self._set_description(self.msg('Выберите предмет, чтобы увидеть его описание.',
                                           'Select an item to see its description.'))
            self.big_icon.clear();self.big_icon.setToolTip('');self.favorite_btn.setText('☆')
            self.refresh_quantity_note()
            return
        record=self.core.catalog.get(iid,{})
        item=self.core.native.get(iid)
        self.item_name.setText(self.core.item_name(iid))
        category=self.category_label(category_of(record))
        if item is not None:
            source={
                'dlc':self.msg('Дополнение','DLC'),
                'base':self.msg('Основная игра','Base game'),
                'both':self.msg('Основная игра и дополнения','Base game & DLC'),
            }[record['_source']]
            category+=' · '+source
        self.item_category.setText(category)
        self.id_field.setText(str(iid) if isinstance(iid,int) else '—')
        owned=self.core.quantity(iid)
        change=self.edit_changes.changes.get(iid)
        with QSignalBlocker(self.qty):
            tracked=record.get('track_quantity',True)
            self.qty.setSpecialValueText('' if tracked else '—')
            self.qty.setMaximum(item.limit if item and 1<=item.limit<=99 else max(owned,99))
            self.qty.setValue((owned if owned or change or not editable else 1) if tracked else 0)
        description=self.core.details_text(iid).strip()
        if isinstance(iid,str):
            description=' '.join(description.split())
        if description in ('◆','◇','-','—'):
            description=''
        stats=''
        if item is not None:
            labels=STAT_NAMES_RU if self.language=='ru' else STAT_NAMES
            stats=' · '.join(f'{label} {value:+d}{"%" if name in ("ACC","EVA") else ""}'
                             for name,label,value in zip(STAT_NAMES,labels,item.stats) if value)
        self._set_description('\n\n'.join(part for part in (description,stats) if part) or
                              self.msg('Описание и характеристики отсутствуют.','No description or stats available.'))
        self.favorite_btn.setText('★' if iid in self.core.favorites else '☆')
        self._set_big_icon(iid,72 if self.width()<1460 else 90)
        if self.big_icon.pixmap().isNull():
            icon_tip=self.msg('Оригинальная иконка недоступна', 'Original icon unavailable')
        elif iid==SHINING_POM_BAIT_ID and not self.art.shining_pom.isNull():
            icon_tip=self.msg('Сияющий пом из боевого блокнота', 'Shining Pom from the battle notebook')
        else:
            icon_tip=self.msg('Оригинальная иконка Cold Steel I', 'Original Cold Steel I icon')
        self.big_icon.setToolTip(icon_tip)
        self.refresh_quantity_note()

    def _quantity_edited(self,_value):
        self._quantity_user_edited=True
        self.refresh_quantity_note()

    def has_pending_quantity(self):
        return bool(self.core.save and self._quantity_user_edited and self.active_item_id is not None and self.qty.value()!=self.core.quantity(self.active_item_id))

    def refresh_quantity_note(self):
        iid=self.active_item_id
        current=self.core.quantity(iid)
        pending=self.qty.value()
        editable=self._file_job is None and self.core.can_edit(iid)
        self.qty.setEnabled(editable)
        self.apply_btn.setEnabled(editable and pending!=current)
        self.delete_btn.setEnabled(editable and current>0)
        if self.bulk_bar.isVisible():
            self._refresh_bulk_controls(self.cat_table,self.selected_ids(self.cat_table))
        if iid is None:
            self.quantity_note.setText('')
            return
        before=self.edit_changes.before.get(iid,0)
        if isinstance(iid,str) and iid.startswith('dlc:'):
            text=self.msg('Набор дополнения · справочно','DLC pack · reference only')
        elif isinstance(iid,str):
            text=self.msg('Запись журнала рыбалки · справочно','Fishing notebook entry · reference only')
        elif iid in NOTEBOOK_IDS:
            text=self.msg('Служебная вкладка блокнота · только просмотр',
                          'Notebook tab · read-only')
        elif not self.core.catalog.get(iid,{}).get('track_quantity',True):
            text=self.msg('Сепит учитывается отдельно от предметов','Sepith is tracked separately from items')
        elif self.core.is_equipped_master(iid):
            text=self.msg(f'В инвентаре: {current} · мастер-кварц экипирован',
                          f'Owned: {current} · Master quartz equipped')
        elif (item:=self.core.native.get(iid)) and not item.editable:
            text=self.msg(f'В инвентаре: {current} · только просмотр',f'Owned: {current} · read-only')
        elif pending!=current and self._quantity_user_edited:
            text=self.msg(f'Сейчас: {current}  →  После применения: {pending}',f'Current: {current}  →  After applying: {pending}')
        elif before!=current:
            text=self.msg(f'Было: {before}  →  Сейчас: {current}',f'Original: {before}  →  Current: {current}')
        else:
            text=self.msg(f'В инвентаре: {current}',f'Owned: {current}')
        self.quantity_note.setText(text)

    def _refresh_bulk_controls(self,table,ids):
        enabled=self._file_job is None and bool(ids)
        if table is self.cat_table:
            can_apply=enabled and all(self.core.can_edit(i) for i in ids)
            self.add_one.setEnabled(can_apply)
            limit=min((self.core.native[i].limit for i in ids),default=0) if can_apply else 0
            self.add_bulk.setEnabled(can_apply and self.qty.value()<=limit)
            self.add_bulk.setToolTip(self.msg(f'Лимит для выбранных: {limit}',f'Selection limit: {limit}') if can_apply else '')
        else:
            self.del_bulk.setEnabled(enabled and all(self.core.can_delete(i) for i in ids))

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
        self.notice.setToolTip('')
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

    def _run_file(self,action,complete):
        if self._file_job is not None or self._close_after_work:
            return False
        self._file_complete=complete
        self._file_job=self._file_pool.submit(action)
        self.file_timer.start()
        self.refresh_save_labels()
        return True

    def _finish_file_job(self):
        job=self._file_job
        if job is None or not job.done():
            return
        self.file_timer.stop()
        complete=self._file_complete
        self._file_job=self._file_complete=None
        self._handle(lambda:complete(job.result()))
        self.refresh_save_labels()
        if self._close_after_work:
            QTimer.singleShot(0,self.close)

    def _apply(self,changes):
        if self._file_job is not None:
            return
        def run():
            before=self.core.save.quantities if self.core.save else None
            self.core.change(changes)
            self.populate_categories();self.update_tables();self.show_item(self.active_item_id)
            if self.core.save and self.core.save.quantities is not before:
                self.show_toast('Правки применены. Их можно просмотреть.', 'Edits applied. You can review them.')
        return self._handle(run)

    def apply_single(self):
        if not self.core.can_edit(self.active_item_id):return
        self._apply({self.active_item_id:self.qty.value()})

    def apply_bulk(self,qty=None):
        ids=self.selected_ids(self.cat_table)
        if not ids:
            QMessageBox.information(self,'CS1',self.msg('Выберите предметы в каталоге','Select items in the catalog'));return
        amount=self.qty.value() if qty is None else qty
        self._apply({i:amount for i in ids})

    def delete_single(self):
        if self.core.can_delete(self.active_item_id):self._apply({self.active_item_id:0})

    def delete_bulk(self):
        ids=self.selected_ids(self.inv_table)
        if ids and QMessageBox.question(self,'CS1',self.msg(f'Удалить выбранные предметы: {len(ids)}?',f'Remove {len(ids)} selected items?'))==QMessageBox.StandardButton.Yes:
            self._apply({i:0 for i in ids})

    def undo(self):
        if self._file_job is not None:return
        changed=self._handle(lambda:self.core.undo())
        if changed:
            self.populate_categories()
            self.update_tables()
            self._refresh_selected_item()
            self.show_toast('Последнее изменение отменено','Last change undone')

    def reset(self):
        if self._file_job is not None:return
        if self.core.save and QMessageBox.question(self,'CS1',self.msg('Сбросить несохранённые изменения?', 'Discard unsaved changes?'))==QMessageBox.StandardButton.Yes:
            self.core.reset();self.populate_categories();self.update_tables();self.show_item(self.active_item_id)
            self.show_toast('Правки сброшены к исходному файлу','Edits reset to the original file')

    def favorite(self):
        item_id=self.active_item_id
        if not isinstance(item_id,int):return
        self._handle(lambda:self.core.toggle_favorite(item_id))
        self.populate_categories();self.update_tables()
        added=item_id in self.core.favorites
        if self.active_item_id==item_id:self.favorite_btn.setText('★' if added else '☆')
        if added:self.show_toast('Предмет добавлен в избранное','Item added to favorites')
        else:self.show_toast('Предмет удалён из избранного','Item removed from favorites')

    def confirm_dirty(self):
        if (self.core.save and self.core.save.changed) or self.has_pending_quantity():
            return QMessageBox.question(self,'CS1',self.msg('Несохранённые изменения будут потеряны. Продолжить?',
                'Unsaved changes will be lost. Continue?')) == QMessageBox.StandardButton.Yes
        return True

    def open_save_dialog(self):
        if self._file_job is not None:return
        if self.core.storage:
            filename, _ = QFileDialog.getOpenFileName(
                self, self.msg('Открыть сохранение Steam', 'Open a Steam save'),
                str(self.core.save_directory), SAVE_FILTER,
            )
            if filename and self.confirm_dirty():
                self.open_save(Path(filename))
            return
        choice = QMessageBox.question(
            self, APP_NAME,
            self.msg('Загрузить учебный инвентарь заново?', 'Reload the sample inventory?'),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice == QMessageBox.StandardButton.Yes:
            self.load_latest()

    def open_save(self, path: Path | None = None):
        return self._run_file(lambda:self.core.read_save(path),self._open_save_finished)

    def _open_save_finished(self,session):
        source=self.core.use_opened_save(session)
        for table in (self.cat_table, self.inv_table):
            with QSignalBlocker(table.selectionModel()):
                table.selectionModel().clear()
        self.show_item(None)
        self.populate_categories()
        self.update_tables()
        self.navigate_section('inventory')
        self.show_toast(f'Сохранение открыто: {source.name}', f'Save opened: {source.name}')

    def load_latest(self):
        if self._file_job is not None or not self.confirm_dirty():
            return
        if self.core.storage:
            self.open_save()
            return
        if not self.core.load_demo():
            self.show_toast('Сначала загрузите каталог игры.', 'Load the game catalog first.')
            return
        for table in (self.cat_table,self.inv_table):
            with QSignalBlocker(table.selectionModel()):
                table.selectionModel().clear()
        self.show_item(None)
        self.populate_categories()
        self.update_tables()
        self.navigate_section('inventory')
        self.show_toast('Учебный инвентарь загружен.', 'Sample inventory loaded.')

    def save_copy_dialog(self):
        if self._file_job is not None or self.core.save is None or not self.show_changes('copy'):
            return
        source = self.core.source
        if source is None:
            return
        preferred = source.with_name(source.stem.split('.dat.', 1)[0] + '_edited.dat')
        filename, _ = QFileDialog.getSaveFileName(
            self, self.msg('Сохранить отдельную копию', 'Save a separate copy'), str(preferred), 'Cold Steel I (*.dat)',
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if filename:
            write=partial(self.core.storage.save_copy,self.core.save,Path(filename),self.core.native)
            self._run_file(write,self._save_copy_finished)

    def _save_copy_finished(self,destination):
        self.show_toast(f'Копия сохранена: {destination.name}', f'Copy saved: {destination.name}')
        self.notice.setToolTip(str(destination))

    def overwrite_dialog(self):
        if self._file_job is not None or not self.core.save or not self.core.save.changed:
            return
        if not self.show_changes('overwrite') or self.core.source is None:
            return
        write=partial(self.core.storage.overwrite,self.core.save,self.core.native)
        self._run_file(write,self._overwrite_finished)

    def _overwrite_finished(self,result):
        session,backup=result
        self.core.use_overwritten_save(session,backup)
        self.update_tables()
        self._refresh_selected_item()
        if backup:
            self.show_toast(f'Сохранено. Резервная копия: {backup.name}', f'Saved. Backup: {backup.name}')
            self.notice.setToolTip(str(backup))

    def compare_dialog(self):
        if self._file_job is not None or self.core.save is None:
            return
        source = self.core.source
        if source:
            filename, _ = QFileDialog.getOpenFileName(
                self, self.msg('Выбрать файл для сравнения', 'Choose a file to compare'), str(source.parent), SAVE_FILTER,
            )
            if not filename:
                return
            path=Path(filename)
            self._run_file(lambda:self.core.compare(path),lambda result:self._show_comparison(result,path.name))
            return
        else:
            self.edit_changes.refresh(self.core.save)
            counts = self.edit_changes.counts()
            self._show_comparison(tuple(counts[key] for key in ('added','removed','modified')))

    def _show_comparison(self,result,filename=None):
        if self._close_after_work:
            return
        added,removed,modified=result
        if filename:
            heading=self.msg(f'Сравнение текущего инвентаря с файлом {filename}',f'Current inventory compared with {filename}')
        else:
            heading=self.msg('Сравнение с исходным учебным инвентарём.','Comparison with the original sample inventory.')
        summary = self.msg(
            f'{heading}\n\nДобавлено: {added}\nУдалено: {removed}\nИзменено: {modified}',
            f'{heading}\n\nAdded: {added}\nRemoved: {removed}\nModified: {modified}',
        )
        QMessageBox.information(self, self.msg('Сравнение инвентаря','Compare inventory'), summary)

    def choose_game(self):
        folder=QFileDialog.getExistingDirectory(self,self.msg('Папка игры','Game directory'),self.core.settings.get('game_root',''))
        if folder:self.scan_game(Path(folder))

    def scan_game(self,path=None,silent=False):
        if self.scan_thread is not None or self._close_after_work:return
        self._scan_started_in_setup=self.pages.currentWidget() is self.startup_page
        self._scan_busy=True;self._scan_stage='locating';self._scan_error='';self._scan_error_details=('','')
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
        self.scan_thread.finished.connect(self.on_scan_finished)
        self.scan_thread.finished.connect(self.scan_thread.deleteLater)
        self.scan_thread.start()

    @Slot(str)
    def on_scan_stage(self,stage):
        self._scan_stage=stage;self.refresh_startup()

    @Slot(object)
    def on_scan_result(self,result):
        self._scan_stage='saving';self.refresh_startup()
        try:self.core.apply_scan_result(result)
        except Exception as exc:
            self.on_scan_error(exc,self._scan_silent);return
        self._scan_succeeded=True;self._scan_error=''
        self._scan_warning_count=len(result.errors)
        details='\n'.join(result.errors[:6])
        self._scan_error_details=tuple(error_text(details,lang) for lang in ('ru','en'))
        self.refresh_catalog()
        self.scan_state.setText(self.scan_summary(result))
        if result.errors and not self._scan_started_in_setup and not self._scan_silent:
            QMessageBox.warning(self,'TBL',error_text('\n'.join(result.errors[:6]),self.language))

    def scan_summary(self,result):
        n=len(result.files);m=len(result.items)
        return self.msg(f'Сканировано таблиц: {n}, предметов: {m}',
                        f'Scanned {n} '+('table' if n==1 else 'tables')+f'; {m} '+('item' if m==1 else 'items'))

    @Slot(object)
    def on_scan_error(self,error,silent=False):
        silent=silent or self._scan_silent
        self._scan_succeeded=False
        self._scan_error='not_found' if str(error)=='Game directory not found' else 'unreadable'
        self._scan_error_details=tuple(error_text(error,lang) for lang in ('ru','en'))
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
            count=len(self._catalog_view())
            self.show_toast(f'Каталог загружен. Предметов: {count}',f'Catalog loaded. Items: {count}')
        if self._close_after_work:
            QTimer.singleShot(0,self.close)

    def open_save_dir(self):
        if self.core.storage and self.core.save_directory.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.core.save_directory)))
        else:
            self.show_toast('Папка сохранений недоступна.', 'The save directory is unavailable.')

    def translation_report(self):
        missing = [f'{item_id}: {name}' for item_id, name in self.core.missing_translations()]
        self.show_report(self.msg('Непереведённые записи','Untranslated records'),missing)

    def import_english_dialog(self):
        if self._file_job is not None:return
        path,_=QFileDialog.getOpenFileName(self,self.msg('Импорт оригинального английского каталога','Import an original English catalog'),'',
                                          'Cold Steel I catalog (*.tbl)')
        if not path:return
        self._run_file(lambda:read_english_catalog(Path(path)),self._english_catalog_finished)

    def _english_catalog_finished(self,records):
        self.core.english=records
        self.refresh_catalog()
        count=len(records)
        self.show_toast(f'Английский каталог загружен: {count} предметов',f'English catalog loaded: {count} items')

    def refresh_catalog(self):
        catalog_changed=self._view_catalog is not self.core.catalog
        self.populate_categories()
        self.update_tables()
        if catalog_changed:
            for table in (self.cat_table,self.inv_table):
                table.model().refresh_icons()
        self._refresh_selected_item()

    def _refresh_selected_item(self):
        pending=self.qty.value()
        edited=self.has_pending_quantity()
        self.show_item(self.active_item_id)
        if edited and self.core.can_edit(self.active_item_id):
            self.qty.setValue(pending)
            self._quantity_user_edited=True
            self.refresh_quantity_note()

    def icon_report(self):
        missing=[]
        for i,record in self.core.visible().items():
            if self._icon(i).isNull():missing.append(f'{i}: {self.core.item_name(i)}')
        self.show_report(self.msg('Отсутствующие оригинальные иконки','Missing original icons'),missing)

    def show_report(self,title,lines,count=True):
        prefix=(self.msg('Найдено: ','Found: ')+str(len(lines))+'\n') if count else ''
        message=prefix+'\n'.join(lines[:60])
        if len(lines)>60:
            remaining=len(lines)-60
            message+=self.msg(f'\n… ещё {remaining}',f'\n… {remaining} more')
        QMessageBox.information(self,title,message)

    def export_csv(self):
        if self._file_job is not None or not self.core.save:return
        filename,_=QFileDialog.getSaveFileName(
            self,self.msg('Экспорт инвентаря','Export inventory'),'CS1_inventory.csv','CSV (*.csv)',
            options=QFileDialog.Option.DontConfirmOverwrite)
        if not filename:return
        rows=self.core.export_rows()
        self._run_file(partial(write_csv,Path(filename),rows,self.language),
                       lambda path:self.show_toast('CSV сохранён: '+path.name,'CSV exported: '+path.name))

    def refresh_save_labels(self):
        self.edit_changes.refresh(self.core.save)
        loaded = self.core.save is not None
        source = self.core.source
        backup = self.core.last_backup
        if source:
            self.rail_file.setText(source.name)
            self.rail_folder.setText(str(source.parent))
            stamp = self.core.save.modified_at
            self.rail_date.setText(datetime.fromtimestamp(stamp).strftime('%d.%m.%Y %H:%M') if stamp else '—')
            self.rail_state.setText(self.msg('Копия создана','Backup created') if backup else
                                    self.msg('Файл загружен','File loaded'))
            self.save_line.setText(self.msg(f'Открыто: {source}', f'Opened: {source}'))
        else:
            self.rail_file.setText(self.msg('Учебный инвентарь','Sample inventory') if loaded else '—')
            self.rail_folder.setText(self.msg('В памяти','In memory') if loaded else '—')
            self.rail_folder.setToolTip('')
            self.rail_date.setText('—')
            self.rail_state.setText(self.msg('Образец загружен','Sample loaded') if loaded else self.msg('Нет данных','No data'))
            self.save_line.setText(self.msg('Учебный инвентарь · правки в памяти','Sample inventory · edits in memory')
                                   if loaded else self.msg('Сохранение Steam не открыто.','No Steam save open.'))
        self.rail_state.setToolTip(str(backup) if backup else '')
        busy=self._file_job is not None
        dirty=bool(self.core.save and self.core.save.changed)
        if busy:
            state='dirty'
            status=self.msg('РАБОТА С ФАЙЛОМ…','FILE OPERATION IN PROGRESS…')
        elif dirty:
            state='dirty'
            status=self.msg('● ЕСТЬ ПРАВКИ','● UNSAVED EDITS')
        elif self.core.save:
            state='clean'
            status=(self.msg('РЕЗЕРВНАЯ КОПИЯ СОЗДАНА','BACKUP CREATED') if backup else
                    self.msg('✓ БЕЗ ИЗМЕНЕНИЙ','✓ NO CHANGES') if source else self.msg('ДЕМО · В ПАМЯТИ','DEMO · IN MEMORY'))
        else:
            state='empty'
            status=self.msg('○ НЕТ ДАННЫХ','○ NO DATA')
        self.dirty_chip.setText(status)
        if self.dirty_chip.property('state')!=state:
            self.dirty_chip.setProperty('state',state)
            self.dirty_chip.style().unpolish(self.dirty_chip)
            self.dirty_chip.style().polish(self.dirty_chip)
        self.dirty_chip.setToolTip(str(backup) if backup else self.msg('Правки хранятся в памяти до записи.',
                                                                      'Edits are kept in memory until saved.'))
        visible=self._catalog_view();n=self.core.save.occupied_count if self.core.save else 0
        self.footer_aux.setText(self.msg(f'Инвентарь: {n}   ·   Правок: {len(self.edit_changes.changes)}',f'Inventory: {n}   ·   Edits: {len(self.edit_changes.changes)}'))
        self.review_button.setText(self.msg(f'Правки: {len(self.edit_changes.changes)}',f'Edits: {len(self.edit_changes.changes)}'))
        self.review_button.setVisible(dirty)
        self.review_button.setToolTip(self.msg('Просмотреть все изменения перед записью','Review every change before saving'))
        for button in (self.cat_quick_favorite,self.inv_quick_favorite):
            button.setToolTip(self.msg(f'Избранное: {len(self.core.favorites)} · нажмите, чтобы отфильтровать список',
                                       f'Favorites: {len(self.core.favorites)} · click to filter'))
        self.refresh_quantity_note()
        self._refresh_bulk_controls(self.cat_table,self.selected_ids(self.cat_table))
        self._refresh_bulk_controls(self.inv_table,self.selected_ids(self.inv_table))
        can_undo=not busy and bool(self.core.undo_stack)
        can_reset=not busy and dirty
        can_use_save=not busy and loaded
        self.undo_btn.setEnabled(can_undo)
        self.reset_btn.setEnabled(can_reset)
        self.btn_latest.setEnabled(not busy)
        self.btn_open.setEnabled(not busy)
        self.btn_compare.setEnabled(can_use_save)
        self.btn_savecopy.setEnabled(can_use_save)
        self.btn_overwrite.setEnabled(can_reset and (source is None or source.suffix.lower()=='.dat'))
        for key,enabled in (
                ('Последнее сохранение',not busy),('Учебный инвентарь',not busy),('Открыть вручную',not busy),
                ('Просмотр правок',loaded),('Сравнить два файла',can_use_save),
                ('Экспорт инвентаря в CSV',can_use_save),('Импорт английского каталога',not busy),
                ('Отменить изменение',can_undo),('Сбросить изменения',can_reset)):
            if key in self.tool_btns:
                self.tool_btns[key].setEnabled(enabled)
        self.refresh_startup(len(visible))

    def _refresh_view_footer(self):
        if self.pages.currentWidget() is self.startup_page:
            self.footer.setText(self.msg('Начало работы','Getting started'))
            return
        visible=len(self._catalog_view())
        section=getattr(self,'current_section','catalog')
        catalog=section=='catalog'
        rows=(self.cat_table if catalog else self.inv_table).model().rowCount()
        caption=self.msg('Избранное','Favorites') if (self.cat_favorites_only if catalog else self.inv_favorites_only) else self.msg('В выбранной группе','In this view')
        total=self.msg(f'Позиций в каталоге: {visible}',f'Catalog entries: {visible}')
        self.footer.setText(total if section=='tools' else f'{total}   |   {caption}: {rows}')

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
        if self._file_job is not None or self.scan_thread is not None:
            self._close_after_work=True
            event.ignore()
            return
        self._close_after_work=False
        if not self.confirm_dirty():event.ignore();return
        self.initial_load_timer.stop()
        self._file_pool.shutdown(wait=False)
        QApplication.instance().removeTranslator(self._qt_translation)
        super().closeEvent(event)


TOOL_EN={
 'Последнее сохранение':'Latest save',
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
 'consumable':'Battle items','food':'Prepared dishes','ingredient':'Ingredients',
 'recipe':'Recipes','book':'Books & magazines','costume':'Outfits','face':'Cosmetic gear',
 'decoration':'ARCUS covers','fish':'Fish','fishing_gear':'Fishing gear','fish_book':'Fishing notebooks',
 'quest':'Quest & key items','material':'Materials & sepith','card':'Minigame items',
 'orbment':'Quest orbs','dlc_pack':'DLC packs','other':'Other'}
