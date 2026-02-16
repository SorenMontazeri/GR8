from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

people = {"einar": 45, "alice": 7}

@app.get("/api/number/{name}")
def get_number(name: str):
    key = name.lower()
    if key not in people:
        raise HTTPException(status_code=404, detail="Name not found")
    return {"number": people[key]}  # <-- bara svaret
