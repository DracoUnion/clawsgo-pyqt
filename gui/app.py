from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QDialog,QHBoxLayout,QLabel,QMainWindow,QPushButton,QStackedWidget,QVBoxLayout,QWidget
from . import theme
from service import ServiceFacade as EmbeddedFacade
from .login import LoginWindow
from .views.home import HomeView
from .views.chat import ChatView
from .views.skills import SkillsView
from .views.hosts import HostsView
from .views.teams import TeamsView
from .views.billing import BillingView
from .views.tickets import TicketsView
from .views.admin import AdminView

NAV = [('home','概览'),('chat','会话'),('skills','技能库'),('hosts','主机'),('teams','团队'),
       ('billing','账单'),('tickets','工单'),('admin','管理后台')]

def _is_admin(user):
    role = (user or {}).get('role')
    return role in ('admin','super_admin')

class MainWindow(QMainWindow):
    def __init__(self,facade,user):
        super().__init__(); self.facade=facade; self.user=user; self.setWindowTitle('ClawsGO Science · Desktop'); self.resize(1200,760); self.stack=QStackedWidget(); self._pages={}
        root=QWidget(); row=QHBoxLayout(root); row.setContentsMargins(0,0,0,0); row.setSpacing(0)
        side=QWidget(); side.setFixedWidth(220); sl=QVBoxLayout(side); sl.setContentsMargins(14,20,14,14)
        brand=QLabel('ClawsGO Science'); brand.setObjectName('h2'); sl.addWidget(brand); sl.addSpacing(16)
        self._nav_btns={}
        for key,label in NAV:
            if key=='admin' and not _is_admin(user): continue
            b=QPushButton(label); b.setObjectName('navButton'); b.clicked.connect(lambda _,k=key:self.navigate(k)); sl.addWidget(b); self._nav_btns[key]=b
        sl.addStretch(); u=QLabel(user.get('displayName') or user.get('name','')); u.setObjectName('muted'); sl.addWidget(u)
        row.addWidget(side); row.addWidget(self.stack,1); self.setCentralWidget(root)
        self._add('home',HomeView(facade,user,None,self)); self._add('chat',ChatView(facade,user,None,self))
        self._add('skills',SkillsView(facade,user,None,self))
        self._add('hosts',HostsView(facade,user,None,self))
        self._add('teams',TeamsView(facade,user,None,self))
        self._add('billing',BillingView(facade,user,None,self))
        self._add('tickets',TicketsView(facade,user,None,self))
        self._add('admin',AdminView(facade,user,None,self))
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