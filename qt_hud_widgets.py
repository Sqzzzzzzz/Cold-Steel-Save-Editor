"""Painted HUD chrome around real, accessible Qt controls.

No screenshot is used as an interface. All coordinates are logical Qt pixels;
the backdrop is scaled once per resize and reused by the glass panels.
"""
from __future__ import annotations

from functools import cache
import math
from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QSize
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QBrush, QLinearGradient,
    QRadialGradient, QPolygonF, QPixmap, QIcon, QFont, QFontMetrics,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QPushButton, QStyledItemDelegate, QStyle, QLabel,
)
from game_art import ASSETS, GameArt


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
    art = _menu_art()
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
        'decoration': 0x14, 'fish': 0x6D, 'fishing_gear': 0x17,
        'quest': 0x95, 'material': 0x27, 'card': 0x16, 'orbment': 0x32,
    }
    return QIcon(art.tile(tiles.get(kind, 0x96)))


@cache
def _menu_art():
    return GameArt()


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
        primary=role in ('primary','toolbarPrimary') or self.isChecked()
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
                f=self.font();f.setPixelSize(19);p.setFont(f);p.setPen(QColor('#E9D7D9'));p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,self.text())
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
        if left:x=24 if nav else 19
        else:x=max(9,(self.width()-text_width-(icon_size+gap if not icon.isNull() else 0))//2)
        if not icon.isNull():
            icon.paint(p,QRect(x,(self.height()-icon_size)//2,icon_size,icon_size),mode=QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled)
            x+=icon_size+gap
        area=QRect(x,3,max(0,self.width()-x-14),self.height()-6)
        p.setPen(QColor('#F3FAFF') if self.isEnabled() else QColor('#A99B9D'))
        if role=='danger':p.setPen(QColor('#F7AEB8'))
        if '\n' not in text:text=p.fontMetrics().elidedText(text,Qt.TextElideMode.ElideRight,area.width())
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
        self.wall=QPixmap(str(ASSETS / 'hero.jpg'))
        self._scaled_wall=QPixmap()
        self.setAutoFillBackground(False)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if not self.wall.isNull() and self.width()>0 and self.height()>0:
            self._scaled_wall=self.wall.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)

    def scene_rect(self,pos,size):
        return QRect(pos,size).translated((self._scaled_wall.width()-self.width())*62//100,(self._scaled_wall.height()-self.height())//2)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),QColor('#1C2636'))
        if not self._scaled_wall.isNull():p.drawPixmap(self.rect(),self._scaled_wall,self.scene_rect(QPoint(0,0),self.size()))
        p.fillRect(self.rect(),QColor(19,25,40,153))
        vignette=QRadialGradient(self.width()*.53,self.height()*.34,self.width()*.75)
        vignette.setColorAt(0,QColor(22,30,46,0));vignette.setColorAt(1,QColor(18,24,36,186))
        p.fillRect(self.rect(),vignette)
        p.save();p.setClipRect(QRect(0,0,210,self.height()))
        _hexes(p,QRectF(0,0,210,self.height()),22,17)
        p.restore()
        p.save();p.setClipRect(QRect(self.width()-280,0,280,self.height()))
        _hexes(p,QRectF(self.width()-280,0,280,self.height()),24,16)
        p.restore()
        # Curved silver frame echoes the reference without obscuring controls.
        sy=self.height()/864
        p.save();p.scale(1,sy)
        curve=QPainterPath();curve.moveTo(91,-25)
        curve.cubicTo(48,120,172,237,160,447)
        curve.cubicTo(154,650,74,714,-42,744)
        metallic=QLinearGradient(62,0,165,0)
        for stop,color in [(0,'#393F52'),(.24,'#C0C8D6'),(.42,'#EFF0EE'),(.64,'#7C899C'),(1,'#C2CAD7')]:metallic.setColorAt(stop,QColor(color))
        p.setPen(QPen(QColor(34,27,31,190),27));p.drawPath(curve)
        p.setPen(QPen(QBrush(metallic),13));p.drawPath(curve)
        p.setPen(QPen(QColor('#F8F4E7'),2));p.drawPath(curve)
        p.translate(16,0);p.setPen(QPen(QColor('#3A2F35'),5));p.drawPath(curve)
        p.translate(6,0);p.setPen(QPen(QColor(194,98,107,175),1));p.drawPath(curve)
        p.restore();p.end()


def _hexes(p,rect,r=22,alpha=35):
    p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor(243,224,227,alpha),.8))
    dy=math.sqrt(3)*r
    for col,x in enumerate(range(int(rect.left())-r,int(rect.right()+r),int(1.5*r))):
        for y in range(int(rect.top())-int(dy),int(rect.bottom()+dy),int(dy)):
            cy=y+(dy/2 if col%2 else 0)
            p.drawPolygon(QPolygonF([QPointF(x+r*math.cos(a*math.pi/3),cy+r*math.sin(a*math.pi/3)) for a in range(6)]))


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
        scene=self.window().centralWidget()
        if isinstance(scene,Backdrop) and not scene._scaled_wall.isNull():
            p.save();p.setClipPath(path)
            p.drawPixmap(self.rect(),scene._scaled_wall,scene.scene_rect(self.mapTo(scene,QPoint(0,0)),self.size()))
            p.restore()
        grad=QLinearGradient(0,0,r.width(),r.height())
        grad.setColorAt(0,QColor(30,38,52,205 if self.kind=='dark' else 213))
        grad.setColorAt(.52,QColor(29,33,43,215 if self.kind=='dark' else 222))
        grad.setColorAt(1,QColor(39,42,53,208))
        p.fillPath(path,grad)
        if self.kind=='dark':
            p.save();p.setClipPath(path)
            _hexes(p,QRectF(r.right()-180,r.top(),180,160),22,18)
            _hexes(p,QRectF(r.left(),r.bottom()-85,190,85),22,20)
            p.restore()
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
    def paint(self,p,option,index):
        p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r=option.rect;selected=bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            grad=QLinearGradient(0,r.top(),0,r.bottom())
            grad.setColorAt(0,QColor('#CD2534'));grad.setColorAt(.52,QColor('#A61E2A'));grad.setColorAt(1,QColor('#79161F'))
            p.fillRect(r,grad)
            p.setPen(QPen(QColor(240,78,93,80),5));p.drawLine(r.topLeft(),r.topRight());p.drawLine(r.bottomLeft(),r.bottomRight())
            p.setPen(QPen(QColor('#F0808A'),1));p.drawLine(r.topLeft(),r.topRight());p.drawLine(r.bottomLeft(),r.bottomRight())
        else:p.fillRect(r,QColor(51,56,70,175) if index.row()%2 else QColor(27,31,44,100))
        p.setFont(option.font);p.setPen(QColor('#EFF7FC'))
        area=r.adjusted(5,0,-5,0)
        change=index.data(Qt.ItemDataRole.UserRole+1)
        if index.column()==0:
            if selected:
                p.setPen(QPen(QColor('#FFEDF0'),2));p.drawPolyline(QPolygonF([QPointF(r.x()+3,r.center().y()-6),QPointF(r.x()+8,r.center().y()),QPointF(r.x()+3,r.center().y()+6)]))
            ico=index.data(Qt.ItemDataRole.DecorationRole)
            if isinstance(ico,QIcon):ico.paint(p,QRect(r.x()+13,r.y()+2,26,r.height()-4))
            area.setLeft(r.x()+45)
            if change:
                area.setRight(r.right()-15)
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#F07882'))
                p.drawEllipse(QPointF(r.right()-7,r.center().y()),2.7,2.7)
                p.setPen(QColor('#EFF7FC'))
            align=Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter
        else:align=Qt.AlignmentFlag.AlignCenter
        if change and index.column()==3:p.setPen(QColor('#F8E5E7'))
        text=str(index.data(Qt.ItemDataRole.DisplayRole) or '')
        text=option.fontMetrics.elidedText(text,Qt.TextElideMode.ElideRight,area.width())
        p.drawText(area,align,text);p.restore()


class ElideLabel(QLabel):
    def __init__(self,text='',parent=None):
        super().__init__(parent);self._full_text='';self.setText(text)

    def setText(self,text):
        self._full_text=text;self.setToolTip(text)
        super().setText(self.fontMetrics().elidedText(text,Qt.TextElideMode.ElideRight,max(1,self.width())))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        super().setText(self.fontMetrics().elidedText(self._full_text,Qt.TextElideMode.ElideRight,max(1,self.width())))


class ItemTitle(QLabel):
    """Wrap long item names without forcing a fixed-width card wider."""
    def __init__(self,parent=None):
        super().__init__(parent);self._full_text='';self._fitting=False
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
            if fm.boundingRect(QRect(0,0,width,1000),Qt.TextFlag.TextWordWrap,shown).height()>height:
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
                shown='\n'.join(lines)
            self.setAccessibleName(self._full_text);super().setText(shown)
        finally:self._fitting=False


class HudTitleBar(QWidget):
    def __init__(self):
        super().__init__()
        self.academy = QPixmap(str(ASSETS / 'academy-full.jpg'))
        self._academy_banner = QPixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.academy.isNull():
            return
        width = max(360, int(event.size().width() * 0.63))
        height = max(1, event.size().height() - 1)
        scaled = self.academy.scaled(
            width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        banner = QPixmap(width, height)
        banner.fill(Qt.GlobalColor.transparent)
        painter = QPainter(banner)
        y = int((scaled.height() - height) * 0.54)
        painter.drawPixmap(banner.rect(), scaled, QRect(0, y, width, height))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        fade = QLinearGradient(0, 0, width, 0)
        for position, alpha in ((0, 0), (0.18, 48), (0.52, 150), (1, 72)):
            fade.setColorAt(position, QColor(255, 255, 255, alpha))
        painter.fillRect(banner.rect(), fade)
        painter.end()
        self._academy_banner = banner

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect().adjusted(0, 0, 0, -1), QColor(18, 25, 40, 83))
        if not self._academy_banner.isNull():
            painter.drawPixmap(self.width() - self._academy_banner.width(), 0, self._academy_banner)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            handle=self.window().windowHandle()
            if handle:handle.startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            w=self.window();w.showNormal() if w.isMaximized() else w.showMaximized()
