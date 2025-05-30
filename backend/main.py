from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import shutil
import requests
import os
import docx2txt
from utils import extract_text_from_pdf  # Make sure this exists
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
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

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

# Serve uploaded files
app.mount("/files", StaticFiles(directory="uploads"), name="files")



@app.post("/generate_question/")
async def generate_question():
    knowledge_base = load_knowledge_base()

    if not knowledge_base.strip():
        return {"question": "The knowledge base is empty. Please upload a document first."}

    truncated_context = knowledge_base[-2000:]  # Use last 2000 characters for relevance

    prompt = f"""
You are a helpful AI that generates quiz questions from text.

Your task: From the content below, generate **only one short, clear question** (max 12 words). 
⚠️ Do NOT include answers, explanations, or extra text. 
Return only the question on a single line.

Context:
{truncated_context}

Question:"""

    try:
        response = requests.post(
            "http://localhost:8080/completion",
            json={
                "prompt": prompt.strip(),
                "temperature": 0.2,
                "max_tokens": 40,
                "stop": ["\n", "</s>", "Answer:", "Explanation:"]
            },
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        raw_output = (
            result.get("content") or
            result.get("text") or
            result.get("response") or
            ""
        ).strip()

        # Clean up output: remove accidental answers
        lines = raw_output.splitlines()
        question_line = lines[0].strip() if lines else ""

        # Extra filter: remove answer fragments
        if "answer" in question_line.lower() or "correct" in question_line.lower():
            return {"question": "Only a question is expected from the document, but the response contained an answer."}

        return {"question": question_line}
    except Exception as e:
        print("❌ Error generating question:", e)
        return {"question": "There was an error generating a question from the document."}





user_answers = []

@app.post("/submit_answer/")
async def submit_answer(question: str = Form(...), answer: str = Form(...)):
    user_answers.append({"question": question, "answer": answer})
    return {"status": "saved"}

@app.post("/evaluate_answer/")
async def evaluate_answer(
    question: str = Form(...),
    answer: str = Form(...)
):
    knowledge_base = load_knowledge_base()
    prompt = f"""
You are a helpful and professional teacher AI. Review the student's answer to the question based on the given context.

Context (from uploaded document):
{knowledge_base[-3000:]}

Question: {question}
Student's Answer: {answer}

Give detailed feedback:
- Start with whether the answer is correct, partially correct, or incorrect.
- Explain why in simple terms.
- Refer to relevant parts of the context if needed.
Avoid repeating "The student's response".
"""


    try:
        response = requests.post(
            "http://localhost:8080/completion",
            json={
                "prompt": prompt,
                "temperature": 0.7,
                "max_tokens": 150,
                 "stop": ["</s>", "\n\n"]
            },
            timeout=30
        )
        result = response.json()
        evaluation = (
            result.get("content") or
            result.get("text") or
            "Couldn't evaluate the answer."
        )

        return {"evaluation": evaluation.strip()}
    except Exception as e:
        print("❌ Evaluation error:", e)
        return {"evaluation": "Sorry, I had trouble evaluating the answer."}
    
    

@app.post("/evaluate_exam_sheet/")
async def evaluate_exam_sheet(file: UploadFile = File(...)):
    import tempfile

    ext = Path(file.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        if ext == '.pdf':
            text = extract_text_from_pdf(tmp_path)
        elif ext in ['.docx', '.doc']:
            text = docx2txt.process(tmp_path)
        else:
            return JSONResponse(status_code=400, content={"feedback": "Only PDF and Word documents are supported."})

        if not text.strip():
            return JSONResponse(status_code=400, content={"feedback": "No text could be extracted from the file."})

        prompt = f"""
You are an expert teacher AI. Analyze the following exam paper answers submitted by a student.

Instructions:
- For each answer, say whether it's correct or incorrect.
- Provide a brief explanation or feedback for each.
- Be helpful, constructive, and professional.

Student Exam Answers:
{text}

Provide your evaluation below:
"""

        response = requests.post(
            "http://localhost:8080/completion",
            json={
                "prompt": prompt,
                "temperature": 0.7,
                "max_tokens": 1024,
                "stop": ["</s>"]
            },
            timeout=60
        )
        result = response.json()
        feedback = result.get("content") or result.get("text") or "No feedback generated."

        return {"feedback": feedback.strip()}
    except Exception as e:
        print("❌ Error processing exam sheet:", e)
        return JSONResponse(status_code=500, content={"feedback": "Something went wrong while evaluating the document."})
    finally:
        os.remove(tmp_path)
