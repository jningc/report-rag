

'''
切分
输入: list[dict],每个元素是{"source": "文件名.pdf", "page": 1, "text": "..."}
输出: list[dict],每个元素是{"source": "文件名.pdf", "page": 1, "text": "..."}
切分规则:
1. 每页切分为1000字符的段落
'''