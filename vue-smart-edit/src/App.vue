<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import axios from 'axios';
import { useEditorStore } from './stores/editorStore';
import TextEditor from './components/TextEditor.vue';

const editorStore = useEditorStore();

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
const isTranscribing = ref(false); // 新增：标记是否正在转录
const textEditorRef = ref(null);

// 监听视频路径变化，更新转录文本
watch(clipPath, async (newPath, oldPath) => {
    if (isUndoRedoOperation.value) {
        // 如果是撤销/重做操作，不触发转录
        isUndoRedoOperation.value = false;
        return;
    }
    
    if (newPath && newPath !== oldPath && !isTranscribing.value) {
        // 重置转录状态
        transcriptWords.value = [];
        // 开始新的转录
        await transcribeFile(newPath);
    }
}, { immediate: false });

// 标记视频是否被修改过
const isVideoModified = ref(false);
// 添加标记是否是撤销/重做操作的状态
const isUndoRedoOperation = ref(false);

// 计算属性：检查撤销/重做状态
const canUndo = computed(() => editorStore.canUndo() && !isTranscribing.value);
const canRedo = computed(() => editorStore.canRedo() && !isTranscribing.value);

// 监听转录状态，控制视频播放
watch(isTranscribing, (newValue) => {
    if (newValue && player.value && !player.value.paused) {
        // 如果开始转录且视频正在播放，就暂停视频
        player.value.pause();
    }
});

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
        // 1. 上传文件
        const uploadResponse = await axios.post('http://127.0.0.1:8000/upload', formData, {
            headers:
            {
                'Content-Type': 'multipart/form-data',
            },
            onUploadProgress: (progressEvent) => {
                uploadProgress.value = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            },
        });

        const filePath = uploadResponse.data.path;
        const fullPath = `http://127.0.0.1:8000/${filePath}`;
        clipPath.value = fullPath;

        // 2. 等待转录完成
        await transcribeFile(fullPath);

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
        isTranscribing.value = true; // 设置转录状态为true
        transcribeStatus.value = '转录中...';
        
        // 清除之前选中的文本
        if (textEditorRef.value) {
            textEditorRef.value.clearSelectedWords();
        }

        // 从 URL 中提取相对路径
        const relativePath = filePath.replace('http://127.0.0.1:8000/', '');

        const transcribeResponse = await axios.post('http://127.0.0.1:8000/transcribe',
            JSON.stringify(relativePath),
            {
                headers: {
                    'Content-Type': 'application/json'
                }
            }
        );
        
        // 更新转录文本
        const newTranscript = transcribeResponse.data.transcript || [];
        
        // 只有在新转录文本与当前不同时才更新
        if (JSON.stringify(newTranscript) !== JSON.stringify(transcriptWords.value)) {
            transcriptWords.value = newTranscript;
            transcribeStatus.value = '转录完成';
        } else {
            transcribeStatus.value = '使用现有转录';
        }
        
    } catch (error) {
        transcribeError.value = `转录失败: ${error.response?.data?.detail || error.message || error}`;
        console.error(error);
        transcribeStatus.value = '转录失败';
    } finally {
        isTranscribing.value = false; // 设置转录状态为false
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

// 处理视频播放尝试
const handleVideoPlay = (event) => {
    if (isTranscribing.value) {
        event.preventDefault(); // 阻止视频播放
        if (player.value) {
            player.value.pause(); // 确保视频暂停
        }
    }
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
        let relativeFilePath = clipPath.value.replace('http://127.0.0.1:8000/', '');
        // 如果路径不包含任何目录前缀，添加 uploads/ 前缀
        if (!relativeFilePath.includes('/')) {
            relativeFilePath = `uploads/${relativeFilePath}`;
        }
        console.log('剪辑视频，使用文件路径:', relativeFilePath);

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
    window.addEventListener('keydown', handleKeyDown);
});

// 在组件卸载时移除快捷键监听
onUnmounted(() => {
    window.removeEventListener('keydown', handleKeyDown);
});


// 处理删除选中的文本并剪辑视频
const deleteSelectedText = async () => {
    // 获取编辑器中选中的时间段
    const segments = textEditorRef.value.getSelectedDeleteSegments();
    
    if (!segments || segments.length === 0) {
        clipError.value = '请选择要删除的文本';
        return;
    }

    if (!clipPath.value) {
        clipError.value = '请先上传视频';
        return;
    }

    // 开始处理前暂停视频
    if (player.value && !player.value.paused) {
        player.value.pause();
    }

    try {
        let relativeFilePath = clipPath.value.replace('http://127.0.0.1:8000/', '');
        if (!relativeFilePath.includes('/')) {
            relativeFilePath = `uploads/${relativeFilePath}`;
        }

        isTranscribing.value = true;
        transcribeStatus.value = '正在处理视频...';

        const response = await axios.post('http://127.0.0.1:8000/cut', {
            file_path: relativeFilePath,
            delete_segments: segments
        });

        // 获取任务ID并轮询状态
        const taskId = response.data.task_id;

        // 在视频和文本都处理前，保存状态
        if (!editorStore.getInitialState()) {
            editorStore.saveInitialState({
                transcriptWords: [...transcriptWords.value],
                selectedIndices: [],
                deleteSegments: [],
                originalVideoPath: clipPath.value,
                isModified: false
            });
        }

        // 传递当前选中的片段给 waitForProcessing
        await waitForProcessing(taskId, segments);
        
    } catch (error) {
        clipError.value = `处理失败: ${error.response?.data?.detail || error.message || error}`;
        isTranscribing.value = false;
        transcribeStatus.value = '处理失败';
    }
};

// 下载视频
const downloadVideo = async () => {
    if (!clipPath.value) {
        clipError.value = '请先上传视频';
        return;
    }

    try {
        const response = await axios.get(clipPath.value, {
            responseType: 'blob' // 以二进制blob形式下载
        });

        // 创建下载链接
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement('a');
        link.href = url;
        
        // 从路径中提取文件名
        const fileName = clipPath.value.split('/').pop() || 'video.mp4';
        link.setAttribute('download', fileName);

        // 触发下载
        document.body.appendChild(link);
        link.click();

        // 清理
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        clipError.value = `下载失败: ${error.message}`;
        console.error('下载视频失败:', error);
    }
};

// 撤销操作 - 恢复到上一次编辑的状态
const handleUndo = async () => {
    if (!canUndo.value) return;
    
    // 设置标记，表示这是撤销操作
    isUndoRedoOperation.value = true;
    
    const previousState = editorStore.undo();
    if (previousState) {
        // 更新界面状态
        transcriptWords.value = previousState.transcriptWords;
        if (textEditorRef.value) {
            textEditorRef.value.setSelectedWords([]);
        }
        
        // 获取初始状态，检查是否回到了初始状态
        const isInitial = editorStore.isInitialState();
        
        // 恢复视频状态
        clipPath.value = previousState.originalVideoPath;
        transcribeStatus.value = isInitial ? '已恢复到最初状态' : '已恢复到上一次编辑的状态';
        isVideoModified.value = !isInitial;
    }
};

// 重做操作 - 恢复到下一个编辑状态
const handleRedo = async () => {
    if (!canRedo.value) return;
    
    // 设置标记，表示这是重做操作
    isUndoRedoOperation.value = true;
    
    const nextState = editorStore.redo();
    if (nextState) {
        // 更新界面状态
        transcriptWords.value = nextState.transcriptWords;
        if (textEditorRef.value) {
            textEditorRef.value.setSelectedWords([]);
        }
        
        // 恢复视频状态
        clipPath.value = nextState.originalVideoPath;
        // 确定是否回到了初始状态
        const isInitial = editorStore.isInitialState();
        transcribeStatus.value = isInitial ? '已恢复到最初状态' : '已恢复到编辑后的状态';
        
        // 更新修改状态
        isVideoModified.value = nextState.isModified;
    }
};

// 添加快捷键支持
const handleKeyDown = (event) => {
    // 如果在输入框中，不处理快捷键
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
        return;
    }
    
    // Ctrl/Cmd + Z: 撤销
    if ((event.ctrlKey || event.metaKey) && event.key === 'z' && !event.shiftKey) {
        event.preventDefault();
        if (canUndo.value) {
            handleUndo();
        }
    }
    // Ctrl/Cmd + Shift + Z 或 Ctrl/Cmd + Y: 重做
    else if (((event.ctrlKey || event.metaKey) && event.key === 'z' && event.shiftKey) ||
             ((event.ctrlKey || event.metaKey) && event.key === 'y')) {
        event.preventDefault();
        if (canRedo.value) {
            handleRedo();
        }
    }
};

// 处理视频片段
const processVideoWithSegments = async (segments) => {
    if (!clipPath.value) {
        isTranscribing.value = false;
        return;
    }
    
    try {
        let relativeFilePath = clipPath.value.replace('http://127.0.0.1:8000/', '');
        if (!relativeFilePath.includes('/')) {
            relativeFilePath = `uploads/${relativeFilePath}`;
        }
        
        isTranscribing.value = true;
        transcribeStatus.value = '正在处理视频...';
        
        const response = await axios.post('http://127.0.0.1:8000/cut', {
            file_path: relativeFilePath,
            delete_segments: segments
        });
        
        const taskId = response.data.task_id;
        await waitForProcessing(taskId);
        
    } catch (error) {
        clipError.value = `处理失败: ${error.response?.data?.detail || error.message || error}`;
        isTranscribing.value = false;
        transcribeStatus.value = '处理失败';
    }
};

// 等待处理完成
const waitForProcessing = async (taskId, deleteSegments) => {
    const checkStatus = async () => {
        try {
            const statusResponse = await axios.get(`http://127.0.0.1:8000/cut/status/${taskId}`);
            const status = statusResponse.data;

            if (status.status === 'completed' && status.result) {
                // 更新视频路径为新的预览视频
                const newVideoPath = `http://127.0.0.1:8000/${status.result.preview_url}`;
                clipPath.value = newVideoPath;
                transcribeStatus.value = '视频处理完成，开始转录...';

                // 清除选中的文本
                textEditorRef.value.clearSelectedWords();
                
                // 触发新视频的转录
                await transcribeFile(newVideoPath);

                // 保存新的编辑状态
                editorStore.saveState({
                    transcriptWords: [...transcriptWords.value],
                    selectedIndices: textEditorRef.value.getSelectedIndices(),
                    deleteSegments: [...deleteSegments],
                    originalVideoPath: clipPath.value,
                    isModified: true
                });

                return;
            } else if (status.status === 'failed') {
                clipError.value = `处理失败: ${status.error_message}`;
                isTranscribing.value = false;
                transcribeStatus.value = '处理失败';
                return;
            }

            // 继续轮询
            setTimeout(checkStatus, 1000);
        } catch (error) {
            clipError.value = `获取任务状态失败: ${error.message}`;
            isTranscribing.value = false;
            transcribeStatus.value = '处理失败';
        }
    };

    await checkStatus();
};

// 重置所有状态
const resetState = () => {
    selectedFile.value = null;
    transcript.value = '';
    uploadError.value = '';
    transcribeError.value = '';
    loading.value = false;
    uploadProgress.value = 0;
    transcribeStatus.value = '';
    clipPath.value = '';
    clipError.value = '';
    isVideoActuallyPlaying.value = false;
    isVideoModified.value = false; // 重置视频修改状态
};
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
            <div class="upload-controls">
                <button 
                    @click="uploadFile" 
                    :disabled="loading" 
                    class="upload-btn"
                >
                    {{ loading ? '上传中...' : '上传并转录' }}
                </button>
                
                <div v-if="!loading && clipPath" class="state-badge">
                    状态{{ editorStore.$state.stateCounter }}
                </div>
            </div>

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
                        class="video-player"
                        :src="clipPath"
                        controls
                        @timeupdate="handleTimeUpdate"
                        @play="handleVideoPlaying"
                        @pause="handleVideoPauseOrEnded"
                        @ended="handleVideoPauseOrEnded"
                        @playing="handleVideoPlay"
                    ></video>
                    
                    <!-- 视频控制区域 -->
                    <div class="video-controls">
                        <!-- 当前时间显示 -->
                        <div class="current-time">
                            当前时间: {{ currentTime.toFixed(1) }}秒
                        </div>
                        
                        <!-- 编辑控制区 -->
                        <div class="edit-controls">
                            <button 
                                @click="handleUndo" 
                                class="control-btn undo-btn"
                                :disabled="!canUndo"
                                title="撤销 (Ctrl+Z)"
                            >
                                撤销
                            </button>
                            
                            <button 
                                @click="handleRedo" 
                                class="control-btn redo-btn"
                                :disabled="!canRedo"
                                title="重做 (Ctrl+Y)"
                            >
                                重做
                            </button>
                            
                            <button 
                                @click="deleteSelectedText" 
                                class="delete-btn"
                                :disabled="isTranscribing"
                            >
                                删除选中文本
                            </button>
                            
                            <button 
                                @click="downloadVideo" 
                                class="download-btn"
                                :disabled="!clipPath || isTranscribing"
                            >
                                下载预览视频
                            </button>
                        </div>
                    </div>
                </div>
                <div v-if="isTranscribing" class="loading-overlay">
                    <div class="loading-spinner"></div>
                    <p>视频处理中...</p>
                </div>
            </div>

            <!-- 转录文本显示区域 -->
            <div class="transcript-section">
                <TextEditor 
                    ref="textEditorRef"
                    :transcriptWords="transcriptWords"
                    :currentTime="currentTime"
                    :isVideoPlaying="isVideoActuallyPlaying"
                    @seek-to-time="handleSeekToTime"
                    @pause-video="handlePauseVideo"
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

.video-controls {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    padding: 16px;
    background: linear-gradient(135deg, #f8f9fa, #e9ecef);
    border-radius: 12px;
    border: 1px solid #dee2e6;
    margin-top: 16px;
    flex-wrap: wrap;
}

.current-time {
    font-weight: 600;
    color: #34495e;
    font-size: 14px;
}

.state-counter {
    font-weight: 600;
    color: #8e44ad;
    font-size: 14px;
    flex-shrink: 0;
}

.edit-controls {
    display: flex;
    gap: 8px;
    align-items: center;
}

.control-btn {
    padding: 8px 16px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    transition: all 0.3s ease;
    background: linear-gradient(135deg, #3498db, #2980b9);
    color: white;
    box-shadow: 0 2px 6px rgba(52, 152, 219, 0.3);
}

.control-btn:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 3px 8px rgba(52, 152, 219, 0.4);
}

.undo-btn {
    background: linear-gradient(135deg, #34495e, #2c3e50);
}

.redo-btn {
    background: linear-gradient(135deg, #2c3e50, #34495e);
}

.control-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
}

.delete-btn {
    background: linear-gradient(135deg, #e74c3c, #c0392b);
    color: white;
    padding: 12px 24px;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 16px;
    font-weight: 600;
    transition: all 0.3s ease;
    box-shadow: 0 2px 8px rgba(231, 76, 60, 0.3);
}

.delete-btn:hover:not(:disabled) {
    background: linear-gradient(135deg, #c0392b, #e74c3c);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(231, 76, 60, 0.4);
}

.download-btn {
    background: linear-gradient(135deg, #2ecc71, #27ae60);
    color: white;
    padding: 12px 24px;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 16px;
    font-weight: 600;
    transition: all 0.3s ease;
    box-shadow: 0 2px 8px rgba(46, 204, 113, 0.3);
}

.download-btn:hover:not(:disabled) {
    background: linear-gradient(135deg, #27ae60, #2ecc71);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(46, 204, 113, 0.4);
}

.delete-btn:disabled,
.download-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
}

.loading-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(255, 255, 255, 0.9);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    border-radius: 12px;
    z-index: 10;
}

.loading-overlay .loading-spinner {
    width: 48px;
    height: 48px;
    border: 4px solid rgba(52, 152, 219, 0.3);
    border-top: 4px solid #3498db;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 16px;
}

.loading-overlay p {
    color: #2980b9;
    font-size: 18px;
    font-weight: 500;
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

/* 新增状态标记样式 */
.upload-controls {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
}

.state-badge {
    background: #8e44ad;
    color: white;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 600;
    box-shadow: 0 2px 4px rgba(142, 68, 173, 0.2);
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

/* 加载动画关键帧定义 */
@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
</style>