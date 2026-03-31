import json
import httpx
import os
from dotenv import load_dotenv
try:
    from .utils import *
except ImportError:
    from utils import *


class LLMClientSync:
    """
    Synchronous client for sending multimodal requests to a chat-completions API.

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
        Initialize the synchronous LLM client.

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

        self.client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    def query(self, prompt, base64image):
        """
        Send a generic multimodal query containing text plus one base64-encoded image.

        The image is sent as a data URL with MIME type `image/jpeg`.

        Args:
            prompt (str): User prompt to send to the model.
            base64image (str): Base64-encoded image content.

        Returns:
            dict: Raw JSON response returned by the LLM endpoint.

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
            response = self.client.post(self.endpoint, json=body)
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

    def query_description_closed(self, base64image, descriptors, image_mime="image/jpeg"):
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
            response = self.client.post(self.endpoint, json=body)
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

    def query_description_open(self, base64image, image_mime="image/jpeg"):
        """
        Analyze an image and return a rich structured description.

        This method asks the model to produce JSON matching a schema with:
        - keywords
        - scene tags
        - objects
        - high-level events with confidence scores
        - per-person descriptions including inferred role, actions, held objects, and clothing
        - a concise natural-language description

        Args:
            base64image (str): Base64-encoded image content.
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
                                "Analyze the provided base64 image and return a structured description.\n\n"
                                "Return ONLY JSON that matches the schema.\n\n"
                                "Guidelines:\n"
                                "- keywords: short searchable terms associated with the image.\n"
                                "- scene: environment/context terms (e.g., 'indoors', 'outdoors', 'street', 'store', 'night', 'day' etc).\n"
                                "- objects: concrete things (objecs) visible in the image.\n"
                                "- events: ONLY high-level situations (e.g., 'birthday party', 'robbery', 'car accident' etc).\n"
                                "  Include a confidence score per event.\n"
                                "- people: create one entry per visible person.\n"
                                "  - person_id: short id like 'p1', 'p2'.\n"
                                "  - role: free-text role label you infer (e.g., civilian, police officer, shopkeeper).\n"
                                "    If unclear/uncertain, set role to 'unknown'.\n"
                                "  - role_confidence: number from 0 to 1.\n"
                                "  - actions: ONLY human actions/behaviors (verbs/phrases like 'walking', 'running', 'sneaking', 'looking around' etc).\n"
                                "    Do NOT include worn/carried items as actions (e.g., NOT 'wearing backpack').\n"
                                "  - held_objects: objects the person is holding.\n"
                                "  - clothing: list EVERY worn clothing item (including accessories such as glasses, backpack, purse etc) with primary color and any secondary colors.\n"
                                "- description: concise natural-language summary of the whole image.\n"
                                "- Use empty arrays if none are applicable.\n"
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
                    "name": "open_image_description_people_v2",
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "keywords": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 0,
                                "uniqueItems": True,
                            },
                            "scene": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 0,
                                "uniqueItems": True,
                            },
                            "objects": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 0,
                                "uniqueItems": True,
                            },
                            "events": {
                                "type": "array",
                                "minItems": 0,
                                "uniqueItems": True,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "label": {"type": "string"},
                                        "confidence": {
                                            "type": "number",
                                            "minimum": 0.0,
                                            "maximum": 1.0,
                                        },
                                    },
                                    "required": ["label", "confidence"],
                                },
                            },
                            "people": {
                                "type": "array",
                                "minItems": 0,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "person_id": {"type": "string"},
                                        "role": {"type": "string"},
                                        "role_confidence": {
                                            "type": "number",
                                            "minimum": 0.0,
                                            "maximum": 1.0,
                                        },
                                        "actions": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "minItems": 0,
                                            "uniqueItems": True,
                                        },
                                        "held_objects": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "minItems": 0,
                                            "uniqueItems": True,
                                        },
                                        "clothing": {
                                            "type": "array",
                                            "minItems": 0,
                                            "items": {
                                                "type": "object",
                                                "additionalProperties": False,
                                                "properties": {
                                                    "item": {"type": "string"},
                                                    "color": {"type": "string"},
                                                    "secondary_colors": {
                                                        "type": "array",
                                                        "items": {"type": "string"},
                                                        "minItems": 0,
                                                        "uniqueItems": True,
                                                    },
                                                    "attributes": {
                                                        "type": "array",
                                                        "items": {"type": "string"},
                                                        "minItems": 0,
                                                        "uniqueItems": True,
                                                    },
                                                },
                                                "required": ["item", "color", "secondary_colors"],
                                            },
                                        },
                                    },
                                    "required": [
                                        "person_id",
                                        "role",
                                        "role_confidence",
                                        "actions",
                                        "held_objects",
                                        "clothing",
                                    ],
                                },
                            },
                            "description": {"type": "string", "minLength": 1},
                        },
                        "required": ["keywords", "scene", "objects", "events", "people", "description"],
                    },
                },
            },
        }

        try:
            response = self.client.post(self.endpoint, json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"HTTP error {exc.response.status_code} from LLM endpoint"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Request to LLM endpoint failed: {exc}") from exc

        try:
            return parse_llm_response(response.json())
        except json.JSONDecodeError as exc:
            raise ValueError("LLM endpoint returned invalid JSON") from exc
        
    def query_description_sequence(self, base64image, image_mime="image/jpeg"):
        pass



    def close(self):
        """
        Close the underlying HTTP client.

        This should be called when the instance is no longer needed
        to release network resources cleanly.
        """
        self.client.close()

def test_sync():
    load_dotenv()
    endpoint = "https://api.ai.auth.axis.cloud/v1/chat/completions"
    api_key = os.environ.get("FACADE_API_KEY")
    model = "prisma_gemini_pro"
    descriptors = ["thief", "civilian", "human", "dog", "cat", "rat", "dark_clothed", "light_clothed"]

    llm = LLMClientSync(endpoint, api_key, model)
    image = "test.webp"
    base64_image = encode_image_to_base64(image)


    response1 = llm.query_description_closed(base64_image, descriptors, image_mime="image/webp" )
    print(response1["keywords"])
    response2 = llm.query_description_open(base64_image, image_mime="image/webp" )

    with open("test1.json", "w", encoding="utf-8") as f:
        json.dump(response1, f, indent=2, ensure_ascii=False)

    with open("test2.json", "w", encoding="utf-8") as f:
        json.dump(response2, f, indent=2, ensure_ascii=False)


    llm.close()

def test_base():
    print("test")
    image = "test.webp"
    base64_image = encode_image_to_base64(image)
    print(base64_image)



if __name__ == "__main__":
    test_sync()
