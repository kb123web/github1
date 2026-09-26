# 本地带货视频 Agent

## 启动

```powershell
conda activate live_sales_agent
Copy-Item .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY（可选；没有时使用本地演示模板）
python app.py
```

打开 http://127.0.0.1:5000 。

## 工作流

1. 上传商品图片，填写商品详情，生成三组文案、拍摄建议、30 秒分镜、台词和合规提示。
2. 上传真人口播或纯产品展示视频；选择“只分析”查看覆盖镜头、缺失镜头与格式问题，或直接生成初稿。
3. 确认分析报告后导出 1080×1920、30fps、H.264/AAC 的 MP4。

任务素材与中间结果保存在本地 `data/<任务ID>/`，API 密钥只从环境变量读取。

当前版本的 AI 配音与逐句口播转写保留接口位置，默认安全地保留实拍原声；视频剪辑使用 imageio-ffmpeg 自带 FFmpeg，不修改系统 PATH。

## 测试

```powershell
conda run -n live_sales_agent pytest -q
```
本项目已完成首次 GitHub 上传。