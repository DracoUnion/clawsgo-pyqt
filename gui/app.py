from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QDialog,QHBoxLayout,QLabel,QMainWindow,QPushButton,QStackedWidget,QVBoxLayout,QWidget
from . import theme
from .backend import ServiceFacade as EmbeddedFacade
from .login import LoginWindow
from .views.home import HomeView
from .views.chat import ChatView

class Placeholder(QWidget):
    def __init__(self,title,subtitle,facade,user):
        super().__init__(); lay=QVBoxLayout(self); lay.setContentsMargins(28,24,28,24)
        h=QLabel(title); h.setObjectName('h1'); lay.addWidget(h)
        s=QLabel(subtitle); s.setObjectName('muted'); s.setWordWrap(True); lay.addWidget(s)
        lay.addStretch()

class MainWindow(QMainWindow):
    def __init__(self,facade,user):
        super().__init__(); self.facade=facade; self.user=user; self.setWindowTitle('ClawsGO Science · Desktop'); self.resize(1200,760); self.stack=QStackedWidget(); self._pages={}
        root=QWidget(); row=QHBoxLayout(root); row.setContentsMargins(0,0,0,0); row.setSpacing(0)
        side=QWidget(); side.setFixedWidth(220); sl=QVBoxLayout(side); sl.setContentsMargins(14,20,14,14)
        brand=QLabel('ClawsGO Science'); brand.setObjectName('h2'); sl.addWidget(brand); sl.addSpacing(16)
        for key,label in [('home','概览'),('chat','会话'),('skills','技能库'),('hosts','主机'),('teams','团队'),('billing','账单'),('tickets','工单'),('admin','管理后台')]:
            b=QPushButton(label); b.setObjectName('navButton'); b.clicked.connect(lambda _,k=key:self.navigate(k)); sl.addWidget(b)
        sl.addStretch(); u=QLabel(user.get('displayName') or user.get('name','')); u.setObjectName('muted'); sl.addWidget(u)
        row.addWidget(side); row.addWidget(self.stack,1); self.setCentralWidget(root)
        self._add('home',HomeView(facade,user,None,self)); self._add('chat',ChatView(facade,user,None,self))
        for k,l in [('skills','技能库'),('hosts','主机管理'),('teams','团队与成员'),('billing','套餐与账单'),('tickets','客服工单'),('admin','管理后台')]: self._add(k,Placeholder(l,'此页面使用嵌入式 Python 后端命令，完整命令面已保留。',facade,user))
        self.navigate('home')
    def _add(self,key,w): self._pages[key]=w; self.stack.addWidget(w)
    def navigate(self,key):
        w=self._pages.get(key);
        if w is not None: self.stack.setCurrentWidget(w); getattr(w,'on_show',lambda:None)()

def launch():
    app=QApplication.instance() or QApplication([]); theme.apply_theme(app); facade=EmbeddedFacade(); login=LoginWindow(facade); holder={}
    def ok(user):
        login.close(); win=MainWindow(facade,user); holder['win']=win; win.show()
    login.login_ok.connect(ok); login.show(); return app,login,holder

if __name__=='__main__':
    app,_,_=launch(); raise SystemExit(app.exec())
