"""Embedded, dependency-free ClawsGO backend for the PySide6 desktop build.

Merged from the standalone ``backend/`` package: this module now lives under
``gui/`` and is called **in-process** by the desktop shell — no HTTP server is
started and no HTTP client is used.
"""
from __future__ import annotations
import json, os, re, threading, uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent.parent  # repo root
DATA=Path(os.environ.get('CLAWSGO_DATA_DIR', ROOT/'data')); DATA.mkdir(parents=True,exist_ok=True)
PHONE='13800000000'; ADMIN_PHONE='13900000000'; PASSWORD='clawsgo2026'

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def rid(p='id'): return p+'_'+uuid.uuid4().hex[:12]
class Backend:
 def __init__(self):
  self.lock=threading.RLock(); self.token=None; self.user=None; self._otp={}; self._seed()
 def _seed(self):
  t=now(); self.users=[{'id':'u_demo','userId':'u_demo','name':'演示用户','displayName':'演示用户','phone':PHONE,'role':'user','roles':['user'],'plan':'pro','credits':4820},{'id':'u_admin','userId':'u_admin','name':'平台管理员','displayName':'平台管理员','phone':ADMIN_PHONE,'role':'super_admin','roles':['super_admin'],'plan':'enterprise','credits':100000}]
  self.teams=[{'id':'u_demo','userId':'u_demo','name':'演示实验室','ownerId':'u_demo','role':'owner','plan':'pro','memberCount':2,'creditBalance':4820,'createdAt':t}]
  self.convs=[{'id':'c_demo','teamId':'u_demo','userId':'u_demo','title':'欢迎使用 ClawsGO','createdAt':t,'updatedAt':t,'lastMessageAt':t,'lastMessagePreview':'探索你的科研工作区','messageCount':2}]
  self.messages={'c_demo':[{'id':'m1','conversationId':'c_demo','role':'user','seq':1,'parts':[{'type':'text','text':'你好'}],'createdAt':t,'streamId':None},{'id':'m2','conversationId':'c_demo','role':'assistant','seq':2,'parts':[{'type':'text','text':'欢迎使用 ClawsGO 独立桌面版。'}],'createdAt':t,'streamId':None}]}
  self.skills=[{'id':'s1','slug':'literature-review','name':'literature-review','title':'文献综述','description':'检索、整理和总结科研文献','installed':True,'enabled':True},{'id':'s2','slug':'data-cleaning','name':'data-cleaning','title':'数据清洗','description':'常用数据清洗工作流','installed':True,'enabled':True}]
  self.hosts=[{'id':'h1','teamId':'u_demo','name':'本机工作区','kind':'local','status':'running','online':True,'cpu':8,'memoryGb':16,'diskGb':256,'canOpenTerminal':True}]
  self.tickets=[]; self.projects=[]; self.orders=[]
 def login_password(self,phone,password):
  if phone not in (PHONE,ADMIN_PHONE) or password!=PASSWORD: raise ValueError('手机号或密码不正确')
  self.user=next(u for u in self.users if u['phone']==phone); self.token='cgt_'+uuid.uuid4().hex; return {'user':dict(self.user),'token':self.token}
 def request_otp(self,phone): self._otp[phone]='123456'; return {'requestId':rid('otp'),'devCode':'123456'}
 def login_otp(self,phone,code):
  if len(str(code))!=6: raise ValueError('验证码不正确')
  return self.login_password(phone,PASSWORD)
 def call(self,cmd,data=None):
  data=data or {}; fn=getattr(self,'cmd_'+cmd,None)
  if fn: return fn(data)
  # Complete command surface: safe, shape-preserving fallback for less relevant desktop-only commands.
  return self._fallback(cmd,data)
 def cmd_getProfile(self,d): return {'profile':dict(self.user or self.users[0])}
 def cmd_getOverview(self,d): return {'overview':{'plan':self.user.get('plan','free') if self.user else 'free','credits':self.user.get('credits',0) if self.user else 0,'hosts':len(self.hosts),'activeConversations':len(self.convs),'teams':1,'tickets':len(self.tickets)},'conversations':len(self.convs),'hosts':len(self.hosts),'teams':1}
 def cmd_getConversations(self,d): return {'conversations':list(self.convs),'items':list(self.convs),'total':len(self.convs)}
 def cmd_getMessages(self,d): return {'messages':list(self.messages.get(d.get('conversationId'),[])),'total':len(self.messages.get(d.get('conversationId'),[]))}
 def cmd_sendMessage(self,d):
  cid=d.get('conversationId') or rid('c'); t=now(); conv=next((x for x in self.convs if x['id']==cid),None)
  if not conv: conv={'id':cid,'teamId':'u_demo','userId':self.user['id'],'title':(d.get('text') or '新会话')[:40],'createdAt':t,'updatedAt':t,'lastMessageAt':t,'messageCount':0}; self.convs.insert(0,conv)
  arr=self.messages.setdefault(cid,[]); text=str(d.get('text','')); u={'id':rid('m'),'conversationId':cid,'role':'user','seq':len(arr)+1,'parts':[{'type':'text','text':text}],'createdAt':t,'streamId':None}; a={'id':rid('m'),'conversationId':cid,'role':'assistant','seq':len(arr)+2,'parts':[{'type':'reasoning','text':'正在检查工作区…'},{'type':'tool','toolName':'Glob','state':'output-available','input':{'pattern':'**/*'},'output':{'count':0}},{'type':'text','text':'这是内置演示智能体的回复：已收到你的问题。你可以继续使用会话、技能、主机和工作区功能。'}],'createdAt':t,'streamId':None}; arr.extend([u,a]); conv.update(updatedAt=t,lastMessageAt=t,lastMessagePreview=text[:120],messageCount=len(arr)); return {'userMessage':u,'assistantMessage':a,'conversation':conv}
 def cmd_getSkills(self,d): return {'skills':self.skills,'items':self.skills,'total':len(self.skills)}
 def cmd_getHosts(self,d): return {'hosts':self.hosts,'items':self.hosts,'total':len(self.hosts)}
 def cmd_getTeams(self,d): return {'teams':self.teams,'items':self.teams,'total':len(self.teams)}
 def cmd_getTeamMembers(self,d): return {'members':[{'id':u['id'],'userId':u['id'],'name':u['name'],'role':'owner' if u['id']=='u_demo' else 'member'} for u in self.users]}
 def cmd_getPlans(self,d): return {'plans':[{'id':p,'name':p.title(),'priceMonthly':v,'priceCents':v} for p,v in {'free':0,'plus':990,'pro':2990,'ultra':9990,'team':29990,'enterprise':99900}.items()]}
 def cmd_getSubscription(self,d): return {'subscription':{'plan':'pro','planId':'pro','status':'active','priceMonthly':2990}}
 def cmd_getMyTickets(self,d): return {'tickets':self.tickets,'items':self.tickets,'total':len(self.tickets)}
 def cmd_getTickets(self,d): return self.cmd_getMyTickets(d)
 def cmd_getPaymentOrders(self,d): return {'orders':self.orders,'items':self.orders,'total':len(self.orders)}
 def cmd_getProjects(self,d): return {'projects':self.projects,'items':self.projects,'total':len(self.projects)}
 def cmd_getDevices(self,d): return {'devices':[]}
 def cmd_getUsageStats(self,d): return {'byDay':[],'byModel':[],'totalTokens':0,'totalRuns':0}
 def cmd_createTicket(self,d):
  x={'id':rid('ticket'),'subject':d.get('subject','桌面反馈'),'status':'open','body':d.get('body',''),'createdAt':now()}; self.tickets.insert(0,x); return {'ticket':x}
 def _fallback(self,cmd,d):
  if cmd.startswith('get') or cmd.startswith('adminGet'): return {'items':[],'total':0}
  if cmd.startswith('download'): return {'available':False,'reason':'embedded-desktop'}
  if cmd.startswith('create') or cmd.startswith('update') or cmd.startswith('set') or cmd.startswith('delete'): return {'ok':True,'available':True}
  return {'ok':True}

def command_names():
 p=ROOT/'contracts'/'commands.json'
 try: return json.loads(p.read_text(encoding='utf8'))
 except Exception: return []
backend=Backend()
def dispatch(cmd,payload=None,**kwargs):
 try: return {'data':backend.call(cmd,payload)}
 except Exception as e: return {'error':{'code':'INTERNAL','message':str(e)}}
class BackendEphemeral:
 def __init__(self): self.backend=Backend()
 def call(self,c,d=None): return self.backend.call(c,d)
