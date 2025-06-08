import requests

url = "http://127.0.0.1:8000/upload"
files = {'file': open('E:/f5_tts/AutoReader_new/AutoReader/resources/ref_voice/读书男声2.WAV', 'rb')}

try:
    response = requests.post(url, files=files)
    response.raise_for_status()  # Raise an exception for bad status codes
    print("上传成功！")
    print(response.json())
except requests.exceptions.RequestException as e:
    print(f"上传失败: {e}")
finally:
    for file in files.values():
        file.close()