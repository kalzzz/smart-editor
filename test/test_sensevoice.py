#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试SenseVoice模型功能
"""

import requests
import json

def test_sensevoice_api():
    """测试SenseVoice API"""
    url = "http://127.0.0.1:8000/transcribe"
    
    # 测试数据
    test_data = {
        "file_path": "uploads/test.mp4",  # 需要替换为实际的音频文件路径
        "model": "sensevoice"
    }
    
    try:
        response = requests.post(url, json=test_data)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")
        
        if response.status_code == 200:
            print("✅ SenseVoice API 测试成功!")
        else:
            print("❌ SenseVoice API 测试失败")
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")

def test_vosk_api():
    """测试Vosk API作为对比"""
    url = "http://127.0.0.1:8000/transcribe"
    
    # 测试数据
    test_data = {
        "file_path": "uploads/test.mp4",  # 需要替换为实际的音频文件路径
        "model": "vosk"
    }
    
    try:
        response = requests.post(url, json=test_data)
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")
        
        if response.status_code == 200:
            print("✅ Vosk API 测试成功!")
        else:
            print("❌ Vosk API 测试失败")
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")

if __name__ == "__main__":
    print("=== 语音转录API测试 ===")
    print("\n1. 测试SenseVoice模型:")
    test_sensevoice_api()
    
    print("\n2. 测试Vosk模型:")
    test_vosk_api()