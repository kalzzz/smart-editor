import requests
import json

response = requests.post('http://127.0.0.1:8000/transcribe', json={'file_path': 'uploads/test.mp4', 'model': 'vosk'})
data = response.json()

print('Response structure:')
print('Keys:', list(data.keys()))
print('Transcript type:', type(data['transcript']))
print('Transcript length:', len(data['transcript']) if isinstance(data['transcript'], list) else 'Not a list')

if isinstance(data['transcript'], list) and len(data['transcript']) > 0:
    print('First element type:', type(data['transcript'][0]))
    if isinstance(data['transcript'][0], dict):
        print('First element keys:', list(data['transcript'][0].keys()))
        print('First element:', json.dumps(data['transcript'][0], indent=2, ensure_ascii=False))