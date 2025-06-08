# SenseVoice 语音转录功能

## 概述

本项目现已支持使用 SenseVoice 模型进行高精度多语言语音转录。SenseVoice 是阿里巴巴达摩院开发的语音基础模型，具有以下特点：

- **多语言支持**: 支持中文、粤语、英语、日语、韩语等50+种语言 <mcreference link="https://www.gpu-mart.com/blog/how-to-use-the-sensevoice-speech-model" index="1">1</mcreference>
- **高效推理**: 比 Whisper-Large 快15倍，处理10秒音频仅需70ms <mcreference link="https://www.gpu-mart.com/blog/how-to-use-the-sensevoice-speech-model" index="1">1</mcreference>
- **情感识别**: 支持语音情感识别和音频事件检测 <mcreference link="https://www.gpu-mart.com/blog/how-to-use-the-sensevoice-speech-model" index="1">1</mcreference>
- **高精度**: 在多个基准测试中超越 Whisper 模型的性能 <mcreference link="https://github.com/FunAudioLLM/SenseVoice" index="5">5</mcreference>

## 安装依赖

系统已自动安装以下依赖：

```bash
pip install funasr torch torchvision torchaudio
```

## API 使用方法

### 1. 转录请求

发送 POST 请求到 `/transcribe` 端点：

```json
{
    "file_path": "uploads/audio.wav",
    "model": "sensevoice"
}
```

### 2. 支持的模型

- `"vosk"`: 原有的 Vosk 模型（默认）
- `"sensevoice"`: 新增的 SenseVoice 模型

### 3. 响应格式

```json
{
    "transcript": [
        {
            "text": "识别出的文本内容",
            "model": "sensevoice"
        }
    ]
}
```

## 功能特性

### 自动语言检测

SenseVoice 支持自动检测音频语言，无需手动指定语言类型。

### 音频格式支持

- 支持任意格式和时长的音频输入 <mcreference link="https://github.com/FunAudioLLM/SenseVoice" index="5">5</mcreference>
- 自动进行音频预处理和格式转换

### 情感和事件检测

除了基本的语音转录，SenseVoice 还能检测：
- 语音情感（愤怒、快乐、中性、悲伤等）
- 音频事件（背景音乐、掌声、笑声、哭声、咳嗽、打喷嚏等）<mcreference link="https://www.gpu-mart.com/blog/how-to-use-the-sensevoice-speech-model" index="1">1</mcreference>

## 测试方法

使用提供的测试脚本：

```bash
cd backend
python test_sensevoice.py
```

## 性能对比

| 特性 | Vosk | SenseVoice |
|------|------|------------|
| 语言支持 | 主要支持中文 | 50+ 种语言 |
| 推理速度 | 中等 | 极快（比Whisper-Large快15倍）|
| 准确率 | 良好 | 优秀（超越Whisper）|
| 额外功能 | 仅转录 | 转录+情感+事件检测 |
| 模型大小 | 较小 | 中等 |

## 注意事项

1. **首次使用**: SenseVoice 模型会在首次使用时自动下载（约893MB），请确保网络连接稳定
2. **硬件要求**: 建议使用 GPU 以获得最佳性能，CPU 也可运行但速度较慢
3. **内存使用**: SenseVoice 模型需要更多内存，建议至少 4GB 可用内存

## 故障排除

### 模型下载失败

如果模型下载失败，可以设置镜像源：

```bash
# Linux/Mac
export HF_ENDPOINT=https://hf-mirror.com

# Windows PowerShell
$env:HF_ENDPOINT = "https://hf-mirror.com"
```

### 导入错误

确保已正确安装所有依赖：

```bash
pip install funasr torch torchvision torchaudio
```

## 更多信息

- [SenseVoice 官方仓库](https://github.com/FunAudioLLM/SenseVoice)
- [FunASR 文档](https://pypi.org/project/funasr/)
- [模型详细信息](https://www.gpu-mart.com/blog/how-to-use-the-sensevoice-speech-model)