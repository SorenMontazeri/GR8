import json
import httpx
import asyncio
import os
from dotenv import load_dotenv

class LLMClient:
    def __init__(self, endpoint, api_key, model, timeout=30.0):
        self.endpoint = endpoint
        self.model = model

        # Create one reusable async HTTP client
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def query(self, metadata):
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(metadata, ensure_ascii=False), # Essentially stringify
                        }
                    ],
                }
            ],
        }

        response = await self.client.post(self.endpoint, json=body)
        return response.json()

    async def close(self):
        await self.client.aclose()


async def test():
        load_dotenv()
        endpoint = "https://api.ai.auth.axis.cloud/v1/chat/completions"
        api_key = os.environ.get("FACADE_API_KEY") 
        model = "prisma_gemini_pro"
        llm = LLMClient(endpoint, api_key, model)
        metadata = {"prompt": "explain what you see in the image"}
        response = await llm.query(metadata)

        with open("response.json", "w", encoding="utf-8") as f:
            json.dump(response, f, indent=2, ensure_ascii=False)    
        await llm.close()

if __name__ == "__main__":
    asyncio.run(test())