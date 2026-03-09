# Image Analysis Module

This module provides an interface for analyzing images using a multimodal LLM through a chat-completions API. It supports both synchronous and asynchronous clients and returns structured JSON descriptions of image content.


# Overview

The module sends base64 encoded images to a multimodal model and requests structured outputs using JSON schemas.

Two types of analysis are supported:

## 1. Closed-set classification

The model selects keywords only from a predefined descriptor list.

Example output:

```json
{
  "keywords": ["human", "dark_clothed"]
}
```

## 2. Open structured description

The model generates a detailed structured representation of the scene.

Example fields:

- keywords
- scene context
- objects
- high-level events
- people descriptions
- clothing attributes
- actions
- natural language summary

Example output:

```json
{
  "keywords": ["store", "person"],
  "scene": ["indoors"],
  "objects": ["shelf", "door"],
  "events": [
    { "label": "shopping", "confidence": 0.84 }
  ],
  "people": [
    {
      "person_id": "p1",
      "role": "civilian",
      "role_confidence": 0.72,
      "actions": ["walking"],
      "held_objects": ["bag"],
      "clothing": [
        {
          "item": "jacket",
          "color": "black",
          "secondary_colors": []
        }
      ]
    }
  ],
  "description": "A person walking inside a store carrying a bag."
}
```

---

# Requirements

Before running the module, create and activate a Python virtual environment and install the required packages.

## 1. Create a virtual environment

```bash
python -m venv venv
```

## 2. Activate the environment

Linux / Mac:

```bash
source venv/bin/activate
```

Windows:

```bash
venv\Scripts\activate
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```



# Environment Setup

Create a `.env` file in the project root.

```
FACADE_API_KEY=your_api_key_here
```

The API key is required to access the Axis AI endpoint.


# How It Works

## Step 1 — Image Encoding

Images are converted to base64 before being sent to the API.

```
image → base64 → API request
```

Handled by:

```
encode_image_to_base64()
```

in `utils.py`.



## Step 2 — Request 

The makes a request containing:

- text instructions
- the base64 image
- a JSON schema defining the expected output

Example request structure:

```json
{
  "model": "...",
  "messages": [
    "text instruction",
    "image payload"
  ],
  "response_format": "json_schema"
}
```


## Step 3 — Model Processing

The LLM analyzes the image and returns structured JSON matching the schema.

---

## Step 4 — Response Parsing

Responses are processed by:

```
parse_llm_response()
```

which extracts the structured data.