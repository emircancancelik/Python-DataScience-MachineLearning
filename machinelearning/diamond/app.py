from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
import pickle
import pandas as pd
from pydantic import BaseModel


app = FastAPI()

with open("diamond_model_complete.pkl", "rb") as f:
    saved_data = pickle.load(f)
    model = saved_data["model"]
    encoders = saved_data["encoders"]
    scaler = saved_data["scaler"]



class DiamondFeatures(BaseModel):
    carat: float
    cut: str
    color: str
    clarity: str
    depth: float
    table: float
    x: float
    y: float
    z: float


@app.post("/predict")
async def predict(features: DiamondFeatures):
    input_data = pd.DataFrame([features.model_dump()])

    try:
        for col in ["cut", "color", "clarity"]:
            input_data[col] = encoders[col].transform(input_data[col])
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid value for category field: {exc}"
        ) from exc

    input_scaled = scaler.transform(input_data)
    prediction = model.predict(input_scaled)

    return {"predicted_price": float(prediction[0])}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(content=html)