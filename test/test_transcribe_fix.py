import requests
import json

# 测试JSON请求
def test_json_request():
    url = "http://localhost:8000/transcribe"
    data = {
        "file_path": "uploads/test.mp4",
        "model": "sensevoice"
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=data, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ JSON请求测试成功")
        else:
            print("❌ JSON请求测试失败")
            
    except Exception as e:
        print(f"❌ 请求异常: {e}")

if __name__ == "__main__":
    print("测试修复后的转录API...")
    test_json_request()