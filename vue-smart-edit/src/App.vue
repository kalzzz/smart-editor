<script setup>
import { ref, computed, onMounted } from 'vue';
import axios from 'axios';

import TextEditor from './components/TextEditor.vue';

const selectedFile = ref(null);
const transcript = ref('');
const uploadError = ref('');
const transcribeError = ref('');
const loading = ref(false);
const uploadProgress = ref(0);
const transcribeStatus = ref('');
const currentTime = ref(0);
const player = ref(null);
const startTime = ref(0);
const endTime = ref(0);
const clipPath = ref('');
const clipError = ref('');
const isVideoActuallyPlaying = ref(false); // Track video play state
const transcriptWords = ref([]);

// 处理文件上传事件
const handleFileUpload = (event) => {
    selectedFile.value = event.target.files[0];
    uploadError.value = '';
    transcript.value = '';
    transcribeError.value = '';
    uploadProgress.value = 0;
    transcribeStatus.value = '';
    clipPath.value = '';
    clipError.value = '';
    isVideoActuallyPlaying.value = false;
};

// 上传文件并触发转录
const uploadFile = async () => {
    if (!selectedFile.value) {
        uploadError.value = '请选择一个文件';
        return;
    }

    loading.value = true;
    uploadProgress.value = 0;
    transcribeStatus.value = '';
    const formData = new FormData();
    formData.append('file', selectedFile.value);

    try {
        const uploadResponse = await axios.post('http://127.0.0.1:8000/upload', formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            },
            onUploadProgress: (progressEvent) => {
                uploadProgress.value = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            },
        });

        const filePath = uploadResponse.data.path;
        transcribeStatus.value = '转录中...';
        await transcribeFile(filePath);
        clipPath.value = `http://127.0.0.1:8000/${filePath}`;

    } catch (error) {
        uploadError.value = `文件上传失败: ${error.response?.data?.detail || error.message || error}`;
        console.error(error);
    } finally {
        loading.value = false;
    }
};

// 调用后端进行语音转文本
const transcribeFile = async (filePath) => {
    try {
        console.log('转录，文件路径:', filePath);
        const transcribeResponse = await axios.post('http://127.0.0.1:8000/transcribe',
            filePath ,
            {
                headers: {
                    'Content-Type': 'application/json'
                }
            }
        );
        transcriptWords.value = transcribeResponse.data.transcript || [];
        transcribeStatus.value = '转录完成';
    } catch (error) {
        transcribeError.value = `转录失败: ${error.response?.data?.detail || error.message || error}`;
        console.error(error);
        transcribeStatus.value = '转录失败';
    }
};

// 处理视频时间更新 - 用于文本高亮同步
const handleTimeUpdate = (event) => {
    currentTime.value = event.target.currentTime;
};

// 处理文本编辑器发出的跳转事件 - 文本到视频同步
const handleSeekToTime = (time) => {
    if (player.value) {
        player.value.currentTime = time;
        // // Attempt to play the video after seeking
        // if (player.value.paused) {
        //     player.value.play().catch(e => {
        //         console.warn("Autoplay after seek failed. User interaction might be required to play.", e);
        //     });
        // }
    }
};

// 处理文本编辑器发出的暂停事件
const handlePauseVideo = () => {
    if (player.value && !player.value.paused) {
        player.value.pause();
    }
};

// Handle video playing state
const handleVideoPlaying = () => {
    isVideoActuallyPlaying.value = true;
};
const handleVideoPauseOrEnded = () => {
    isVideoActuallyPlaying.value = false;
};

// 剪辑视频
const clipVideo = async () => {
    if (!clipPath.value) {
        clipError.value = '请先上传视频';
        return;
    }
    if (startTime.value >= endTime.value) {
        clipError.value = '开始时间必须小于结束时间';
        return;
    }

    try {
        const relativeFilePath = clipPath.value.replace('http://127.0.0.1:8000/', '');

        const clipResponse = await axios.post('http://127.0.0.1:8000/clip_video', {
            file_path: relativeFilePath,
            start_time: startTime.value,
            end_time: endTime.value,
        });
        clipPath.value = `http://127.0.0.1:8000/${clipResponse.data.clip_path}`;
        clipError.value = '';
        transcribeStatus.value = '剪辑成功';
    } catch (error) {
        clipError.value = `剪辑失败: ${error.response?.data?.detail || error.message || error}`;
        console.error(error);
    }
};

// 设置当前时间为开始时间
const setCurrentAsStart = () => {
    startTime.value = Math.round(currentTime.value * 10) / 10;
};

// 设置当前时间为结束时间
const setCurrentAsEnd = () => {
    endTime.value = Math.round(currentTime.value * 10) / 10;
};

onMounted(() => {
    startTime.value = 0;
    endTime.value = 0;
});
</script>

<template>
    <main class="main-container">
        <h1 class="title">智能口播视频剪辑</h1>

        <!-- 文件上传区域 -->
        <div class="upload-section">
            <input 
                type="file" 
                @change="handleFileUpload" 
                accept="video/*,audio/*" 
                class="file-input"
            >
            <button 
                @click="uploadFile" 
                :disabled="loading" 
                class="upload-btn"
            >
                {{ loading ? '上传中...' : '上传并转录' }}
            </button>

            <div v-if="uploadProgress > 0" class="progress-container">
                <div 
                    class="progress-bar" 
                    :style="{ width: `${uploadProgress}%` }"
                ></div>
                <span class="progress-label">{{ uploadProgress }}%</span>
            </div>

            <div v-if="uploadError" class="error-message">{{ uploadError }}</div>
            <div v-if="transcribeError" class="error-message">{{ transcribeError }}</div>
            <div v-if="transcribeStatus" class="status-message">{{ transcribeStatus }}</div>
        </div>

        <!-- 主内容区域 -->
        <div class="content-layout">
            <!-- 视频播放和控制区域 -->
            <div class="video-section">
                <div v-if="clipPath" class="video-container">
                    <video 
                        ref="player" 
                        :src="clipPath" 
                        controls 
                        autoplay 
                        @timeupdate="handleTimeUpdate"
                        @playing="handleVideoPlaying"
                        @pause="handleVideoPauseOrEnded"
                        @ended="handleVideoPauseOrEnded"
                        class="video-player"
                    ></video>
                    
                    <div class="clip-controls">
                        <div class="time-input-group">
                            <label>开始时间:</label>
                            <input 
                                type="number" 
                                v-model.number="startTime" 
                                step="0.1" 
                                class="time-input"
                            >
                            <span>秒</span>
                            <button @click="setCurrentAsStart" class="time-set-btn">
                                设为当前时间
                            </button>
                        </div>
                        
                        <div class="time-input-group">
                            <label>结束时间:</label>
                            <input 
                                type="number" 
                                v-model.number="endTime" 
                                step="0.1" 
                                class="time-input"
                            >
                            <span>秒</span>
                            <button @click="setCurrentAsEnd" class="time-set-btn">
                                设为当前时间
                            </button>
                        </div>
                        
                        <div class="current-time">
                            当前播放时间: {{ currentTime.toFixed(2) }} 秒
                        </div>
                        
                        <button @click="clipVideo" class="clip-btn">
                            剪辑视频
                        </button>
                        
                        <div v-if="clipError" class="error-message">{{ clipError }}</div>
                    </div>
                </div>
            </div>

            <!-- 转录文本显示区域 -->
            <div class="transcript-section">
                <TextEditor 
                    :transcriptWords="transcriptWords" 
                    :currentTime="currentTime" 
                    @seek-to-time="handleSeekToTime"
                    @pause-video="handlePauseVideo"
                    :is-video-playing="isVideoActuallyPlaying"
                />
            </div>
        </div>
    </main>
</template>

<style scoped>
/* 重置和基础样式 */
* {
    box-sizing: border-box;
}

html, body {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
}

.main-container {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    height: 100vh;
    width: 100vw;
    margin: 0;
    padding: 16px;
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.title {
    text-align: center;
    color: #2c3e50;
    margin: 0 0 16px 0;
    font-size: clamp(24px, 3vw, 36px);
    font-weight: 700;
    text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    flex-shrink: 0;
}

.upload-section {
    background: white;
    padding: 20px;
    border-radius: 12px;
    margin-bottom: 16px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    flex-shrink: 0;
}

.file-input {
    width: 100%;
    padding: 16px;
    border: 2px dashed #4CAF50;
    border-radius: 8px;
    margin-bottom: 16px;
    font-size: 16px;
    transition: all 0.3s ease;
    background-color: #fafafa;
    cursor: pointer;
}

.file-input:hover {
    border-color: #45a049;
    background-color: #f0f8f0;
    transform: translateY(-1px);
}

.upload-btn {
    background: linear-gradient(135deg, #4CAF50, #45a049);
    color: white;
    padding: 12px 24px;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 16px;
    font-weight: 600;
    transition: all 0.3s ease;
    box-shadow: 0 2px 8px rgba(76, 175, 80, 0.3);
}

.upload-btn:hover:not(:disabled) {
    background: linear-gradient(135deg, #45a049, #4CAF50);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(76, 175, 80, 0.4);
}

.upload-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
}

.progress-container {
    margin: 16px 0;
    background-color: rgba(240, 240, 240, 0.8);
    border-radius: 8px;
    overflow: hidden;
    position: relative;
    height: 24px;
    box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.1);
}

.progress-bar {
    background: linear-gradient(90deg, #4CAF50, #45a049, #66bb6a);
    height: 100%;
    transition: width 0.3s ease;
    border-radius: 8px;
}

.progress-label {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    color: white;
    font-weight: 600;
    font-size: 12px;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.error-message {
    color: #e74c3c;
    background: linear-gradient(135deg, #fadbd8, #f8d7da);
    padding: 12px 16px;
    border: 1px solid #f1948a;
    border-radius: 8px;
    margin: 12px 0;
    font-size: 14px;
    box-shadow: 0 2px 8px rgba(231, 76, 60, 0.1);
}

.status-message {
    color: #2980b9;
    background: linear-gradient(135deg, #d6eaf8, #cce7f0);
    padding: 12px 16px;
    border: 1px solid #a9cce3;
    border-radius: 8px;
    margin: 12px 0;
    font-style: italic;
    font-size: 14px;
    box-shadow: 0 2px 8px rgba(41, 128, 185, 0.1);
}

.content-layout {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    flex: 1;
    min-height: 0; /* 允许子元素收缩 */
    overflow: hidden;
}

.video-section {
    background: white;
    padding: 20px;
    border-radius: 12px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.video-container {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
}

.video-player {
    width: 100%;
    flex: 1;
    min-height: 0;
    border-radius: 8px;
    margin-bottom: 16px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    object-fit: contain;
    background: #000;
}

.clip-controls {
    display: flex;
    flex-direction: column;
    gap: 12px;
    flex-shrink: 0;
}

.time-input-group {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    padding: 12px;
    background-color: #f8f9fa;
    border-radius: 8px;
    border: 1px solid #e9ecef;
}

.time-input-group label {
    font-weight: 600;
    color: #34495e;
    min-width: 80px;
    font-size: 14px;
}

.time-input {
    width: 100px;
    padding: 8px 12px;
    border: 2px solid #ddd;
    border-radius: 6px;
    font-size: 14px;
    transition: border-color 0.3s ease;
}

.time-input:focus {
    outline: none;
    border-color: #3498db;
    box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.1);
}

.time-set-btn {
    background: linear-gradient(135deg, #95a5a6, #7f8c8d);
    color: white;
    padding: 8px 12px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 500;
    transition: all 0.3s ease;
    box-shadow: 0 1px 4px rgba(149, 165, 166, 0.3);
}

.time-set-btn:hover {
    background: linear-gradient(135deg, #7f8c8d, #95a5a6);
    transform: translateY(-1px);
}

.current-time {
    background: linear-gradient(135deg, #ecf0f1, #d5dbdb);
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 16px;
    color: #2c3e50;
    text-align: center;
    font-weight: 600;
    box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.1);
}

.clip-btn {
    background: linear-gradient(135deg, #3498db, #2980b9);
    color: white;
    padding: 12px 24px;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 16px;
    font-weight: 600;
    transition: all 0.3s ease;
    box-shadow: 0 2px 8px rgba(52, 152, 219, 0.3);
}

.clip-btn:hover {
    background: linear-gradient(135deg, #2980b9, #3498db);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(52, 152, 219, 0.4);
}

.transcript-section {
    background: white;
    padding: 20px;
    border-radius: 12px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

/* 响应式设计 */
@media (max-width: 1200px) {
    .content-layout {
        grid-template-columns: 1fr;
        gap: 16px;
    }
    
    .main-container {
        padding: 12px;
    }
}

@media (max-width: 768px) {
    .main-container {
        padding: 8px;
    }
    
    .upload-section,
    .video-section,
    .transcript-section {
        padding: 16px;
    }
    
    .time-input-group {
        flex-direction: column;
        align-items: flex-start;
        gap: 6px;
    }
    
    .time-input-group label {
        min-width: auto;
    }
    
    .time-input {
        width: 100%;
    }
    
    .file-input {
        padding: 12px;
        font-size: 14px;
    }
    
    .upload-btn,
    .clip-btn {
        padding: 10px 20px;
        font-size: 14px;
    }
}

@media (max-width: 480px) {
    .main-container {
        padding: 6px;
    }
    
    .content-layout {
        gap: 12px;
    }
    
    .upload-section,
    .video-section,
    .transcript-section {
        padding: 12px;
    }
    
    .title {
        font-size: 20px;
        margin-bottom: 12px;
    }
}
</style>