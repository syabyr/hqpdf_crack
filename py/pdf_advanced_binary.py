#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
高级PDF二进制编码转换工具
支持处理PDF内部的字体编码、CMap和Unicode映射
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import zlib

class AdvancedPDFBinaryConverter:
    """高级PDF二进制级别编码转换器"""
    
    def __init__(self, source_encoding='gb2312', target_encoding='utf-8'):
        self.source_encoding = source_encoding
        self.target_encoding = target_encoding
        self.stats = {
            'streams_processed': 0,
            'strings_converted': 0,
            'hex_strings_converted': 0,
            'bytes_changed': 0,
        }
    
    def read_pdf(self, pdf_path: str) -> bytes:
        """读取PDF文件"""
        with open(pdf_path, 'rb') as f:
            return f.read()
    
    def write_pdf(self, pdf_path: str, data: bytes) -> None:
        """保存PDF文件"""
        with open(pdf_path, 'wb') as f:
            f.write(data)
    
    def _extract_stream_content(self, pdf_data: bytes, stream_start: int, stream_end: int) -> bytes:
        """提取stream对象的内容"""
        # 查找stream关键字后的内容
        pattern = rb'stream[\r\n]+(.*?)[\r\n]+endstream'
        match = re.search(pattern, pdf_data[stream_start:stream_end], re.DOTALL)
        if match:
            return match.group(1)
        return b''
    
    def _convert_string_encoding(self, s: bytes, is_hex: bool = False) -> Tuple[bytes, bool]:
        """转换字符串的编码"""
        try:
            if is_hex:
                # 十六进制编码的字符串
                hex_str = s.decode('ascii')
                binary = bytes.fromhex(hex_str)
            else:
                binary = s
            
            # 尝试用GB2312解码
            try:
                text = binary.decode(self.source_encoding)
            except:
                # 尝试GBK
                try:
                    text = binary.decode('gbk')
                except:
                    return s, False
            
            # 用UTF-8编码
            utf8_binary = text.encode(self.target_encoding)
            
            if is_hex:
                return utf8_binary.hex().upper().encode('ascii'), True
            else:
                return utf8_binary, True
        
        except Exception as e:
            return s, False
    
    def _process_content_stream(self, content: bytes) -> Tuple[bytes, int]:
        """处理PDF内容流（可能是压缩的）"""
        conversions = 0
        
        # 尝试解压
        try:
            decompressed = zlib.decompress(content)
            print(f"    (压缩的内容流已解压)")
            content = decompressed
        except:
            pass
        
        # 修改内容
        modified = bytearray(content)
        
        # 查找 (...) 格式的字符串
        pattern1 = rb'\(([^)]+)\)'
        for match in re.finditer(pattern1, content):
            start = match.start(1)
            end = match.end(1)
            old_str = match.group(1)
            
            new_str, changed = self._convert_string_encoding(old_str, False)
            
            if changed and len(new_str) == len(old_str):
                modified[start:end] = new_str
                conversions += 1
        
        # 查找 <...> 格式的十六进制字符串
        pattern2 = rb'<([0-9A-Fa-f]+)>'
        for match in re.finditer(pattern2, content):
            start = match.start(1)
            end = match.end(1)
            old_str = match.group(1)
            
            new_str, changed = self._convert_string_encoding(old_str, True)
            
            if changed and len(new_str) == len(old_str):
                modified[start:end] = new_str
                conversions += 1
        
        # 尝试重新压缩
        try:
            compressed = zlib.compress(bytes(modified))
            return compressed, conversions
        except:
            return bytes(modified), conversions
    
    def convert(self, input_pdf: str, output_pdf: str) -> bool:
        """执行高级二进制转换"""
        print(f"\n{'='*70}")
        print(f"高级 PDF 二进制级别编码转换")
        print(f"{'='*70}")
        print(f"输入: {input_pdf}")
        print(f"输出: {output_pdf}")
        print(f"转换: {self.source_encoding.upper()} → {self.target_encoding.upper()}")
        print(f"{'='*70}\n")
        
        if not Path(input_pdf).exists():
            print(f"✗ 输入文件不存在")
            return False
        
        # 读取PDF
        pdf_data = self.read_pdf(input_pdf)
        original_size = len(pdf_data)
        print(f"原文件大小: {original_size} 字节\n")
        
        # 转换为bytearray便于修改
        pdf_modified = bytearray(pdf_data)
        
        # 第一步：处理直接的文本字符串
        print("第一步：扫描并转换文本字符串...")
        string_pattern1 = rb'\(([^)]{1,500})\)'  # (...) 格式，最多500字符
        string_pattern2 = rb'<([0-9A-Fa-f]{2,1000})>'  # <...> 格式
        
        strings_found = 0
        strings_converted = 0
        
        # 处理 (...) 格式
        for match in re.finditer(string_pattern1, pdf_data):
            strings_found += 1
            start = match.start(1)
            end = match.end(1)
            old_str = match.group(1)
            
            new_str, changed = self._convert_string_encoding(old_str, False)
            
            if changed and len(new_str) == len(old_str):
                pdf_modified[start:end] = new_str
                strings_converted += 1
                self.stats['bytes_changed'] += len(new_str)
        
        # 处理 <...> 格式
        for match in re.finditer(string_pattern2, pdf_data):
            strings_found += 1
            start = match.start(1)
            end = match.end(1)
            old_str = match.group(1)
            
            new_str, changed = self._convert_string_encoding(old_str, True)
            
            if changed and len(new_str) == len(old_str):
                pdf_modified[start:end] = new_str
                strings_converted += 1
                self.stats['bytes_changed'] += len(new_str)
        
        print(f"  找到字符串: {strings_found}")
        print(f"  转换成功: {strings_converted}\n")
        self.stats['strings_converted'] = strings_converted
        
        # 第二步：处理stream对象
        print("第二步：处理Stream对象...")
        stream_pattern = rb'stream[\r\n]+(.*?)[\r\n]+endstream'
        
        stream_count = 0
        for match in re.finditer(stream_pattern, pdf_data, re.DOTALL):
            stream_count += 1
            stream_content = match.group(1)
            
            if len(stream_content) > 10000:  # 跳过太大的stream
                continue
            
            processed, conversions = self._process_content_stream(stream_content)
            
            if conversions > 0:
                # 需要更新stream的长度（如果有FlateDecode）
                start = match.start(1)
                end = match.end(1)
                
                if len(processed) == len(stream_content):
                    pdf_modified[start:end] = processed
                    self.stats['streams_processed'] += 1
        
        print(f"  处理stream: {stream_count}")
        print(f"  修改stream: {self.stats['streams_processed']}\n")
        
        # 保存
        print("第三步：保存修改后的PDF...")
        try:
            self.write_pdf(output_pdf, pdf_modified)
            new_size = len(pdf_modified)
            print(f"✓ 已保存: {output_pdf}")
            print(f"  新文件大小: {new_size} 字节\n")
            
            print(f"{'='*70}")
            print("转换结果:")
            print(f"{'='*70}")
            print(f"  文本字符串转换: {self.stats['strings_converted']}")
            print(f"  Stream对象修改: {self.stats['streams_processed']}")
            print(f"  字节数变化: {new_size - original_size:+d}")
            print(f"{'='*70}\n")
            
            return True
        
        except Exception as e:
            print(f"✗ 保存失败: {e}")
            return False


def compare_pdfs(pdf1: str, pdf2: str) -> None:
    """比较两个PDF文件"""
    print(f"\n{'='*70}")
    print("PDF 文件比较")
    print(f"{'='*70}\n")
    
    with open(pdf1, 'rb') as f:
        data1 = f.read()
    with open(pdf2, 'rb') as f:
        data2 = f.read()
    
    size1 = len(data1)
    size2 = len(data2)
    
    print(f"文件1: {pdf1}")
    print(f"  大小: {size1} 字节")
    
    print(f"\n文件2: {pdf2}")
    print(f"  大小: {size2} 字节")
    
    if data1 == data2:
        print("\n✓ 两个文件完全相同")
    else:
        # 找到第一个不同的字节
        diff_count = 0
        for i in range(min(size1, size2)):
            if data1[i] != data2[i]:
                diff_count += 1
                if diff_count == 1:
                    print(f"\n首个差异位置: 字节 {i}")
                    print(f"  文件1: {data1[max(0, i-20):i+20]}")
                    print(f"  文件2: {data2[max(0, i-20):i+20]}")
        
        if diff_count > 0:
            print(f"\n✓ 发现 {diff_count} 处差异")
        else:
            print(f"\n文件内容相同，但大小不同 ({size1} vs {size2})")


def main():
    """主程序"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='高级二进制级别的PDF编码转换'
    )
    parser.add_argument('-i', '--input', default='0.pdf', help='输入PDF')
    parser.add_argument('-o', '--output', default='00_adv.pdf', help='输出PDF')
    parser.add_argument('-s', '--source', default='gb2312', help='源编码')
    parser.add_argument('-t', '--target', default='utf-8', help='目标编码')
    parser.add_argument('-c', '--compare', help='与另一个PDF比较')
    
    args = parser.parse_args()
    
    converter = AdvancedPDFBinaryConverter(args.source, args.target)
    success = converter.convert(args.input, args.output)
    
    if args.compare:
        compare_pdfs(args.output, args.compare)
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
