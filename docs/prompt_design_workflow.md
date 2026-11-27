# Prompt Design & Iterative Refinement Workflow

## Workflow Overview
```text
User Message
   │
   ▼
[1. GuardrailEngine] ──► Unsafe / Injection? ──► Safe Refusal
   │                 ──► Out-of-Scope?       ──► Scope Redirect
   │                 ──► Ambiguous?          ──► Clarification Questions
   │                 ──► PII Detected?       ──► Regex Redaction
   ▼
[2. ConversationMemory] ──► Extract Profile Entities + Sliding Window (6 turns) + Rolling Summary
   │
   ▼
[3. TemplateRegistry] ──► Select & Render Variable Template (Q&A / Ticket JSON / Table / Checklist)
   │
   ▼
[4. ChatbotLLMClient] ──► Groq / Gemini / OpenAI / Demo Fallback
   │
   ▼
[5. Output Validators] ──► Pydantic `SupportTicketOutput` or Markdown Table Validator
```

## Refinement Iterations
- **v1 Baseline**: Single generic system prompt (`"You are a helpful IT and HR support chatbot"`), no policy injection, no structured schema instructions, and no pre-LLM guardrails. Failed on strict JSON schema adherence, multi-turn recall when context wasn't formatted, and out-of-scope / prompt-injection resilience.
- **v2 Refined**: Introduced `SYSTEM_PROMPT_V2_REFINED`, variable-validated `PromptTemplate` JSON definitions, sliding-window + rolling-summary `ConversationMemory`, pre-LLM `GuardrailEngine`, and Pydantic/Markdown validators.
