from fastapi import FastAPI

app = FastAPI(title="Amorim CRM API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
