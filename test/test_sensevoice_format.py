import requests
import json

response = requests.post('http://127.0.0.1:8000/transcribe', json={'file_path': 'uploads/test.mp4', 'model': 'sensevoice'})
data = response.json()

print('SenseVoice response structure:')
print('Keys:', list(data.keys()))
print('Transcript type:', type(data['transcript']))
print('Transcript length:', len(data['transcript']) if isinstance(data['transcript'], list) else 'Not a list')

if isinstance(data['transcript'], list) and len(data['transcript']) > 0:
    result = data['transcript'][0]
    print('\nFirst result keys:', list(result.keys()))
    print('Text:', result.get('text', '')[:100] + '...' if len(result.get('text', '')) > 100 else result.get('text', ''))
    print('Model:', result.get('model', ''))
    print('Timestamp type:', type(result.get('timestamp', [])))
    print('Timestamp length:', len(result.get('timestamp', [])))
    
    if result.get('timestamp'):
        print('\nFirst few timestamps:')
        for i, ts in enumerate(result['timestamp'][:5]):
            print(f'  {i}: {ts}')
        
        print('\nText length:', len(result.get('text', '')))
        print('Timestamp count:', len(result.get('timestamp', [])))