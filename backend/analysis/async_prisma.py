import json
import httpx
import asyncio
import os
from dotenv import load_dotenv
from utils import *


class LLMClient:
    """
    Asynchronous client for sending multimodal requests to a chat-completions API.

    This client supports:
    - generic prompt + image queries
    - closed-set image classification using a fixed descriptor list
    - open-ended structured image description with a JSON schema

    Parameters:
        endpoint (str): Full URL to the chat completions endpoint.
        api_key (str): Bearer token used for authentication.
        model (str): Model identifier sent in the request body.
        timeout (float, optional): HTTP timeout in seconds. Defaults to 30.0.

    Raises:
        ValueError: If endpoint, api_key, or model is missing.
    """

    def __init__(self, endpoint, api_key, model, timeout=30.0):
        """
        Initialize the asynchronous LLM client.

        Args:
            endpoint (str): API endpoint URL.
            api_key (str): Authentication token.
            model (str): Model name to use for inference.
            timeout (float, optional): Request timeout in seconds.

        Raises:
            ValueError: If any required constructor argument is empty or missing.
        """
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

    async def query_description_closed(self, base64image, descriptors, image_mime="image/jpeg"):
        print("sending")
        """
        Analyze an image and return only keywords chosen from a fixed descriptor list.

        This method requests a strict JSON-schema response with the shape:
            {
                "keywords": [...]
            }

        The model is instructed to:
        - choose only from the supplied `descriptors`
        - return an empty list if nothing applies
        - avoid any additional fields

        Args:
            base64image (str): Base64-encoded image content.
            descriptors (list[str]): Allowed descriptor labels.
            image_mime (str, optional): MIME type of the encoded image.
                Defaults to "image/jpeg".

        Returns:
            dict: Parsed structured response, typically produced by `parse_llm_response`.

        Raises:
            RuntimeError: If the HTTP request fails or the endpoint returns an error status.
            ValueError: If the endpoint returns invalid JSON.
        """
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Analyze the provided base64 image and return keywords using ONLY the allowed descriptors.\n\n"
                                f"Allowed descriptors:\n{descriptors}\n\n"
                                "Rules:\n"
                                "- Only choose from Allowed descriptors.\n"
                                "- If none apply or if you don't see an image, return an empty list.\n"
                                "- Return ONLY JSON that matches the schema.\n"
                                "- Do not include extra fields."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{image_mime};base64,{base64image}"},
                        },
                    ],
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "closed_image_keywords",
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "keywords": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": descriptors,
                                },
                                "minItems": 0,
                                "uniqueItems": True,
                            }
                        },
                        "required": ["keywords"],
                    },
                },
            },
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
            print("sent")
            return parse_llm_response(response.json())
        except json.JSONDecodeError as exc:
            raise ValueError("LLM endpoint returned invalid JSON") from exc

    async def query_description_open(self, base64images, image_mime="image/jpeg", sequence=False):
        """
        Analyze one or more images and return a concise natural-language description.

        This method sends one or more images in a single request and requests a strict
        JSON-schema response with the shape:
            {
                "description": "..."
            }

        The model is instructed to:
        - describe what happens in the image when `sequence` is False
        - describe what happens across the image sequence when `sequence` is True
        - avoid any additional fields

        Args:
            base64images (list[str]): List of base64-encoded image contents.
            image_mime (str, optional): MIME type of the encoded images.
                Defaults to "image/jpeg".
            sequence (bool, optional): Whether to interpret `base64images` as an
                ordered sequence. Defaults to False.

        Returns:
            dict: Parsed structured response, typically produced by `parse_llm_response`.

        Raises:
            RuntimeError: If the HTTP request fails or the endpoint returns an error status.
            ValueError: If the endpoint returns invalid JSON or `base64images` is empty.
        """
        print("sending")
        if not base64images or len(base64images) == 0:
            raise ValueError("base64images list cannot be empty")

        # Build content array with all images
        if sequence == False:
             content = [
                {
                    "type": "text",
                    "text": (
                        "Analyze the provided image and return a concise natural-language description of what happens in the image.\n\n"
                        "Return ONLY JSON that matches the schema.\n"
                        "Do not include extra fields."
                    ),
                }
            ]
        else:  
            content = [
                {
                    "type": "text",
                    "text": (
                        "Analyze the provided sequence of images and return a concise natural-language description of what happens across the sequence.\n\n"
                        "Return ONLY JSON that matches the schema.\n"
                        "Do not include extra fields."
                    ),
                }
            ]

        # Add all images to the content
        for base64_image in base64images:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{image_mime};base64,{base64_image}"},
            })

        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "sequence_description_simple",
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "description": {"type": "string", "minLength": 1},
                        },
                        "required": ["description"],
                    },
                },
            },
        }

        try:
            response = await self.client.post(self.endpoint, json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            error_body = exc.response.text
            print(f"Error body: {error_body}")
            raise RuntimeError(
                f"HTTP error {exc.response.status_code} from LLM endpoint: {error_body}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Request to LLM endpoint failed: {exc}") from exc

        try:
            print("sent")
            return parse_llm_response(response.json())
        except json.JSONDecodeError as exc:
            raise ValueError("LLM endpoint returned invalid JSON") from exc

    async def close(self):
        """
        Close the underlying async HTTP client.

        This should be called when the instance is no longer needed
        to release network resources cleanly.
        """
        await self.client.aclose()


async def test_async():

    load_dotenv()
    endpoint = "https://api.ai.auth.axis.cloud/v1/chat/completions"
    api_key = os.environ.get("FACADE_API_KEY")
    model = "prisma_gemini_pro"
    descriptors = ["thief", "civilian", "human", "dog", "cat", "rat", "dark_clothed", "light_clothed"]

    llm = LLMClient(endpoint, api_key, model)
    image = "test.webp"
    base64_image = encode_image_to_base64(image)

    response1 = await llm.query_description_closed(
        base64_image, descriptors, image_mime="image/webp"
    )
    response2 = await llm.query_description_open(
        [base64_image], image_mime="image/webp"
    )

    with open("test1.json", "w", encoding="utf-8") as f:
        json.dump(response1, f, indent=2, ensure_ascii=False)

    with open("test2.json", "w", encoding="utf-8") as f:
        json.dump(response2, f, indent=2, ensure_ascii=False)

    await llm.close()


async def test_async_base():
    load_dotenv()
    endpoint = "https://api.ai.auth.axis.cloud/v1/chat/completions"
    api_key = os.environ.get("FACADE_API_KEY")
    model = "prisma_gemini"

    llm = LLMClient(endpoint, api_key, model)
    image = "test.webp"
    base64_image = encode_image_to_base64(image)

    response = await llm.query_description_open(
        [base64_image], image_mime="image/webp"
    )

    with open("response.json", "w", encoding="utf-8") as f:
        json.dump(response, f, indent=2, ensure_ascii=False)

    await llm.close()


if __name__ == "__main__":
    asyncio.run(test_async())
