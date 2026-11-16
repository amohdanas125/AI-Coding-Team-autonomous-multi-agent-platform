import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        
        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 755, "AI Coding Team | Full-Stack Multi-Agent Platform - Interview Master Guide")
            self.setStrokeColor(colors.HexColor("#e2e8f0"))
            self.setLineWidth(0.5)
            self.line(54, 748, 558, 748)
            
        # Footer
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 36, page_text)
        self.drawString(54, 36, "CONFIDENTIAL & PROPRIETARY | Prepared for Technical Interviews")
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(54, 48, 558, 48)
        self.restoreState()

def build_pdf(filename="AI_Coding_Team_Interview_Preparation_Guide.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()
    
    # Custom Palette
    c_primary = colors.HexColor("#1e1b4b")       # Dark Indigo
    c_accent = colors.HexColor("#4f46e5")        # Electric Indigo
    c_cyan = colors.HexColor("#0284c7")          # Deep Cyan
    c_dark = colors.HexColor("#0f172a")          # Slate 900
    c_body = colors.HexColor("#334155")          # Slate 700
    c_bg_box = colors.HexColor("#f8fafc")        # Light Slate Box
    c_border = colors.HexColor("#cbd5e1")        # Border Slate
    c_success = colors.HexColor("#047857")       # Emerald Green
    c_danger = colors.HexColor("#b91c1c")        # Red

    # Custom Typography Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=c_primary,
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=c_accent,
        spaceAfter=15
    )
    
    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=19,
        textColor=c_primary,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )
    
    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=c_accent,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )

    h3_style = ParagraphStyle(
        'Heading3_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=c_dark,
        spaceBefore=8,
        spaceAfter=2,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=c_body,
        spaceAfter=6
    )

    body_bold = ParagraphStyle(
        'Body_Bold',
        parent=body_style,
        fontName='Helvetica-Bold',
        textColor=c_dark
    )

    bullet_style = ParagraphStyle(
        'Bullet_Custom',
        parent=body_style,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=4
    )

    q_style = ParagraphStyle(
        'Question_Style',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14.5,
        textColor=c_primary,
        spaceBefore=6,
        spaceAfter=3
    )

    ans_style = ParagraphStyle(
        'Answer_Style',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.2,
        leading=13.5,
        textColor=c_body,
        leftIndent=8,
        spaceAfter=8
    )

    quote_style = ParagraphStyle(
        'Script_Quote',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#1e293b")
    )

    tip_style = ParagraphStyle(
        'Tip_Style',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor("#475569")
    )

    story = []

    # Title & Subtitle Banner
    story.append(Paragraph("AI Coding Team: Multi-Agent Platform", title_style))
    story.append(Paragraph("Comprehensive Technical Interview Mastery Guide & Cross-Question Handbook", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_accent, spaceBefore=0, spaceAfter=14))

    # EXECUTIVE SUMMARY BOX
    meta_table_data = [
        [
            Paragraph("<b>Role Target:</b> Full-Stack AI Engineer / Software Engineer / AI Agent Architect", tip_style),
            Paragraph("<b>Core Stack:</b> Python, FastAPI, LangGraph, React 18, Vite, Node/Express, Jest, MongoDB", tip_style)
        ],
        [
            Paragraph("<b>Key Highlight:</b> 5 Autonomous Agents with Closed-Loop QA Self-Healing", tip_style),
            Paragraph("<b>Live Demo:</b> http://localhost:8000 (Light Glassmorphism + Live Code Explorer)", tip_style)
        ]
    ]
    meta_table = Table(meta_table_data, colWidths=[250, 254])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f1f5f9")),
        ('PADDING', (0,0), (-1,-1), 6),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#cbd5e1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 12))

    # SECTION 1: ELEVATOR PITCH
    story.append(Paragraph("1. The Winning Elevator Pitch (How to Introduce the Project)", h1_style))
    story.append(Paragraph("When the interviewer asks: <i>'Tell me about your project'</i> or <i>'Walk me through what you built'</i>, do NOT start listing libraries immediately. Use this structured 3-part framework:", body_style))
    
    pitch_data = [
        [Paragraph("<b>Phase</b>", body_bold), Paragraph("<b>What to Say (Exact Script in Simple English)</b>", body_bold)],
        [
            Paragraph("<b>The Hook<br/>(15 sec)</b>", body_style),
            Paragraph("\"Most people use ChatGPT to generate single code snippets, but when you ask a single LLM to generate a complete full-stack web application, it fails. It hits token ceilings, hallucinates endpoints, generates broken database schemas, and writes frontend code that doesn't match backend routes.\"", quote_style)
        ],
        [
            Paragraph("<b>The Solution<br/>(30 sec)</b>", body_style),
            Paragraph("\"To solve this, I built <b>AI Coding Team</b>—an autonomous multi-agent development engine orchestrated via <b>LangGraph</b>. You enter one plain-English prompt, and five specialized AI agents collaborate just like a human engineering team: a Project Manager, a Backend Developer, a Frontend Developer, a sandboxed QA Engineer, and a Documentation Writer.\"", quote_style)
        ],
        [
            Paragraph("<b>The 'Wow' Factor<br/>(20 sec)</b>", body_style),
            Paragraph("\"What makes my platform unique is our <b>closed-loop self-healing QA mechanism</b>: the QA agent executes automated Jest suites against an in-memory MongoDB database in real time. If any test fails, it captures the stack trace and feeds it back to the backend agent to fix the code autonomously. Once verified, it packages a ready-to-run ZIP archive with startup scripts, an in-browser Code Explorer, and a live UI preview.\"", quote_style)
        ]
    ]
    pitch_table = Table(pitch_data, colWidths=[80, 424])
    pitch_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#eef2ff")),
        ('PADDING', (0,0), (-1,-1), 6),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#c7d2fe")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e0e7ff")),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(pitch_table)
    story.append(Spacer(1, 12))

    # SECTION 2: ARCHITECTURE & 5 AGENTS
    story.append(Paragraph("2. Step-by-Step Architecture (The 5 Autonomous Agents)", h1_style))
    story.append(Paragraph("Explain the workflow in a sequential, logical story that shows your deep understanding of systems engineering:", body_style))

    agents_data = [
        [Paragraph("<b>Agent Name</b>", body_bold), Paragraph("<b>Responsibilities & Technical Implementation</b>", body_bold)],
        [
            Paragraph("<b>1. Project Manager (PM)</b>", body_style),
            Paragraph("Analyzes the user prompt and establishes the technical blueprint. Discovers relational database entities (models, fields, types, foreign-key references), RESTful endpoint contracts (paths, HTTP methods, request bodies), and authentication requirements. Generates a strict structured Pydantic specification.", body_style)
        ],
        [
            Paragraph("<b>2. Backend Developer</b>", body_style),
            Paragraph("Consumes the PM's specification. Generates complete Express.js controllers, Mongoose schemas, router modules, JWT authorization middleware, and database seed scripts. Before writing to disk, it executes automated syntax checking via <code>node --check</code> to guarantee zero syntax or parsing errors.", body_style)
        ],
        [
            Paragraph("<b>3. Frontend Developer</b>", body_style),
            Paragraph("Builds a responsive React 18 + Vite application. It generates a multi-page app with React Router, a centralized API client with JWT interception, and tactile <b>Neomorphic (Soft UI)</b> styling (extruded cards, inset search inputs, KPI stat cards, and auth cards). To prevent token limits on large apps, it utilizes a modular per-page generation pattern.", body_style)
        ],
        [
            Paragraph("<b>4. QA Engineer (Self-Healing)</b>", body_style),
            Paragraph("Spins up an isolated sandboxed Node environment with <b>mongodb-memory-server</b> and runs automated <b>Jest + Supertest</b> suites. If all tests pass, the pipeline proceeds. If tests fail, it captures error logs, increments retry count, and routes back to the Backend Developer with precise debug feedback.", body_style)
        ],
        [
            Paragraph("<b>5. Documentation Writer</b>", body_style),
            Paragraph("Generates production documentation: Markdown README with setup steps, OpenAPI/Swagger endpoint specifications, entity relationship descriptions, and cross-platform one-click launch scripts (<code>start-dev.bat</code> for Windows, <code>start-dev.sh</code> for Linux/Mac).", body_style)
        ]
    ]
    agents_table = Table(agents_data, colWidths=[130, 374])
    agents_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f8fafc")),
        ('PADDING', (0,0), (-1,-1), 5),
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#f1f5f9")),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(agents_table)
    story.append(Spacer(1, 14))

    # SECTION 3: KEY TECHNICAL INNOVATIONS
    story.append(Paragraph("3. Four Key Technical Innovations to Highlight", h1_style))
    
    story.append(Paragraph("<b>A. Why LangGraph Instead of Simple Sequential Chains?</b>", h2_style))
    story.append(Paragraph("Sequential chains (like basic LangChain or prompt chaining) can only move in one direction (A &rarr; B &rarr; C). If step C fails, the whole pipeline crashes. <b>LangGraph</b> models the workflow as a <b>Stateful Directed Cyclic Graph</b>. This allows conditional edge routing, branching, state persistence, and most importantly, <b>cycles</b> (looping back from QA to Backend for bug fixes).", body_style))

    story.append(Paragraph("<b>B. Closed-Loop QA Self-Healing Loop</b>", h2_style))
    story.append(Paragraph("Instead of relying on LLM 'self-reflection' (which is prone to hallucinations), our QA agent tests against real execution environments with <code>mongodb-memory-server</code> and <code>jest</code>. Real assertion failures and stack traces are captured and injected into the prompt context for the developer agent, achieving autonomous error recovery with a safety cap (max 2 retries).", body_style))

    story.append(Paragraph("<b>C. Overcoming Free-Tier LLM Token Limits (Per-Page Splitting)</b>", h2_style))
    story.append(Paragraph("Generating a complete 5-page React frontend with routing and CSS in one single LLM call easily exceeds standard token ceilings (e.g. Groq 8,000 TPM limit). We engineered a modular architecture: the PM outlines the page list, and the Frontend Agent makes focused per-page generation calls in parallel, plus one shared skeleton call. This prevents truncation and token exhaustion.", body_style))

    story.append(Paragraph("<b>D. In-Browser Live Code Explorer & UI Sandbox</b>", h2_style))
    story.append(Paragraph("We built a dual-view modal on our Light Glassmorphic dashboard: users can inspect and copy raw generated code with line numbers, or switch to the <b>Live UI Preview</b> tab to interact with responsive mock data, device viewport toggles (Desktop/Tablet/Mobile), and live search filtering without leaving port 8000.", body_style))

    story.append(Spacer(1, 10))

    # SECTION 4: TOP 15 INTERVIEWER CROSS-QUESTIONS & ANSWERS
    story.append(Paragraph("4. Top 15 Interviewer Cross-Questions & Winning Answers", h1_style))
    story.append(Paragraph("Here are the exact technical questions interviewers ask, the underlying concepts they are testing, and the optimal answers in clear English:", body_style))

    qa_list = [
        (
            "Q1: Why did you build a multi-agent system? Couldn't a single LLM prompt do this?",
            "Concept Tested: Architectural motivation & token economics.",
            "Answer: \"A single prompt fails for complex full-stack apps due to three fundamental limitations: 1) Context window and token limits—generating 15 backend and frontend files in one prompt leads to truncation; 2) Cognitive drift—a model tasked with designing architecture, coding CSS, and writing tests simultaneously produces shallow code and hallucinated endpoints; 3) Lack of separation of concerns. By decomposing the problem into specialized agents with explicit schemas and contracts, each agent focuses on a single responsibility, producing robust, verifiable code.\""
        ),
        (
            "Q2: How do your agents share state and communicate with each other?",
            "Concept Tested: LangGraph state management & contract passing.",
            "Answer: \"All agents communicate through a centralized, typed StateGraph defined in orchestrator/state.py. Instead of passing massive raw source code between agents, agents pass structured contracts. For example, the PM outputs an api_contract and spec. The Backend Developer generates routes matching that contract. The Frontend Developer only receives the api_contract (endpoint paths, parameters, auth requirements)—not the backend source code. This minimizes token consumption and ensures strict API alignment.\""
        ),
        (
            "Q3: What happens if an agent produces invalid JSON or malformed code?",
            "Concept Tested: Defensive programming, validation, and error recovery.",
            "Answer: \"We enforce strict Pydantic schemas using structured outputs. If an LLM response contains invalid escape sequences (such as unescaped single quotes or raw newlines), our parser extracts the JSON block using regex cleaning. Furthermore, for JavaScript files, we execute automated validation before assembly—running `node --check` on generated backend files to verify syntax integrity before running test suites.\""
        ),
        (
            "Q4: How does the QA Self-Healing loop actually work? Give a concrete example.",
            "Concept Tested: Cyclic graphs, debugging workflows, recursion limits.",
            "Answer: \"When the Backend Developer finishes, control transitions to the QA Engineer. The QA Agent launches an isolated Node child process running Jest with mongodb-memory-server. Suppose the test fails because a route returned 404 due to a missing router prefix. The QA agent captures the failed test name and exact stack trace. LangGraph checks the state: since retry_count < 2, it routes back to Backend Developer with an augmented prompt: 'Fix these specific test errors: [stack trace]'. The Backend Developer patches the route, and QA re-verifies. If retries hit the maximum limit, it safely flags the issue and proceeds to packaging without crashing the server.\""
        ),
        (
            "Q5: Why did you use mongodb-memory-server instead of a real MongoDB instance or Docker?",
            "Concept Tested: Sandboxing, portability, test isolation.",
            "Answer: \"mongodb-memory-server runs a lightweight MongoDB binary completely in RAM. This provides three huge advantages: 1) Zero infrastructure dependency—the system runs anywhere on developer machines without requiring a running Docker daemon or cloud database; 2) Extreme speed—database operations in RAM execute in milliseconds; 3) Hermetic test isolation—every test run starts with a clean database state and leaves zero lingering files or port conflicts.\""
        ),
        (
            "Q6: Why did you combine Groq and Gemini instead of using only one LLM provider?",
            "Concept Tested: Pragmatic multi-provider AI architecture and cost optimization.",
            "Answer: \"We optimized for both speed and context capacity: Groq (Llama 3.3 70B) provides ultra-fast inference (over 250 tokens per second), which is ideal for the Project Manager, Backend Developer, and QA analysis. However, generating rich multi-component React frontends with extensive Neomorphic CSS requires large token throughput where Groq's free-tier rate limits could be tight. We strategically routed the Frontend Developer agent to Gemini's large-window model, giving us optimal speed on the backend and deep context on the frontend.\""
        ),
        (
            "Q7: How do you prevent infinite loops if the Backend Developer keeps failing tests?",
            "Concept Tested: Distributed systems safeguards & termination guarantees.",
            "Answer: \"In our LangGraph conditional router (`should_continue_qa`), we enforce an explicit recursion ceiling: `max_retries = 2`. Each retry increments a state counter. If tests fail twice, the graph breaks the cycle, logs a warning in the execution timeline, and gracefully continues to the Documentation and Assembly phases. The final QA report clearly documents any failing tests for the user rather than hanging indefinitely.\""
        ),
        (
            "Q8: How does the frontend communicate with the backend? How do you ensure matching URLs?",
            "Concept Tested: Contract-driven design & frontend/backend synergy.",
            "Answer: \"The PM Agent creates a single source of truth: `api_contract`. It defines the exact HTTP method, route (e.g. `/api/books`), and query/body schemas. The Backend Developer generates Express routes strictly implementing this contract. The Frontend Developer receives this exact same contract and generates a centralized `src/api.js` client that wraps all calls, prepends base URLs, automatically attaches JWT Bearer tokens from localStorage, and handles 401 redirects.\""
        ),
        (
            "Q9: What is the difference between Neomorphism and Glassmorphism in your UI?",
            "Concept Tested: Design system understanding and UI architecture.",
            "Answer: \"We intentionally used both design systems for distinct purposes: 1) Neomorphism (Soft UI) is used for the generated applications—it uses extruded dual drop-shadows (light on top-left, dark on bottom-right) on a soft matte surface with inset concave form fields, giving a tactile physical feel; 2) Glassmorphism is used for our main Orchestrator Dashboard (`localhost:8000`)—it uses frosted glass translucent panels (`backdrop-filter: blur(20px)`), subtle white borders, and vibrant glowing aurora mesh gradients, creating a modern, luminous studio experience.\""
        ),
        (
            "Q10: How does the in-browser Live UI Preview work without running npm install or Vite?",
            "Concept Tested: Client-side sandboxing and preview architectures.",
            "Answer: \"Running `npm install` and starting Vite dev servers inside containerized environments can take minutes and consume heavy RAM. For instant previewing, we built an intelligent sandbox engine in `orchestrator/preview_generator.py`. It reads the generated `src/index.css`, parses page components, and renders a fully self-contained interactive application inside an iframe. It renders the exact Neomorphic styles, responsive device bezels (Desktop, Tablet, Mobile), and domain-specific mock data with live search filtering, while also providing one-click commands for developers who want to launch the real Vite server locally.\""
        ),
        (
            "Q11: How do you handle security? What prevents an LLM from generating vulnerable code?",
            "Concept Tested: AI security, prompt injection, and code safety.",
            "Answer: \"We implement defense-in-depth: 1) System prompts strictly mandate parameterized Mongoose queries to prevent NoSQL injection; 2) Passwords must be hashed with bcrypt; 3) Endpoints enforce JWT verification middleware; 4) CORS is explicitly configured with restricted origins; 5) In the orchestrator, test code is executed in isolated child processes with timeouts, preventing runaway processes from blocking the server.\""
        ),
        (
            "Q12: If you had to scale this platform to serve 1,000 concurrent developers, what would you change?",
            "Concept Tested: Scalability, distributed systems, and cloud architecture.",
            "Answer: \"Currently, the orchestrator uses FastAPI's in-memory background tasks and local file storage. To scale to 1,000 concurrent developers, I would: 1) Replace FastAPI background tasks with a distributed message queue like Celery or BullMQ backed by Redis; 2) Move agent execution to containerized worker pods on Kubernetes (EKS/GKE); 3) Store project artifacts and ZIPs in AWS S3 or Google Cloud Storage; 4) Execute QA Jest tests inside isolated gVisor/Firecracker microVM sandboxes for multitenant security; 5) Use Redis for distributed LangGraph state checkpointing.\""
        ),
        (
            "Q13: How do you stream real-time progress and logs to the browser dashboard?",
            "Concept Tested: Real-time web architecture, WebSockets vs Polling.",
            "Answer: \"The frontend polls the `/build/status/{task_id}` endpoint every 1 second, or consumes streamed state updates. In the orchestrator, we use LangGraph's native `.stream(stream_mode='updates')`. As each agent node yields updates (e.g., PM discovers entities, Backend generates files, QA outputs test passes), the worker records timestamps and logs into the task state, updating progress percentages from 10% to 100% in real time.\""
        ),
        (
            "Q14: What was the hardest bug or challenge you faced while building this, and how did you resolve it?",
            "Concept Tested: Real problem-solving ability, debugging under pressure.",
            "Answer: \"A major challenge was multiline string escape collision between Python and JavaScript. In our FastAPI dashboard, HTML and JavaScript were stored in a Python multiline string (`\"\"\"...\"\"\"`). In one function, `content.split('\\n')` had its backslash evaluated by Python into a literal byte newline (`0x0A`). When served to Chrome, it produced an unclosed string literal and a JavaScript SyntaxError that halted client scripts. I systematically debugged it using `node --check` on the evaluated string, diagnosed the escape expansion, and replaced it with `content.split(String.fromCharCode(10))`. This eliminated escape expansion entirely and taught me the importance of automated syntax verification.\""
        ),
        (
            "Q15: What are your key takeaways from building this project?",
            "Concept Tested: Engineering maturity and self-reflection.",
            "Answer: \"My biggest takeaway is that autonomous AI agents are only as good as their evaluation mechanisms and contract boundaries. Giving an LLM access to real execution environments (like Jest and MongoDB memory server) transforms an agent from an unpredictable text generator into a reliable software engineer. Second, breaking down monolithic prompts into specialized, contract-driven agents is the only scalable way to build production-grade AI systems.\""
        )
    ]

    for q, concept, ans in qa_list:
        q_box = [
            [Paragraph(f"<b>{q}</b>", q_style)],
            [Paragraph(f"<font color='#0284c7'><b>Core Concept Tested:</b> {concept}</font>", tip_style)],
            [Paragraph(ans, ans_style)]
        ]
        q_table = Table(q_box, colWidths=[504])
        q_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
            ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor("#e2e8f0")),
            ('PADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,-1), (-1,-1), 8),
        ]))
        story.append(q_table)
        story.append(Spacer(1, 7))

    # SECTION 5: DOS AND DON'TS
    story.append(Paragraph("5. Critical 'Do's and 'Don't's During the Interview", h1_style))
    
    dos_donts = [
        [Paragraph("<b>DO (Demonstrates Seniority)</b>", body_bold), Paragraph("<b>DON'T (Red Flags to Avoid)</b>", body_bold)],
        [
            Paragraph("&bull; Emphasize <b>closed-loop evaluation</b> and testing over prompt magic.<br/>&bull; Speak about <b>architectural trade-offs</b> (e.g. why LangGraph over LangChain).<br/>&bull; Explain how you handled <b>rate limits, syntax checks, and sandboxing</b>.<br/>&bull; Frame the agents as a <b>specialized engineering team</b>.", body_style),
            Paragraph("&bull; Don't claim the AI writes 100% bug-free code on the first pass (unrealistic).<br/>&bull; Don't say 'LangChain did everything'—highlight your custom graph, state schemas, and handlers.<br/>&bull; Don't get stuck in marketing buzzwords; talk about child processes, memory servers, and AST syntax checks.<br/>&bull; Don't ignore production scaling and security.", body_style)
        ]
    ]
    t_dos = Table(dos_donts, colWidths=[250, 254])
    t_dos.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,0), colors.HexColor("#ecfdf5")),
        ('BACKGROUND', (1,0), (1,0), colors.HexColor("#fef2f2")),
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('PADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(t_dos)
    story.append(Spacer(1, 14))

    # CONCLUSION FOOTER BANNER
    summary_p = Paragraph(
        "<b>Summary Pro-Tip:</b> In the interview, keep your answers structured using the <b>STAR Method</b> (Situation, Task, Action, Result). Offer to demonstrate the live platform running at <code>localhost:8000</code> or walk through the <code>orchestrator/graph.py</code> code. Real working code combined with clear architectural reasoning guarantees top impressions!",
        quote_style
    )
    story.append(Table([[summary_p]], colWidths=[504], style=[
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#eef2ff")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#c7d2fe")),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated {filename}")

if __name__ == "__main__":
    out_path = "AI_Coding_Team_Interview_Preparation_Guide.pdf"
    if len(sys.argv) > 1:
        out_path = sys.argv[1]
    build_pdf(out_path)
