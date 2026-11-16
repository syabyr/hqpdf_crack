#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
二进制级别的PDF编码转换工具
直接修改PDF内部的二进制内容，将GB2312编码转换为UTF-8编码
不重建PDF，保留原有格式和属性
"""

import re
from pathlib import Path
from typing import Tuple, List
import sys

class PDFBinaryConverter:
    """PDF二进制级别编码转换器"""
    
    def __init__(self, source_encoding='gb2312', target_encoding='utf-8'):
        self.source_encoding = source_encoding
        self.target_encoding = target_encoding
        self.stats = {
            'total_objects': 0,
            'modified_objects': 0,
            'text_segments_found': 0,
            'bytes_modified': 0,
        }
    
    def read_pdf_binary(self, pdf_path):
        """读取PDF二进制内容"""
        print(f"✓ 读取PDF文件: {pdf_path}")
        with open(pdf_path, 'rb') as f:
            return f.read()
    
    def _detect_text_encoding(self, data: bytes, max_sample=1000) -> str:
        """检测二进制数据中的文本编码"""
        sample = data[:max_sample]
        
        # 尝试GB2312
        try:
            sample.decode('gb2312')
            return 'gb2312'
        except:
            pass
        
        # 尝试GBK
        try:
            sample.decode('gbk')
            return 'gbk'
        except:
            pass
        
        # 尝试UTF-8
        try:
            sample.decode('utf-8')
            return 'utf-8'
        except:
            pass
        
        return 'unknown'
    
    def _find_pdf_streams(self, data: bytes) -> List[Tuple[int, int]]:
        """找到PDF中所有的stream对象位置"""
        streams = []
        pattern = rb'stream\s*\n(.*?)\nendstream'
        
        for match in re.finditer(pattern, data, re.DOTALL):
            start = match.start(1)
            end = match.end(1)
            streams.append((start, end, match.group(1)))
        
        return streams
    
    def _find_text_strings(self, data: bytes) -> List[Tuple[int, int, bytes]]:
        """找到PDF中的文本字符串 (由() 或 <> 括起的)"""
        strings = []
        
        # 查找 (...) 格式的字符串
        pattern1 = rb'\((.*?)\)'
        for match in re.finditer(pattern1, data):
            start = match.start(1)
            end = match.end(1)
            strings.append((start, end, match.group(1), 'paren'))
        
        # 查找 <...> 格式的十六进制字符串
        pattern2 = rb'<([0-9A-Fa-f]+)>'
        for match in re.finditer(pattern2, data):
            start = match.start(1)
            end = match.end(1)
            strings.append((start, end, match.group(1), 'hex'))
        
        return strings
    
    def _convert_hex_string(self, hex_str: bytes) -> bytes:
        """转换十六进制编码的文本"""
        try:
            # 十六进制字符串转字节
            binary_data = bytes.fromhex(hex_str.decode('ascii'))
            
            # 尝试用源编码解码
            text = binary_data.decode(self.source_encoding)
            
            # 用目标编码重新编码
            converted = text.encode(self.target_encoding)
            
            # 转回十六进制
            return converted.hex().upper().encode('ascii')
        except Exception as e:
            return hex_str
    
    def _convert_paren_string(self, text: bytes) -> bytes:
        """转换括号括起的文本"""
        try:
            # 尝试用源编码解码
            decoded = text.decode(self.source_encoding)
            
            # 用目标编码重新编码
            converted = decoded.encode(self.target_encoding)
            
            return converted
        except Exception as e:
            return text
    
    def convert_pdf_binary(self, input_pdf: str, output_pdf: str) -> bool:
        """执行二进制级别的PDF转换"""
        print(f"\n{'='*60}")
        print(f"PDF 二进制级别编码转换工具")
        print(f"{'='*60}")
        print(f"输入文件: {input_pdf}")
        print(f"输出文件: {output_pdf}")
        print(f"编码转换: {self.source_encoding} → {self.target_encoding}")
        print(f"{'='*60}\n")
        
        # 检查文件
        if not Path(input_pdf).exists():
            print(f"✗ 输入文件不存在: {input_pdf}")
            return False
        
        # 读取二进制内容
        pdf_data = self.read_pdf_binary(input_pdf)
        original_size = len(pdf_data)
        print(f"  文件大小: {original_size} 字节\n")
        
        # 创建修改副本
        modified_data = bytearray(pdf_data)
        
        # 步骤1: 处理stream中的文本
        print("第一步: 扫描PDF stream对象...")
        streams = self._find_pdf_streams(pdf_data)
        print(f"  找到 {len(streams)} 个stream对象\n")
        
        stream_modified = 0
        for idx, (start, end, stream_content) in enumerate(streams):
            # 在stream内容中查找文本字符串
            text_strings = self._find_text_strings(stream_content)
            
            if text_strings:
                print(f"  Stream {idx}: 找到 {len(text_strings)} 个文本字符串")
                
                for str_idx, (str_start, str_end, content, str_type) in enumerate(text_strings):
                    # 调整相对位置为绝对位置
                    abs_start = start + str_start
                    abs_end = start + str_end
                    
                    old_content = modified_data[abs_start:abs_end]
                    
                    # 根据类型转换
                    if str_type == 'hex':
                        new_content = self._convert_hex_string(content)
                    else:  # paren
                        new_content = self._convert_paren_string(content)
                    
                    # 如果内容改变了，更新
                    if new_content != old_content:
                        if len(new_content) == len(old_content):
                            # 长度相同，直接替换
                            modified_data[abs_start:abs_end] = new_content
                            self.stats['bytes_modified'] += len(new_content)
                            stream_modified += 1
                            self.stats['modified_objects'] += 1
                        else:
                            # 长度不同，需要调整（这会很复杂）
                            print(f"    警告: 字符串长度变化 ({len(old_content)} → {len(new_content)})，跳过")
        
        print(f"✓ 修改了 {stream_modified} 个文本字符串\n")
        
        # 步骤2: 处理PDF对象中的文本
        print("第二步: 扫描PDF对象中的文本字符串...")
        object_strings = self._find_text_strings(pdf_data)
        print(f"  找到 {len(object_strings)} 个文本对象\n")
        
        obj_modified = 0
        for idx, (start, end, content, str_type) in enumerate(object_strings):
            old_content = modified_data[start:end]
            
            # 根据类型转换
            if str_type == 'hex':
                new_content = self._convert_hex_string(content)
            else:  # paren
                new_content = self._convert_paren_string(content)
            
            # 如果内容改变了，更新
            if new_content != old_content:
                if len(new_content) == len(old_content):
                    modified_data[start:end] = new_content
                    self.stats['bytes_modified'] += len(new_content)
                    obj_modified += 1
                    self.stats['modified_objects'] += 1
        
        print(f"✓ 修改了 {obj_modified} 个对象字符串\n")
        
        # 保存修改后的PDF
        print("第三步: 保存修改后的PDF...")
        try:
            with open(output_pdf, 'wb') as f:
                f.write(modified_data)
            
            new_size = len(modified_data)
            print(f"✓ 已保存: {output_pdf}")
            print(f"  新文件大小: {new_size} 字节\n")
            
            # 验证
            print(f"{'='*60}")
            print("转换统计:")
            print(f"{'='*60}")
            print(f"  修改的对象数: {self.stats['modified_objects']}")
            print(f"  修改的字节数: {self.stats['bytes_modified']}")
            print(f"  文件大小变化: {new_size - original_size:+d} 字节")
            print(f"{'='*60}\n")
            
            return True
        
        except Exception as e:
            print(f"✗ 保存文件失败: {e}")
            return False
    
    def safe_convert_with_backup(self, input_pdf: str, output_pdf: str) -> bool:
        """安全转换，保留备份"""
        from shutil import copy2
        
        # 创建备份
        backup_path = f"{input_pdf}.backup"
        if not Path(backup_path).exists():
            copy2(input_pdf, backup_path)
            print(f"✓ 已创建备份: {backup_path}\n")
        
        # 执行转换
        return self.convert_pdf_binary(input_pdf, output_pdf)


def verify_pdf_encoding(pdf_path: str) -> None:
    """验证PDF中的编码"""
    print(f"\n{'='*60}")
    print(f"PDF 编码验证")
    print(f"{'='*60}\n")
    
    try:
        with open(pdf_path, 'rb') as f:
            data = f.read()
        
        # 查找文本字符串
        strings = []
        pattern1 = rb'\((.*?)\)'
        for match in re.finditer(pattern1, data):
            strings.append(('paren', match.group(1)))
        
        pattern2 = rb'<([0-9A-Fa-f]+)>'
        for match in re.finditer(pattern2, data):
            strings.append(('hex', match.group(1)))
        
        print(f"找到 {len(strings)} 个文本字符串\n")
        
        # 分析前几个
        for idx, (str_type, content) in enumerate(strings[:5]):
            print(f"字符串 {idx+1} ({str_type}):")
            print(f"  原始: {content[:50]}")
            
            # 检测编码
            if str_type == 'hex':
                try:
                    binary = bytes.fromhex(content.decode('ascii'))
                    print(f"  解码(GB2312): {binary.decode('gb2312')}")
                except:
                    print(f"  解码失败")
            else:
                try:
                    print(f"  解码(GB2312): {content.decode('gb2312')}")
                except:
                    print(f"  解码失败")
            print()
    
    except Exception as e:
        print(f"✗ 验证失败: {e}")


def main():
    """主程序"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='在二进制级别将PDF编码从GB2312转换为UTF-8'
    )
    parser.add_argument('-i', '--input', default='0.pdf', help='输入PDF文件')
    parser.add_argument('-o', '--output', default='00.pdf', help='输出PDF文件')
    parser.add_argument('-s', '--source-encoding', default='gb2312', help='源编码')
    parser.add_argument('-t', '--target-encoding', default='utf-8', help='目标编码')
    parser.add_argument('-v', '--verify', action='store_true', help='验证PDF编码')
    parser.add_argument('-b', '--backup', action='store_true', help='创建备份')
    
    args = parser.parse_args()
    
    # 验证模式
    if args.verify:
        verify_pdf_encoding(args.input)
        return 0
    
    # 创建转换器
    converter = PDFBinaryConverter(args.source_encoding, args.target_encoding)
    
    # 执行转换
    if args.backup:
        success = converter.safe_convert_with_backup(args.input, args.output)
    else:
        success = converter.convert_pdf_binary(args.input, args.output)
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
