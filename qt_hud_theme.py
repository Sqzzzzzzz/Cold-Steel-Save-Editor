"""Single Cold Steel I glass HUD theme for the native Qt editor."""

from game_art import ASSETS

HUD_STYLESHEET = r'''
QWidget {color:#FFEAED;font-family:'Segoe UI','DejaVu Sans';font-size:14px;font-weight:400;}
QWidget#canvas,QFrame,QLabel,QWidget#detailInner,QWidget#toolsInner {background:transparent;border:0;}
QWidget#titleBar {background:transparent;border-bottom:1px solid rgba(238,219,222,155);}
QLabel[role="title"] {font-family:'Cambria','DejaVu Serif';font-size:38px;font-weight:400;color:#FAFAF8;}
QLabel[role="subtitle"] {font-family:'Cambria','DejaVu Serif';font-size:17px;color:#E1CFD2;}
QLabel[role="section"] {font-size:16px;font-weight:500;color:#FFEAED;}
QLabel[role="muted"] {color:#E3D1D3;}
QLabel[role="itemName"] {font-size:20px;font-weight:600;color:#F6FAFC;}
QLabel[role="descriptionTitle"] {font-size:17px;color:#FCE8EB;}
QLabel#fieldCaption {font-size:13px;}
QLabel#heroIcon {background:transparent;border:0;}
QFrame#hudSeparator {background:rgba(215,198,200,143);border:0;}
QPushButton {background:transparent;border:0;padding:0;font-weight:400;font-size:14px;}
QPushButton[role="filter"] {font-size:12px;}
QLineEdit,QSpinBox,QComboBox {
  background:rgba(23,29,41,215);border:1px solid #ABB2C0;border-radius:3px;
  color:#FFEBEE;selection-background-color:#9F2840;padding:4px 8px;
  font-weight:400;font-size:14px;
}
QLineEdit:focus,QSpinBox:focus,QComboBox:focus {border:1px solid #F9E6E8;}
QLineEdit {selection-color:white;}
QLineEdit:read-only {background:rgba(36,29,33,160);color:#FEE9EC;}
QSpinBox:disabled {background:#252936;border-color:#626775;color:#B8ABAE;}
QComboBox {padding-right:22px;}
QComboBox#languageSwitch {font-size:12px;background:rgba(41,33,37,150);border-color:rgba(190,175,177,130);}
QComboBox QAbstractItemView {background:#303745;border:1px solid #C67179;color:#FFEDF0;selection-background-color:#A0212C;}
QSpinBox {padding-right:20px;}
QCheckBox {spacing:9px;color:#F5E2E4;font-size:13px;background:transparent;}
QCheckBox::indicator {width:15px;height:15px;border:1px solid #BEAFB1;border-radius:1px;background:#303746;}
QCheckBox::indicator:checked {background:#9F2840;border-color:#EBD9DB;}
QCheckBox::indicator:hover {border-color:#F9E6E8;}
QCheckBox::indicator:disabled {background:#252936;border-color:#626775;}
QTreeWidget {background:transparent;border:0;border-right:1px solid rgba(188,97,106,130);color:#FCE8EB;outline:0;}
QTreeWidget::item {padding:3px 3px;min-height:24px;border:1px solid transparent;}
QTreeWidget::item:selected {
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #D62736,stop:.4 #8E2439,stop:1 #861822);
  border:1px solid #E6838C;color:white;
}
QTreeWidget::item:hover:!selected {background:rgba(149,61,69,88);}
QTreeWidget::branch {background:transparent;}
QTableWidget {background:rgba(22,28,40,170);border:1px solid #969EAE;border-radius:3px;outline:0;gridline-color:transparent;font-size:14px;font-weight:400;}
QTableWidget::item {border:0;}
QTableView#inventoryTable {background:#1B202D;border:1px solid #969EAE;border-radius:3px;outline:0;}
QHeaderView {background:transparent;}
QHeaderView::section {
  background:#363C49;border:0;border-bottom:1px solid #75383E;border-right:1px solid #763D42;
  padding:6px;color:#F8F4F6;font-size:14px;font-weight:500;
}
QTableCornerButton::section {background:#333B4A;border:0;}
QScrollArea,QStackedWidget,QScrollArea QWidget#qt_scrollarea_viewport {background:transparent;border:0;}
QPlainTextEdit {background:rgba(35,28,32,190);border:1px solid #A25E64;border-radius:3px;}
QPlainTextEdit#itemDescription {
  background:#181D28;border:1px solid #A8AFBD;border-radius:3px;
  font-family:'Cambria','DejaVu Serif';font-size:16px;color:#EEF3F7;padding:9px;
}
QScrollBar:vertical {background:#262D39;width:12px;margin:14px 1px 14px 1px;border:1px solid #96555B;}
QScrollBar::handle:vertical {
  background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #CDBDBF,stop:.5 #EAD8DA,stop:1 #9C5259);
  border:1px solid #83484E;min-height:28px;border-radius:1px;
}
QScrollBar::add-line:vertical {height:13px;subcontrol-position:bottom;subcontrol-origin:margin;background:#473940;border:1px solid #C3B3B5;}
QScrollBar::sub-line:vertical {height:13px;subcontrol-position:top;subcontrol-origin:margin;background:#473940;border:1px solid #C3B3B5;}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {background:transparent;}
QScrollBar:horizontal {height:9px;background:#2F262B;}
QScrollBar::handle:horizontal {background:#B7A8AA;min-width:25px;}
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal {width:0;}
QMenu {background:#303745;color:#FFEDF0;border:1px solid #BCADAF;padding:5px;}
QMenu::item {padding:8px 22px 8px 16px;}
QMenu::item:selected {background:#8E2439;}
QMenu::item:disabled {color:#AEA5AD;}
QMenu::separator {height:1px;background:#4A3B43;margin:5px;}
QLabel#saveStateChip {font-size:11px;color:#E9D7D9;padding:2px 7px;border:1px solid rgba(192,177,179,100);border-radius:3px;background:rgba(38,30,34,120);}
QLabel#saveStateChip[state="dirty"] {color:#FFE6B6;border-color:#BFA46D;background:rgba(86,58,23,180);}
QLabel#saveStateChip[state="clean"] {color:#E1CFD2;}
QWidget#footerRow {border-top:1px solid rgba(191,105,112,90);background:transparent;}
QToolTip {background:#303745;color:#FFEDF0;border:1px solid #CFBFC1;padding:5px;}
QMessageBox {background:#282E3B;}
QMessageBox QPushButton {background:#493A42;border:1px solid #C6B6B8;min-width:75px;padding:7px 14px;}
'''


# v7.9.1: edit feedback and review keep the same dark glass palette.
HUD_STYLESHEET += r'''
QLabel#itemCategoryBadge {font-size:12px;color:#DFCED0;}
QLabel#quantityChange {font-size:13px;color:#ECDADC;padding:0 0 1px 0;}
QLabel#toastNotice {
  background:#372C32;border:1px solid #C2656E;border-left:3px solid #DD7881;
  color:#FFEDF0;border-radius:4px;padding:9px 13px;font-size:13px;
}
QDialog#changesDialog {
  background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #382D33,stop:1 #2B2227);
  border:1px solid #CFBFC1;
}
QLabel#reviewHeading {font-size:21px;font-weight:600;color:#F4FAFF;}
QLabel#reviewNote {font-size:12px;color:#DFCED0;}
QLabel#reviewDestination {font-size:13px;color:#E7D5D7;}
QTableWidget#reviewTable {background:#262D39;alternate-background-color:#362B31;selection-background-color:#8E1E28;}
QTableWidget#reviewTable::item {padding:4px 6px;border-bottom:1px solid #333B4A;}
'''

# v7.9.2: first-launch guidance uses the existing game-style chrome.
HUD_STYLESHEET += r'''
QScrollArea#firstLaunchScroller,QWidget#firstLaunchInner,QWidget#firstLaunchContent {background:transparent;border:0;}
QLabel#setupKicker {font-size:12px;letter-spacing:2px;color:#E2D0D3;}
QLabel#setupHeading {font-family:'Cambria','DejaVu Serif';font-size:33px;color:#F4FAFD;}
QLabel#setupIntro {font-size:15px;color:#E7D5D7;}
QLabel#setupStep {font-size:14px;color:#FEE9EC;border:1px solid #9C595F;background:#3A2E35;border-radius:3px;}
QLabel#setupCardTitle {font-size:18px;font-weight:600;color:#F1F8FC;}
QLabel#setupCardText {font-size:14px;color:#E1CFD2;}
QLabel#setupStatus {font-size:13px;color:#DDCCCE;}
QLabel#setupStatus[state="ready"] {color:#E3D1D3;}
QLabel#setupStatus[state="busy"] {color:#F8E5E7;}
QLabel#setupStatus[state="error"],QLabel#setupStatus[state="warning"] {color:#F2C79C;}
QLabel#setupLater {font-size:12px;color:#D0C0C2;}
QProgressBar#setupProgress {background:#2A2226;border:1px solid #7E4449;border-radius:2px;}
QProgressBar#setupProgress::chunk {background:#D14E59;border:0;border-radius:1px;}
'''

ARROW_UP = ASSETS / 'arrow-up.png'
ARROW_DOWN = ASSETS / 'arrow-down.png'
if ARROW_UP.is_file() and ARROW_DOWN.is_file():
    HUD_STYLESHEET += r'''
QSpinBox::up-button {subcontrol-origin:border;subcontrol-position:top right;width:17px;border:1px solid #949FAE;background:#333B4A;border-top-right-radius:2px;}
QSpinBox::down-button {subcontrol-origin:border;subcontrol-position:bottom right;width:17px;border:1px solid #949FAE;background:#333B4A;border-bottom-right-radius:2px;}
QSpinBox::up-arrow, QScrollBar::up-arrow:vertical {image:url("@UP@");width:8px;height:6px;}
QSpinBox::down-arrow, QScrollBar::down-arrow:vertical {image:url("@DOWN@");width:8px;height:6px;}
'''.replace('@UP@', ARROW_UP.as_posix()).replace('@DOWN@', ARROW_DOWN.as_posix())
