import { defineStore } from 'pinia'

interface EditorState {
  transcriptWords: any[]
  selectedIndices: number[]
  deleteSegments: any[]
  originalVideoPath?: string
  isModified: boolean
  timestamp: number
}

export const useEditorStore = defineStore('editor', {
  state: () => ({
    undoStack: [] as EditorState[],
    redoStack: [] as EditorState[],
    currentState: {
      transcriptWords: [],
      selectedIndices: [],
      deleteSegments: [],
      isModified: false,
      timestamp: Date.now()
    } as EditorState,
    initialState: null as EditorState | null,
    maxHistoryLength: 20,
    stateCounter: 0 // 添加状态计数器
  }),

  actions: {    // 保存当前状态到历史记录
    saveState(state: EditorState) {
      // 增加状态计数
      this.stateCounter++;
      
      // 深拷贝当前状态并添加时间戳
      const stateToSave = {
        ...JSON.parse(JSON.stringify(state)),
        timestamp: Date.now(),
        isModified: true
      };

      // 将当前状态添加到撤销栈中
      this.undoStack.push(JSON.parse(JSON.stringify(this.currentState)));

      // 更新当前状态
      this.currentState = stateToSave;

      // 更新重做栈（只包含初始状态）
      if (this.initialState) {
        this.redoStack = [JSON.parse(JSON.stringify(this.initialState))];
      } else {
        this.redoStack = [];
      }

      // 限制历史记录长度
      if (this.undoStack.length > this.maxHistoryLength) {
        this.undoStack.shift();
      }
    },

    // 撤销操作
    undo() {
      // 首先检查是否已经在初始状态
      if (this.isInitialState()) {
        return null;
      }

      if (this.undoStack.length > 0) {
        // 获取上一个状态
        const previousState = this.undoStack.pop()!;
        
        // 恢复到上一个状态
        this.currentState = JSON.parse(JSON.stringify(previousState));

        // 减少状态计数
        this.stateCounter--;

        // 如果恢复后到达初始状态，清空所有栈
        if (this.initialState &&
            this.initialState.timestamp === this.currentState.timestamp) {
          this.currentState.isModified = false;
          this.undoStack = [];
          this.redoStack = [];
          this.stateCounter = 1; // 重置为初始状态
        } else {
          // 不是初始状态，则重做栈中保持初始状态
          if (this.initialState) {
            this.redoStack = [JSON.parse(JSON.stringify(this.initialState))];
          }
        }

        return this.currentState;
      }
      return null;
    },    // 重做操作 - 直接回到初始状态并清空所有栈
    redo() {
      // 如果已经在初始状态，不执行任何操作
      if (this.isInitialState()) {
        return null;
      }

      // 如果有初始状态且当前不在初始状态，则直接回到初始状态
      if (this.initialState) {
        // 恢复到初始状态
        this.currentState = JSON.parse(JSON.stringify(this.initialState));
        
        // 清空所有栈并标记为未修改
        this.currentState.isModified = false;
        this.undoStack = [];
        this.redoStack = [];
        this.stateCounter = 1; // 重置为初始状态

        return this.currentState;
      }
      return null;
    },    // 获取当前是否可以撤销
    canUndo(): boolean {
      // 如果在初始状态，禁用撤销按钮
      if (this.initialState?.timestamp === this.currentState.timestamp) {
        return false;
      }
      return this.undoStack.length > 0;
    },    // 获取当前是否可以重做
    canRedo(): boolean {
      // 如果在初始状态，禁用重做按钮
      if (this.initialState?.timestamp === this.currentState.timestamp) {
        return false;
      }
      // 只要有初始状态且当前不在初始状态就可以重做
      return this.initialState !== null;
    },

    // 清空历史记录
    clearHistory() {
      this.undoStack = [];
      this.redoStack = [];
      this.initialState = null;
      this.stateCounter = 1; // 重置计数器
      this.currentState = {
        transcriptWords: [],
        selectedIndices: [],
        deleteSegments: [],
        isModified: false,
        timestamp: Date.now()
      };
    },

    // 保存初始状态
    saveInitialState(state: EditorState) {
      // 清空历史记录
      this.clearHistory();
      this.stateCounter = 1; // 确保是初始状态

      // 保存带时间戳的初始状态
      this.initialState = {
        ...JSON.parse(JSON.stringify(state)),
        timestamp: Date.now(),
        isModified: false
      };

      // 设置为当前状态
      this.currentState = JSON.parse(JSON.stringify(this.initialState));
    },

    // 获取初始状态
    getInitialState(): EditorState | null {
      return this.initialState;
    },

    // 检查当前是否为初始状态
    isInitialState(): boolean {
      return this.initialState?.timestamp === this.currentState.timestamp;
    }
  }
})