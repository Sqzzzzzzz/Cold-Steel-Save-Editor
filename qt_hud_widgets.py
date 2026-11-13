"""Painted HUD chrome around real, accessible Qt controls.

The window backdrop is rendered once per size and device scale.
"""
from __future__ import annotations

from functools import cache
import math
from PySide6.QtCore import QEvent, Qt, QPointF, QRect, QRectF, QSize
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QBrush, QLinearGradient,
    QPolygonF, QPixmap, QIcon, QFont, QFontMetrics,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QPushButton, QCheckBox, QStyledItemDelegate, QStyle, QStyleOptionButton, QLabel,
)
from game_art import ASSETS, BLADE_CARD_TILE, SECTION_ICONS, YELLOW_ORB_TILE, shared_game_art


def bevel(rect, cut=7):
    x,y,w,h=rect.x(),rect.y(),rect.width(),rect.height()
    path=QPainterPath()
    path.moveTo(x+cut,y);path.lineTo(x+w-cut,y);path.lineTo(x+w,y+cut)
    path.lineTo(x+w,y+h-cut);path.lineTo(x+w-cut,y+h)
    path.lineTo(x+cut,y+h);path.lineTo(x,y+h-cut);path.lineTo(x,y+cut)
    path.closeSubpath()
    return path


@cache
def hud_icon(kind, size=28):
    """Use extracted game-menu art and native window-control symbols."""
    symbols = {
        'help': QStyle.StandardPixmap.SP_DialogHelpButton,
    }
    if kind in symbols:
        return QApplication.style().standardIcon(symbols[kind])
    art = shared_game_art()
    menu = {
        'latest': 'open', 'open': 'open', 'save': 'save', 'backup': 'save',
        'inventory': 'inventory', 'catalog': 'catalog', 'tools': 'game',
        'remove': 'remove', 'compare': 'catalog', 'check': 'save',
        'undo': 'open', 'reset': 'open',
    }
    if kind in menu:
        icon = art.menu_icon(menu[kind])
        if not icon.isNull():
            return icon
    tiles = {
        'search': 0x11, 'clock': 0x5F, 'all': 0x96, 'favorites': 0xC8, 'recent': 0x5F,
        'quartz': 0x50, 'quartz_normal': 0x50, 'quartz_master': 0x32,
        'weapon': 0x01, 'armor': 0x0F, 'shoes': 0x10, 'accessory': 0x11,
        'consumable': 0x70, 'food': 0x67, 'ingredient': 0x15, 'recipe': 0x16,
        'book': 0x16, 'costume': 0x12, 'face': 0x13, 'hair': 0x13,
        'decoration': 0x72, 'dlc_pack': 0x14, 'fish': 0x6D, 'fishing_gear': 0x17, 'fish_book': 0x16,
        'quest': SECTION_ICONS['key'], 'material': 0x27, 'card': BLADE_CARD_TILE, 'orbment': YELLOW_ORB_TILE,
    }
    return art.tile_icon(tiles.get(kind, 0x96))


class HudCheckBox(QCheckBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isChecked():
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        rect = QRectF(self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self))
        x, y = rect.center().x(), rect.center().y()
        mark = QPainterPath(QPointF(x - 4.5, y))
        mark.lineTo(x - 1.5, y + 3)
        mark.lineTo(x + 4.5, y - 3)
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor("#FFF3F4" if self.isEnabled() else "#AFA3A6"), 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(mark)


class HudButton(QPushButton):
    def __init__(self,text='',parent=None):
        super().__init__(text,parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def minimumSizeHint(self):
        # Native QPushButton estimates uncondensed text. Our painted labels can
        # elide; they must not force a compact panel beyond the window edge.
        return QSize(40,28 if self.property('role')=='window' else 40)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        role=self.property('role') or 'normal'
        window=role=='window'
        nav=role=='nav'
        primary=self.isEnabled() and (role in ('primary','toolbarPrimary') or self.isChecked())
        hovered=self.underMouse() and self.isEnabled()
        r=QRectF(self.rect()).adjusted(4,4,-4,-4)
        if window:
            if hovered:p.fillRect(self.rect(),QColor('#AF3C54') if self.property('symbol')=='close' else QColor(218,102,113,55))
        elif nav and not self.isChecked():
            g=QLinearGradient(0,0,self.width(),0)
            g.setColorAt(0,QColor(53,42,48,35));g.setColorAt(1,QColor(35,28,32,125))
            p.fillRect(r,g)
            p.setPen(QColor(214,106,116,65));p.drawLine(QPointF(7,r.bottom()),QPointF(r.right(),r.bottom()))
            if hovered:p.fillRect(r,QColor(192,50,63,55))
        else:
            path=bevel(r,12 if nav else 5)
            grad=QLinearGradient(0,r.top(),0,r.bottom())
            if not self.isEnabled():colors=('#392D34','#2D2429','#282025')
            elif role=='danger':colors=('#563C48','#352A3B','#292126')
            elif primary:colors=('#E12B3B','#B8212F','#831821')
            else:colors=('#44373E','#352B31','#2E252A')
            for stop,c in zip((0,.48,1),colors):grad.setColorAt(stop,QColor(c))
            if primary:
                p.setPen(QPen(QColor(240,49,66,24),9));p.drawPath(path)
                p.setPen(QPen(QColor(240,54,70,70),5));p.drawPath(path)
            p.fillPath(path,grad)
            if hovered:p.fillPath(path,QColor(240,100,113,24))
            if self.isDown():p.fillPath(path,QColor(31,25,29,60))
            edge=QColor('#F07D87') if primary else QColor('#CC7685') if role=='danger' else QColor('#CCBCBE')
            if not self.isEnabled():edge=QColor('#4A3C43')
            p.setPen(QPen(QColor(29,23,27,220),3));p.drawPath(path)
            p.setPen(QPen(edge,1.2));p.drawPath(path)
            inset=bevel(r.adjusted(3,3,-3,-3),max(2,9 if nav else 3))
            p.setPen(QPen(QColor(250,231,233,130 if primary else 40),1));p.drawPath(inset)
            glow=QLinearGradient(0,r.top(),0,r.top()+16)
            glow.setColorAt(0,QColor(255,237,240,125 if primary else 25))
            glow.setColorAt(1,QColor(240,131,140,0))
            p.save();p.setClipPath(path);p.fillRect(QRectF(r.left(),r.top(),r.width(),16),glow);p.restore()
        if window:
            if not self.icon().isNull():self.icon().paint(p,QRect((self.width()-23)//2,(self.height()-23)//2,23,23))
            elif self.text():
                f=self.font();f.setPixelSize(19);p.setFont(f)
                p.setPen(QColor('#E9D7D9' if self.isEnabled() else '#91878B'))
                p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,self.text())
            if self.hasFocus():
                p.setPen(QPen(QColor('#EAD8DA'),1,Qt.PenStyle.DotLine))
                p.drawRect(self.rect().adjusted(2,2,-3,-3))
            p.end();return
        f=self.font();f.setPixelSize(17 if nav else 14 if role.startswith('toolbar') else 14);f.setStretch(93)
        f.setWeight(QFont.Weight.Medium if nav else QFont.Weight.Normal)
        if nav:f.setPixelSize(16);f.setStretch(93)
        if role.startswith('toolbar'):f.setStretch(85)
        p.setFont(f)
        text=self.text();icon=self.icon()
        left=role.startswith('toolbar') or nav
        icon_size=34 if nav else 31 if role.startswith('toolbar') else 23
        gap=14 if left else 12
        text_width=max((p.fontMetrics().horizontalAdvance(line) for line in text.split('\n')),default=0)
        icon_width=icon_size+gap if not icon.isNull() else 0
        if nav:x=16 if self.width()<185 else 24
        elif left:x=19
        else:x=max(9,(self.width()-text_width-icon_width)//2)
        if not icon.isNull():
            icon.paint(p,QRect(x,(self.height()-icon_size)//2,icon_size,icon_size),mode=QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled)
            x+=icon_size+gap
        area=QRect(x,3,max(0,self.width()-x-14),self.height()-6)
        p.setPen(QColor(('#F7AEB8' if role=='danger' else '#F3FAFF') if self.isEnabled() else '#B8ABAE'))
        metrics=p.fontMetrics()
        text='\n'.join(metrics.elidedText(line,Qt.TextElideMode.ElideRight,area.width()) for line in text.split('\n'))
        p.drawText(area,Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft,text)
        if self.hasFocus():
            p.setPen(QPen(QColor(255,237,240,175),1,Qt.PenStyle.DotLine));p.drawPath(bevel(r.adjusted(5,5,-5,-5),3))
        p.end()


class AngularTab(QPushButton):
    def __init__(self,text,parent=None):
        super().__init__(text,parent);self.setCheckable(True)
        self.setFixedHeight(51);self.setMinimumWidth(200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w,h=self.width(),self.height()
        poly=QPolygonF([QPointF(2,49),QPointF(2,22),QPointF(25,3),QPointF(w-30,3),QPointF(w-3,48)])
        grad=QLinearGradient(0,0,0,h)
        grad.setColorAt(0,QColor('#A3232E') if self.isChecked() else QColor('#382D33'))
        grad.setColorAt(.5,QColor('#8B1F29') if self.isChecked() else QColor('#31272C'))
        grad.setColorAt(1,QColor('#41343B'))
        p.setBrush(grad);p.setPen(QPen(QColor('#DE828B') if self.isChecked() else QColor('#B4A6A7'),1.3));p.drawPolygon(poly)
        p.setPen(QPen(QColor('#FCE8EB'),1));p.drawLine(25,6,w-32,6);p.drawLine(w-30,7,w-8,46)
        if self.isChecked():
            p.setPen(QPen(QColor(240,105,117,80),5));p.drawLine(21,8,w-36,8)
            p.setPen(QPen(QColor('#E1646F'),1));p.drawLine(22,h-6,w-10,h-6)
        p.setFont(self.font());p.setPen(QColor('#F3FBFF'))
        p.drawText(QRect(12,5,w-35,h-5),Qt.AlignmentFlag.AlignCenter,self.text());p.end()


class Backdrop(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.texture=QPixmap(str(ASSETS / 'heimdallr.jpg'))
        if not self.texture.isNull():
            # Remove the black letterbox baked into the Falcom screenshot.
            self.texture=self.texture.copy(self.texture.rect().adjusted(0,12,0,-13))
        self._scene=QPixmap()
        self._scene_key=None
        self.setAutoFillBackground(False)

    def paintEvent(self,event):
        dpr=self.devicePixelRatioF()
        key=(self.size(),dpr)
        if key!=self._scene_key:
            self._render_scene(dpr)
            self._scene_key=key
        p=QPainter(self)
        p.drawPixmap(0,0,self._scene)

    def _render_scene(self,dpr):
        size=QSize(math.ceil(self.width()*dpr),math.ceil(self.height()*dpr))
        self._scene=QPixmap(size)
        self._scene.setDevicePixelRatio(dpr)
        painter=QPainter(self._scene)
        painter.fillRect(self.rect(),QColor('#19212E'))
        if not self.texture.isNull():
            # Crop the reference texture to cover the window at its original proportions.
            scale=max(self.width()/self.texture.width(),self.height()/self.texture.height())
            crop=QRectF(0,0,self.width()/scale,self.height()/scale)
            crop.moveCenter(QRectF(self.texture.rect()).center())
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(QRectF(self.rect()),self.texture,crop)
        shade=QLinearGradient(0,0,0,self.height())
        shade.setColorAt(0,QColor(17,26,42,189))
        shade.setColorAt(.45,QColor(18,27,41,196))
        shade.setColorAt(1,QColor(13,20,32,225))
        painter.fillRect(self.rect(),shade)
        left=QLinearGradient(0,0,self.width()*.34,0)
        left.setColorAt(0,QColor(14,22,35,94))
        left.setColorAt(1,QColor(14,22,35,0))
        painter.fillRect(self.rect(),left)
        painter.end()


class RailWatermark(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.mark=QPixmap(str(ASSETS / 'thors.png'))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self,event):
        if self.mark.isNull() or self.width()<=20 or self.height()<=24:
            return
        size=self.mark.size().scaled(min(174,self.width()-20),min(174,self.height()-24),
                                     Qt.AspectRatioMode.KeepAspectRatio)
        target=QRectF((self.width()-size.width())/2,self.height()-size.height()-16,
                      size.width(),size.height())
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(0.68)
        painter.drawPixmap(target,self.mark,QRectF(self.mark.rect()))


class GlassPanel(QFrame):
    def __init__(self,parent=None,kind='normal'):
        super().__init__(parent);self.kind=kind
        self.setObjectName('glassPanel');self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self,event):
        if self.kind=='rail':return
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r=QRectF(self.rect()).adjusted(3,3,-4,-4)
        if r.width()<30 or r.height()<30:p.end();return
        path=bevel(r,24 if self.kind=='dark' else 16)
        grad=QLinearGradient(0,0,r.width(),r.height())
        grad.setColorAt(0,QColor(30,38,52,220 if self.kind=='dark' else 204))
        grad.setColorAt(.52,QColor(26,31,42,226))
        grad.setColorAt(1,QColor(36,40,53,216))
        p.fillPath(path,grad)
        p.setPen(QPen(QColor(25,20,24,230),5));p.drawPath(path)
        p.setPen(QPen(QColor('#BFC8D9'),1.4));p.drawPath(path)
        p.setPen(QPen(QColor(229,107,118,110),1));p.drawPath(bevel(r.adjusted(4,4,-4,-4),max(6,20 if self.kind=='dark' else 12)))
        p.setPen(QPen(QColor('#F2DFE2'),1.2))
        p.drawLine(QPointF(r.left()+23,r.top()+3),QPointF(r.left()+64,r.top()+3))
        p.drawLine(QPointF(r.right()-23,r.bottom()-3),QPointF(r.right()-70,r.bottom()-3))
        for is_left in (True,False):
            x=r.left() if is_left else r.right();direction=1 if is_left else -1
            p.drawLine(QPointF(x,r.bottom()-24),QPointF(x+20*direction,r.bottom()-4))
            p.drawLine(QPointF(x+3*direction,r.bottom()-25),QPointF(x+22*direction,r.bottom()-6))
        if self.kind=='dark':
            p.setPen(QPen(QColor(240,75,90,60),6));p.drawLine(QPointF(r.left()+28,r.bottom()-1),QPointF(r.right()-26,r.bottom()-1))
            p.setPen(QPen(QColor('#DF727B'),1.4));p.drawLine(QPointF(r.left()+28,r.bottom()-1),QPointF(r.right()-26,r.bottom()-1))
        p.end()


class HudTableDelegate(QStyledItemDelegate):
    """Continuous illuminated rows, with text and icons still supplied by Qt."""
    EVEN=QColor('#1B202D')
    ODD=QColor('#2A303E')
    TEXT=QColor('#F0F5F9')

    def paint(self,p,option,index):
        p.save()
        r=option.rect;selected=bool(option.state & QStyle.StateFlag.State_Selected)
        model=index.model()
        row_index=index.row()
        column=index.column()
        row=model.rows[row_index]
        if selected:
            grad=QLinearGradient(0,r.top(),0,r.bottom())
            grad.setColorAt(0,QColor('#B3283C'));grad.setColorAt(.52,QColor('#8F2233'));grad.setColorAt(1,QColor('#691827'))
            p.fillRect(r,grad)
            p.setPen(QPen(QColor(240,78,93,80),5));p.drawLine(r.topLeft(),r.topRight());p.drawLine(r.bottomLeft(),r.bottomRight())
            p.setPen(QPen(QColor('#F0808A'),1));p.drawLine(r.topLeft(),r.topRight());p.drawLine(r.bottomLeft(),r.bottomRight())
        else:p.fillRect(r,self.ODD if row_index%2 else self.EVEN)
        p.setFont(option.font);p.setPen(self.TEXT)
        area=r.adjusted(5,0,-5,0)
        change=row.change
        if column==0:
            if selected:
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setPen(QPen(QColor('#FFEDF0'),2));p.drawPolyline(QPolygonF([QPointF(r.x()+3,r.center().y()-6),QPointF(r.x()+8,r.center().y()),QPointF(r.x()+3,r.center().y()+6)]))
            ico=model.icon(row.item_id)
            if isinstance(ico,QIcon):ico.paint(p,QRect(r.x()+13,r.y()+2,26,r.height()-4))
            area.setLeft(r.x()+45)
            if change:
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                area.setRight(r.right()-15)
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#F07882'))
                p.drawEllipse(QPointF(r.right()-7,r.center().y()),2.7,2.7)
            p.setPen(self.TEXT)
            align=Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter
        else:align=Qt.AlignmentFlag.AlignCenter
        if change and column==3:p.setPen(QColor('#F8E5E7'))
        text=row.text(column)
        text=option.fontMetrics.elidedText(text,Qt.TextElideMode.ElideRight,area.width())
        p.drawText(area,align,text)
        if option.state & QStyle.StateFlag.State_HasFocus:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor('#E1D3D8'),1,Qt.PenStyle.DotLine))
            p.drawRect(r.adjusted(1,2,-2,-3))
        p.restore()


class ElideLabel(QLabel):
    def __init__(self,text='',parent=None,*,mode=Qt.TextElideMode.ElideRight):
        super().__init__(parent)
        self._full_text=''
        self._mode=mode
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setText(text)

    def setText(self,text):
        if text==self._full_text:return
        self._full_text=text;self.setToolTip(text);self.setAccessibleName(text)
        self._render_text()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._render_text()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.FontChange and hasattr(self,'_mode'):
            self._render_text()

    def _render_text(self):
        super().setText(self.fontMetrics().elidedText(self._full_text,self._mode,max(1,self.contentsRect().width())))


class ItemTitle(QLabel):
    """Wrap long item names without forcing a fixed-width card wider."""
    def __init__(self,parent=None):
        super().__init__(parent);self._full_text='';self._fitting=False
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True);self.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)

    def setText(self,text):
        self._full_text=text;self.setToolTip(text);self._fit()

    def resizeEvent(self,event):
        super().resizeEvent(event);self._fit()

    def _fit(self):
        if self._fitting:return
        self._fitting=True
        try:
            width=max(40,self.width()-2);height=max(20,self.height())
            font=self.font();font.setWeight(QFont.Weight.DemiBold)
            chosen=14
            for px in range(20,13,-1):
                font.setPixelSize(px);fm=QFontMetrics(font)
                bounds=fm.boundingRect(QRect(0,0,width,1000),Qt.TextFlag.TextWordWrap,self._full_text)
                if bounds.height()<=height and bounds.width()<=width:
                    chosen=px;break
            style=f'font-size:{chosen}px;font-weight:600;'
            if self.styleSheet()!=style:self.setStyleSheet(style)
            font.setPixelSize(chosen);fm=QFontMetrics(font)
            shown=self._full_text
            bounds=fm.boundingRect(QRect(0,0,width,1000),Qt.TextFlag.TextWordWrap,shown)
            if bounds.height()>height or bounds.width()>width:
                # Keep the complete string in the tooltip and accessible name.
                lines=[];line=''
                for word in shown.split():
                    candidate=(line+' '+word).strip()
                    if line and fm.horizontalAdvance(candidate)>width:lines.append(line);line=word
                    else:line=candidate
                if line:lines.append(line)
                count=max(1,height//max(1,fm.lineSpacing()))
                if len(lines)>count:
                    lines=lines[:count-1]+[fm.elidedText(' '.join(lines[count-1:]),Qt.TextElideMode.ElideRight,width)]
                shown='\n'.join(fm.elidedText(line,Qt.TextElideMode.ElideRight,width) for line in lines)
            self.setAccessibleName(self._full_text);super().setText(shown)
        finally:self._fitting=False


class HudTitleBar(QWidget):
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            handle=self.window().windowHandle()
            if handle:handle.startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            w=self.window();w.showNormal() if w.isMaximized() else w.showMaximized()
