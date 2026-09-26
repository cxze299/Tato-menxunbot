#!/usr/bin/env python3
"""Potato 适配层：复用完整的门训同行业务逻辑，只替换 Delta Chat 传输层。"""
from __future__ import annotations
import importlib.util, json, logging, os, re, ssl, sys, time, types, zoneinfo, threading, unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta, timezone
from http.client import RemoteDisconnected
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent
if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr,"reconfigure"): sys.stderr.reconfigure(encoding="utf-8")
REFERENCE=Path(os.getenv("MENXUN_REFERENCE_BOT",str(ROOT/"reference"/"menxun_bot.py")))
CONFIG=ROOT/"config.json"; DATA=ROOT/"data"
API_HEALTH=DATA/"api-health.json"
api_health_last_write=0.0
if not REFERENCE.exists(): raise SystemExit(f"找不到参考业务实现：{REFERENCE}")
config=json.loads(CONFIG.read_text(encoding="utf-8-sig")); token=str(config.get("bot_token","")).strip()
if not token: raise SystemExit(f"请先填写 {CONFIG} 中的 bot_token")
API=f"{str(config.get('api_base','https://api.rct2008.com:8443')).rstrip('/')}/{token}"
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger("potato-adapter")

class _ChatType: GROUP=2
class _MessageData:
    def __init__(self,text="",html=None): self.text=text; self.html=html
class _Events:
    class RawEvent: pass
    class NewMessage: pass
class _Cli:
    new_message=None; on_start_callback=None
    def __init__(self,*_): pass
    def on(self,event):
        def decorator(fn):
            if event is _Events.NewMessage:self.new_message=fn
            return fn
        return decorator
    def on_start(self,fn): self.on_start_callback=fn; return fn
    def start(self): pass
fake_dc=types.ModuleType("deltachat2"); fake_dc.ChatType=_ChatType; fake_dc.MessageData=_MessageData; fake_dc.events=_Events
fake_cli=types.ModuleType("deltabot_cli"); fake_cli.BotCli=_Cli
sys.modules["deltachat2"]=fake_dc; sys.modules["deltabot_cli"]=fake_cli
os.environ["MENXUN_SITES_FILE"]=str(CONFIG); os.environ["MENXUN_DATA_DIR"]=str(DATA); os.environ["MENXUN_ADMIN_KEY_FILE"]=str(DATA/"admin-key.json")
os.environ.setdefault("WEBSITE_POLL_INTERVAL",str(config.get("poll_interval",5)))
os.environ.setdefault("BOT_TIMEZONE",str(config.get("timezone","Asia/Shanghai")))
# Windows 精简 Python 可能未携带 tzdata；门训默认使用中国标准时间。
_real_zoneinfo=zoneinfo.ZoneInfo
def _zoneinfo_fallback(name):
    try:return _real_zoneinfo(name)
    except zoneinfo.ZoneInfoNotFoundError:
        if name=="Asia/Shanghai":return timezone(timedelta(hours=8))
        raise
zoneinfo.ZoneInfo=_zoneinfo_fallback
spec=importlib.util.spec_from_file_location("menxun_reference",REFERENCE); reference=importlib.util.module_from_spec(spec); sys.modules[spec.name]=reference; spec.loader.exec_module(reference)

def potato_api(method,params=None):
    """调用 Potato API；网络/TLS 和服务端短暂故障自动重试。"""
    params=params or {}; query=urlencode({k:v for k,v in params.items() if v is not None})
    last_error=None
    max_attempts = 8 if method == "sendTextMessage" else 4
    for attempt in range(max_attempts):
        try:
            if method in {"getMe","getUpdates","delWebhook"}:
                req=Request(f"{API}/{method}"+("?"+query if query else ""),headers={"Accept":"application/json","Connection":"close"})
            else:
                req=Request(f"{API}/{method}",data=json.dumps(params,ensure_ascii=False).encode(),headers={"Content-Type":"application/json; charset=utf-8","Connection":"close"})
            request_timeout = 6 if method == "getUpdates" else 20
            with urlopen(req,timeout=request_timeout) as response:
                payload=response.read().decode("utf-8")
            if not payload and method == "getUpdates":
                return []
            result=json.loads(payload)
            if result.get("ok"):
                if method in {"getMe", "getUpdates"}:
                    global api_health_last_write
                    if time.monotonic()-api_health_last_write >= 15:
                        DATA.mkdir(parents=True,exist_ok=True)
                        temporary=API_HEALTH.with_suffix(".tmp")
                        temporary.write_text(json.dumps({"updated_at":time.time()}),encoding="utf-8")
                        temporary.replace(API_HEALTH)
                        api_health_last_write=time.monotonic()
                return result.get("result")
            last_error=RuntimeError(result.get("result") or result.get("description") or "Potato API 请求失败")
            retryable=True
        except HTTPError as error:
            detail=error.read(500).decode("utf-8",errors="replace").strip()
            last_error=RuntimeError(f"HTTP {error.code}"+(f"：{detail}" if detail else ""))
            retryable=error.code in {429,500,502,503,504}
        except (RemoteDisconnected, TimeoutError, URLError, ConnectionError, ssl.SSLError, json.JSONDecodeError) as error:
            last_error=error; retryable=True
        if not retryable or attempt==max_attempts-1: break
        delay=min(0.8*(2**attempt),8)
        log.warning("Potato API 暂时不可用：method=%s attempt=%s/%s error=%s；%.1f 秒后重试",method,attempt+1,max_attempts,last_error,delay)
        time.sleep(delay)
    raise last_error or RuntimeError("Potato API 请求失败")

class PotatoRpc:
    def __init__(self): self.chat_types={int(k):int(v) for k,v in reference.state.get("potato_chat_types",{}).items()}
    def send_msg(self,_accid,chat_id,data):
        payload={"chat_type":int(self.chat_types.get(int(chat_id),1)),"chat_id":int(chat_id),"text":data.text}
        if re.search(r"\[[^\]\n]+\]\(https://[^\s)]+\?reader_source=[^\s)]+\)",data.text): payload["markdown"]=True
        potato_api("sendTextMessage",payload)
        log.info("Potato 消息发送成功：chat_id=%s",chat_id)
    def get_basic_chat_info(self,_accid,chat_id):
        ctype=int(self.chat_types.get(int(chat_id),1)); return SimpleNamespace(chat_type=_ChatType.GROUP if ctype in {2,3} else 1,self_in_group=ctype in {2,3})
    def get_full_chat_by_id(self,accid,chat_id): return self.get_basic_chat_info(accid,chat_id)
    def create_chat_by_contact_id(self,_accid,contact_id): return int(reference.state.get("potato_private_chats",{}).get(str(contact_id),contact_id))
    def get_all_account_ids(self): return [1]
class PotatoBot:
    def __init__(self): self.rpc=PotatoRpc(); self.logger=log
bot=PotatoBot()

_original_admin_help=reference.admin_help_text
_original_help=reference.help_text
def _potato_help(site=None):
    return _original_help(site).replace(
        "群状态 — 查看全群完成情况",
        "群状态 — 查看今日全群完成情况\n本周总结 — 查看本周全组总结\n历史总结 — 查看全组历史总结",
    )
reference.help_text=_potato_help

def _potato_admin_help(super_admin=False, group_admin=False):
    base=_original_admin_help(super_admin,group_admin)
    if not super_admin and not group_admin: return base
    base=base.replace("管理员 绑定群 网站 群ID — 绑定通知群",
                      "管理员 绑定群 — 按提示绑定 Cedar 通知群\n管理员 解绑群 — 按提示解除 Cedar 通知群绑定")
    return base+"\n\n【总结推送】\n管理员 本周总结 — 发布本周总结\n管理员 历史总结 — 发布历史总结"
reference.admin_help_text=_potato_admin_help

reference.admin_bind_group_guide=lambda: "私聊发送“管理员 绑定群”并按提示回复；发送“管理员 解绑群”可解除 Cedar 群绑定。"

def _potato_admin_group_list_text():
    chat_types=reference.state.get("potato_chat_types",{})
    chat_names=reference.state.get("potato_chat_names",{})
    group_ids={int(chat_id) for chat_id,ctype in chat_types.items() if int(ctype) in {2,3}}
    group_ids.update(reference.SITE_BY_CHAT_ID)
    lines=["🛡️ 机器人已发现的群聊"]
    if not group_ids:
        return "\n".join(lines+["暂无。请先把机器人加入群，并在群里发送任意一条消息；机器人不会回复，但会记录群 ID。"])
    for group_id in sorted(group_ids):
        site=reference.SITE_BY_CHAT_ID.get(group_id)
        binding=f"已绑定：{site.name}" if site else "未绑定"
        chat_type=int(chat_types.get(str(group_id),bot.rpc.chat_types.get(group_id,2)))
        type_name="超级群/频道" if chat_type==3 else "群聊"
        name=str(chat_names.get(str(group_id),"")).strip()
        label=f" · {name}" if name else ""
        lines.append(f"{group_id}{label}｜{type_name}｜{binding}")
    lines.extend(["","发送“管理员 绑定群”按提示绑定 Cedar 小组。","发送“管理员 解绑群”按提示解除绑定。"])
    return "\n".join(lines)
reference.admin_group_list_text=_potato_admin_group_list_text

group_binding_flows={}

def _cedar_sites():
    return [site for site in reference.SITES if reference.is_cedar_site(site)]

def _group_name(group_id):
    return str(reference.state.get("potato_chat_names",{}).get(str(group_id),"")).strip()

def _binding_label(site):
    return site.name.rsplit("/",1)[-1].strip()

def _match_name(value):
    value=unicodedata.normalize("NFKC",value).casefold().replace("侍奉","事奉").replace("🚪训","门训")
    value=value.rsplit("/",1)[-1]
    for word in ("yds","hz","jh","个人","门训","小组","通知","群聊","群","组"):
        value=value.replace(word,"")
    return "".join(char for char in value if char.isalnum())

def _suggest_site(group_id):
    key=_match_name(_group_name(group_id))
    if len(key)<2:
        return None
    matches=[]
    for site in _cedar_sites():
        site_key=_match_name(_binding_label(site))
        if site_key and (key==site_key or key in site_key or site_key in key):
            matches.append(site)
    return matches[0] if len(matches)==1 else None

def _binding_groups(mode):
    if mode=="bind":
        return sorted(int(group_id) for group_id,kind in reference.state.get("potato_chat_types",{}).items()
                      if int(kind) in {2,3} and int(group_id) not in reference.SITE_BY_CHAT_ID)
    return sorted(group_id for group_id,site in reference.SITE_BY_CHAT_ID.items() if reference.is_cedar_site(site))

def _flow_group_list(mode,groups):
    title="🧭 选择要绑定的群（回复编号）" if mode=="bind" else "🧭 选择要解绑的 Cedar 通知群（回复编号）"
    lines=[title]
    for index,group_id in enumerate(groups,1):
        name=_group_name(group_id)
        label=f" · {name}" if name else ""
        site=_suggest_site(group_id) if mode=="bind" else reference.SITE_BY_CHAT_ID.get(group_id)
        hint=f" → 建议：{_binding_label(site)}" if mode=="bind" and site else f" → {_binding_label(site)}" if site else ""
        lines.append(f"{index}. {group_id}{label}{hint}")
    lines.append("回复“取消”退出。")
    return "\n".join(lines)

def _flow_site_list():
    lines=["请选择 Cedar 小组（回复编号）："]
    lines.extend(f"{index}. {_binding_label(site)}" for index,site in enumerate(_cedar_sites(),1))
    lines.append("回复“取消”退出。")
    return "\n".join(lines)

def _start_group_binding_flow(cid,uid,mode):
    group_binding_flows.pop(cid,None)
    if not reference.is_super_admin(uid):
        reference.send(bot,1,cid,"Cedar 通知群绑定与解绑仅限超级管理员。")
        return
    if not _cedar_sites():
        reference.send(bot,1,cid,"尚未配置 Cedar 小组。")
        return
    groups=_binding_groups(mode)
    if not groups:
        message="没有待绑定的群。请先把机器人加入群，并在群里发送任意消息。" if mode=="bind" else "目前没有已绑定的 Cedar 通知群。"
        reference.send(bot,1,cid,message)
        return
    group_binding_flows[cid]={"uid":uid,"mode":mode,"stage":"group","groups":groups,"expires":time.monotonic()+900}
    reference.send(bot,1,cid,_flow_group_list(mode,groups))

def _handle_group_binding_flow(cid,uid,text):
    clean=text.strip().rstrip("！!。.")
    if re.match(r"^管理员\s*绑定群",clean):
        _start_group_binding_flow(cid,uid,"bind")
        return True
    if re.match(r"^管理员\s*解绑群",clean):
        _start_group_binding_flow(cid,uid,"unbind")
        return True
    flow=group_binding_flows.get(cid)
    if not flow:
        return False
    if clean.startswith("管理员"):
        group_binding_flows.pop(cid,None)
        return False
    if flow["uid"]!=uid or not reference.is_super_admin(uid):
        group_binding_flows.pop(cid,None)
        reference.send(bot,1,cid,"该操作仅限发起流程的超级管理员。")
        return True
    if time.monotonic()>flow["expires"]:
        group_binding_flows.pop(cid,None)
        reference.send(bot,1,cid,"操作已超时。请重新发送“管理员 绑定群”或“管理员 解绑群”。")
        return True
    if clean in {"取消","退出"}:
        group_binding_flows.pop(cid,None)
        reference.send(bot,1,cid,"已取消，群绑定未变更。")
        return True
    if flow["stage"]=="group":
        groups=flow["groups"]
        group_id=groups[int(clean)-1] if clean.isdigit() and 1<=int(clean)<=len(groups) else int(clean) if clean.isdigit() and int(clean) in groups else None
        if group_id is None:
            reference.send(bot,1,cid,_flow_group_list(flow["mode"],groups))
            return True
        flow["group_id"]=group_id
        if flow["mode"]=="unbind":
            site=reference.SITE_BY_CHAT_ID.get(group_id)
            if not site or not reference.is_cedar_site(site):
                group_binding_flows.pop(cid,None)
                reference.send(bot,1,cid,"该群的 Cedar 绑定已变化，请重新开始。")
                return True
            flow["site_id"]=site.site_id
        else:
            site=_suggest_site(group_id)
            if not site:
                flow["stage"]="site"
                reference.send(bot,1,cid,_flow_site_list())
                return True
            flow["site_id"]=site.site_id
        flow["stage"]="confirm"
        site=reference.SITE_BY_ID[flow["site_id"]]
        verb="绑定到" if flow["mode"]=="bind" else "从此小组解绑"
        option="；回复“其他”选择小组" if flow["mode"]=="bind" else ""
        reference.send(bot,1,cid,f"群：{group_id} · {_group_name(group_id) or '未命名'}\nCedar 小组：{_binding_label(site)}\n确认{verb}？回复“确认”{option}，或回复“取消”。")
        return True
    if flow["stage"]=="site":
        sites=_cedar_sites()
        site=sites[int(clean)-1] if clean.isdigit() and 1<=int(clean)<=len(sites) else reference.find_site(clean)
        if not site or not reference.is_cedar_site(site):
            reference.send(bot,1,cid,_flow_site_list())
            return True
        flow["site_id"]=site.site_id
        flow["stage"]="confirm"
        reference.send(bot,1,cid,f"群：{flow['group_id']} · {_group_name(flow['group_id']) or '未命名'}\nCedar 小组：{_binding_label(site)}\n确认绑定？回复“确认”，或回复“取消”。")
        return True
    if clean=="其他" and flow["mode"]=="bind":
        flow["stage"]="site"
        reference.send(bot,1,cid,_flow_site_list())
        return True
    if clean!="确认":
        reference.send(bot,1,cid,"请回复“确认”或“取消”；绑定时也可回复“其他”重新选择小组。")
        return True
    group_binding_flows.pop(cid,None)
    site=reference.SITE_BY_ID.get(flow["site_id"])
    if not site or not reference.is_cedar_site(site):
        reference.send(bot,1,cid,"小组配置已变化，请重新开始。")
        return True
    group_id=flow["group_id"]
    try:
        if flow["mode"]=="bind":
            group_chat=bot.rpc.get_full_chat_by_id(1,group_id)
            if group_chat.chat_type!=_ChatType.GROUP or not group_chat.self_in_group:
                raise ValueError("机器人已不在该群，请重新加入后再绑定。")
            reference.bind_group_to_site(site,group_id)
            result="绑定"
        else:
            reference.unbind_group_from_site(site,group_id)
            result="解绑"
        reference.send(bot,1,cid,f"✅ 已{result}：群 {group_id} · {_binding_label(site)}。配置已保存并立即生效。")
    except (ValueError,RuntimeError,OSError) as error:
        reference.send(bot,1,cid,f"❌ {error}")
    return True

def _percent(done,total): return f"{(done*100/total):.1f}%" if total else "0.0%"

def _message_chunks(message,max_length=3500):
    """按行拆分长总结，给 Potato 的单条消息长度留出余量。"""
    chunks=[]; current=[]; current_length=0
    for line in message.splitlines():
        addition=len(line)+(1 if current else 0)
        if current and current_length+addition>max_length:
            chunks.append("\n".join(current)); current=[]; current_length=0
        current.append(line); current_length+=len(line)+(1 if current_length else 0)
    if current: chunks.append("\n".join(current))
    return chunks or [message]

def _broadcast_summary(site,message):
    delivered=0
    for group_chat_id in sorted(site.chat_ids):
        try:
            for index,chunk in enumerate(_message_chunks(message),1):
                suffix=f"\n\n（第 {index}/{len(_message_chunks(message))} 段）" if len(_message_chunks(message))>1 else ""
                reference.send(bot,1,group_chat_id,chunk+suffix)
            delivered+=1
        except Exception as error:
            log.exception("发送群总结失败：site=%s chat_id=%s error=%s",site.site_id,group_chat_id,error)
    return delivered

def _weekly_group_summary(site):
    website_state,site_config=reference.website_snapshot(site); members=[str(x).strip() for x in website_state.get("members") or [] if str(x).strip()]
    records=website_state.get("records") or []; schedule=website_state.get("weeklySchedule") or site_config.get("weekly_schedule") or []; current=reference.now(site).date(); plan=reference.current_week(schedule,current)
    week_start=date.fromisoformat(str(plan.get("start"))) if plan else current-timedelta(days=current.weekday())
    week_end=min(current,date.fromisoformat(str(plan.get("end"))) if plan else current)
    week_days=[week_start+timedelta(days=index) for index in range((week_end-week_start).days+1)]
    tasks=[("每日灵修","灵修")]
    for task,label in (("周读物","周读物"),("周视频","视频"),("周背经","背经")):
        if plan and reference.weekly_task_value(plan,task): tasks.append((task,label))
    category=[]; member_rows=[]; overall_done=0; overall_required=len(members)*(len(week_days)+len(tasks)-1); task_results={}
    daily_results={name:{day for day in week_days if any(reference.website_record_matches(row,name,"每日灵修",day,schedule,site) for row in records)} for name in members}
    task_results["每日灵修"]=daily_results
    daily_done=sum(len(days) for days in daily_results.values()); daily_required=len(members)*len(week_days)
    all_daily=[name for name,days in daily_results.items() if len(days)==len(week_days)]
    partial_daily=[f"{name}（{len(days)}/{len(week_days)}）" for name,days in daily_results.items() if 0<len(days)<len(week_days)]
    category.extend([f"【灵修】本周累计：{daily_done}/{daily_required} 次｜完成率 {_percent(daily_done,daily_required)}",f"全程完成：{'、'.join(all_daily) or '暂无'}",f"进行中：{'、'.join(partial_daily) or '暂无'}",""])
    for task,label in tasks[1:]:
        completed=[name for name in members if any(reference.website_record_matches(row,name,task,week_start,schedule,site) for row in records)]
        task_results[task]=set(completed)
        missing=[name for name in members if name not in completed]
        category.extend([f"【{label}】本周：{len(completed)}/{len(members)} 人｜完成率 {_percent(len(completed),len(members))}",f"已完成：{'、'.join(completed) or '暂无'}",f"待完成：{'、'.join(missing) or '无（全员完成）'}",""])
    for name in members:
        daily_count=len(daily_results[name]); weekly_count=sum(name in task_results[task] for task,_ in tasks[1:]); completed=daily_count+weekly_count; required=len(week_days)+len(tasks)-1; overall_done+=completed
        icon="✅" if completed==required else "🟡" if completed else "⭕"
        buttons=f"灵修 {daily_count}/{len(week_days)}（{_percent(daily_count,len(week_days))}）"
        if tasks[1:]: buttons+="\n"+" ".join(f"{label}{'✅' if name in task_results[task] else '❌'}" for task,label in tasks[1:])
        member_rows.append(f"{icon} {name}：{completed}/{required} 项｜{_percent(completed,required)}\n{buttons}\n────────────")
    week_label=str((plan or {}).get("title") or "本周门训")
    return "\n".join([f"📊 {site.name}｜本周全组总结",f"统计区间：{week_start.isoformat()} 至 {week_end.isoformat()}",f"本周主题：{week_label}","",f"【总体】{overall_done}/{overall_required} 项｜完成率 {_percent(overall_done,overall_required)}",f"全程完成：{sum(row.startswith('✅') for row in member_rows)}/{len(members)} 人","","一、各项完成情况",*category,"二、个人完成情况","说明：✅全部完成｜🟡部分完成｜⭕尚未完成","────────────",*member_rows])

def _history_group_summary(site):
    history_start=date(2026,4,6)
    website_state,site_config=reference.website_snapshot(site); members=[str(x).strip() for x in website_state.get("members") or [] if str(x).strip()]
    original_snapshot=reference.website_snapshot; reference.website_snapshot=lambda _site:(website_state,site_config)
    stats=[]; total_done=total_required=0
    task_totals={label:[0,0] for label in ("灵修","周读物","视频","背经")}
    try:
        for name in members:
            text=reference.member_history_summary(site,name,start_date=history_start); match=re.search(r"总进度：(\d+)/(\d+) 项",text)
            done,required=(int(match.group(1)),int(match.group(2))) if match else (0,0); total_done+=done; total_required+=required
            breakdown={}
            for label in ("灵修","周读物","视频","背经"):
                item=re.search(rf"^{label}：(\d+)/(\d+)",text,re.MULTILINE)
                values=(int(item.group(1)),int(item.group(2))) if item else (0,0)
                breakdown[label]=values; task_totals[label][0]+=values[0]; task_totals[label][1]+=values[1]
            stats.append((done/required if required else 0,name,done,required,breakdown))
    finally: reference.website_snapshot=original_snapshot
    current=reference.now(site).date().isoformat()
    rows=[]
    for index,(ratio,name,done,required,breakdown) in enumerate(sorted(stats,key=lambda item:(-item[0],item[1])),1):
        icon="🟢" if ratio>=0.8 else "🟡" if ratio>=0.6 else "🟠" if ratio>=0.4 else "🔴"
        buttons=(
            f"灵修 {breakdown['灵修'][0]}/{breakdown['灵修'][1]}｜"
            f"周读物 {breakdown['周读物'][0]}/{breakdown['周读物'][1]}\n"
            f"视频 {breakdown['视频'][0]}/{breakdown['视频'][1]}｜"
            f"背经 {breakdown['背经'][0]}/{breakdown['背经'][1]}"
        )
        rows.append(f"{index}. {icon} {name}：{done}/{required} 项｜{_percent(done,required)}\n{buttons}\n────────────")
    task_rows=[f"【{label}】{done}/{required}｜{_percent(done,required)}" for label,(done,required) in task_totals.items()]
    return "\n".join([f"📈 {site.name}｜全组历史总结",f"统计区间：{history_start.isoformat()} 至 {current}",f"参与统计：{len(members)} 人","",f"【总体】{total_done}/{total_required} 项｜完成率 {_percent(total_done,total_required)}","","一、各打卡按钮完成分析",*task_rows,"","二、个人明细（按总完成率排序）","说明：🟢≥80%｜🟡60–79%｜🟠40–59%｜🔴<40%","────────────",*rows])

def _send_private_summary(cid,uid,text):
    normalized=text.strip().replace(" ","").rstrip("！!。.")
    if normalized not in {"本周总结","本周门训总结","全组本周总结","历史总结","全组历史总结"}: return False
    _,site=reference.resolve_message_site(bot,1,cid,uid)
    if not site:
        reference.send(bot,1,cid,"请先发送“网站”，再选择需要统计的网站。")
        return True
    try:
        message=_weekly_group_summary(site) if normalized in {"本周总结","本周门训总结","全组本周总结"} else _history_group_summary(site)
        chunks=_message_chunks(message)
        for index,chunk in enumerate(chunks,1):
            suffix=f"\n\n（第 {index}/{len(chunks)} 段）" if len(chunks)>1 else ""
            reference.send(bot,1,cid,chunk+suffix)
    except Exception:
        log.exception("私聊生成门训总结失败")
        reference.send(bot,1,cid,"生成总结失败，请检查网站连接后重试。")
    return True

def _handle_potato_admin_summary(cid,uid,text):
    if not re.match(r"^管理员(?:\s|本周|历史)",text.strip()): return False
    normalized=re.sub(r"^管理员\s*", "", text.strip()).replace(" ","")
    if normalized not in {"本周总结","本周门训总结","历史总结","历史门训总结"}: return False
    _,site=reference.resolve_message_site(bot,1,cid,uid)
    if not site:
        reference.send(bot,1,cid,"请先发送“网站”，再选择需要统计的网站。")
        return True
    if not reference.is_admin(uid,site):
        reference.send(bot,1,cid,f"你没有 {site.name} 的管理权限。")
        return True
    try:
        message=_weekly_group_summary(site) if normalized in {"本周总结","本周门训总结"} else _history_group_summary(site)
        delivered=_broadcast_summary(site,message)
        reference.send(bot,1,cid,f"✅ 总结已发送到 {delivered} 个通知群。" if delivered else "该网站还没有配置通知群。")
    except Exception:
        log.exception("生成门训总结失败")
        reference.send(bot,1,cid,"生成总结失败，请检查网站连接后重试。")
    return True

dispatch_pool=ThreadPoolExecutor(max_workers=8,thread_name_prefix="potato-message")
dispatch_locks={}; dispatch_locks_guard=threading.Lock()

def dispatch(update):
    message=update.get("message") or {}; chat=message.get("chat") or {}; cid=chat.get("id")
    if cid is None:return
    ctype=int(chat.get("type",1)); uid=int((message.get("from") or {}).get("id",cid)); bot.rpc.chat_types[int(cid)]=ctype
    changed=False
    if str(reference.state.setdefault("potato_chat_types",{}).get(str(cid)))!=str(ctype): reference.state["potato_chat_types"][str(cid)]=ctype; changed=True
    chat_name=str(chat.get("title") or chat.get("name") or "").strip()
    if ctype in {2,3} and chat_name and reference.state.setdefault("potato_chat_names",{}).get(str(cid))!=chat_name: reference.state["potato_chat_names"][str(cid)]=chat_name; changed=True
    if ctype==1 and str(reference.state.setdefault("potato_private_chats",{}).get(str(uid)))!=str(cid): reference.state["potato_private_chats"][str(uid)]=int(cid); changed=True
    if changed: reference.save_state()
    log.info("收到消息：chat_id=%s chat_type=%s", cid, chat.get("type",1))
    # 群聊只作为通知出口；任何群消息都不进入命令处理器，也不回复帮助。
    if ctype in {2,3}:
        return
    if _handle_group_binding_flow(int(cid),uid,message.get("text") or ""): return
    if _handle_potato_admin_summary(int(cid),uid,message.get("text") or ""): return
    if _send_private_summary(int(cid),uid,message.get("text") or ""): return
    event=SimpleNamespace(msg=SimpleNamespace(chat_id=int(cid),from_id=uid,text=message.get("text") or ""))
    reference.cli.new_message(bot,1,event)

def dispatch_ordered(update):
    message=update.get("message") or {}; chat=message.get("chat") or {}
    lock_key=int(chat.get("id") or 0)
    with dispatch_locks_guard:
        lock=dispatch_locks.setdefault(lock_key,threading.Lock())
    started=time.monotonic()
    with lock:
        dispatch(update)
    elapsed=time.monotonic()-started
    if elapsed >= 1:
        log.info("消息处理完成：chat_id=%s elapsed=%.2fs",lock_key,elapsed)

def log_dispatch_failure(future):
    error=future.exception()
    if error is not None:
        log.error("Potato 消息处理或回复失败",exc_info=(type(error),error,error.__traceback__))

def main():
    while True:
        try:
            potato_api("getMe")
            break
        except KeyboardInterrupt:
            return
        except Exception:
            log.exception("Potato 启动认证暂时失败，10 秒后重试")
            time.sleep(10)
    if reference.cli.on_start_callback:
        reference.cli.on_start_callback(bot,None)
    log.info("Potato 门训同行机器人已启动（完整参考业务模式）"); offset=0
    while True:
        try:
            # Potato 服务端偶尔会关闭空闲长轮询连接；短轮询更稳定，断开后自动续拉。
            # 短轮询让新消息尽快返回；消息本身交给线程池处理，不阻塞下一轮拉取。
            for update in potato_api("getUpdates",{"offset":offset,"timeout":1}) or []:
                offset=max(offset,int(update["update_id"])+1)
                dispatch_pool.submit(dispatch_ordered,update).add_done_callback(log_dispatch_failure)
        except KeyboardInterrupt:return
        except (RemoteDisconnected, TimeoutError, URLError, ConnectionError) as error:
            log.warning("Potato 轮询连接中断，将自动重试：%s", error)
            time.sleep(2)
        except Exception:
            log.exception("Potato 轮询失败，2 秒后重试")
            time.sleep(2)
if __name__=="__main__": main()
