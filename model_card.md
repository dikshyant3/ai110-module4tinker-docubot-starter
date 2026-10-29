# DocuBot Model Card

This model card is a short reflection on your DocuBot system. Fill it out after you have implemented retrieval and experimented with all three modes:

1. Naive LLM over full docs  
2. Retrieval only  
3. RAG (retrieval plus LLM)

Use clear, honest descriptions. It is fine if your system is imperfect.

---

## 1. System Overview

**What is DocuBot trying to do?**  
Describe the overall goal in 2 to 3 sentences.

> DocuBot answers developer questions about a small project using only the documentation in the `docs/` folder (AUTH.md, API_REFERENCE.md, DATABASE.md, SETUP.md). It finds the doc sections most relevant to a question and either shows them directly or has Gemini write a short answer grounded in them. When the docs have no evidence, it should say so instead of guessing.

**What inputs does DocuBot take?**  
For example: user question, docs in folder, environment variables.

> - A developer question (typed in, or the 8 built-in sample queries from `dataset.py`)
> - The `.md` and `.txt` files in `docs/`
> - `GEMINI_API_KEY` from the environment / `.env` (needed only for modes 1 and 3)
> - A mode choice: 1 (Naive LLM), 2 (Retrieval only), 3 (RAG)

**What outputs does DocuBot produce?**

> - Mode 1: a free-form Gemini answer
> - Mode 2: up to 3 raw doc sections, each labeled with its filename
> - Mode 3: a short Gemini answer that names the files it relied on
> - A refusal when there is no evidence: "I don't know based on these docs." (retrieval guardrail) or "I do not know based on the docs I have." (Gemini's refusal in RAG mode)

---

## 2. Retrieval Design

**How does your retrieval system work?**  
Describe your choices for indexing and scoring.

- How do you turn documents into an index?
- How do you score relevance for a query?
- How do you choose top snippets?

> - **Chunking:** each document is split into sections at every markdown heading (`#`, `##`, `###`). The 4 docs become 40 chunks. For example, DATABASE.md becomes 10 chunks such as `## Connection Configuration` and `### users`.
> - **Index:** an inverted index maps each lowercase word (split on whitespace, punctuation stripped) to the files it appears in.
> - **Scoring:** `score_document` counts how many query words appear in a chunk. Each word counts once, no matter how often it appears.
> - **Selecting snippets:** `retrieve` uses the index to find candidate files and scores every chunk in them. It drops chunks that fail the guardrail (see Section 5), sorts by score from highest to lowest, and returns the top 3.

**What tradeoffs did you make?**  
For example: speed vs precision, simplicity vs accuracy.

> - **Simplicity vs accuracy:** exact word matching is easy to explain and debug, but it misses word variants. "connect" does not match "connection", and "table" does not match "Tables". Filler words like "the", "is" and "in" count toward the ranking score just as much as keywords do.
> - **Short chunks vs complete evidence:** chunking made results much shorter (DATABASE.md went from one 464-word result to sections of about 30–70 words). But a chunk can now lose a keyword that sat in its parent heading. Before chunking, "Which fields are stored in the users table?" returned DATABASE.md first. After chunking, the `### users` chunk matched only the word "users" and dropped out of the top 3.
> - **Guardrail strictness:** a minimum of 1 keyword match blocked every unrelated question I tested, but it also lets weak matches through (see Failure case 3).

---

## 3. Use of the LLM (Gemini)

**When does DocuBot call the LLM and when does it not?**  
Briefly describe how each mode behaves.

- Naive LLM mode:
- Retrieval only mode:
- RAG mode:

> - **Naive LLM mode:** always calls Gemini. Despite the menu label "over full docs", `naive_answer_over_full_docs` ignores the docs text (by design, as a baseline) and sends only the question with "You are a documentation assistant." Gemini never sees the project docs.
> - **Retrieval only mode:** never calls Gemini. It returns the top retrieved chunks verbatim.
> - **RAG mode:** runs retrieval first. If the guardrail leaves no chunks, it refuses right away without calling Gemini. Otherwise it sends the top 3 chunks plus the question to Gemini (`gemini-flash-lite-latest`).

**What instructions do you give the LLM to keep it grounded?**  
Summarize the rules from your prompt. For example: only use snippets, say "I do not know" when needed, cite files.

> From `answer_from_snippets` in `llm_client.py`:
> - Answer using only the information in the snippets; each snippet is labeled with its filename.
> - Do not invent new functions, endpoints, or configuration values.
> - If the snippets are not enough to answer confidently, reply exactly "I do not know based on the docs I have."
> - When answering, briefly mention which files were relied on.

---

## 4. Experiments and Comparisons

Run the **same set of queries** in all three modes. Fill in the table with short notes.

You can reuse or adapt the queries from `dataset.py`.

All 8 sample queries from `dataset.py` were run once in each mode with `python main.py` (2026-10-28). Gemini output can change from run to run, so these notes describe this one run.

| Query | Naive LLM: helpful or harmful? | Retrieval only: helpful or harmful? | RAG: helpful or harmful? | Notes |
|------|---------------------------------|--------------------------------------|---------------------------|-------|
| Where is the auth token generated? | Not helpful: asked the user to paste the codebase | Helpful, but the top result was off-topic (`GET /api/users/<user_id>`); the answer was in result #2 (`AUTH.md ## Token Generation`) | **Helpful:** "`generate_access_token` function in `auth_utils.py`", cites AUTH.md | Correct per AUTH.md. RAG picked the right chunk even though it wasn't ranked first. |
| What environment variables are required for authentication? | **Harmful:** listed `JWT_SECRET`, `CLIENT_ID`, `CLIENT_SECRET`, none of which are in the docs | Partly helpful: returned AUTH.md intro + SETUP.md `### Required Variables`; missed `AUTH.md ## Environment Variables` | Partly helpful: only `AUTH_SECRET_KEY`, cites SETUP.md | AUTH.md says two variables are required: `AUTH_SECRET_KEY` and `TOKEN_LIFETIME_SECONDS`. RAG's answer was accurate but incomplete because retrieval missed the chunk listing both. |
| How do I connect to the database? | **Harmful:** invented `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` plus Node/Python/PHP code | Helpful: three SETUP.md chunks mentioning `DATABASE_URL` | Helpful but incomplete: explains `DATABASE_URL`, SQLite default, `createdb appdb`; cites SETUP.md | `DATABASE.md ## Connection Configuration` (which has the PostgreSQL URL format) was never retrieved: "connect" ≠ "connection". |
| Which endpoint lists all users? | Not helpful: asked which API/project | Helpful: `### GET /api/users` was result #2 | **Helpful:** "`GET /api/users`", cites API_REFERENCE.md | Correct. RAG left out that the endpoint is admin-only. |
| What does the /api/projects/<project_id> route return? | **Harmful:** described "standard" fields (`id`, `created_at`, `updated_at`) that aren't in the docs | Helpful: correct chunk ranked #1 | **Helpful:** exact JSON example and 401/403/404 failure cases | RAG's answer matched API_REFERENCE.md exactly. |
| Is there any mention of payment processing in these docs? | Not harmful: asked the user to paste the docs | **Correct refusal:** "I don't know based on these docs." | **Correct refusal** (guardrail, Gemini not called) | Docs never mention payments. All non-stopword query words matched 0 chunks. |
| How does a client refresh an access token? | **Harmful:** generic OAuth flow with `POST /oauth/token` and `grant_type=refresh_token` | Helpful: `AUTH.md ## Client Workflow` ranked #1 | **Helpful:** "calling `/api/refresh`", cites AUTH.md | The project's endpoint is `/api/refresh`; Naive's `/oauth/token` would not work. |
| Which fields are stored in the users table? | **Harmful:** confidently listed `id`, `username`, `created_at`, `updated_at` as "the standard schema for the application" | Not helpful: two AUTH.md chunks + `# Database Guide`; the `### users` table chunk was not retrieved | Refused: "I do not know based on the docs I have." | Real columns: `user_id`, `email`, `password_hash`, `joined_at`. RAG refused correctly given the bad snippets, but the answer *is* in the docs, so this was a retrieval failure. |

**What patterns did you notice?**  

- When does naive LLM look impressive but untrustworthy?  
- When is retrieval only clearly better?  
- When is RAG clearly better than both?

> - **Naive LLM** looked most impressive on the database, refresh-token, and users-table questions: long, well-formatted answers with code samples. All three were wrong for this project. The users-table answer claimed to be "the standard schema for the application" and got 3 of 4 column names wrong, even though Gemini never saw the docs. On the other 3 queries it asked for more context, which is unhelpful but honest.
> - **Retrieval only** never hallucinates, because it only shows real doc text, and its payment refusal was correct. It is clearly better than Naive whenever exact details matter, but the reader must find the answer. Sometimes the best chunk was ranked #2 (auth token, list users), and sometimes it was missing entirely (users table).
> - **RAG** was clearly better than both on the auth token, list users, project route, and refresh questions: short, correct, and citing the right file. It never introduced a value that wasn't in the retrieved snippets. Its quality is capped by retrieval: when retrieval missed the key chunk, RAG gave an incomplete answer (env vars, database) or refused (users table).

---

## 5. Failure Cases and Guardrails

**Describe at least two concrete failure cases you observed.**  
For each one, say:

- What was the question?  
- What did the system do?  
- What should have happened instead?

> **Failure case 1: Naive LLM hallucinated a schema.**
> *Question:* "Which fields are stored in the users table?" (mode 1)
> *What happened:* Gemini listed `id`, `username`, `email`, `password_hash`, `created_at`, `updated_at`, described as "the standard schema for the application."
> *What should have happened:* the real columns from DATABASE.md are `user_id`, `email`, `password_hash`, `joined_at`. Without the docs, the model should have said it didn't know this project's schema.

> **Failure case 2: Retrieval missed the right chunk, so RAG refused a question the docs answer.**
> *Question:* "Which fields are stored in the users table?" (modes 2 and 3)
> *What happened:* retrieval returned `AUTH.md ## Token Generation`, `AUTH.md ## Common Failure Cases`, and `DATABASE.md # Database Guide`. The `### users` chunk matched only "users", while filler words ("are", "in", "the") pushed other chunks higher. RAG replied "I do not know based on the docs I have."
> *What should have happened:* retrieval should have returned `DATABASE.md ### users`, and RAG should have listed the four columns.

> **Failure case 3: Incomplete answers from partial retrieval.**
> *Questions:* "How do I connect to the database?" and "What environment variables are required for authentication?" (mode 3)
> *What happened:* the database answer used only SETUP.md and left out the PostgreSQL URL format, because "connect" didn't match "connection" in `DATABASE.md ## Connection Configuration`. The env-vars answer listed only `AUTH_SECRET_KEY` and missed `TOKEN_LIFETIME_SECONDS`, because `AUTH.md ## Environment Variables` wasn't retrieved.
> *What should have happened:* both answers were accurate as far as they went, but they should have come from the sections that answer the question completely.

> **Failure case 4: The guardrail let a weak match through.**
> *Question:* "How do I reset my password?" (tested in retrieval only)
> *What happened:* it returned `API_REFERENCE.md ### POST /api/login`, because the single keyword "password" matched. The docs don't describe password resets.
> *What should have happened:* "I don't know based on these docs."

**When should DocuBot say “I do not know based on the docs I have”?**  
Give at least two specific situations.

> 1. When the topic isn't in the docs at all. Example: "Is there any mention of payment processing in these docs?" (correctly refused in modes 2 and 3). Unrelated questions like "How do I bake sourdough bread?", "What is the weather in Paris?" and "Is there any mention of Kubernetes deployment?" were also refused in retrieval-only testing.
> 2. When the retrieved snippets are related but don't contain the answer. Example: "Which fields are stored in the users table?" Given snippets without the table, RAG correctly refused instead of inventing columns like Naive mode did.
> 3. When a question shares only an incidental word with the docs. Example: "How do I reset my password?" DocuBot should refuse here but currently doesn't (Failure case 4).

**What guardrails did you implement?**  
Examples: refusal rules, thresholds, limits on snippets, safe defaults.

> - **Evidence threshold in `retrieve`:** a chunk is kept only if it shares at least `MIN_KEYWORD_MATCHES = 1` non-stopword word with the question. The threshold was chosen by measurement: every unrelated test question matched 0 keywords, and every supported sample question matched at least 1. Raw scores couldn't separate the two groups because of filler words ("What is the weather in Paris?" scored 3, higher than the answerable "Which endpoint lists all users?" at 2).
> - **Refusal before the LLM:** if no chunk passes, both mode 2 and mode 3 return "I don't know based on these docs.", and RAG never calls Gemini.
> - **Prompt-level refusal:** the RAG prompt requires an exact refusal when the snippets aren't enough. This triggered on the users-table question.
> - **Snippet limit:** at most 3 chunks are sent to Gemini.
> - **Citations:** the prompt asks Gemini to name its source files. All 6 non-refusal RAG answers did.

---

## 6. Limitations and Future Improvements

**Current limitations**  
List at least three limitations of your DocuBot system.

1. **Exact word matching only:** no handling of word variants ("connect" vs "connection", "table" vs "Tables") or synonyms ("fields" vs "Column"). This caused Failure cases 2 and 3.
2. **Filler words affect ranking:** stopwords are ignored by the guardrail but still count in `score_document`, so unrelated chunks can outrank the right one (e.g. `GET /api/users/<user_id>` ranked #1 for the auth token question).
3. **Chunks lose parent-heading context:** `### users` doesn't include the `## Tables` heading above it, so the word "table" isn't in the chunk.
4. **The guardrail threshold is coarse:** one shared keyword is enough to pass, so weak matches like "reset my password" get through.
5. **Naive mode doesn't see the docs**, so it isn't a fair "LLM with full docs" comparison. It only shows what the model does with no grounding.

**Future improvements**  
List two or three changes that would most improve reliability or usefulness.

1. Ignore stopwords in `score_document` as well, so ranking depends only on meaningful words.
2. Add simple word normalization (lowercase plus stripping common suffixes like "-ion", "-s"), so "connect"/"connection" and "table"/"tables" match.
3. Prefix each `###` chunk with its parent `##` heading so subsections keep their context.

---

## 7. Responsible Use

**Where could this system cause real world harm if used carelessly?**  
Think about wrong answers, missing information, or over trusting the LLM.

> - Naive mode gives confident, well-formatted answers that are wrong for this project. Examples: `/oauth/token` instead of `/api/refresh`, `DB_HOST`/`DB_PASSWORD` instead of `DATABASE_URL`, and invented users-table columns. A developer who trusts these could write code that fails, or set up the wrong configuration.
> - RAG answers can be correct but incomplete. The auth env-var answer left out `TOKEN_LIFETIME_SECONDS` without saying anything was missing, so a developer could think their setup was complete.
> - A refusal doesn't always mean the docs lack the answer. The users-table refusal happened even though DATABASE.md has the table.

**What instructions would you give real developers who want to use DocuBot safely?**  
Write 2 to 4 short bullet points.

- Don't rely on Naive LLM mode for project-specific facts. It never sees the docs.
- Check the files a RAG answer cites, and use Retrieval only mode to see exactly which snippets the answer came from.
- Treat "I don't know" as "retrieval didn't find it", not "it isn't documented". Try rephrasing, or check the docs directly.
- Don't treat an answer as complete for setup and security details (env vars, auth). Confirm against the full doc section.
