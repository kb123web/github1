from __future__ import annotations
import base64, json, os, re, subprocess
from pathlib import Path
from typing import Any, Iterable
import cv2, imageio_ffmpeg
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

IMAGE_EXTENSIONS={".jpg",".jpeg",".png",".webp"}; VIDEO_EXTENSIONS={".mp4",".mov",".mkv",".avi"}; ALLOWED=IMAGE_EXTENSIONS|VIDEO_EXTENSIONS|{".mp3",".wav",".m4a"}

def save_uploads(folder: Path, files: Iterable[Any], subdir: str)->list[Path]:
    target=folder/subdir; target.mkdir(exist_ok=True); saved=[]
    for number,item in enumerate(files,1):
        name=Path(item.filename or "").name
        if name and Path(name).suffix.lower() in ALLOWED:
            path=target/f"{number:03d}_{name}"; item.save(path); saved.append(path)
    return saved

def provider_status()->dict[str,bool]: return {"deepseek":bool(os.getenv("DEEPSEEK_API_KEY")),"openai_vision":bool(os.getenv("OPENAI_API_KEY"))}
def _data_url(path:Path)->str:
    mime="image/png" if path.suffix.lower()==".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
def _json(text:str)->dict[str,Any]:
    text=re.sub(r"^```(?:json)?\s*|\s*```$","",text.strip(),flags=re.I); first,last=text.find("{"),text.rfind("}")
    if first<0 or last<first: raise ValueError("Model did not return JSON")
    return json.loads(text[first:last+1])
def _deepseek():
    return OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"),base_url=os.getenv("DEEPSEEK_BASE_URL","https://api.deepseek.com")) if OpenAI and os.getenv("DEEPSEEK_API_KEY") else None
def _openai(): return OpenAI() if OpenAI and os.getenv("OPENAI_API_KEY") else None

def _manual_recognition(description:str)->dict[str,Any]:
    return {"name":description.splitlines()[0][:40] if description else "待确认商品","category":"待人工确认","appearance":["已上传商品图片"],"possible_uses":["拍摄前请确认用途"],"visible_selling_points":["仅使用可验证卖点"],"unknowns":["材质、规格、功效、价格和认证均需人工确认"],"confidence":"人工确认","provider":"人工识别兜底"}

def recognize_product(description:str, images:list[Path])->dict[str,Any]:
    prompt="Return JSON only in Chinese: name, category, appearance(array), possible_uses(array), visible_selling_points(array), unknowns(array), confidence. Identify only visible or user-provided facts. Put uncertain material, price, efficacy, certification and specs in unknowns. User notes: "+description
    probe="未配置 DeepSeek 密钥。"
    client=_deepseek()
    if client and images:
        try:
            content=[{"type":"text","text":prompt}]+[{"type":"image_url","image_url":{"url":_data_url(path)}} for path in images[:4]]
            reply=client.chat.completions.create(model=os.getenv("DEEPSEEK_MODEL","deepseek-chat"),messages=[{"role":"user","content":content}],temperature=.1)
            result=_json(reply.choices[0].message.content or ""); result["provider"]="DeepSeek 图片识别"; return result
        except Exception as exc: probe=str(exc)[:180]
    client=_openai()
    if client and images:
        try:
            content=[{"type":"input_text","text":prompt}]+[{"type":"input_image","image_url":_data_url(path)} for path in images[:4]]
            reply=client.responses.create(model=os.getenv("OPENAI_VISION_MODEL","gpt-4.1-mini"),input=[{"role":"user","content":content}])
            result=_json(reply.output_text); result["provider"]="OpenAI 图片识别兜底"; result["deepseek_probe"]=probe; return result
        except Exception as exc: probe+=" OpenAI："+str(exc)[:120]
    result=_manual_recognition(description); result["vision_warning"]=probe; return result

def _default_options(recognition:dict[str,Any])->list[dict[str,Any]]:
    product=recognition.get("name","这款商品"); points=recognition.get("visible_selling_points") or ["真实外观","使用方式","适用场景"]
    data=[("痛点解决型","你是不是也遇到过这个问题？"),("场景种草型","这正是它派上用场的时候。"),("体验展示型","先看清细节，再决定是否需要。")] ; options=[]
    for option_id,(title,hook) in enumerate(data,1):
        rows=[("开场钩子","竖屏特写，展示痛点或最有吸引力的视觉细节",hook),("产品亮相","展示产品全貌、包装和清晰细节特写",f"这就是{product}。"),("使用演示","手持或真人出镜，演示一个真实使用动作","重点看这个真实使用细节。"),("卖点证明","展示两个可验证卖点或适用场景","按自己的真实需要来选择。"),("行动引导","产品定格并展示已核实的活动信息","可以查看下方已核实的商品详情。")]
        storyboard=[{"id":index,"duration":6,"scene":scene,"visual":visual,"dialogue":dialogue,"subtitle":dialogue,"transition":"cut","source_option":option_id} for index,(scene,visual,dialogue) in enumerate(rows,1)]
        options.append({"id":option_id,"title":title,"hook":hook,"angle":title,"target_audience":"有对应真实需求的用户","selling_points":points,"cta":"仅使用已核实的促销信息","storyboard":storyboard})
    return options

def _deepseek_options(recognition:dict[str,Any],description:str)->list[dict[str,Any]]|None:
    client=_deepseek()
    if not client:return None
    prompt=f"Return JSON only with key options containing exactly 3 Chinese Douyin plans. Product: {json.dumps(recognition,ensure_ascii=False)}. Notes:{description}. Each option has id,title,hook,angle,target_audience,selling_points,cta,storyboard. Each storyboard has 5 items id,duration,scene,visual,dialogue,subtitle,transition,source_option. Total 30 seconds. Use pain point, scenario, experience. Do not invent price, efficacy, certification or unseen facts."
    try:
        reply=client.chat.completions.create(model=os.getenv("DEEPSEEK_MODEL","deepseek-chat"),messages=[{"role":"user","content":prompt}],temperature=.7)
        return _json(reply.choices[0].message.content or "").get("options")
    except Exception:return None

def _risk_flags(text:str)->list[str]:
    rules={"绝对化表述":r"best|first|100%|permanent|绝对|最好|第一","功效承诺":r"cure|treat|guarantee|治愈|治疗|根治|保证","夸大或无依据表述":r"instant|zero risk|no side effects|立刻见效|零风险|无副作用"}
    return [label for label,rule in rules.items() if re.search(rule,text,re.I)]

def create_plan(description:str,image_dir:Path)->dict[str,Any]:
    images=sorted(path for path in image_dir.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS); recognition=recognize_product(description,images); options=_deepseek_options(recognition,description) or _default_options(recognition)
    return {"recognition":recognition,"options":options,"selected_storyboard":options[0]["storyboard"],"shooting_advice":{"talking_head":"竖屏拍摄，镜头与眼睛平齐。先拍完整口播，再补拍产品特写、手部动作、包装与使用场景。","product_only":"使用稳定机位和柔和光线，分别拍摄产品全貌、材质细节、操作、使用结果与已核实信息。"},"compliance":{"flags":_risk_flags(description),"note":"发布前请核实价格、活动、功效、对比数据和素材权益。"},"missing_shots":["产品正面清晰特写","关键细节近景","完整使用动作","已核实的包装或活动信息镜头"]}

def update_storyboard(plan:dict[str,Any],shots:list[dict[str,Any]])->dict[str,Any]:
    clean=[]
    for index,shot in enumerate(shots[:8],1):
        duration=max(1,min(12,float(shot.get("duration",0))))
        clean.append({"id":index,"duration":duration,"scene":str(shot.get("scene","镜头"))[:80],"visual":str(shot.get("visual",""))[:500],"dialogue":str(shot.get("dialogue",""))[:300],"subtitle":str(shot.get("subtitle",shot.get("dialogue","")))[:120],"transition":"cut","source_option":int(shot.get("source_option",0))})
    plan["selected_storyboard"]=clean; plan["total_duration"]=sum(shot["duration"] for shot in clean); return plan

def _video_info(path:Path)->dict[str,Any]:
    cap=cv2.VideoCapture(str(path)); fps=cap.get(cv2.CAP_PROP_FPS) or 0; frames=cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0; width,height=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)); cap.release()
    return {"file":path.name,"duration":round(frames/fps,2) if fps else 0,"fps":round(fps,2),"width":width,"height":height,"orientation":"vertical" if height>width else "horizontal"}
def analyze_video(folder:Path,plan:dict[str,Any])->dict[str,Any]:
    videos=sorted(path for path in (folder/"raw_videos").iterdir() if path.suffix.lower() in VIDEO_EXTENSIONS); info=[_video_info(path) for path in videos]; duration=sum(item["duration"] for item in info); missing=list(plan.get("missing_shots",[])); issues=[]
    if duration<20:missing.append("请补拍更多素材：当前总时长不足 20 秒。")
    if any(item["orientation"]=="horizontal" for item in info):issues.append("横屏素材将在导出时裁切为 9:16 竖屏。")
    return {"videos":info,"total_duration":round(duration,2),"covered_shots":min(len(plan.get("selected_storyboard",[])),len(videos)*2),"missing_shots":missing,"issues":issues,"timeline":[{"source":item["file"],"start":0,"duration":min(item["duration"],6),"target_scene":index+1} for index,item in enumerate(info[:5])]}
def _write_srt(folder:Path,plan:dict[str,Any])->Path:
    def stamp(value:float)->str:
        hour,rest=divmod(int(value),3600); minute,second=divmod(rest,60); return f"{hour:02}:{minute:02}:{second:02},{int((value%1)*1000):03}"
    rows=[]; start=0.0
    for index,shot in enumerate(plan.get("selected_storyboard",[]),1):
        duration=float(shot["duration"]); rows += [str(index),f"{stamp(start+.2)} --> {stamp(start+duration-.2)}",shot.get("subtitle") or shot.get("dialogue",""),""]; start+=duration
    path=folder/"subtitles.srt"; path.write_text("\n".join(rows),encoding="utf-8"); return path
def export_video(folder:Path,report:dict[str,Any],voice_mode:str="original")->dict[str,Any]:
    videos=sorted(path for path in (folder/"raw_videos").iterdir() if path.suffix.lower() in VIDEO_EXTENSIONS)
    if not videos:return {"ok":False,"message":"没有可用的实拍视频。"}
    plan=json.loads((folder/"plan.json").read_text(encoding="utf-8")); srt=_write_srt(folder,plan); ffmpeg=imageio_ffmpeg.get_ffmpeg_exe(); output=folder/"final.mp4"; srt_path=str(srt.resolve()).replace("\\","/").replace(":","\\:")
    command=[ffmpeg,"-y","-i",str(videos[0]),"-map","0:v:0","-map","0:a?","-vf",f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,subtitles='{srt_path}',format=yuv420p","-t","30","-c:v","libx264","-preset","medium","-b:v","8M","-c:a","aac","-b:a","128k","-movflags","+faststart",str(output)]
    try: subprocess.run(command,check=True,capture_output=True,text=True); return {"ok":True,"message":"初稿已导出：1080×1920、H.264/AAC 的 MP4 视频。"}
    except subprocess.CalledProcessError as exc:return {"ok":False,"message":f"导出失败：{exc.stderr[-400:]}"}
