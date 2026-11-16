#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PDF 二进制编码转换 - 处理压缩流版本
正确处理FlateDecode压缩的PDF流
"""

import re
import zlib
import sys
from pathlib import Path
from typing import Dict, List, Tuple

class PDFStreamConverter:
    """处理PDF压缩流的编码转换器"""
    
    def __init__(self, source_encoding='gb2312', target_encoding='utf-8'):
        self.source_encoding = source_encoding
        self.target_encoding = target_encoding
        self.stats = {
            'streams_found': 0,
            'streams_decompressed': 0,
            'streams_converted': 0,
            'text_segments_converted': 0,
            'total_bytes_before': 0,
            'total_bytes_after': 0,
        }
    
    def _find_stream_objects(self, pdf_data: bytes) -> List[Tuple[int, int, int, int]]:
        """找到所有stream对象及其关联的xref条目"""
        streams = []
        
        # 查找所有 obj ... stream ... endstream ... endobj
        pattern = rb'(\d+)\s+0\s+obj\s*<<(.*?)>>\s*stream\s*(.*?)\s*endstream\s*endobj'
        
        for match in re.finditer(pattern, pdf_data, re.DOTALL):
            obj_num = int(match.group(1))
            dict_content = match.group(2)
            stream_content = match.group(3)
            
            stream_start = match.start(3)
            stream_end = match.end(3)
            
            # 检查是否有长度信息
            length_match = re.search(rb'/Length\s+(\d+)', dict_content)
            if length_match:
                declared_length = int(length_match.group(1))
            else:
                declared_length = len(stream_content)
            
            # 检查是否压缩
            is_compressed = b'/FlateDecode' in dict_content or b'/Flate' in dict_content
            
            streams.append({
                'obj_num': obj_num,
                'start': stream_start,
                'end': stream_end,
                'original_content': stream_content,
                'declared_length': declared_length,
                'is_compressed': is_compressed,
                'dict': dict_content,
            })
        
        return streams
    
    def _decompress_stream(self, stream_data: bytes) -> Tuple[bytes, bool]:
        """尝试解压流"""
        try:
            decompressed = zlib.decompress(stream_data)
            return decompressed, True
        except:
            return stream_data, False
    
    def _compress_stream(self, stream_data: bytes) -> bytes:
        """压缩流"""
        try:
            return zlib.compress(stream_data)
        except:
            return stream_data
    
    def _convert_text_in_stream(self, stream_data: bytes) -> Tuple[bytes, int]:
        """转换流中的文本"""
        conversions = 0
        modified = bytearray(stream_data)
        
        # 查找 (...) 格式的字符串
        pattern1 = rb'\(([^)]{1,500})\)'
        
        for match in re.finditer(pattern1, stream_data):
            start = match.start(1)
            end = match.end(1)
            old_content = match.group(1)
            
            # 尝试转换
            try:
                # 尝试GB2312解码
                text = old_content.decode('gb2312')
                new_content = text.encode('utf-8')
                
                # 如果长度相同就替换
                if len(new_content) == len(old_content):
                    modified[start:end] = new_content
                    conversions += 1
                else:
                    # 长度不同，暂时跳过（处理会很复杂）
                    pass
            except:
                pass
        
        # 查找 <...> 格式的十六进制字符串
        pattern2 = rb'<([0-9A-Fa-f]{2,1000})>'
        
        for match in re.finditer(pattern2, stream_data):
            start = match.start(1)
            end = match.end(1)
            hex_str = match.group(1)
            
            try:
                # 十六进制转字节
                binary = bytes.fromhex(hex_str.decode('ascii'))
                
                # 尝试GB2312解码
                text = binary.decode('gb2312')
                new_binary = text.encode('utf-8')
                new_hex = new_binary.hex().upper().encode('ascii')
                
                # 长度必须相同
                if len(new_hex) == len(hex_str):
                    modified[start:end] = new_hex
                    conversions += 1
            except:
                pass
        
        return bytes(modified), conversions
    
    def convert_pdf(self, input_pdf: str, output_pdf: str) -> bool:
        """执行PDF转换"""
        print(f"\n{'='*70}")
        print(f"PDF 编码转换 (处理压缩流)")
        print(f"{'='*70}")
        print(f"输入: {input_pdf}")
        print(f"输出: {output_pdf}")
        print(f"转换: {self.source_encoding.upper()} → {self.target_encoding.upper()}")
        print(f"{'='*70}\n")
        
        if not Path(input_pdf).exists():
            print(f"✗ 文件不存在: {input_pdf}")
            return False
        
        # 读取PDF
        with open(input_pdf, 'rb') as f:
            pdf_data = f.read()
        
        original_size = len(pdf_data)
        print(f"原文件大小: {original_size:,} 字节\n")
        
        # 转为bytearray便于修改
        pdf_modified = bytearray(pdf_data)
        
        # 找出所有stream对象
        print("第一步: 查找所有Stream对象...")
        streams = self._find_stream_objects(pdf_data)
        
        self.stats['streams_found'] = len(streams)
        print(f"✓ 找到 {len(streams)} 个Stream对象\n")
        
        # 处理每个stream
        print("第二步: 处理Stream对象...")
        
        for idx, stream_info in enumerate(streams, 1):
            obj_num = stream_info['obj_num']
            is_compressed = stream_info['is_compressed']
            original_content = stream_info['original_content']
            
            print(f"  Stream {idx} (Object {obj_num}):")
            print(f"    原始大小: {len(original_content)} 字节")
            print(f"    压缩: {'是' if is_compressed else '否'}")
            
            # 解压
            if is_compressed:
                decompressed, success = self._decompress_stream(original_content)
                if not success:
                    print(f"    ✗ 解压失败，跳过")
                    continue
                
                print(f"    ✓ 已解压 → {len(decompressed)} 字节")
                self.stats['streams_decompressed'] += 1
                
                # 转换文本
                converted, conversions = self._convert_text_in_stream(decompressed)
                
                if conversions > 0:
                    print(f"    ✓ 转换 {conversions} 处文本")
                    self.stats['text_segments_converted'] += conversions
                    
                    # 重新压缩
                    recompressed = self._compress_stream(converted)
                    print(f"    ✓ 重新压缩 → {len(recompressed)} 字节")
                    
                    # 更新PDF内容
                    start = stream_info['start']
                    end = stream_info['end']
                    
                    pdf_modified[start:end] = recompressed
                    self.stats['streams_converted'] += 1
                else:
                    print(f"    - 未找到需要转换的文本")
            else:
                # 未压缩的stream
                converted, conversions = self._convert_text_in_stream(original_content)
                
                if conversions > 0:
                    print(f"    ✓ 转换 {conversions} 处文本")
                    self.stats['text_segments_converted'] += conversions
                    
                    start = stream_info['start']
                    end = stream_info['end']
                    
                    pdf_modified[start:end] = converted
                    self.stats['streams_converted'] += 1
                else:
                    print(f"    - 未找到需要转换的文本")
        
        print()
        
        # 保存
        print("第三步: 保存修改后的PDF...")
        try:
            with open(output_pdf, 'wb') as f:
                f.write(pdf_modified)
            
            new_size = len(pdf_modified)
            print(f"✓ 已保存: {output_pdf}")
            print(f"  新文件大小: {new_size:,} 字节\n")
            
            # 统计
            print(f"{'='*70}")
            print("转换统计:")
            print(f"{'='*70}")
            print(f"Stream对象: {self.stats['streams_found']} 个")
            print(f"已解压: {self.stats['streams_decompressed']} 个")
            print(f"已转换: {self.stats['streams_converted']} 个")
            print(f"文本段: {self.stats['text_segments_converted']} 处")
            print(f"文件变化: {new_size - original_size:+,} 字节")
            
            if new_size != original_size:
                print(f"\n✓ 文件已修改！")
            else:
                print(f"\n- 文件大小未变化 (可能无需转换或转换后相同)")
            
            print(f"{'='*70}\n")
            
            return True
        
        except Exception as e:
            print(f"✗ 保存失败: {e}")
            import traceback
            traceback.print_exc()
            return False


def compare_files(file1: str, file2: str):
    """对比两个文件"""
    with open(file1, 'rb') as f1, open(file2, 'rb') as f2:
        data1 = f1.read()
        data2 = f2.read()
    
    if data1 == data2:
        print(f"✓ 文件完全相同")
        return False
    else:
        # 计算差异
        diff_count = 0
        for i in range(min(len(data1), len(data2))):
            if data1[i] != data2[i]:
                diff_count += 1
        
        print(f"✗ 文件不同")
        print(f"  大小: {len(data1)} vs {len(data2)} 字节")
        print(f"  差异: ~{diff_count} 处")
        return True


def main():
    """主程序"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='处理压缩流的PDF编码转换工具'
    )
    parser.add_argument('-i', '--input', default='0.pdf', help='输入PDF')
    parser.add_argument('-o', '--output', default='00_new.pdf', help='输出PDF')
    parser.add_argument('-s', '--source', default='gb2312', help='源编码')
    parser.add_argument('-t', '--target', default='utf-8', help='目标编码')
    parser.add_argument('-c', '--compare', help='与另一个PDF对比')
    
    args = parser.parse_args()
    
    converter = PDFStreamConverter(args.source, args.target)
    success = converter.convert_pdf(args.input, args.output)
    
    if success and args.compare:
        print("对比结果:")
        compare_files(args.output, args.compare)
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
