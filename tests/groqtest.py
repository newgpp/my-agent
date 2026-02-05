import os
from groq import Groq

# 确保将 "YOUR_API_KEY_HERE" 替换为您在 Groq 控制台生成的实际密钥
client = Groq(
    api_key="" 
)

# 直接指定完整路径
filename = "/home/ff/Documents/github/my-agent/data/voice/1.m4a"

with open(filename, "rb") as file:
    transcription = client.audio.transcriptions.create(
      file=(filename, file.read()),
      model="whisper-large-v3-turbo",
      temperature=0,
      response_format="verbose_json",
    )
    print(transcription.text)
