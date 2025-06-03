import requests

url = "http://127.0.0.1:8000/transcribe"
data = "uploads/test.WAV"  # 替换为你的实际文件路径

try:
    response = requests.post(url, json=data)
    response.raise_for_status()
    transcript = response.json()
    print("转录成功！")
    print(transcript)
except requests.exceptions.RequestException as e:
    print(f"转录失败: {e}")