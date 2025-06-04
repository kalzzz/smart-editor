from fastapi import FastAPI, File, UploadFile, Body, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Annotated, List, Dict, Optional
import subprocess
import json
import shutil
from vosk import Model, KaldiRecognizer, SetLogLevel
import os
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from uuid import uuid4
from pathlib import Path
from datetime import datetime
import tempfile
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel, Field
import time

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SetLogLevel(-1)  # Suppress Vosk logging

# 配置
MAX_PREVIEW_DURATION = 600  # 预览最大时长10分钟
MIN_SEGMENT_DURATION = 0.1  # 最小片段时长
TEMP_FILE_CLEANUP_HOURS = 24  # 临时文件清理时间
MAX_CONCURRENT_JOBS = 2  # 最大并发处理任务数

# 创建线程池执行器
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS)

# 全局任务状态跟踪
processing_tasks = {}

# Pydantic 模型定义
class CutRequest(BaseModel):
    file_path: str = Field(..., description="视频文件路径")
    delete_segments: List[Dict[str, float]] = Field(..., description="需要删除的时间段")
    
    class Config:
        schema_extra = {
            "example": {
                "file_path": "uploads/video.mp4",
                "delete_segments": [{"start": 10.0, "end": 20.0}, {"start": 30.0, "end": 40.0}]
            }
        }

class TaskStatus(BaseModel):
    task_id: str
    status: str  # "processing", "completed", "failed"
    progress: int = 0
    result: Optional[Dict] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

# Load Vosk model
model_path = "vosk-model-small-cn-0.22"

# 创建必要的目录
app_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(app_dir)  # 获取backend目录
directories = {
    "uploads": os.path.join(backend_dir, "uploads"),
    "clips": os.path.join(backend_dir, "clips"),
    "processed_videos": os.path.join(backend_dir, "processed_videos"),
    "temp": os.path.join(backend_dir, "temp")
}

for dir_name, dir_path in directories.items():
    try:
        os.makedirs(dir_path, exist_ok=True)
        logger.info(f"确保目录存在: {dir_path}")
    except Exception as e:
        logger.error(f"创建目录 {dir_path} 时出错: {e}")

if not os.path.exists(model_path):
    logger.warning("Vosk model not found. Please download from https://alphacephei.com/vosk/models")
    model = None
else:
    model = Model(model_path)

app = FastAPI(title="Video Processing API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据库配置
engine = create_engine('sqlite:///transcriptions.db', pool_pre_ping=True)
Base = declarative_base()

class UploadedFile(Base):
    __tablename__ = 'uploaded_files'
    id = Column(Integer, primary_key=True)
    unique_filename = Column(String(50), unique=True)
    original_filename = Column(String(200))
    file_path = Column(String(200))
    upload_time = Column(DateTime, default=datetime.utcnow)
    file_type = Column(String(50))

class Transcription(Base):
    __tablename__ = 'transcriptions'
    id = Column(Integer, primary_key=True)
    video_id = Column(String(50), unique=True)
    file_path = Column(String(200))
    transcription = Column(Text)

Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

def validate_segments(segments: List[Dict], duration: float) -> List[Dict]:
    """验证并清理时间段数据"""
    if not segments:
        raise ValueError("至少需要一个删除时间段")
    
    validated_segments = []
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict) or 'start' not in seg or 'end' not in seg:
            raise ValueError(f"片段 {i+1} 格式错误，需要包含 start 和 end 字段")
        
        start = float(seg['start'])
        end = float(seg['end'])
        
        if start < 0 or end < 0:
            raise ValueError(f"片段 {i+1} 时间不能为负数")
        
        if start >= end:
            raise ValueError(f"片段 {i+1} 开始时间必须小于结束时间")
        
        if start >= duration or end > duration:
            raise ValueError(f"片段 {i+1} 超出视频时长 ({duration}秒)")
        
        validated_segments.append({"start": start, "end": end})
    
    return validated_segments

def get_video_duration(file_path: str) -> float:
    """获取视频文件的总时长（秒）"""
    try:
        command = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            file_path
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
        duration = float(result.stdout.strip())
        return duration
    except subprocess.TimeoutExpired:
        raise Exception("获取视频时长超时")
    except subprocess.CalledProcessError as e:
        raise Exception(f"FFprobe执行失败: {e.stderr}")
    except (ValueError, IndexError):
        raise Exception("无法解析视频时长")
    except Exception as e:
        raise Exception(f"获取视频时长失败: {str(e)}")

def calculate_keep_segments(duration: float, delete_segments: List[Dict]) -> List[Dict]:
    """计算需要保留的视频片段"""
    if not delete_segments:
        return [{"start": 0, "end": duration}]
    
    # 合并重叠的删除片段
    delete_segments = sorted(delete_segments, key=lambda x: x["start"])
    merged_deletes = []
    current_start, current_end = delete_segments[0]["start"], delete_segments[0]["end"]
    
    for segment in delete_segments[1:]:
        if segment["start"] <= current_end:  # 重叠或相邻
            current_end = max(current_end, segment["end"])
        else:
            merged_deletes.append({"start": current_start, "end": current_end})
            current_start, current_end = segment["start"], segment["end"]
    
    merged_deletes.append({"start": current_start, "end": current_end})
    
    # 计算保留片段
    keep_segments = []
    current_time = 0
    
    for segment in merged_deletes:
        if current_time < segment["start"]:
            keep_segments.append({"start": current_time, "end": segment["start"]})
        current_time = max(current_time, segment["end"])
    
    if current_time < duration:
        keep_segments.append({"start": current_time, "end": duration})
    
    # 过滤掉过短的片段
    keep_segments = [seg for seg in keep_segments if seg["end"] - seg["start"] > MIN_SEGMENT_DURATION]
    
    return keep_segments

def update_task_status(task_id: str, status: str, progress: int = 0, result: Dict = None, error_message: str = None):
    """更新任务状态"""
    if task_id in processing_tasks:
        processing_tasks[task_id].update({
            "status": status,
            "progress": progress,
            "result": result,
            "error_message": error_message,
            "updated_at": datetime.utcnow()
        })

def cleanup_temp_files():
    """清理过期的临时文件"""
    try:
        temp_dir = directories["temp"]
        current_time = time.time()
        cleanup_threshold = TEMP_FILE_CLEANUP_HOURS * 3600
        
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            if os.path.isfile(file_path):
                file_age = current_time - os.path.getmtime(file_path)
                if file_age > cleanup_threshold:
                    os.remove(file_path)
                    logger.info(f"清理过期临时文件: {filename}")
    except Exception as e:
        logger.warning(f"清理临时文件时出错: {e}")

def process_video_cutting(task_id: str, file_path: str, delete_segments: List[Dict]):
    """异步处理视频剪切"""
    try:
        update_task_status(task_id, "processing", 10)
        
        # 验证文件存在
        if not os.path.exists(file_path):
            # 根据文件路径中的目录确定查找位置
            if file_path.startswith('processed_videos/'):
                absolute_path = os.path.join(directories["processed_videos"], os.path.basename(file_path))
            elif file_path.startswith('uploads/'):
                absolute_path = os.path.join(directories["uploads"], os.path.basename(file_path))
            else:
                absolute_path = os.path.join(directories["uploads"], file_path)

            logger.info(f"process_video_cutting: 尝试查找文件 {absolute_path}")
            
            if not os.path.exists(absolute_path):
                raise FileNotFoundError(f"视频文件不存在: {file_path}")
            file_path = absolute_path
        
        # 获取视频时长
        duration = get_video_duration(file_path)
        update_task_status(task_id, "processing", 20)
        
        # 验证时间段
        validated_segments = validate_segments(delete_segments, duration)
        
        # 计算保留片段
        keep_segments = calculate_keep_segments(duration, validated_segments)
        if not keep_segments:
            raise ValueError("删除操作后没有剩余内容")
        
        update_task_status(task_id, "processing", 30)
        
        # 检查预览时长限制
        total_keep_duration = sum(seg["end"] - seg["start"] for seg in keep_segments)
        if total_keep_duration > MAX_PREVIEW_DURATION:
            logger.warning(f"预览时长 ({total_keep_duration}s) 超过限制 ({MAX_PREVIEW_DURATION}s)")
        
        # 生成输出文件路径
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = Path(file_path).stem
        output_filename = f"cut_{base_name}_{timestamp}.mp4"
        output_path = os.path.join(directories["processed_videos"], output_filename)
        
        update_task_status(task_id, "processing", 40)
        
        # 执行视频处理
        if len(keep_segments) == 1:
            # 单个片段，直接剪切
            segment = keep_segments[0]
            command = [
                "ffmpeg", "-y",
                "-i", file_path,
                "-ss", str(segment["start"]),
                "-to", str(segment["end"]),
                "-c:v", "libx264",
                "-c:a", "aac",
                "-preset", "fast",
                "-crf", "23",
                "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero",
                output_path
            ]
            
            update_task_status(task_id, "processing", 60)
            result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, command, result.stderr)
                
        else:
            # 多个片段，使用 filter_complex
            update_task_status(task_id, "processing", 50)
            
            # 构建复杂过滤器
            filter_parts = []
            stream_maps = []
            valid_segments = []
            
            # 首先过滤掉过短的片段
            for segment in keep_segments:
                duration = segment["end"] - segment["start"]
                if duration >= 0.3:  # 跳过过短片段
                    valid_segments.append(segment)
            
            if not valid_segments:
                raise Exception("没有有效的视频片段可以处理")
            
            # 为每个有效片段创建过滤器
            for i, segment in enumerate(valid_segments):
                filter_parts.append(
                    f"[0:v]trim=start={segment['start']}:end={segment['end']},setpts=PTS-STARTPTS[v{i}];"
                    f"[0:a]atrim=start={segment['start']}:end={segment['end']},asetpts=PTS-STARTPTS[a{i}]"
                )
                stream_maps.extend([f"[v{i}]", f"[a{i}]"])
            
            n_segments = len(valid_segments)
            # 构建视频流连接
            video_concat = "".join(f"[v{i}]" for i in range(n_segments)) + f"concat=n={n_segments}:v=1:a=0[v_out];"
            # 构建音频流连接
            audio_concat = "".join(f"[a{i}]" for i in range(n_segments)) + f"concat=n={n_segments}:v=0:a=1[a_out]"
            
            # 合并所有filter命令
            filter_complex = ";".join(filter_parts) + ";" + video_concat + audio_concat
            
            logger.info(f"使用filter_complex命令: {filter_complex}")
            
            command = [
                "ffmpeg", "-y",
                "-i", file_path,
                "-filter_complex", filter_complex,
                "-map", "[v_out]",
                "-map", "[a_out]",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-preset", "fast",
                "-crf", "23",
                "-movflags", "+faststart",
                output_path
            ]
            
            update_task_status(task_id, "processing", 70)
            try:
                result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=1800)
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr if e.stderr else str(e)
                raise Exception(f"FFmpeg处理失败: {error_msg}")
        
        update_task_status(task_id, "processing", 90)
        
        # 验证输出文件
        if not os.path.exists(output_path):
            raise Exception("输出文件生成失败")
        
        final_duration = get_video_duration(output_path)
        
        result = {
            "success": True,
            "preview_path": output_path,
            "preview_url": f"processed_videos/{output_filename}",  # 不带前导斜杠，与其他接口保持一致
            "deleted_segments": validated_segments,
            "kept_segments": keep_segments,
            "original_duration": duration,
            "new_duration": final_duration,
            "compression_ratio": final_duration / duration if duration > 0 else 0
        }
        
        update_task_status(task_id, "completed", 100, result)
        logger.info(f"视频处理完成: {task_id}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"视频处理失败 {task_id}: {error_msg}")
        update_task_status(task_id, "failed", error_message=error_msg)

@app.get("/")
async def root():
    return {"message": "Video Processing API v1.0", "status": "running"}

@app.post("/upload")
async def upload_file(file: Annotated[UploadFile, File()]):
    if file.filename is None:
        raise HTTPException(status_code=400, detail="File name is missing.")

    # 检查文件大小
    MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large")

    # 验证文件扩展名
    file_extension = Path(file.filename).suffix.lower()
    allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v'}
    if file_extension not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Unsupported file format")

    # 生成唯一文件名并保存文件
    unique_filename = f"{uuid4()}{file_extension}"
    absolute_path = os.path.join(directories["uploads"], unique_filename)  # 绝对路径，用于文件系统操作

    with open(absolute_path, "wb") as f:
        f.write(content)

    # 保存到数据库
    db = SessionLocal()
    try:
        file_record = UploadedFile(
            unique_filename=unique_filename,
            original_filename=file.filename,
            file_path=absolute_path,  # 存储绝对路径
            file_type="video" if file.content_type and file.content_type.startswith("video/") else "unknown"
        )
        db.add(file_record)
        db.commit()
        db.refresh(file_record)
    except Exception as e:
        logger.error(f"数据库保存文件记录失败: {e}")
        if os.path.exists(absolute_path):
            os.remove(absolute_path)
        raise HTTPException(status_code=500, detail="Failed to save file record")
    finally:
        db.close()

    # 返回URL路径供前端访问
    return {
        "original_filename": file.filename,
        "unique_filename": unique_filename,
        "path": f"uploads/{unique_filename}",  # 返回不带前导斜杠的相对路径
        "url": f"uploads/{unique_filename}",  # 用于前端访问的URL路径，不带前导斜杠
        "size": len(content)
    }

@app.post("/cut")
async def cut_video(background_tasks: BackgroundTasks, request: CutRequest):
    """
    异步剪切视频API
    """
    try:
        # 基本验证
        if not os.path.exists(request.file_path):
            # 尝试从relative_path转换为absolute_path
            file_name = os.path.basename(request.file_path)
            absolute_path = os.path.join(directories["uploads"], file_name)
            if not os.path.exists(absolute_path):
                raise FileNotFoundError(f"视频文件不存在: {request.file_path}")
            file_path = absolute_path
        else:
            file_path = request.file_path
        
        if not request.delete_segments:
            raise HTTPException(status_code=400, detail="No segments to delete specified")
        
        # 检查并发任务数量
        active_tasks = sum(1 for task in processing_tasks.values() if task["status"] == "processing")
        if active_tasks >= MAX_CONCURRENT_JOBS:
            raise HTTPException(status_code=429, detail="Too many concurrent processing jobs")
        
        # 生成任务ID
        task_id = str(uuid4())
        
        # 初始化任务状态
        processing_tasks[task_id] = {
            "task_id": task_id,
            "status": "processing",
            "progress": 0,
            "result": None,
            "error_message": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
          # 提交后台任务
        background_tasks.add_task(
            process_video_cutting,
            task_id,
            file_path,  # 使用已经处理过的绝对路径
            request.delete_segments
        )
        
        return {
            "task_id": task_id,
            "status": "processing",
            "message": "Video cutting started"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动视频剪切任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start processing: {str(e)}")

@app.get("/cut/status/{task_id}")
async def get_cut_status(task_id: str):
    """获取剪切任务状态"""
    if task_id not in processing_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = processing_tasks[task_id]
    
    # 清理完成超过1小时的任务
    if task["status"] in ["completed", "failed"]:
        time_diff = datetime.utcnow() - task["updated_at"]
        if time_diff.total_seconds() > 3600:  # 1小时
            del processing_tasks[task_id]
            raise HTTPException(status_code=404, detail="Task expired")
    
    return task

@app.post("/transcribe")
async def transcribe_audio(file_path: Annotated[str, Body()]):
    if model is None:
        raise HTTPException(status_code=503, detail="Speech recognition service unavailable")    # 处理URL或相对路径转换为绝对路径
    # 首先移除可能的前导斜杠
    file_path = file_path.lstrip('/')
    # 分割路径，获取目录和文件名
    path_parts = file_path.split('/')
    if len(path_parts) >= 2:
        directory = path_parts[0]  # 例如 "uploads" 或 "processed_videos"
        file_name = path_parts[-1]  # 文件名
        if directory in directories:
            absolute_path = os.path.join(directories[directory], file_name)
            if not os.path.exists(absolute_path):
                raise HTTPException(status_code=400, detail=f"Input file not found: {file_path}")
        else:
            raise HTTPException(status_code=400, detail=f"Invalid directory: {directory}")
    else:
        # 如果只有文件名，默认在uploads目录中查找
        absolute_path = os.path.join(directories["uploads"], file_path)
        if not os.path.exists(absolute_path):
            raise HTTPException(status_code=400, detail=f"Input file not found: {file_path}")
        
    # 使用绝对路径进行后续处理
    file_path = absolute_path

    audio_output_path = None
    wf = None
    
    try:
        # 创建临时音频文件
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=directories["temp"]) as temp_file:
            audio_output_path = temp_file.name

        # 转换音频
        command = [
            "ffmpeg", "-y",
            "-i", file_path,
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            audio_output_path
        ]

        logger.info(f"开始转换音频: {file_path}")
        result = subprocess.run(command, check=True, capture_output=True, timeout=300)
        
        if not os.path.exists(audio_output_path) or os.path.getsize(audio_output_path) == 0:
            raise Exception("Failed to create valid audio file")

        # 语音识别
        rec = KaldiRecognizer(model, 16000)
        rec.SetWords(True)
        wf = open(audio_output_path, "rb")
        wf.read(44)  # Skip WAV header

        results = []
        logger.info("开始语音识别...")
        while True:
            data = wf.read(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if "result" in result and result["result"]:
                    results.extend(result["result"])

        final_result = json.loads(rec.FinalResult())
        if "result" in final_result and final_result["result"]:
            results.extend(final_result["result"])

        logger.info(f"识别完成，获得 {len(results)} 个词语")

        # 保存转录结果到数据库
        db = SessionLocal()
        try:
            # 存储相对路径到数据库
            relative_path = f"uploads/{os.path.basename(file_path)}"  # 不带前导斜杠
            transcription_record = Transcription(
                video_id=os.path.basename(file_path),
                file_path=relative_path,
                transcription=json.dumps(results, ensure_ascii=False)
            )
            db.merge(transcription_record)  # 使用merge而不是add，避免重复键错误
            db.commit()
        finally:
            db.close()

        return {"transcript": results}

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Audio processing timeout")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        raise HTTPException(status_code=500, detail=f"Audio conversion failed: {error_msg}")
    except Exception as e:
        logger.error(f"转录失败: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription error: {str(e)}")
    finally:
        if wf:
            wf.close()
        if audio_output_path and os.path.exists(audio_output_path):
            try:
                os.remove(audio_output_path)
            except Exception as e:
                logger.warning(f"清理临时音频文件失败: {e}")

@app.post("/clip_video")
async def clip_video(
    file_path: Annotated[str, Body()],
    start_time: Annotated[float, Body()],
    end_time: Annotated[float, Body()]
):
    """剪辑视频片段"""
    # 根据文件路径中的目录确定查找位置
    if file_path.startswith('processed_videos/'):
        absolute_path = os.path.join(directories["processed_videos"], os.path.basename(file_path))
    elif file_path.startswith('uploads/'):
        absolute_path = os.path.join(directories["uploads"], os.path.basename(file_path))
    else:
        absolute_path = os.path.join(directories["uploads"], file_path)
    
    logger.info(f"clip_video: 使用文件路径 {absolute_path}")
    
    if not os.path.exists(absolute_path):
        raise HTTPException(status_code=400, detail=f"Video file not found: {file_path}")
    
    file_path = absolute_path

    if start_time < 0 or end_time <= start_time:
        raise HTTPException(status_code=400, detail="Invalid time range")

    # 检查时间范围是否在视频时长内
    try:
        duration = get_video_duration(file_path)
        if end_time > duration:
            raise HTTPException(status_code=400, detail=f"End time exceeds video duration ({duration}s)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get video duration: {e}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"clip_{os.path.basename(file_path)}_{start_time}_{end_time}_{timestamp}.mp4"
    output_path = os.path.join(directories["clips"], output_filename)

    command = [
        "ffmpeg", "-y",
        "-i", file_path,
        "-ss", str(start_time),
        "-to", str(end_time),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        "-movflags", "+faststart",
        output_path
    ]

    try:
        result = subprocess.run(command, check=True, capture_output=True, timeout=300)
        
        if not os.path.exists(output_path):
            raise Exception("Output file was not created")
            return {
            "success": True,
            "clip_path": output_path,
            "clip_url": f"clips/{output_filename}",  # 不带前导斜杠，与其他接口保持一致
            "duration": end_time - start_time
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Video clipping timeout")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        raise HTTPException(status_code=500, detail=f"FFmpeg error: {error_msg}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clipping failed: {str(e)}")

# 清理任务的后台服务
@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化任务"""
    logger.info("Video Processing API started")
    cleanup_temp_files()

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的清理任务"""
    logger.info("Shutting down Video Processing API")
    executor.shutdown(wait=True)

# --- 静态文件服务配置 ---
# 注意：这些配置必须放在所有路由定义之后
from fastapi.staticfiles import StaticFiles

# 确保目录存在
for directory in ["uploads", "clips", "processed_videos"]:
    os.makedirs(os.path.join(app_dir, directory), exist_ok=True)

# 挂载静态文件目录
app.mount("/uploads", StaticFiles(directory=directories["uploads"]), name="uploads")
app.mount("/clips", StaticFiles(directory=directories["clips"]), name="clips")
app.mount("/processed_videos", StaticFiles(directory=directories["processed_videos"]), name="processed_videos")