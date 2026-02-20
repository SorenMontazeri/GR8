import json
import httpx
import asyncio
import os
from dotenv import load_dotenv


#a
class LLMClient:
    def __init__(self, endpoint, api_key, model, timeout=30.0):
        if not endpoint:
            raise ValueError("endpoint is required")
        if not api_key:
            raise ValueError("api_key is required")
        if not model:
            raise ValueError("model is required")

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

        try:
            response = await self.client.post(self.endpoint, json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"HTTP error {exc.response.status_code} from LLM endpoint"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Request to LLM endpoint failed: {exc}") from exc

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise ValueError("LLM endpoint returned invalid JSON") from exc


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
