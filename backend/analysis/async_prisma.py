import json
import httpx
import asyncio
import os
from dotenv import load_dotenv

class LLMClient:
    def __init__(self, endpoint, api_key, model, timeout=30.0):
        self.endpoint = endpoint
        self.model = model

        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def query(self, prompt, base64image):
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64image}"
                            }
                        }
                    ]
                }
            ]
        }

        response = await self.client.post(self.endpoint, json=body)
        response.raise_for_status()
        return response.json()


    async def close(self):
        await self.client.aclose()


async def test():
        load_dotenv()
        endpoint = "https://api.ai.auth.axis.cloud/v1/chat/completions"
        api_key = os.environ.get("FACADE_API_KEY") 
        model = "prisma_gemini"
        llm = LLMClient(endpoint, api_key, model)
        image = "pass"

        response = await llm.query(
            "Explain what color you see in the image. If you see nothing, say so.",
            image
            )


        with open("response.json", "w", encoding="utf-8") as f:
            json.dump(response, f, indent=2, ensure_ascii=False)    
        await llm.close()

if __name__ == "__main__":
    asyncio.run(test())