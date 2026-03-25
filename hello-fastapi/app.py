from fastapi import FastAPI

app = FastAPI(title="InstaVM Hello FastAPI")


@app.get("/")
def index() -> dict[str, str]:
    return {"message": "Hello from InstaVM cookbooks"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
