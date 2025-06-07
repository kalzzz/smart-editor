<template>
  <div class="text-editor">
      <h3 class="editor-title">文本编辑框</h3>
      <div v-if="transcriptWords.length > 0" class="editor-content" ref="editorContainer" @scroll="handleScroll">
          <span
              v-for="(word, index) in transcriptWords"
              :key="index"
              :class="{
                  'word': true,
                  'clickable': true,
                  'highlight': index === highlightedWordIndex,
                  'selected': selectedWordIndices.includes(index)
              }"
              @click="seekToWord(word.start, index)"
          >
              {{ getWordDisplay(word) }}
          </span>
      </div>
      <div v-else class="waiting-message">

          <div class="loading-spinner"></div>
          <p>等待转录文本...</p>
      </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue';

// 接收来自App.vue的props
const props = defineProps({
  transcriptWords: {
      type: Array,
      default: () => [],
  },
  currentTime: {
      type: Number,
      default: 0,
  },
  isVideoPlaying: { 

    type: Boolean,
    default: false,
  }
});

// 向App.vue发送事件
const emit = defineEmits(['seek-to-time', 'pause-video']);

const highlightedWordIndex = ref(-1);
const lastHighlightedIndex = ref(-1);
const editorContainer = ref(null);
const isUserScrolling = ref(false);
const scrollTimeout = ref(null);
const isUserSeeking = ref(false); // 新增：标记用户是否正在手动跳转
const selectedWordIndices = ref([]);





// 监听播放时间变化，高亮当前词语
watch(
  () => props.currentTime,
  (newTime) => {
      if (props.transcriptWords.length > 0) {
          updateHighlight(newTime);
      }
  },
  { immediate: true }
);

// 新增：监听视频播放状态，用于在视频开始播放后恢复自动高亮
watch(
  () => props.isVideoPlaying,
  (isPlaying) => {
    // 如果视频开始播放，并且当前是用户手动跳转状态
    if (isPlaying && isUserSeeking.value) {
      isUserSeeking.value = false; // 恢复自动高亮更新
      console.log('TextEditor: Video started playing, resuming auto-highlight.');
    }
  }
);

// 监听转录词语数据变化，重置高亮状态
watch(
  () => props.transcriptWords,
  (newWords) => {
      highlightedWordIndex.value = -1;
      lastHighlightedIndex.value = -1;
      
      // 如果有新的转录数据，重新计算当前高亮
      if (newWords.length > 0 && props.currentTime > 0) {
          nextTick(() => {
              updateHighlight(props.currentTime);
          });
      }
  }
);

// 更新高亮逻辑
const updateHighlight = (currentTime) => {
    // 如果用户正在手动跳转，暂时不更新高亮（给视频时间同步）
    if (isUserSeeking.value) {
        return;
    }
    
    const currentWordIndex = findCurrentWordIndex(currentTime);
    
    if (currentWordIndex !== -1 && currentWordIndex !== highlightedWordIndex.value) {
        lastHighlightedIndex.value = highlightedWordIndex.value;
        highlightedWordIndex.value = currentWordIndex;
        
        // 自动滚动到高亮词语（如果用户未手动滚动）
        if (!isUserScrolling.value) {
            nextTick(() => {
                scrollToHighlightedWord(currentWordIndex);
            });
        }
    }
};






// 点击词语选择或取消选择
const toggleWordSelection = (wordIndex) => {
  if (selectedWordIndices.value.includes(wordIndex)) {
    selectedWordIndices.value = selectedWordIndices.value.filter(index => index !== wordIndex);
  } else {
    selectedWordIndices.value.push(wordIndex);
  }
};
// 寻找当前时间对应的词语索引 - 改进算法
const findCurrentWordIndex = (currentTime) => {
    if (!props.transcriptWords.length) return -1;
    
    // 首先寻找精确匹配（在时间范围内）
    for (let i = 0; i < props.transcriptWords.length; i++) {
        const word = props.transcriptWords[i];
        if (currentTime >= word.start && currentTime <= word.end) {
            return i;
        }
    }
    
    // 如果没找到精确匹配，寻找最接近的词语
    let closestIndex = -1;
    let minDistance = Infinity;
    
    for (let i = 0; i < props.transcriptWords.length; i++) {
        const word = props.transcriptWords[i];
        
        // 计算到单词开始时间的距离
        const distanceToStart = Math.abs(currentTime - word.start);
        const distanceToEnd = Math.abs(currentTime - word.end);
        const minWordDistance = Math.min(distanceToStart, distanceToEnd);
        
        if (minWordDistance < minDistance) {
            minDistance = minWordDistance;
            closestIndex = i;
        }
    }
    
    // 如果找到了相对接近的词语（容差范围内），返回它
    if (closestIndex !== -1 && minDistance <= 1.0) { // 1秒容差
        return closestIndex;
    }
    
    return -1;
};

// 点击词语跳转到对应时间 - 改进版本
const seekToWord = (startTime, wordIndex) => {
    console.log('TextEditor: Seeking to time:', startTime, 'Word index:', wordIndex);
    
    // 立即更新高亮到点击的词语
    highlightedWordIndex.value = wordIndex;
    //
    toggleWordSelection(wordIndex);
    // 标记用户正在跳转
    isUserSeeking.value = true;
    
    // 发送跳转事件
    emit('seek-to-time', startTime);

    // 发送暂停事件
    emit('pause-video');
    
    // 标记用户正在交互，暂时停止自动滚动
    isUserScrolling.value = true;
    clearTimeout(scrollTimeout.value);
    scrollTimeout.value = setTimeout(() => {
        isUserScrolling.value = false;
    }, 3000); // 3秒后恢复自动滚动
};

// 获取选中的删除时间段
const getSelectedDeleteSegments = () => {
  if (selectedWordIndices.value.length === 0) {
    return [];
  }

  const segments = [];
  // Sort indices to easily group contiguous words
  const sortedIndices = [...selectedWordIndices.value].sort((a, b) => a - b);

  let currentSegment = null;

  for (let i = 0; i < sortedIndices.length; i++) {
    const wordIndex = sortedIndices[i];
    const word = props.transcriptWords[wordIndex];

    if (!currentSegment) {
      currentSegment = {
        start: word.start,
        end: word.end
      };
    } else if (wordIndex === sortedIndices[i - 1] + 1) {
      // 如果是连续的词，更新结束时间
      currentSegment.end = word.end;
    } else {
      // 如果不连续，保存当前片段并开始新片段
      segments.push(currentSegment);
      currentSegment = {
        start: word.start,
        end: word.end
      };
    }
  }

  // Push the last segment being built
  if (currentSegment) {
    segments.push(currentSegment);
  }

  return segments;
};

// 清除选中的词语
const clearSelectedWords = () => {
  selectedWordIndices.value = [];
};

// 自动滚动到高亮的词语
const scrollToHighlightedWord = (wordIndex) => {
    if (!editorContainer.value || wordIndex < 0) return;
    
    const wordElements = editorContainer.value.querySelectorAll('.word');
    const targetElement = wordElements[wordIndex];
    
    if (targetElement) {
        setTimeout(() => {
            const containerRect = editorContainer.value.getBoundingClientRect();
            const elementRect = targetElement.getBoundingClientRect();
            
            // 检查元素是否在可视区域内
            const isVisible = (
                elementRect.top >= containerRect.top + 50 &&
                elementRect.bottom <= containerRect.bottom - 50
            );
            
            if (!isVisible) {
                targetElement.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center',
                    inline: 'nearest'
                });
            }
        }, 100);
    }
};

// 获取词语的显示文本（处理标点符号和不同数据格式）
const getWordDisplay = (word) => {
    if (typeof word === 'string') return word;
    // 支持不同的转录数据格式
    return word?.word || word?.text || word?.content || '';
};

// 检查是否为标点符号
const isPunctuation = (text) => {
    if (!text) return false;
    const punctuationRegex = /^[.,!?;:，。！？；："""''()（）\[\]【】\-—–\s]+$/;
    return punctuationRegex.test(text.trim());
};

// 处理用户滚动事件
const handleScroll = () => {
    isUserScrolling.value = true;
    clearTimeout(scrollTimeout.value);
    scrollTimeout.value = setTimeout(() => {
        isUserScrolling.value = false;
    }, 2000);
};

// 添加新的方法
const setSelectedWords = (indices) => {
    selectedWordIndices.value = [...indices];
};

const getSelectedIndices = () => {
    return [...selectedWordIndices.value];
};

// 导出方法供父组件调用（如果需要）
defineExpose({
    scrollToWord: scrollToHighlightedWord,
    getCurrentWordIndex: () => highlightedWordIndex.value,
    resetScroll: () => {
        isUserScrolling.value = false;
        clearTimeout(scrollTimeout.value);
        isUserSeeking.value = false; // 重置用户跳转状态
    },
    getSelectedDeleteSegments, // 暴露获取删除片段的方法
    clearSelectedWords,      // 暴露清除选中词语的方法
    setSelectedWords,
    getSelectedIndices,
});

</script>

<style scoped>
.text-editor {
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Microsoft YaHei', sans-serif;
}

.editor-title {
    color: #2c3e50;
    margin: 0 0 16px 0;
    padding-bottom: 12px;
    border-bottom: 2px solid #3498db;
    font-size: clamp(18px, 2.5vw, 24px);
    font-weight: 700;
    flex-shrink: 0;
    background: linear-gradient(135deg, #2c3e50, #34495e);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.editor-content {
    flex: 1;
    line-height: 2.2;
    font-size: clamp(14px, 1.2vw, 18px);
    color: #34495e;
    text-align: justify;
    overflow-y: auto;
    padding: 16px;
    background: linear-gradient(135deg, #fafafa, #f8f9fa);
    border-radius: 12px;
    border: 1px solid #e9ecef;
    user-select: text;
    min-height: 0;
    box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.1);
    scroll-behavior: smooth;
}

.word {
    display: inline;
    margin: 0 1px;
    padding: 2px 4px;
    border-radius: 6px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    line-height: 2;
}

.word.clickable {
    cursor: pointer;
    touch-action: manipulation;
}

.word.clickable:hover {
    background-color: rgba(52, 152, 219, 0.15);
    transform: scale(1.02);
    box-shadow: 0 2px 8px rgba(52, 152, 219, 0.25);
}

.word.clickable:active {
    transform: scale(0.98);
    background-color: rgba(52, 152, 219, 0.25);
}

.word.highlight {
    background: linear-gradient(135deg, #ffeb3b, #fff176);
    color: #1a1a1a;
    font-weight: 700;
    box-shadow: 0 3px 12px rgba(255, 235, 59, 0.6);
    transform: scale(1.05);
    z-index: 1;
    animation: highlightPulse 0.6s cubic-bezier(0.4, 0, 0.2, 1);
    border: 1px solid rgba(255, 193, 7, 0.4);
}

.word.selected {
    background-color: rgba(244, 67, 54, 0.2);
    border: 1px solid rgba(244, 67, 54, 0.4);
    color: #d32f2f;
    font-weight: 600;
}

.word.selected.highlight {
    background: linear-gradient(135deg, #ffeb3b, #ff9800);
    color: #d32f2f;
    font-weight: 700;
    box-shadow: 0 3px 12px rgba(255, 152, 0, 0.6);
}

@keyframes highlightPulse {
    0% {
        transform: scale(1);
        background: linear-gradient(135deg, #fff176, #ffeb3b);
        box-shadow: 0 2px 8px rgba(255, 235, 59, 0.4);
    }
    50% {
        transform: scale(1.08);
        background: linear-gradient(135deg, #ffeb3b, #ffc107);
        box-shadow: 0 4px 16px rgba(255, 235, 59, 0.8);
    }
    100% {
        transform: scale(1.05);
        background: linear-gradient(135deg, #ffeb3b, #fff176);
        box-shadow: 0 3px 12px rgba(255, 235, 59, 0.6);
    }
}

.waiting-message {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex: 1;
    color: #7f8c8d;
    font-style: italic;
}

.waiting-message p {
    margin: 20px 0 0 0;
    font-size: clamp(16px, 1.5vw, 20px);
    font-weight: 500;
}

.loading-spinner {
    width: 48px;
    height: 48px;
    border: 4px solid #ecf0f1;
    border-top: 4px solid #3498db;
    border-radius: 50%;
    animation: spin 1.2s linear infinite;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

/* 滚动条样式 */
.editor-content::-webkit-scrollbar {
    width: 8px;
}

.editor-content::-webkit-scrollbar-track {
    background: #f1f3f4;
    border-radius: 4px;
}

.editor-content::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, #c1c1c1, #a8a8a8);
    border-radius: 4px;
    transition: background 0.3s ease;
}

.editor-content::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(135deg, #a8a8a8, #888);
}

/* 响应式设计 */
@media (max-width: 768px) {
    .editor-content {
        padding: 12px;
        line-height: 2;
        font-size: 16px;
    }
    
    .word {
        padding: 3px 6px;
        margin: 0 2px;
        border-radius: 8px;
    }
    
    .word.highlight {
        transform: scale(1.03);
        box-shadow: 0 2px 8px rgba(255, 235, 59, 0.5);
    }
    
    .editor-title {
        font-size: 20px;
        margin-bottom: 12px;
        padding-bottom: 8px;
    }
    
    .loading-spinner {
        width: 40px;
        height: 40px;
        border-width: 3px;
    }
    
    /* 触摸设备优化 */
    .word.clickable:hover {
        background-color: transparent;
        transform: none;
        box-shadow: none;
    }
    
    .word.clickable:active {
        background-color: rgba(52, 152, 219, 0.2);
        transform: scale(0.95);
    }
}

@media (max-width: 480px) {
    .editor-content {
        padding: 8px;
        line-height: 1.8;
        font-size: 15px;
    }
    
    .word {
        padding: 2px 4px;
        margin: 0 1px;
    }
    
    .editor-title {
        font-size: 18px;
        margin-bottom: 10px;
    }
}

/* 高对比度模式支持 */
@media (prefers-contrast: high) {
    .word.highlight {
        background: #000;
        color: #fff;
        border: 2px solid #fff;
    }
    
    .editor-content {
        border: 2px solid #000;
        background: #fff;
    }
}

/* 减少动画模式支持 */
@media (prefers-reduced-motion: reduce) {
    .word {
        transition: none;
    }
    
    .word.highlight {
        animation: none;
    }
    
    .loading-spinner {
        animation: none;
    }
    
    .editor-content {
        scroll-behavior: auto;
    }
}

/* 深色模式支持 */
@media (prefers-color-scheme: dark) {
    .editor-title {
        color: #ecf0f1;
        border-bottom-color: #5dade2;
        background: linear-gradient(135deg, #ecf0f1, #bdc3c7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .editor-content {
        background: linear-gradient(135deg, #2c3e50, #34495e);
        color: #ecf0f1;
        border-color: #5d6d7e;
    }
    
    .word.clickable:hover {
        background-color: rgba(93, 173, 226, 0.2);
    }
    
    .word.highlight {
        background: linear-gradient(135deg, #f39c12, #e67e22);
        color: #2c3e50;
    }
    
    .waiting-message {
        color: #bdc3c7;
    }
    
    .loading-spinner {
        border-color: #34495e;
        border-top-color: #5dade2;
    }
}
</style>