from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import shutil
from utils import extract_text_from_pdf  # Assumes you already have this
import requests
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Persistent knowledge base
knowledge_base_file = Path("knowledge_base.txt")
knowledge_base_file.touch(exist_ok=True)

def load_knowledge_base():
    return knowledge_base_file.read_text(encoding="utf-8")


def save_to_knowledge_base(text: str):
    with open(knowledge_base_file, "a", encoding="utf-8") as f:
        f.write(text + "\n")


@app.on_event("startup")
async def load_documents_on_startup():
    """Index all previously uploaded PDFs into knowledge base."""
    for file_path in UPLOAD_DIR.glob("*.pdf"):
        try:
            text = extract_text_from_pdf(str(file_path))
            save_to_knowledge_base(text)
        except Exception as e:
            print(f"Failed to process {file_path.name}: {e}")

@app.post("/upload/")
async def upload_pdf(file: UploadFile = File(...)):
    file_path = UPLOAD_DIR / file.filename

    # Save the uploaded file
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Extract text and add to knowledge base
    try:
        text = extract_text_from_pdf(str(file_path))
        save_to_knowledge_base(text)
    except Exception as e:
        return {"message": f"File saved but failed to process PDF: {e}"}

    return {"message": f"{file.filename} uploaded and indexed successfully."}

@app.post("/ask/")
async def ask_question(question: str = Form(...)):
    knowledge_base = load_knowledge_base()

    if not knowledge_base.strip():
        return {"answer": "The knowledge base is empty. Please upload a document first."}

    # Limit prompt size to avoid model overload
    truncated_context = knowledge_base[-3000:]

    prompt = f"""You are a helpful teacher assistant. Use the following knowledge base to answer the question.

Context:
{truncated_context}

Question: {question}
Answer:"""

    try:
        response = requests.post(
            "http://localhost:8080/completion",
            json={
                "prompt": prompt,
                "temperature": 0.7,
                "max_tokens": 1024,
                "stop": ["\n"]
            },
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        # Log for debugging
        print("🤖 MODEL RESPONSE:", result)

        # Check for different keys if 'content' is empty
        answer = (
            result.get("content") or
            result.get("text") or
            "Sorry, I couldn't find an answer."
        )

        return {"answer": answer.strip()}
    except Exception as e:
        print("❌ Error talking to LLaMA server:", e)
        return {"answer": "There was an error communicating with the AI model."}



@app.get("/uploaded_files/")
async def get_uploaded_files():
    files = [f.name for f in UPLOAD_DIR.glob("*.pdf")]
    return {"files": files}

# Mount the "uploads" folder at the /files URL path
app.mount("/files", StaticFiles(directory="uploads"), name="files")


@app.post("/generate_question/")
async def generate_question():
    knowledge_base = load_knowledge_base()

    if not knowledge_base.strip():
        return {"question": "The knowledge base is empty. Please upload a document first."}

    truncated_context = knowledge_base[-3000:]

    prompt = f"""You are a helpful assistant that generates quiz-style questions. Based on the following content, generate one clear and relevant question to test understanding.

Content:
{truncated_context}

Question:"""

    try:
        response = requests.post(
            "http://localhost:8080/completion",
            json={
                "prompt": prompt,
                "temperature": 0.7,
                "max_tokens": 100,
                "stop": ["\n"]
            },
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        question = (
        result.get("content") or
        result.get("text") or
        result.get("response") or
        "No question could be generated."
)

        return {"question": question.strip()}
    except Exception as e:
        print("❌ Error generating question:", e)
        return {"question": "There was an error generating a question."}


user_answers = []

@app.post("/submit_answer/")
async def submit_answer(question: str = Form(...), answer: str = Form(...)):
    print("✅ Received answer:")
    print("Q:", question)
    print("A:", answer)
    user_answers.append({"question": question, "answer": answer})
    return {"status": "saved"}

@app.post("/evaluate_answer/")
async def evaluate_answer(
    question: str = Form(...),
    answer: str = Form(...)
):
    knowledge_base = load_knowledge_base()
    prompt = f"""You are a teacher assistant. Given the question and the user's answer, evaluate their response based on the content provided below.

Knowledge Base:
{knowledge_base[-3000:]}

Question: {question}
User's Answer: {answer}

Evaluation (be kind and helpful):"""

    try:
        response = requests.post(
            "http://localhost:8080/completion",
            json={
                "prompt": prompt,
                "temperature": 0.7,
                "max_tokens": 150,
                "stop": ["\n"]
            },
            timeout=30
        )
        result = response.json()
        print("🧠 Evaluation response:", result)

        evaluation = (
            result.get("content") or
            result.get("text") or
            "Couldn't evaluate the answer."
        )

        return {"evaluation": evaluation.strip()}
    except Exception as e:
        print("❌ Evaluation error:", e)
        return {"evaluation": "Sorry, I had trouble evaluating the answer."}
