from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Calculatrice")


class Operandes(BaseModel):
    a: float
    b: float


def calculate(a: float, b: float, op: str) -> float:
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            raise ValueError("Division par zéro")
        return a / b
    raise ValueError("Opérateur invalide. Utiliser +, -, *, /")


def executer(op: str, donnees: Operandes) -> dict:
    try:
        return {"result": calculate(donnees.a, donnees.b, op)}
    except ValueError as erreur:
        raise HTTPException(status_code=400, detail=str(erreur)) from erreur


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/add")
def add(donnees: Operandes) -> dict:
    return executer("+", donnees)


@app.post("/subtract")
def subtract(donnees: Operandes) -> dict:
    return executer("-", donnees)


@app.post("/multiply")
def multiply(donnees: Operandes) -> dict:
    return executer("*", donnees)


@app.post("/divide")
def divide(donnees: Operandes) -> dict:
    return executer("/", donnees)
