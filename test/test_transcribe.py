import requests

url = "http://127.0.0.1:8000/transcribe"
data = {
    "file_path": "uploads/test.mp4",
    "model": "vosk"
}

try:
    response = requests.post(url, json=data)
    response.raise_for_status()
    transcript = response.json()
    print("转录成功！")
    print(f"转录结果: {transcript}")
except requests.exceptions.RequestException as e:
    print(f"转录失败: {e}")