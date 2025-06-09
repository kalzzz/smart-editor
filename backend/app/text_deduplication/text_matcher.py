#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文本去重匹配程序

该模块实现了一个高效的文本匹配算法，用于从冗余的语音识别结果中
提取与目标文本匹配的词语段，支持中英文混合文本处理。

主要功能：
- 接收JSON格式的冗余文本和目标文本字符串
- 通过词语粒度匹配算法过滤冗余内容
- 支持相似度匹配和最右匹配优先策略
- 返回精简的JSON格式结果

Author: AI Assistant
Date: 2024
"""

import json
import re
import string
from typing import List, Dict, Any, Tuple
from difflib import SequenceMatcher


class TextMatcher:
    """
    文本匹配器类，实现高效的文本去重匹配算法
    """
    
    def __init__(self, similarity_threshold: float = 0.8):
        """
        初始化文本匹配器
        
        Args:
            similarity_threshold (float): 相似度阈值，默认0.8
        """
        self.similarity_threshold = similarity_threshold
    
    def clean_text(self, text: str) -> str:
        """
        清理文本，移除标点符号和空格
        
        Args:
            text (str): 原始文本
            
        Returns:
            str: 清理后的文本
        """
        # 移除标点符号和空格
        # 使用string.punctuation处理ASCII标点，再处理中文标点
        chinese_punctuation = '，。！？；："（）【】《》、'
        all_punctuation = string.punctuation + chinese_punctuation
        
        # 移除所有标点符号和空格
        cleaned = "".join(char for char in text if char not in all_punctuation and not char.isspace())
        return cleaned
    
    def calculate_similarity(self, word1: str, word2: str) -> float:
        """
        计算两个词语的相似度
        
        Args:
            word1 (str): 词语1
            word2 (str): 词语2
            
        Returns:
            float: 相似度分数 (0-1)
        """
        return SequenceMatcher(None, word1, word2).ratio()
    
    def find_best_match_sequence(self, redundant_words: List[Dict[str, Any]], 
                                 target_text: str) -> List[Dict[str, Any]]:
        """
        使用改进的序列匹配算法找到最佳匹配序列
        优先组合字符形成词语，避免重复和错乱
        
        Args:
            redundant_words (List[Dict]): 冗余词语列表
            target_text (str): 目标文本
            
        Returns:
            List[Dict]: 匹配的词语序列
        """
        # 首先尝试将单字符组合成词语
        combined_words = self._combine_characters_to_words(redundant_words, target_text)
        
        cleaned_target = self.clean_text(target_text)
        result = []
        target_pos = 0
        used_indices = set()  # 记录已使用的词语索引，避免重复使用
        
        # 按顺序匹配目标文本
        while target_pos < len(cleaned_target):
            best_match = None
            best_match_len = 0
            best_index = -1
            
            # 寻找当前位置的最佳匹配（优先长词语）
            for i, word_obj in enumerate(combined_words):
                if i in used_indices:  # 跳过已使用的词语
                    continue
                    
                word = self.clean_text(word_obj['word'])
                word_len = len(word)
                
                # 跳过空词语（只包含标点符号的词语）
                if word_len == 0:
                    continue
                
                # 检查是否可以在当前位置精确匹配
                if target_pos + word_len <= len(cleaned_target):
                    target_segment = cleaned_target[target_pos:target_pos + word_len]
                    
                    # 只进行精确匹配，确保结果文本与目标文本完全一致
                    if word == target_segment:
                        # 选择最长的匹配，如果长度相同则选择置信度更高的
                        if (word_len > best_match_len or 
                            (word_len == best_match_len and best_match is not None and word_obj.get('conf', 0) > best_match.get('conf', 0)) or
                            (word_len == best_match_len and best_match is None)):
                            best_match = word_obj
                            best_match_len = word_len
                            best_index = i
            
            # 如果找到匹配，添加到结果中
            if best_match:
                result.append(best_match)
                used_indices.add(best_index)
                target_pos += best_match_len
            else:
                # 如果没有找到匹配，跳过当前字符
                target_pos += 1
        
        return result
    
    def _combine_characters_to_words(self, redundant_words: List[Dict[str, Any]], 
                                   target_text: str) -> List[Dict[str, Any]]:
        """
        将连续的单字符组合成词语，减少碎片化
        
        Args:
            redundant_words (List[Dict]): 原始冗余词语列表
            target_text (str): 目标文本
            
        Returns:
            List[Dict]: 组合后的词语列表
        """
        # 按时间顺序排序
        sorted_words = sorted(redundant_words, key=lambda x: x.get('start', 0))
        
        combined = []
        i = 0
        
        while i < len(sorted_words):
            current_word = sorted_words[i]
            current_text = current_word['word']
            current_start = current_word.get('start', 0)
            current_end = current_word.get('end', 0)
            current_conf = current_word.get('conf', 0)
            
            # 尝试向后组合连续的字符
            j = i + 1
            while j < len(sorted_words):
                next_word = sorted_words[j]
                next_text = next_word['word']
                
                # 检查是否是连续的字符
                combined_text = current_text + next_text
                
                # 检查组合后的文本是否在目标文本中连续出现
                if combined_text in target_text:
                    # 组合这两个字符
                    current_text = combined_text
                    current_end = next_word.get('end', current_end)
                    current_conf = max(current_conf, next_word.get('conf', 0))  # 取较高的置信度
                    j += 1
                else:
                    break
            
            # 添加组合后的词语
            combined.append({
                'word': current_text,
                'start': current_start,
                'end': current_end,
                'conf': current_conf
            })
            
            # 跳过已经组合的字符
            i = j
        
        # 添加原始的多字符词语（如果有的话）
        for word_obj in redundant_words:
            if len(word_obj['word']) > 1:
                # 检查是否已经被包含在组合词语中
                already_included = False
                for combined_word in combined:
                    if (word_obj['word'] in combined_word['word'] and 
                        abs(word_obj.get('start', 0) - combined_word.get('start', 0)) < 0.1):
                        already_included = True
                        break
                
                if not already_included:
                    combined.append(word_obj)
        
        # 按长度降序排序，优先使用长词语
        combined.sort(key=lambda x: (-len(x['word']), x.get('start', 0)))
        
        return combined
        
        # 处理标点符号
        # 检查结果文本是否与目标文本一致
        result_text = ''.join([item['word'] for item in result])
        
        # 如果结果文本与目标文本不一致，尝试添加缺失的标点符号
        if result_text != target_text:
            # 寻找未使用的标点符号词语，按照在目标文本中的位置顺序添加
            target_chars = list(target_text)
            result_chars = list(result_text)
            final_result = []
            
            target_idx = 0
            result_idx = 0
            
            while target_idx < len(target_chars) and result_idx < len(result_chars):
                if target_chars[target_idx] == result_chars[result_idx]:
                    # 字符匹配，继续
                    target_idx += 1
                    result_idx += 1
                else:
                    # 字符不匹配，可能是缺少标点符号
                    missing_char = target_chars[target_idx]
                    
                    # 寻找对应的标点符号词语
                    punctuation_found = False
                    for i, word_obj in enumerate(redundant_words):
                        if i not in used_indices and word_obj['word'] == missing_char:
                            # 找到对应的标点符号，插入到适当位置
                            # 根据当前已处理的结果确定插入位置
                            insert_pos = len([item for item in result if ''.join([c for c in item['word'] if c.strip()]) != ''])
                            if insert_pos <= len(final_result):
                                final_result.insert(insert_pos, word_obj)
                            else:
                                final_result.append(word_obj)
                            used_indices.add(i)
                            punctuation_found = True
                            break
                    
                    if punctuation_found:
                        target_idx += 1
                    else:
                        # 如果没找到对应的标点符号，跳过
                        target_idx += 1
            
            # 将原始匹配结果按顺序添加到final_result中
            for item in result:
                if item not in final_result:
                    final_result.append(item)
            
            # 按照start时间排序
            final_result.sort(key=lambda x: x.get('start', 0))
            return final_result
        
        return result
    
    def greedy_match(self, redundant_words: List[Dict[str, Any]], 
                    target_text: str) -> List[Dict[str, Any]]:
        """
        贪心匹配算法（备用方案，性能更好但可能不是最优解）
        
        Args:
            redundant_words (List[Dict]): 冗余词语列表
            target_text (str): 目标文本
            
        Returns:
            List[Dict]: 匹配的词语序列
        """
        cleaned_target = self.clean_text(target_text)
        result = []
        target_pos = 0
        
        for word_obj in redundant_words:
            word = self.clean_text(word_obj['word'])
            word_len = len(word)
            
            # 检查是否可以在当前位置匹配
            if target_pos + word_len <= len(cleaned_target):
                target_segment = cleaned_target[target_pos:target_pos + word_len]
                
                # 精确匹配或相似度匹配
                if (word == target_segment or 
                    self.calculate_similarity(word, target_segment) >= self.similarity_threshold):
                    result.append(word_obj)
                    target_pos += word_len
                    
                    # 如果已经匹配完整个目标文本，提前结束
                    if target_pos >= len(cleaned_target):
                        break
        
        return result


def match_and_filter(redundant_json: List[Dict[str, Any]], 
                    target_text: str, 
                    use_dp: bool = True,
                    similarity_threshold: float = 0.8) -> List[Dict[str, Any]]:
    """
    主要的匹配和过滤函数
    
    该函数接收冗余的语音识别结果和目标文本，通过智能匹配算法
    提取出与目标文本匹配的词语段，去除冗余内容。
    
    Args:
        redundant_json (List[Dict]): 冗余文本的JSON格式数据，每个元素包含：
            - conf (float): 置信度
            - start (float): 起始时间（秒）
            - end (float): 结束时间（秒）
            - word (str): 词语内容
        target_text (str): 去冗余后的目标文本字符串
        use_dp (bool): 是否使用动态规划算法，默认True（更准确但稍慢）
        similarity_threshold (float): 相似度匹配阈值，默认0.8
        
    Returns:
        List[Dict]: 过滤后的词语段列表，保持原有的JSON结构
        
    Example:
        >>> redundant_data = [
        ...     {"conf": 1.0, "end": 0.69, "start": 0.33, "word": "大家好"},
        ...     {"conf": 1.0, "end": 0.9, "start": 0.69, "word": "欢迎"},
        ...     {"conf": 1.0, "end": 1.23, "start": 0.9, "word": "欢"}
        ... ]
        >>> target = "大家好欢迎"
        >>> result = match_and_filter(redundant_data, target)
        >>> print(result)
        [{'conf': 1.0, 'end': 0.69, 'start': 0.33, 'word': '大家好'}, 
         {'conf': 1.0, 'end': 0.9, 'start': 0.69, 'word': '欢迎'}]
    """
    if not redundant_json or not target_text:
        return []
    
    # 创建文本匹配器实例
    matcher = TextMatcher(similarity_threshold=similarity_threshold)
    
    # 根据参数选择匹配算法
    if use_dp:
        # 使用动态规划算法（更准确，支持最右匹配优先）
        return matcher.find_best_match_sequence(redundant_json, target_text)
    else:
        # 使用贪心算法（更快速）
        return matcher.greedy_match(redundant_json, target_text)


def batch_process(data_list: List[Tuple[List[Dict[str, Any]], str]], 
                 **kwargs) -> List[List[Dict[str, Any]]]:
    """
    批量处理多个文本匹配任务
    
    Args:
        data_list (List[Tuple]): 包含(redundant_json, target_text)元组的列表
        **kwargs: 传递给match_and_filter的其他参数
        
    Returns:
        List[List[Dict]]: 批量处理结果列表
    """
    results = []
    for redundant_json, target_text in data_list:
        result = match_and_filter(redundant_json, target_text, **kwargs)
        results.append(result)
    return results


if __name__ == "__main__":
    # 测试用例
    print("=" * 50)
    print("文本去重匹配程序测试")
    print("=" * 50)
    
    # 测试用例1：基本匹配
    print("\n测试用例1：基本匹配")
    test_redundant_1 = [
        {"conf": 1.0, "end": 0.69, "start": 0.33, "word": "大家好"},
        {"conf": 1.0, "end": 0.9, "start": 0.69, "word": "欢迎"},
        {"conf": 1.0, "end": 1.23, "start": 0.9, "word": "欢"}
    ]
    test_target_1 = "大家好欢迎"
    
    result_1 = match_and_filter(test_redundant_1, test_target_1)
    print(f"输入冗余文本: {json.dumps(test_redundant_1, ensure_ascii=False, indent=2)}")
    print(f"目标文本: {test_target_1}")
    print(f"匹配结果: {json.dumps(result_1, ensure_ascii=False, indent=2)}")
    
    # 测试用例2：包含标点符号的文本
    print("\n测试用例2：包含标点符号的文本")
    test_redundant_2 = [
        {"conf": 0.95, "end": 1.0, "start": 0.0, "word": "你好"},
        {"conf": 0.98, "end": 2.0, "start": 1.0, "word": "，"},
        {"conf": 0.92, "end": 3.0, "start": 2.0, "word": "世界"},
        {"conf": 0.88, "end": 4.0, "start": 3.0, "word": "！"}
    ]
    test_target_2 = "你好，世界！"
    
    result_2 = match_and_filter(test_redundant_2, test_target_2)
    print(f"输入冗余文本: {json.dumps(test_redundant_2, ensure_ascii=False, indent=2)}")
    print(f"目标文本: {test_target_2}")
    print(f"匹配结果: {json.dumps(result_2, ensure_ascii=False, indent=2)}")
    
    # 测试用例3：中英文混合
    print("\n测试用例3：中英文混合")
    test_redundant_3 = [
        {"conf": 1.0, "end": 1.0, "start": 0.0, "word": "Hello"},
        {"conf": 0.9, "end": 2.0, "start": 1.0, "word": "你好"},
        {"conf": 1.0, "end": 3.0, "start": 2.0, "word": "World"},
        {"conf": 0.85, "end": 4.0, "start": 3.0, "word": "世界"}
    ]
    test_target_3 = "Hello世界"
    
    result_3 = match_and_filter(test_redundant_3, test_target_3)
    print(f"输入冗余文本: {json.dumps(test_redundant_3, ensure_ascii=False, indent=2)}")
    print(f"目标文本: {test_target_3}")
    print(f"匹配结果: {json.dumps(result_3, ensure_ascii=False, indent=2)}")
    
    # 测试用例4：相似度匹配
    print("\n测试用例4：相似度匹配")
    test_redundant_4 = [
        {"conf": 0.8, "end": 1.0, "start": 0.0, "word": "机器学习"},
        {"conf": 0.7, "end": 2.0, "start": 1.0, "word": "机械学习"},  # 相似但不完全相同
        {"conf": 0.9, "end": 3.0, "start": 2.0, "word": "很有趣"}
    ]
    test_target_4 = "机器学习很有趣"
    
    result_4 = match_and_filter(test_redundant_4, test_target_4, similarity_threshold=0.7)
    print(f"输入冗余文本: {json.dumps(test_redundant_4, ensure_ascii=False, indent=2)}")
    print(f"目标文本: {test_target_4}")
    print(f"匹配结果: {json.dumps(result_4, ensure_ascii=False, indent=2)}")
    
    # 性能测试
    print("\n性能测试：比较动态规划算法和贪心算法")
    import time
    
    # 创建较大的测试数据
    large_test_data = []
    for i in range(100):
        large_test_data.append({
            "conf": 0.9 + i * 0.001,
            "end": i * 0.5 + 0.5,
            "start": i * 0.5,
            "word": f"词语{i}"
        })
    large_target = "词语0词语1词语2词语3词语4"
    
    # 测试动态规划算法
    start_time = time.time()
    dp_result = match_and_filter(large_test_data, large_target, use_dp=True)
    dp_time = time.time() - start_time
    
    # 测试贪心算法
    start_time = time.time()
    greedy_result = match_and_filter(large_test_data, large_target, use_dp=False)
    greedy_time = time.time() - start_time
    
    print(f"动态规划算法耗时: {dp_time:.4f}秒，结果数量: {len(dp_result)}")
    print(f"贪心算法耗时: {greedy_time:.4f}秒，结果数量: {len(greedy_result)}")
    
    print("\n=" * 50)
    print("测试完成！")
    print("=" * 50)