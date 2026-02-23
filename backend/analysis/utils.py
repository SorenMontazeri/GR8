import base64
import json

def encode_image_to_base64(path: str) -> str: #path
    with open(path, "rb") as file:
        return base64.b64encode(file.read()).decode("utf-8")
    

def encode_bytes_to_base64(jpeg_bytes: bytes) -> str: #raw bytes
    return base64.b64encode(jpeg_bytes).decode("utf-8")


def parse_llm_response(response: dict) -> dict:
    
    content = response["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    
    return parsed