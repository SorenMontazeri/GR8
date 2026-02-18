import json
import httpx
import os
from dotenv import load_dotenv
class LLMClientSync:
    def __init__(self, endpoint, api_key, model, timeout=30.0):
        self.endpoint = endpoint
        self.model = model

        self.client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    def query(self, metadata):
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(metadata, ensure_ascii=False),
                        }
                    ],
                }
            ],
        }

        response = self.client.post(self.endpoint, json=body)
        return response.json()

    def close(self):
        self.client.close()


def test_sync():
    load_dotenv()
    endpoint = "https://api.ai.auth.axis.cloud/v1/chat/completions"
    api_key = os.environ.get("FACADE_API_KEY")
    model = "prisma_gemini_pro"

    llm = LLMClientSync(endpoint, api_key, model)
    metadata = {"prompt": "explain what you see in the image"}
    response = llm.query(metadata)

    with open("response_sync.json", "w", encoding="utf-8") as f:
        json.dump(response, f, indent=2, ensure_ascii=False)

    llm.close()

if __name__ == "__main__":
    test_sync()
