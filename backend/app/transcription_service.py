import json
import logging
import subprocess
import os
import tempfile
import wave
from typing import List, Dict
from vosk import Model, KaldiRecognizer
from fastapi import HTTPException
from .database import SessionLocal
from .models import Transcription
from funasr.utils.postprocess_utils import rich_transcription_postprocess

# SenseVoice imports
try:
    from funasr import AutoModel
    from funasr.utils.postprocess_utils import rich_transcription_postprocess
    SENSEVOICE_AVAILABLE = True
except ImportError:
    SENSEVOICE_AVAILABLE = False
    print("Warning: FunASR not installed. SenseVoice model will not be available.")
    print("To install: pip install funasr")

# 配置日志
import logging

# 只获取logger，不重新配置basicConfig
logger = logging.getLogger(__name__)

class TranscriptionService:
    def __init__(self, model_path: str, temp_dir: str):
        """
        初始化转录服务
        
        Args:
            model_path: Vosk模型路径
            temp_dir: 临时文件目录
        """
        vosk_model_path = os.path.join(model_path, "vosk-model-small-cn-0.22")
        sensevoice_model_path = os.path.join(model_path, "iic", "SenseVoiceSmall")
        if not os.path.exists(vosk_model_path):
            logger.warning("Vosk model not found. Please download from https://alphacephei.com/vosk/models")
            self.model = None
        else:
            self.model = Model(vosk_model_path)
        
        self.sensevoice_model = None
        self.temp_dir = temp_dir
        os.makedirs(temp_dir, exist_ok=True)
        self._load_sensevoice_model(sensevoice_model_path)
    
    def _load_sensevoice_model(self, model_path: str):
        """加载SenseVoice模型"""
        if not SENSEVOICE_AVAILABLE:
            return
        
        try:
            
            # 检查模型路径是否存在
            if not os.path.exists(model_path):
                logger.error(f"SenseVoice模型路径不存在: {model_path}")
                self.sensevoice_model = None
                return
            
            self.sensevoice_model = AutoModel(
                model=model_path,
                disable_update=True,
                #trust_remote_code=True,
                vad_model="fsmn-vad",
                merge_vad=False,
                vad_kwargs={"max_single_segment_time": 30000},
                device="cuda:0",  # 使用CPU，如果有GPU可以改为"cuda:0"
            )
            logger.info(f"SenseVoice模型从本地路径加载成功: {model_path}")
        except Exception as e:
            logger.error(f"加载SenseVoice模型失败: {e}")
            self.sensevoice_model = None
    
    def _convert_to_wav(self, input_file: str) -> str:
        """
        将输入音频转换为WAV格式
        
        Args:
            input_file: 输入文件路径
            
        Returns:
            WAV文件路径
        """
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=self.temp_dir) as temp_file:
            audio_output_path = temp_file.name

        command = [
            "ffmpeg", "-y",
            "-i", input_file,
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            audio_output_path
        ]

        logger.info(f"开始转换音频: {input_file}")
        result = subprocess.run(command, check=True, capture_output=True, timeout=300)
        
        if not os.path.exists(audio_output_path) or os.path.getsize(audio_output_path) == 0:
            raise Exception("Failed to create valid audio file")
            
        return audio_output_path

    def _transcribe_wav(self, wav_file: str) -> List[Dict]:
        """
        使用Vosk进行语音识别
        
        Args:
            wav_file: WAV音频文件路径
            
        Returns:
            识别结果列表，每个元素包含词语和时间戳信息
        """
        wf = wave.open(wav_file, "rb")
        
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
            logger.error("音频格式不正确，需要单声道16kHz 16bit WAV")
            raise HTTPException(status_code=400, detail="Audio format must be mono 16kHz 16bit WAV")
        
        rec = KaldiRecognizer(self.model, wf.getframerate())
        rec.SetWords(True)  # 启用词级别的时间戳
        
        results = []
        logger.info("开始语音识别...")
        
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                logger.info(f"中间结果: {result}")
                if "result" in result and result["result"]:
                    logger.info(f"result['result']的值: {result['result']}")
                    results.extend(result["result"])

        final_result = json.loads(rec.FinalResult())
        logger.info(f"最终结果: {final_result}")
        if "result" in final_result and final_result["result"]:
            logger.info(f"final_result['result']的值: {final_result['result']}")
            results.extend(final_result["result"])
        
        # 提取完整文本和时间戳
        full_text = " ".join([word.get("word", "") for word in results])
        word_timestamps = []
        
        for word_info in results:
            word_timestamps.append([
                word_info.get("start", 0),
                word_info.get("end", 0)
            ])
                
        logger.info(f"识别完成，获得 {len(results)} 个词语")
        
        # 直接返回词语列表，前端需要每个词语的详细信息
        return results

    def _transcribe_sensevoice(self, file_path: str) -> List[Dict]:
        """
        使用SenseVoice进行语音识别，并转换为词语级别的时间戳格式
        
        Args:
            file_path: 音频文件路径
            
        Returns:
            识别结果列表，每个元素包含词语和时间戳信息
        """
        if self.sensevoice_model is None:
            raise HTTPException(status_code=503, detail="SenseVoice service unavailable")
        
        try:
            logger.info(f"开始使用SenseVoice识别: {file_path}")
            res = self.sensevoice_model.generate(
                input=file_path,
                cache={},
                language="auto",  # "zh", "en", "yue", "ja", "ko", "nospeech"
                use_itn=False,
                batch_size_s=60,
                merge_vad=False,
                merge_length_s=15,
                output_timestamp=True
            )
            
            if res and len(res) > 0:
                text = res[0]["text"]
                timestamp = res[0]["timestamp"]
                #text = rich_transcription_postprocess(text)
                logger.info(f"SenseVoice识别完成: {text[:100]}...")
                
                # 转换为词语级别的时间戳格式
                results = self._convert_sensevoice_to_word_level(text, timestamp)
                logger.info(f"转换完成，获得 {len(results)} 个词语")
                return results
            else:
                logger.warning("SenseVoice未返回识别结果")
                return []
                
        except Exception as e:
            logger.error(f"SenseVoice识别失败: {e}")
            raise HTTPException(status_code=500, detail=f"SenseVoice transcription failed: {str(e)}")
    
    def _convert_sensevoice_to_word_level(self, text: str, timestamps: List[List[int]]) -> List[Dict]:
        """
        将SenseVoice的输出转换为词语级别的时间戳格式
        
        Args:
            text: 识别的文本
            timestamps: 时间戳列表，每个元素为[start_ms, end_ms]
            
        Returns:
            词语级别的结果列表
        """
        results = []
        
        # 调试输出：记录输入数据
        import os
        import json
        from datetime import datetime
        
        debug_dir = "debug_output"
        if not os.path.exists(debug_dir):
            os.makedirs(debug_dir)
        
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        debug_file = os.path.join(debug_dir, f"sensevoice_debug_{timestamp_str}.txt")
        
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(f"=== SenseVoice 转换调试信息 ===\n")
            f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"原始文本: {repr(text)}\n")
            f.write(f"原始时间戳数量: {len(timestamps)}\n")
            f.write(f"原始时间戳: {timestamps}\n\n")
        
        # 清理文本，移除SenseVoice的特殊标记
        clean_text = text
        # 移除语言标记和情感标记
        import re
        clean_text = re.sub(r'<\|[^|]*\|>', '', clean_text)
        clean_text = clean_text.strip()
        
        # 调试输出：记录清理后的文本
        with open(debug_file, 'a', encoding='utf-8') as f:
            f.write(f"清理后文本: {repr(clean_text)}\n")
            f.write(f"文本长度: {len(clean_text)}\n\n")
        
        if not clean_text or not timestamps:
            with open(debug_file, 'a', encoding='utf-8') as f:
                f.write(f"提前返回：文本为空或时间戳为空\n")
            return results
        
        # 将文本按字符分割（对中文更合适）或按词分割（对英文更合适）
        # 这里采用混合策略：中文按字符，英文按词
        words = []
        current_word = ""
        
        for char in clean_text:
            if char.isspace():
                if current_word:
                    words.append(current_word)
                    current_word = ""
            elif '\u4e00' <= char <= '\u9fff':  # 中文字符
                if current_word and not ('\u4e00' <= current_word[-1] <= '\u9fff'):
                    words.append(current_word)
                    current_word = char
                else:
                    if current_word:
                        words.append(current_word)
                    words.append(char)
                    current_word = ""
            else:  # 英文字符和标点
                current_word += char
        
        if current_word:
            words.append(current_word)
        
        # 调试输出：记录分词结果
        with open(debug_file, 'a', encoding='utf-8') as f:
            f.write(f"分词结果:\n")
            f.write(f"词语数量: {len(words)}\n")
            f.write(f"词语列表: {words}\n\n")
        
        # 将时间戳分配给词语
        if len(words) > 0 and len(timestamps) > 0:
            # 如果时间戳数量多于词语数量，尝试合理分配
            if len(timestamps) >= len(words):
                # 平均分配时间戳
                for i, word in enumerate(words):
                    if i < len(timestamps):
                        start_ms, end_ms = timestamps[i]
                        results.append({
                            "word": word,
                            "start": start_ms / 1000.0,  # 转换为秒
                            "end": end_ms / 1000.0,
                            "conf": 0.9  # SenseVoice没有置信度，设置默认值
                        })
            else:
                # 时间戳数量少于词语数量，需要插值
                for i, word in enumerate(words):
                    # 计算在时间戳数组中的位置
                    timestamp_index = int(i * len(timestamps) / len(words))
                    if timestamp_index >= len(timestamps):
                        timestamp_index = len(timestamps) - 1
                    
                    start_ms, end_ms = timestamps[timestamp_index]
                    results.append({
                        "word": word,
                        "start": start_ms / 1000.0,
                        "end": end_ms / 1000.0,
                        "conf": 0.9
                    })
        
        # 调试输出：记录最终结果
        with open(debug_file, 'a', encoding='utf-8') as f:
            f.write(f"时间戳分配策略: {'平均分配' if len(timestamps) >= len(words) else '插值分配'}\n")
            f.write(f"最终结果数量: {len(results)}\n")
            f.write(f"最终结果:\n")
            for i, result in enumerate(results):
                f.write(f"  [{i}] {result['word']} -> {result['start']:.3f}s - {result['end']:.3f}s (conf: {result['conf']})\n")
            f.write(f"\n=== 调试信息结束 ===\n")
        
        return results
    
    def _save_to_database(self, file_path: str, results: List[Dict], model: str = "vosk"):
        """
        将转录结果保存到数据库
        
        Args:
            file_path: 原始文件路径
            results: 转录结果列表
            model: 使用的模型名称
        """
        try:
            db = SessionLocal()
            transcription = Transcription(
                file_path=file_path,
                results=json.dumps(results, ensure_ascii=False)
            )
            db.add(transcription)
            db.commit()
            logger.info(f"转录结果已保存到数据库: {file_path} (模型: {model})")
        except Exception as e:
            logger.error(f"保存到数据库失败: {e}")
            raise
        finally:
            db.close()

    def transcribe(self, file_path: str, model: str = "vosk") -> List[Dict]:
        """
        执行完整的音频转录工作流
        
        Args:
            file_path: 音频文件路径
            model: 使用的模型 ("vosk" 或 "sensevoice")
            
        Returns:
            转录结果列表
        """
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

        temp_wav = None
        try:
            # 根据模型选择进行转录
            if model.lower() == "sensevoice":
                results = self._transcribe_sensevoice(file_path)
            else:
                # 默认使用Vosk模型
                # 转换音频为WAV格式
                temp_wav = self._convert_to_wav(file_path)
                
                # 执行语音识别
                results = self._transcribe_wav(temp_wav)
            
            # 保存结果到数据库
            if results:
                self._save_to_database(file_path, results, model)
            
            return results

        except subprocess.CalledProcessError as e:
            logger.error(f"音频转换失败: {e}")
            raise HTTPException(status_code=500, detail="Audio conversion failed")
        except Exception as e:
            logger.error(f"转录过程出错: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            # 清理临时WAV文件
            if temp_wav and os.path.exists(temp_wav):
                try:
                    os.remove(temp_wav)
                except Exception as e:
                    logger.warning(f"清理临时文件失败: {e}")
