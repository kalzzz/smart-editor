import sys
sys.path.append('backend')
import traceback
from app.transcription_service import TranscriptionService

try:
    # 创建转录服务实例
    model_path = "backend/vosk-model-small-cn-0.22"
    temp_dir = "backend/temp"
    service = TranscriptionService(model_path, temp_dir)
    print("TranscriptionService创建成功")
    
    # 测试SenseVoice转录
    file_path = "backend/uploads/test.mp4"
    print(f"开始测试SenseVoice转录: {file_path}")
    
    results = service._transcribe_sensevoice(file_path)
    print(f"转录成功，结果类型: {type(results)}")
    print(f"结果数量: {len(results)}")
    
    if len(results) > 0:
        print(f"第一个结果: {results[0]}")
        print(f"前5个结果:")
        for i, result in enumerate(results[:5]):
            print(f"  {i+1}: {result}")
    
except Exception as e:
    print(f"发生错误: {e}")
    print("详细错误信息:")
    traceback.print_exc()