# Please make sure the requests library is installed
# pip install requests
import os
import base64
import requests
import time

API_URL = ""
TOKEN = ""

file_path = "/Users/mini/Documents/py_projects/my-agent/data/picture/1.png"
input_filename = os.path.splitext(os.path.basename(file_path))[0]

with open(file_path, "rb") as file:
    file_bytes = file.read()
    file_data = base64.b64encode(file_bytes).decode("ascii")

headers = {
    "Authorization": f"token {TOKEN}",
    "Content-Type": "application/json"
}

required_payload = {
    "file": file_data,
    "fileType": 1,  # For PDF documents, set `fileType` to 0; for images, set `fileType` to 1
}

optional_payload = {
    "useDocOrientationClassify": False,
    "useDocUnwarping": False,
    "useTextlineOrientation": False,
}

payload = {**required_payload, **optional_payload}


t1 = time.perf_counter()
response = requests.post(API_URL, json=payload, headers=headers)
t2 = time.perf_counter()
print(f"take time: {t2-t1}")

assert response.status_code == 200
data = response.json()
print("Top-level keys:", list(data.keys()))
result = data.get("result")
print("Result type:", type(result))
if isinstance(result, dict):
    print("Result keys:", list(result.keys()))
    if "ocrResults" in result:
        print("ocrResults type:", type(result["ocrResults"]))
        if isinstance(result["ocrResults"], list):
            print("ocrResults length:", len(result["ocrResults"]))
            if result["ocrResults"]:
                first = result["ocrResults"][0]
                print("ocrResults[0] type:", type(first))
                if isinstance(first, dict):
                    print("ocrResults[0] keys:", list(first.keys()))
    if "rec_texts" in result:
        print("rec_texts type:", type(result["rec_texts"]))
        if isinstance(result["rec_texts"], list):
            print("rec_texts length:", len(result["rec_texts"]))

os.makedirs("output", exist_ok=True)

if isinstance(result, dict) and isinstance(result.get("ocrResults"), list):
    for i, res in enumerate(result["ocrResults"]):
        if isinstance(res, dict):
            print(res.get("prunedResult"))
            image_url = res.get("ocrImage")
            if image_url:
                img_response = requests.get(image_url)
                if img_response.status_code == 200:
                    # Save image to local
                    filename = f"output/{input_filename}_{i}.jpg"
                    with open(filename, "wb") as f:
                        f.write(img_response.content)
                    print(f"Image saved to: {filename}")
                else:
                    print(f"Failed to download image, status code: {img_response.status_code}")
elif isinstance(result, dict) and isinstance(result.get("rec_texts"), list):
    for text in result["rec_texts"]:
        print(text)
else:
    print("Unexpected result shape:", result)
