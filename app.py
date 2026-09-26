from __future__ import annotations
import json, os, uuid
from pathlib import Path
from typing import Any
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from agent_core import analyze_video, create_plan, export_video, provider_status, save_uploads, update_storyboard

load_dotenv(); ROOT=Path(__file__).resolve().parent; DATA_DIR=ROOT/"data"; DATA_DIR.mkdir(exist_ok=True)
app=Flask(__name__); app.secret_key=os.getenv("FLASK_SECRET_KEY","local-live-sales-agent"); app.config["MAX_CONTENT_LENGTH"]=1024*1024*1024
def job_path(job_id:str)->Path:return DATA_DIR/job_id
def read_json(path:Path,default:Any=None)->Any:
    try:return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError,json.JSONDecodeError):return default
def write_json(path:Path,data:Any)->None:path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

@app.get("/")
def index():
    jobs=[]
    for folder in sorted(DATA_DIR.iterdir(),reverse=True):
        if folder.is_dir():
            meta=read_json(folder/"meta.json",{}); jobs.append({"id":folder.name,"title":meta.get("title","未命名商品"),"has_plan":(folder/"plan.json").exists(),"has_video":(folder/"final.mp4").exists()})
    return render_template("index.html",jobs=jobs[:20],providers=provider_status())

@app.post("/jobs")
def create_job():
    description=request.form.get("description","").strip(); images=request.files.getlist("product_images")
    if not any(item.filename for item in images):
        flash("请至少上传一张商品图片。","error"); return redirect(url_for("index"))
    job_id=uuid.uuid4().hex[:12]; folder=job_path(job_id); folder.mkdir(parents=True); write_json(folder/"meta.json",{"title":request.form.get("title","").strip() or "未命名商品","description":description})
    save_uploads(folder,images,"product_images"); write_json(folder/"plan.json",create_plan(description,folder/"product_images")); return redirect(url_for("job",job_id=job_id))

@app.route("/jobs/<job_id>",methods=["GET","POST"])
def job(job_id:str):
    folder=job_path(job_id)
    if not folder.exists():return "任务不存在",404
    plan=read_json(folder/"plan.json",{})
    if "recognition" not in plan:
        plan=create_plan(read_json(folder/"meta.json",{}).get("description",""),folder/"product_images")
        write_json(folder/"plan.json",plan)
    if request.method=="POST":
        videos=request.files.getlist("raw_videos"); music=request.files.get("music")
        if not any(item.filename for item in videos):flash("请至少上传一个实拍视频。","error"); return redirect(url_for("job",job_id=job_id))
        save_uploads(folder,videos,"raw_videos")
        if music and music.filename:save_uploads(folder,[music],"music")
        report=analyze_video(folder,plan); write_json(folder/"analysis.json",report)
        if request.form.get("mode")=="quick":
            result=export_video(folder,report); flash(result["message"],"success" if result["ok"] else "error")
        return redirect(url_for("job",job_id=job_id))
    return render_template("job.html",job_id=job_id,meta=read_json(folder/"meta.json",{}),plan=plan,analysis=read_json(folder/"analysis.json"),has_video=(folder/"final.mp4").exists())

@app.post("/jobs/<job_id>/storyboard")
def save_storyboard(job_id:str):
    folder=job_path(job_id); plan=read_json(folder/"plan.json",{}); payload=request.get_json(silent=True) or {}
    try:write_json(folder/"plan.json",update_storyboard(plan,payload.get("shots",[]))); return jsonify({"ok":True,"total_duration":read_json(folder/"plan.json",{}).get("total_duration",0)})
    except (ValueError,TypeError):return jsonify({"ok":False,"message":"分镜数据格式不正确。"}),400

@app.post("/jobs/<job_id>/export")
def export(job_id:str):
    report=read_json(job_path(job_id)/"analysis.json")
    if not report:flash("请先分析实拍素材再导出。","error")
    else:
        result=export_video(job_path(job_id),report); flash(result["message"],"success" if result["ok"] else "error")
    return redirect(url_for("job",job_id=job_id))
@app.get("/jobs/<job_id>/download/<filename>")
def download(job_id:str,filename:str):return send_from_directory(job_path(job_id),filename,as_attachment=True)
if __name__=="__main__":app.run(host="127.0.0.1",port=int(os.getenv("PORT","5000")),debug=True)
