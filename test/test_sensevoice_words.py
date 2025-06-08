import requests
import json

# 测试SenseVoice的词语级别时间定位功能
url = "http://localhost:8000/transcribe"

# 使用测试音频文件
files = {"file": open("backend/uploads/test.mp4", "rb")}
data = {"model": "sensevoice"}

try:
    response = requests.post(url, files=files, data=data)
    
    if response.status_code == 200:
        result = response.json()
        print("SenseVoice词语级别转录结果:")
        print(f"返回数据类型: {type(result)}")
        print(f"返回数据键: {result.keys() if isinstance(result, dict) else 'Not a dict'}")
        
        if "transcript" in result:
            transcript = result["transcript"]
            print(f"\n转录结果类型: {type(transcript)}")
            print(f"词语数量: {len(transcript)}")
            
            # 显示前10个词语的详细信息
            print("\n前10个词语的详细信息:")
            for i, word_info in enumerate(transcript[:10]):
                print(f"词语 {i+1}: {word_info}")
                
            # 检查数据格式是否正确
            if len(transcript) > 0:
                first_word = transcript[0]
                required_keys = ["word", "start", "end", "conf"]
                missing_keys = [key for key in required_keys if key not in first_word]
                
                if missing_keys:
                    print(f"\n警告: 缺少必需的键: {missing_keys}")
                else:
                    print("\n✓ 数据格式正确，包含所有必需的键")
                    print(f"示例词语: '{first_word['word']}', 开始时间: {first_word['start']}s, 结束时间: {first_word['end']}s")
        else:
            print("错误: 响应中没有找到 'transcript' 键")
    else:
        print(f"请求失败，状态码: {response.status_code}")
        print(f"错误信息: {response.text}")
        
except Exception as e:
    print(f"测试过程中发生错误: {e}")
finally:
    files["file"].close()