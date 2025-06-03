from fastapi import FastAPI, File, UploadFile, Body, HTTPException
from typing import Annotated
import subprocess
import json
from vosk import Model, KaldiRecognizer, SetLogLevel
import os
from fastapi.middleware.cors import CORSMiddleware  # 导入 CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime # 导入 DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from uuid import uuid4
from pathlib import Path
from datetime import datetime # 导入 datetime

SetLogLevel(-1)  # Suppress Vosk logging

# Load Vosk model (ensure you have a model downloaded, e.g., 'vosk-model-small-cn-0.22.zip')
# You might need to adjust the path to your model
model_path = "vosk-model-small-cn-0.22"
if not os.path.exists(model_path):
    print(
        "Please download the Vosk model from https://alphacephei.com/vosk/models and place it in the backend directory."
    )
    model = None
else:
    model = Model(model_path)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许的来源，你可以设置为 ["*"] 允许所有
    #allow_origins=["http://localhost:5173"],  # 允许的来源，你可以设置为 ["*"] 允许所有
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有 HTTP 头部
)

# --- 数据库配置和模型定义 ---
# 创建数据库引擎
engine = create_engine('sqlite:///transcriptions.db')
Base = declarative_base()

# 定义 UploadedFile 模型
class UploadedFile(Base):
    __tablename__ = 'uploaded_files'

    id = Column(Integer, primary_key=True)
    unique_filename = Column(String(50), unique=True)
    original_filename = Column(String(200))
    file_path = Column(String(200))
    upload_time = Column(DateTime, default=datetime.utcnow) # 使用 DateTime
    file_type = Column(String(50))  # video 或 audio

# 定义 Transcription 模型
class Transcription(Base):
    __tablename__ = 'transcriptions'

    id = Column(Integer, primary_key=True)
    video_id = Column(String(50), unique=True) # 假设这里存储 unique_filename
    file_path = Column(String(200))
    transcription = Column(Text) # 存储 JSON 格式的带时间戳的词语列表

# 创建数据表 (在所有模型定义之后)
Base.metadata.create_all(engine)

# 创建会话工厂
SessionLocal = sessionmaker(bind=engine)
# --- 数据库配置和模型定义结束 ---


@app.get("/")
async def root():
    return {"message": "Hello from FastAPI backend!"}


@app.post("/upload")
async def upload_file(file: Annotated[UploadFile, File()]):
    # 检查文件名是否存在
    if file.filename is None:
        raise HTTPException(status_code=400, detail="File name is missing.")

    # 生成唯一文件名
    file_extension = Path(file.filename).suffix
    unique_filename = f"{uuid4()}{file_extension}"
    file_path = f"uploads/{unique_filename}"

    # 确保 uploads 目录存在
    os.makedirs("uploads", exist_ok=True)

    # 保存文件
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # 保存文件元数据到数据库
    db = SessionLocal()
    try:
        file_record = UploadedFile(
            unique_filename=unique_filename,
            original_filename=file.filename,
            file_path=file_path,
            file_type="video" if file.content_type.startswith("video/") else "audio"
        )
        db.add(file_record)
        db.commit()
        db.refresh(file_record) # 刷新以获取可能由数据库生成的ID等
    finally:
        db.close()

    return {
        "original_filename": file.filename,
        "unique_filename": unique_filename,
        "path": file_path
    }


@app.post("/transcribe")
async def transcribe_audio(file_path: Annotated[str, Body()]):
    if model is None:
        return {"error": "Vosk model not loaded."}

    audio_output_path = "uploads/temp_audio.wav"
    wf = None
    try:
        # 检查输入文件
        print(f"处理文件: {file_path}")
        if not os.path.exists(file_path):
            return {"error": f"Input file not found: {file_path}"}

        # Extract audio using FFmpeg with debug output
        command = [
            "ffmpeg",
            "-i", file_path,
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-y",
            audio_output_path
        ]

        print("执行FFmpeg命令...")
        process = subprocess.run(command, check=True, capture_output=True)
        print("FFmpeg转换完成")

        # 检查转换后的文件
        if not os.path.exists(audio_output_path):
            return {"error": "Failed to create converted audio file"}

        file_size = os.path.getsize(audio_output_path)
        print(f"转换后的音频文件大小: {file_size} 字节")

        rec = KaldiRecognizer(model, 16000)
        rec.SetWords(True)
        wf = open(audio_output_path, "rb")
        wf.read(44)  # Skip header

        results = []
        print("开始识别...")
        while True:
            data = wf.read(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                print(f"识别中间结果: {result} ")
                # # 将 SRT 字幕写入文件
                # with open("output.srt", "w", encoding="utf-8") as f:
                #     rec.SrtResult(f)
                # Vosk的Result()通常包含带时间戳的词语列表
                if "result" in result and result["result"]:
                    results.extend(result["result"])
            # else:
            #     partial = json.loads(rec.PartialResult())
            #     # print(f"识别部分结果: {partial}") # 如果需要调试部分结果可以取消注释

        final_result = json.loads(rec.FinalResult())
        print(f"最终识别结果: {final_result}")

        # 统一处理 final_result，只提取 "result" 键中的带时间戳的词语
        if "result" in final_result and final_result["result"]:
            results.extend(final_result["result"])
        # 如果 final_result 只有 "text" 键而没有 "result" 键（例如对于非常短的音频），
        # 并且我们仍然希望包含这个文本，可以根据需求添加一个 fallback。
        # 但为了严格的 {word, start, end} 格式，我们通常只依赖 "result" 键。
        # 如果需要，可以添加：
        # elif "text" in final_result and final_result["text"]:
        #     # 这是一个没有时间戳的完整文本，如果需要，可以将其包装成 {word, start, end} 格式
        #     # 但 start 和 end 将是占位符
        #     results.append({"word": final_result["text"], "start": 0.0, "end": 0.0})


        # 将转录结果保存到数据库
        db = SessionLocal()
        try:
            # 假设 file_path 对应 unique_filename 或者你可以根据 file_path 查询 UploadedFile
            # 这里我们简单地使用 os.path.basename(file_path) 作为 video_id，实际应用中可能需要更精确的关联
            transcription_record = Transcription(
                video_id=os.path.basename(file_path), # 使用文件名作为ID (例如 unique_filename)
                file_path=file_path,
                transcription=json.dumps(results) # 将结果列表转换为JSON字符串保存
            )
            db.add(transcription_record)
            db.commit()
        finally:
            db.close()


        return {"transcript": results} # 现在results包含带时间戳的词语列表

    except Exception as e:
        print(f"发生错误: {str(e)}")
        return {"error": f"Transcription error: {str(e)}"}
    finally:
        if wf:
            wf.close()
        try:
            if os.path.exists(audio_output_path):
                os.remove(audio_output_path)
        except Exception as e:
            print(f"无法删除临时文件: {e}")


@app.post("/clip_video")
async def clip_video(
    file_path: Annotated[str, Body()],
    start_time: Annotated[float, Body()],
    end_time: Annotated[float, Body()]
):
    """
    剪辑视频。

    Args:
        file_path (str): 要剪辑的视频文件的路径。
        start_time (float): 剪辑的开始时间（秒）。
        end_time (float): 剪辑的结束时间（秒）。

    Returns:
        dict: 包含剪辑后的视频文件路径的字典。
    """

    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail="Video file not found")

    output_path = f"clips/clip_{os.path.basename(file_path)}_{start_time}_{end_time}.mp4"
    os.makedirs("clips", exist_ok=True)  # 确保 clips 目录存在

    command = [
        "ffmpeg",
        "-i", file_path,
        "-ss", str(start_time),
        "-to", str(end_time),
        "-c:v", "copy",  # 复制视频流
        "-c:a", "copy",  # 复制音频流
        output_path
    ]

    try:
        subprocess.run(command, check=True, capture_output=True)
        return {"clip_path": output_path}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"FFmpeg error: {e.stderr.decode()}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

# --- 静态文件服务 (确保在所有路由定义之后) ---
from fastapi.staticfiles import StaticFiles # 导入 StaticFiles

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/clips", StaticFiles(directory="clips"), name="clips")
