#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PDF GB2312→UTF-8 编码转换综合工具
提供3种不同的转换方案
"""

import sys
import os
from pathlib import Path

def show_menu():
    """显示菜单"""
    print(f"\n{'='*70}")
    print("PDF 编码转换工具 - GB2312 → UTF-8")
    print(f"{'='*70}\n")
    
    print("请选择转换方案:\n")
    print("1️⃣  二进制级别转换 (推荐)")
    print("   - 方法: 直接修改PDF二进制中的文本编码")
    print("   - 优点: 保留原始PDF结构，文件小，快速")
    print("   - 缺点: 只能转换已检测到的编码文本")
    print("   - 输出: 00.pdf (~7KB)")
    print()
    
    print("2️⃣  文本提取重建转换")
    print("   - 方法: 提取文本后用新编码重建PDF")
    print("   - 优点: 确保完整转换，兼容性最好")
    print("   - 缺点: 文件较大，可能改变排版")
    print("   - 输出: 00_rebuilt.pdf (~50KB)")
    print()
    
    print("3️⃣  查看比较")
    print("   - 查看现有的所有转换结果")
    print()
    
    print("4️⃣  退出")
    print()


def run_binary_conversion(input_file='0.pdf', output_file='00.pdf'):
    """运行二进制转换"""
    print(f"\n执行二进制级别转换: {input_file} → {output_file}\n")
    
    cmd = f".venv/bin/python pdf_advanced_binary.py -i {input_file} -o {output_file}"
    exit_code = os.system(cmd)
    
    if exit_code == 0:
        print(f"\n✓ 转换成功！已生成: {output_file}")
        return True
    else:
        print(f"\n✗ 转换失败")
        return False


def run_text_rebuild(input_file='0.pdf', output_file='00_rebuilt.pdf'):
    """运行文本重建转换"""
    print(f"\n执行文本提取重建转换: {input_file} → {output_file}\n")
    
    cmd = f".venv/bin/python pdf_encoding_converter.py -i {input_file} -o {output_file}"
    exit_code = os.system(cmd)
    
    if exit_code == 0:
        print(f"\n✓ 转换成功！已生成: {output_file}")
        return True
    else:
        print(f"\n✗ 转换失败")
        return False


def show_results():
    """显示结果对比"""
    print(f"\n{'='*70}")
    print("现有转换结果")
    print(f"{'='*70}\n")
    
    files = [
        ('0.pdf', '原始PDF (GB2312编码)'),
        ('00.pdf', '高级二进制转换结果'),
        ('00_advanced.pdf', '二进制转换测试版本'),
        ('00_rebuilt.pdf', '文本重建转换结果'),
    ]
    
    results = []
    for filename, description in files:
        if os.path.exists(filename):
            size = os.path.getsize(filename)
            results.append((filename, description, size))
            print(f"✓ {filename}")
            print(f"  {description}")
            print(f"  大小: {size:,} 字节 ({size/1024:.1f} KB)")
            print()
        else:
            print(f"✗ {filename}")
            print(f"  {description}")
            print(f"  (文件不存在)")
            print()
    
    return results


def show_encoding_info(pdf_file='0.pdf'):
    """显示PDF编码信息"""
    print(f"\n{'='*70}")
    print(f"PDF 编码分析: {pdf_file}")
    print(f"{'='*70}\n")
    
    if not os.path.exists(pdf_file):
        print(f"✗ 文件不存在: {pdf_file}")
        return
    
    cmd = f".venv/bin/python pdf_binary_converter.py -v -i {pdf_file}"
    os.system(cmd)


def interactive_mode():
    """交互模式"""
    while True:
        show_menu()
        choice = input("请输入选择 (1-4): ").strip()
        
        if choice == '1':
            run_binary_conversion()
            input("\n按Enter继续...")
        
        elif choice == '2':
            run_text_rebuild()
            input("\n按Enter继续...")
        
        elif choice == '3':
            show_results()
            show_encoding_info()
            input("\n按Enter继续...")
        
        elif choice == '4':
            print("\n再见！")
            break
        
        else:
            print("\n✗ 无效的选择，请重试")
            input("\n按Enter继续...")


def quick_convert(method='binary'):
    """快速转换"""
    if method == 'binary':
        return run_binary_conversion()
    elif method == 'text':
        return run_text_rebuild()
    else:
        return False


def main():
    """主程序"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='PDF编码转换综合工具 (GB2312→UTF-8)'
    )
    parser.add_argument('-m', '--method', 
                       choices=['binary', 'text', 'interactive'],
                       default='interactive',
                       help='转换方法')
    parser.add_argument('-i', '--input', default='0.pdf', help='输入文件')
    parser.add_argument('-o', '--output', help='输出文件')
    parser.add_argument('--info', action='store_true', help='显示编码信息')
    parser.add_argument('--results', action='store_true', help='显示结果对比')
    
    args = parser.parse_args()
    
    # 显示信息
    if args.info:
        show_encoding_info(args.input)
        return 0
    
    # 显示结果
    if args.results:
        show_results()
        return 0
    
    # 快速转换
    if args.method == 'binary':
        output = args.output or '00.pdf'
        success = quick_convert('binary')
        return 0 if success else 1
    
    elif args.method == 'text':
        output = args.output or '00_rebuilt.pdf'
        success = quick_convert('text')
        return 0 if success else 1
    
    # 交互模式
    else:
        interactive_mode()
        return 0


if __name__ == '__main__':
    sys.exit(main())
