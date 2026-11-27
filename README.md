# NovaCloud AI Chatbot with Prompt Templates & Memory

A domain-specific **Enterprise IT & HR Helpdesk Chatbot (`Nova`)** featuring modular variable-driven prompt templates, multi-turn conversation memory, Pydantic-validated structured JSON & Markdown table outputs, safety/scope guardrails, and an automated 24-test-case refinement benchmark.

## Features
- **Defined Persona & Domain Scope**: Tailored for NovaCloud employees, new hires, and IT/HR teams ([`docs/persona_and_design.md`](docs/persona_and_design.md)).
- **Reusable Variable Prompt Templates**: Custom `PromptTemplate` & `TemplateRegistry` with strict variable checking in [`src/prompt_templates.py`](src/prompt_templates.py) and [`prompts/templates.json`](prompts/templates.json).
- **Multi-Turn Conversation Memory**: Sliding-window turn buffer (`window_size=6`), automatic rolling summary compression, and entity extraction (name, department, device/OS) in [`src/memory.py`](src/memory.py).
- **Validated Structured Outputs**:
  - **JSON Support Tickets** validated via Pydantic v2 `SupportTicketOutput` ([`src/schemas.py`](src/schemas.py)).
  - **Markdown Policy Comparison Tables** validated via `validate_markdown_table`.
- **Multi-Layer Guardrails**: Detects and handles unsafe/prompt-injection inputs, out-of-scope topics, PII (SSNs, cards, API keys), and ambiguous short inputs ([`src/guardrails.py`](src/guardrails.py)).
- **24-Test-Case Refinement Benchmark**: Evaluates **v1 Baseline** vs **v2 Refined** prompts in [`scripts/run_evaluation.py`](scripts/run_evaluation.py) with results logged in [`reports/refinement_report.md`](reports/refinement_report.md).

## Technologies & Models Used
- **Frontend & Backend**: Python 3.12, Streamlit, Pydantic v2, Pandas
- **LLM Providers**: Groq (`openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`), Google Gemini (`gemini-2.0-flash`), OpenAI (`gpt-4o-mini`), plus offline Demo Simulator
- **Testing**: `pytest`

## Project Structure
```text
cognevance_ai_chatbot_memory/
├── app.py                         # Streamlit chat UI + memory/template inspector
├── prompts/
│   ├── system_prompts.py          # v1 vs v2 system prompts & policy knowledge
│   └── templates.json             # Reusable variable-driven prompt templates
├── src/
│   ├── chatbot.py                 # Main turn orchestration pipeline
│   ├── prompt_templates.py        # Template engine with variable validation
│   ├── memory.py                  # Sliding window + rolling summary + entities
│   ├── schemas.py                 # Pydantic JSON & Markdown table validators
│   ├── guardrails.py              # Unsafe, out-of-scope, ambiguity & PII guards
│   └── llm_client.py              # Multi-provider LLM client
├── tests/
│   ├── test_cases.json            # 24 structured evaluation test cases
│   └── test_chatbot.py            # Pytest unit & integration tests
├── scripts/
│   └── run_evaluation.py          # v1 vs v2 prompt refinement evaluation script
├── reports/
│   ├── refinement_report.md       # Benchmark comparison report
│   └── eval_results.json          # Raw evaluation metrics
├── docs/
│   ├── persona_and_design.md
│   └── prompt_design_workflow.md
├── screenshots/
├── .env.example
└── requirements.txt
```

## Setup & Running Locally
```bash
pip install -r requirements.txt
cp .env.example .env   # Configure GROQ_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY
streamlit run app.py
```

Run tests and evaluation:
```bash
pytest tests -v
python scripts/run_evaluation.py
```

## Deployment
- Ready for **Streamlit Community Cloud**, **Hugging Face Spaces**, or **Render** (`streamlit run app.py --server.port $PORT --server.address 0.0.0.0`).
- Secrets are loaded strictly from environment variables (`.env` excluded via `.gitignore`).
