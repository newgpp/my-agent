import httpx
from groq import Groq

# 1. 配置你的代理地址 (请确保你的代理软件已开启并支持 HTTP/HTTPS)
# 常见的本地代理端口通常是 7890 (Clash), 1080 (V2Ray) 等
PROXY_URL = "http://127.0.0.1:7890"

# 2. 初始化带代理的 httpx 客户端
client_with_proxy = httpx.Client(
    proxies={
        "http://": PROXY_URL,
        "https://": PROXY_URL,
    }
)

# 3. 初始化 Groq 客户端，并注入自定义的 http_client
client = Groq(
    api_key="",
    http_client=client_with_proxy
)

def transcribe_audio(file_path):
    with open(file_path, "rb") as file:
        transcription = client.audio.transcriptions.create(
            file=(file_path, file.read()), # 文件名及二进制内容
            model="whisper-large-v3",      # 目前 Groq 最强的 ASR 模型
            response_format="json",        # 可选 "json", "verbose_json", "text"
            language="zh",                 # 强制指定中文识别可提高准确率
            temperature=0.0                # 0 获得最稳定的结果
        )
        return transcription

# 运行测试
try:
    result = transcribe_audio("/home/ff/Documents/github/my-agent/data/voice/1.m4a")
    print("识别结果：", result)
except Exception as e:
    print(f"调用失败，请检查代理是否连通: {e}")
