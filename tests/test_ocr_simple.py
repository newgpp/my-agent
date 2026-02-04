import os
import warnings
from paddleocr import PaddleOCR

# 必留环境变量
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
warnings.filterwarnings('ignore')

# 初始化OCR（稳定版参数）
ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
# 替换成你图片目录下的「单张小图片路径」，比如截图的png
img_path = "/Users/mini/Documents/py_projects/my-agent/data/picture/1.png"
# 单张图片识别
result = ocr.ocr(img_path, cls=True)
# 打印结果
for idx, line in enumerate(result[0], 1):
    text, score = line[1]
    print(f"第{idx}行：{text} | 置信度：{score:.2f}")
print("✅ 单张图片识别成功！")