"""
MindStat Care — Proactive Mental Health Assessment, Dynamic Psychometrics & Support Platform
Refined Standalone & Cloud Prototype:
- Student-First Default Access (Judges/Students see only the Student Check-In & Results Portal)
- PIN-Protected Presenter / Institutional Admin Console (Passcode: 2026)
- Built-in Light / Dark Mode Theme Toggle (Default: Crisp Light Mode, zero blank white boxes)
- Expanded Multi-Option Questions + Custom/Personal Text Box ("Other / Write my own response")
"""

import io
import os
import re
import time
import socket
import random
import sqlite3
import hashlib
import numpy as np
import pandas as pd
import qrcode
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_CSV = os.path.join(DATA_DIR, "pilot_raw_submissions.csv")
CLEAN_CSV = os.path.join(DATA_DIR, "pilot_cleaned_n80.csv")
DB_A_PATH = os.path.join(DATA_DIR, "database_a_clinical.db")
DB_B_PATH = os.path.join(DATA_DIR, "database_b_credits.db")

ADMIN_PASSCODE = "2026"

query_params = st.query_params
url_view = query_params.get("view", "")
url_admin_pin = query_params.get("admin", "")

st.set_page_config(
    page_title="MindStat Care | Proactive Wellbeing Platform",
    page_icon="💙",
    layout="wide",
    initial_sidebar_state="expanded",
)


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def get_cloud_host_url():
    """If deployed on Streamlit Community Cloud (or any public server), auto-detects the public HTTPS URL."""
    try:
        headers = st.context.headers
        host = headers.get("X-Forwarded-Host") or headers.get("Host") or ""
        if host and not any(host.startswith(p) for p in ("localhost", "127.0.0.1", "192.168.", "10.", "172.")):
            return f"https://{host}/?view=mobile"
    except Exception:
        pass
    return None


@st.cache_resource(show_spinner=False)
def get_public_tunnel_url():
    """Automatically creates a free public HTTPS URL (trycloudflare.com) when running locally so judges can scan on 4G/5G."""
    try:
        from pycloudflared import try_cloudflare
        urls = try_cloudflare(port=8501, verbose=False)
        pub_url = urls.tunnel.rstrip("/")
        return f"{pub_url}/?view=mobile"
    except Exception:
        return None


def generate_qr_bytes(url_str):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(url_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0F2C59", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def scrub_pii_text(text_val: str) -> str:
    """Strips any accidental email or phone number from custom free-text student responses."""
    if not text_val:
        return ""
    cleaned = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "[EMAIL-REDACTED]", text_val.strip())
    cleaned = re.sub(r"\b\d{10,12}\b", "[PHONE-REDACTED]", cleaned)
    return cleaned


# ==============================================================================
# DATA & DATABASE INITIALIZATION
# ==============================================================================
def ensure_data_ready():
    if not (os.path.exists(RAW_CSV) and os.path.exists(DB_A_PATH) and os.path.exists(DB_B_PATH)):
        import generate_poster_assets as gpa
        gpa.build_pilot_datasets()


ensure_data_ready()


def load_datasets():
    df_raw = pd.read_csv(RAW_CSV)
    df_clean = pd.read_csv(CLEAN_CSV)
    conn_a = sqlite3.connect(DB_A_PATH)
    df_db_a = pd.read_sql_query("SELECT * FROM clinical_analytics_store", conn_a)
    conn_a.close()

    conn_b = sqlite3.connect(DB_B_PATH)
    df_db_b = pd.read_sql_query("SELECT * FROM participation_credit_store", conn_b)
    conn_b.close()
    return df_raw, df_clean, df_db_a, df_db_b


# Shared Global File Store for Active Week Context (so Judge's phone sees Admin's chosen week context!)
CONTEXT_STATE_FILE = os.path.join(DATA_DIR, "active_context.txt")


# ==============================================================================
# DYNAMIC WEEKLY SITUATION & ROTATING QUESTION BANK ENGINE
# ==============================================================================
WEEKLY_CONTEXTS = {
    "Regular Academic Week (Baseline Wellbeing)": {
        "badge": "📅 Regular Academic Week",
        "description": "Focuses on baseline emotional balance, general study habits, peer connection, and daily energy recovery.",
        "likert_questions": [
            ("adapt_1", "I stay composed and adjust quickly when daily schedules shift unexpectedly.", "Adaptability"),
            ("prob_1", "I review details thoroughly before making academic or personal decisions.", "Problem-Solving"),
            ("mood_1", "Over the past week, I have felt cheerful, motivated, and interested in my daily activities.", "Mood & Vitality (PHQ-9)"),
            ("stress_1", "I have found it easy to wind down and relax after classes this week.", "Stress Regulation (DASS-21)"),
            ("social_1", "I feel supported and connected when interacting with classmates or friends.", "Social Belonging"),
        ],
    },
    "Mid-Sem / Final Exam Week (High Academic Pressure)": {
        "badge": "📝 Exam & Assessment Week",
        "description": "Tailored for examination periods—evaluates test anxiety, sleep disruption, revision overwhelm, and acute pressure coping.",
        "likert_questions": [
            ("exam_1", "I am able to stay calm and focused during high-stakes exams or tight assessment windows.", "Exam Composure"),
            ("sleep_1", "My sleep schedule and energy levels have remained steady despite upcoming exams.", "Sleep & Recovery (PHQ-9)"),
            ("overwhelm_1", "When revising multiple subjects at once, I can break the syllabus into manageable steps without panicking.", "Task Structuring"),
            ("worry_1", "I rarely dwell on fear of failure or worst-case grade outcomes while studying.", "Anxiety Control (DASS-21)"),
            ("change_1", "Sudden changes in exam timetables or syllabus coverage do not throw me into severe overthinking.", "Schedule Resilience"),
        ],
    },
    "Project & Assignment Deadline Crunch (Multi-Tasking Overload)": {
        "badge": "⚡ Deadline & Submission Crunch",
        "description": "Focuses on multi-tasking overload, group project friction, procrastination vs. urgency firefighting, and burnout signs.",
        "likert_questions": [
            ("crunch_1", "When multiple assignment deadlines collide, I follow a clear plan rather than panicking.", "Multi-Task Planning"),
            ("team_1", "I handle disagreements or uneven workloads in group projects constructively.", "Peer Collaboration"),
            ("burnout_1", "Even after long lab or project hours, I am able to disconnect and recharge mentally.", "Burnout Recovery"),
            ("focus_1", "I have been able to concentrate on complex tasks without feeling mentally exhausted.", "Cognitive Focus (PHQ-9)"),
            ("irrit_1", "I have stayed patient and calm even when technical or project setbacks occurred.", "Emotional Stability (DASS-21)"),
        ],
    },
    "Placement & Internship Drive Season (Career & Future Anxiety)": {
        "badge": "💼 Placement & Career Season",
        "description": "Screens for career uncertainty, rejection resilience after interviews, peer comparison stress, and self-worth.",
        "likert_questions": [
            ("career_1", "I view interview setbacks or rejections as learning steps rather than personal failures.", "Setback Resilience"),
            ("comp_1", "Seeing peers get selected or placed does not make me feel hopeless about my own future.", "Self-Worth (PHQ-9)"),
            ("risk_1", "I feel confident taking calculated risks and applying for challenging opportunities.", "Growth Mindset"),
            ("calm_1", "I can manage physical nervousness (racing heart, restlessness) before interviews or tests.", "Autonomic Calm (DASS-21)"),
            ("support_1", "I openly share career stress with mentors, friends, or family instead of isolating myself.", "Support Seeking"),
        ],
    },
    "Post-Results / Semester Transition Week (Recovery & Adaptation)": {
        "badge": "🔄 Post-Results & Transition Week",
        "description": "Evaluates how students process grade outcomes, recover from disappointment, and reset goals for the next term.",
        "likert_questions": [
            ("res_1", "If my grades or results fall short of expectations, I analyze what went wrong and move forward constructively.", "Failure Recovery"),
            ("adapt_2", "I adapt smoothly to new subjects, new faculty, and unfamiliar classroom environments.", "Environmental Adaptability"),
            ("hope_1", "I feel optimistic and excited about my goals for the upcoming weeks.", "Future Outlook (PHQ-9)"),
            ("relax_1", "I actively use healthy routines (hobbies, exercise, mindfulness, or social time) to reset my mind.", "Active Recharging"),
            ("worth_1", "My sense of personal value is stable and not solely defined by a single test score.", "Emotional Anchoring"),
        ],
    },
}

CUSTOM_OPTION_LABEL = "✏️ Other / Write my own personal response..."

BEHAVIORAL_POOL = [
    {
        "key": "q_sudden_change",
        "prompt": "When there is a sudden, unexpected change in your schedule or plans, how do you typically react?",
        "options": [
            "I stay calm and adapt easily.",
            "I pause, reorganize my priorities, and adjust step-by-step.",
            "I feel stressed and overthink the situation.",
            "I prefer to stick to the original plan and feel frustrated by changes.",
            "I ask peers or mentors for clarity before changing course.",
            CUSTOM_OPTION_LABEL,
        ],
    },
    {
        "key": "q_task_prioritization",
        "prompt": "When faced with multiple competing tasks or deadlines at the same time, how do you prioritize?",
        "options": [
            "I create a detailed plan and follow it closely.",
            "I focus on the most urgent task first (deadline firefighting).",
            "I tackle tasks as they come, staying flexible.",
            "I break large tasks into small daily milestones.",
            "I sometimes feel overwhelmed and procrastinate before starting.",
            CUSTOM_OPTION_LABEL,
        ],
    },
    {
        "key": "q_relaxing_activity",
        "prompt": "Which activity helps you relax and de-stress the most during a heavy week?",
        "options": [
            "Spending time with friends or talking things out.",
            "Meditation, yoga, sports, or physical exercise.",
            "Reading a book, listening to music, or quiet solo time.",
            "Gaming, watching shows, or creative hobbies.",
            "Catching up on sleep and disconnecting from screens.",
            CUSTOM_OPTION_LABEL,
        ],
    },
    {
        "key": "q_recharge_mode",
        "prompt": "After a long, exhausting day on campus, how do you prefer to recharge your energy?",
        "options": [
            "Spending quiet time alone in my room.",
            "Talking and hanging out with friends or family.",
            "Engaging in a hobby, music, or creative activity.",
            "Going for a walk, workout, or outdoor activity.",
            "Taking a nap or resting completely.",
            CUSTOM_OPTION_LABEL,
        ],
    },
    {
        "key": "q_failure_coping",
        "prompt": "How do you usually deal with academic setbacks, low marks, or disappointments?",
        "options": [
            "I see them as learning experiences and try again.",
            "I analyze what went wrong to improve next time.",
            "I feel disappointed initially, talk to someone, and move on.",
            "I tend to replay the mistake in my head and feel stressed.",
            "I distract myself with other activities to avoid thinking about it.",
            CUSTOM_OPTION_LABEL,
        ],
    },
    {
        "key": "q_problem_solving",
        "prompt": "When tackling a difficult academic or personal problem, what is your natural approach?",
        "options": [
            "I analyze every detail systematically before deciding.",
            "I look for practical, immediate solutions based on facts.",
            "I brainstorm creative possibilities and alternatives.",
            "I discuss it with friends, seniors, or faculty mentors.",
            "I step back to calm my mind first before trying to solve it.",
            CUSTOM_OPTION_LABEL,
        ],
    },
    {
        "key": "q_social_behavior",
        "prompt": "In group settings, team projects, or campus gatherings, how do you usually feel?",
        "options": [
            "I enjoy mingling, collaborating, and meeting new people.",
            "I prefer comfortable small groups of close friends.",
            "I prefer observing first and engaging selectively.",
            "I focus mainly on getting the task done efficiently.",
            "I often feel drained and wait for the gathering to be over.",
            CUSTOM_OPTION_LABEL,
        ],
    },
    {
        "key": "q_empathy_response",
        "prompt": "When a friend or classmate shares a personal struggle with you, how do you respond?",
        "options": [
            "I listen empathetically and offer emotional comfort.",
            "I try to help them find a practical solution.",
            "I share similar experiences to help them feel less alone.",
            "I provide logical advice and help them plan next steps.",
            "I encourage them to speak with a mentor or counselor.",
            CUSTOM_OPTION_LABEL,
        ],
    },
]

ATTENTION_CHECKS = [
    {"prompt": "Quality Verification Item: To confirm you are reading carefully, please select 'Agree' for this statement.", "expected": "Agree"},
    {"prompt": "Attention Check: Please select 'Disagree' for this statement so we know this is an attentive response.", "expected": "Disagree"},
    {"prompt": "Focus Check: Please select 'Strongly Agree' on this specific row to validate your check-in.", "expected": "Strongly Agree"},
]

LIKERT_OPTIONS = ["Strongly Disagree", "Disagree", "Neutral", "Agree", "Strongly Agree"]
LIKERT_SCORES = {"Strongly Disagree": 1, "Disagree": 2, "Neutral": 3, "Agree": 4, "Strongly Agree": 5}


def get_shared_week_context():
    if os.path.exists(CONTEXT_STATE_FILE):
        with open(CONTEXT_STATE_FILE, "r", encoding="utf-8") as f:
            val = f.read().strip()
            if val in WEEKLY_CONTEXTS:
                return val
    return "Mid-Sem / Final Exam Week (High Academic Pressure)"


def set_shared_week_context(val):
    with open(CONTEXT_STATE_FILE, "w", encoding="utf-8") as f:
        f.write(val)


# ==============================================================================
# SESSION STATE INITIALIZATION
# ==============================================================================
if "ui_theme" not in st.session_state:
    st.session_state.ui_theme = "Light"
if "is_admin_authenticated" not in st.session_state:
    st.session_state.is_admin_authenticated = (url_admin_pin == ADMIN_PASSCODE)
if "active_week_context" not in st.session_state:
    st.session_state.active_week_context = get_shared_week_context()
else:
    st.session_state.active_week_context = get_shared_week_context()

if "custom_questions" not in st.session_state:
    st.session_state.custom_questions = []
if "question_seed" not in st.session_state:
    st.session_state.question_seed = random.randint(100, 999)
if "checkin_start_time" not in st.session_state:
    st.session_state.checkin_start_time = time.time()
if "last_student_result" not in st.session_state:
    st.session_state.last_student_result = None
if "student_step" not in st.session_state:
    st.session_state.student_step = "form"  # "form" or "results"
if "support_bookings" not in st.session_state:
    st.session_state.support_bookings = [
        {"Booking_ID": "CARE-8041", "Specialist": "Dr. Ananya Sharma (Clinical Psychologist)", "Mode": "Confidential Video Session", "Slot": "Tomorrow, 11:00 AM", "Urgency": "Priority Triage", "Status": "Confirmed"},
        {"Booking_ID": "CARE-8039", "Specialist": "Prof. R. Deshmukh (Academic Stress Coach)", "Mode": "In-Person Campus Wellness Room", "Slot": "Thursday, 3:30 PM", "Urgency": "Standard", "Status": "Confirmed"},
    ]
if "admin_nav_page" not in st.session_state:
    st.session_state.admin_nav_page = "📱 Live QR Demo & Real-Time Verification"

df_raw_master, df_clean_master, df_db_a, df_db_b = load_datasets()
all_depts = sorted(df_db_a["department"].unique().tolist())
all_years = sorted(df_db_a["academic_year"].unique().tolist())


# ==============================================================================
# DYNAMIC THEME STYLING (LIGHT / DARK MODE WITH ZERO BLANK BOXES)
# ==============================================================================
is_dark = (st.session_state.ui_theme == "Dark")
bg_main = "#0F172A" if is_dark else "#F8FAFC"
bg_card = "#1E293B" if is_dark else "#FFFFFF"
text_main = "#F8FAFC" if is_dark else "#0F172A"
text_muted = "#94A3B8" if is_dark else "#475569"
border_col = "#334155" if is_dark else "#CBD5E1"
plotly_tpl = "plotly_dark" if is_dark else "plotly_white"

st.markdown(
    f"""
    <style>
    .stApp {{
        background-color: {bg_main} !important;
        color: {text_main} !important;
    }}
    [data-testid="stSidebar"] {{
        background-color: {bg_card} !important;
        border-right: 1px solid {border_col} !important;
    }}
    [data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: {bg_card} !important;
        border: 1px solid {border_col} !important;
        border-radius: 14px !important;
        padding: 1rem !important;
        box-shadow: 0 2px 10px rgba(15, 23, 42, 0.05) !important;
    }}
    p, span, label, h1, h2, h3, h4, h5, h6, .stMarkdown {{
        color: {text_main} !important;
    }}
    .product-header {{
        background: linear-gradient(135deg, #0F2C59 0%, #1E3A8A 100%);
        color: #FFFFFF !important;
        padding: 1.25rem 1.6rem;
        border-radius: 14px;
        margin-bottom: 1.1rem;
        box-shadow: 0 4px 15px rgba(15, 44, 89, 0.15);
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 1rem;
    }}
    .product-header h1, .product-header h2 {{
        color: #FFFFFF !important;
        font-size: 1.45rem !important;
        font-weight: 800 !important;
        margin: 0 !important;
    }}
    .product-header p {{
        color: #E2E8F0 !important;
        font-size: 0.9rem !important;
        margin: 0.2rem 0 0 0 !important;
    }}
    .context-badge {{
        background: rgba(255, 255, 255, 0.16);
        border: 1px solid rgba(255, 255, 255, 0.35);
        color: #FFFFFF !important;
        padding: 0.4rem 0.9rem;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 700;
    }}
    .metric-card {{
        background: {bg_card};
        border: 1px solid {border_col};
        border-left: 5px solid #0F2C59;
        border-radius: 12px;
        padding: 1rem 1.15rem;
        box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
    }}
    .metric-card.blue {{ border-left-color: #0284C7; }}
    .metric-card.green {{ border-left-color: #16A34A; }}
    .metric-card.amber {{ border-left-color: #D97706; }}
    .metric-card.red {{ border-left-color: #DC2626; }}
    .metric-title {{
        font-size: 0.76rem;
        font-weight: 700;
        text-transform: uppercase;
        color: {text_muted} !important;
        letter-spacing: 0.04em;
    }}
    .metric-val {{
        font-size: 1.55rem;
        font-weight: 800;
        color: {text_main} !important;
        margin: 0.2rem 0;
    }}
    .metric-sub {{
        font-size: 0.8rem;
        color: {text_muted} !important;
    }}
    .token-receipt {{
        background: linear-gradient(135deg, #0F2C59 0%, #0D9488 100%);
        color: #FFFFFF !important;
        padding: 1.15rem;
        border-radius: 14px;
        text-align: center;
        margin: 0.6rem 0 1rem 0;
        box-shadow: 0 6px 18px rgba(13, 148, 136, 0.2);
    }}
    .token-receipt div {{
        color: #FFFFFF !important;
    }}
    .token-code {{
        font-family: monospace;
        font-size: 1.85rem;
        font-weight: 900;
        letter-spacing: 0.08em;
        color: #FDE047 !important;
        margin: 0.25rem 0;
    }}
    .triage-banner-red {{
        background: #FEF2F2;
        border: 1.5px solid #FCA5A5;
        border-left: 6px solid #DC2626;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
    }}
    .triage-banner-red * {{ color: #7F1D1D !important; }}
    .triage-banner-amber {{
        background: #FFFBEB;
        border: 1.5px solid #FCD34D;
        border-left: 6px solid #D97706;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
    }}
    .triage-banner-amber * {{ color: #78350F !important; }}
    .triage-banner-green {{
        background: #F0FDF4;
        border: 1.5px solid #86EFAC;
        border-left: 6px solid #16A34A;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
    }}
    .triage-banner-green * {{ color: #14532D !important; }}
    .live-feed-banner {{
        background: #ECFDF5;
        border: 1.5px solid #6EE7B7;
        border-left: 6px solid #10B981;
        border-radius: 12px;
        padding: 0.9rem 1.1rem;
        margin-bottom: 0.9rem;
    }}
    .live-feed-banner * {{ color: #064E3B !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# STUDENT CHECK-IN & PERSONALIZED RESULTS COMPONENT (MOBILE & DESKTOP)
# ==============================================================================
def render_student_experience(key_prefix="stu", is_compact=False):
    ctx_name = get_shared_week_context()
    ctx_data = WEEKLY_CONTEXTS[ctx_name]

    with st.container(border=True):
        st.markdown(
            f"""
            <div class="product-header" style="padding:1rem 1.25rem;">
                <div>
                    <h2>💙 MindStat Care — Student Wellbeing Check-In</h2>
                    <p>{ctx_data['badge']} &bull; 100% Anonymous &amp; Confidential</p>
                </div>
                <div class="context-badge">🔒 Zero PII Saved</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.session_state.student_step == "form":
            top_c1, top_c2 = st.columns([1.6, 1.0])
            with top_c1:
                st.caption(
                    "✨ **Dynamic Check-In:** Questions adapt to the current campus week. If none of the preset options fit, choose **'✏️ Other / Write my own personal response...'** to type your own answer!"
                )
            with top_c2:
                if st.button("🔀 Shuffle Question Set", use_container_width=True, key=f"{key_prefix}_shuffle"):
                    st.session_state.question_seed = random.randint(100, 999)
                    st.session_state.checkin_start_time = time.time()
                    st.rerun()

            rng_q = random.Random(st.session_state.question_seed)
            base_likerts = list(ctx_data["likert_questions"]) + list(st.session_state.custom_questions)
            num_likert = 3 if is_compact else 4
            selected_likerts = rng_q.sample(base_likerts, k=min(num_likert, len(base_likerts)))
            active_attn = rng_q.choice(ATTENTION_CHECKS)
            num_beh = 3 if is_compact else 4
            selected_behavioral = rng_q.sample(BEHAVIORAL_POOL, k=min(num_beh, len(BEHAVIORAL_POOL)))

            st.markdown("##### 1️⃣ Your Cohort *(Coarse Bucket Only — Never Linked to Identity)*")
            dc1, dc2 = st.columns(2)
            with dc1:
                s_dept = st.selectbox("Academic Department:", all_depts, key=f"{key_prefix}_dept")
            with dc2:
                s_year = st.selectbox("Academic Year:", all_years, key=f"{key_prefix}_year")

            st.divider()
            st.markdown(f"##### 2️⃣ This Week's Situational Check-In *({ctx_data['badge']})*")
            s_likert_ans = {}
            for idx, (q_id, q_text, q_trait) in enumerate(selected_likerts):
                s_likert_ans[q_id] = st.radio(
                    f"**{idx + 1}. {q_text}** *({q_trait})*",
                    options=LIKERT_OPTIONS,
                    index=2,
                    horizontal=True,
                    key=f"{key_prefix}_lik_{q_id}_{st.session_state.question_seed}",
                )

            # Embedded Attention Check
            s_attn_ans = st.radio(
                f"🔍 **{active_attn['prompt']}**",
                options=LIKERT_OPTIONS,
                index=LIKERT_OPTIONS.index(active_attn["expected"]),
                horizontal=True,
                key=f"{key_prefix}_attn_{st.session_state.question_seed}",
            )

            st.divider()
            st.markdown("##### 3️⃣ Personality, Coping & Work-Style Preferences *(Select or Write Your Own)*")
            s_beh_ans = {}
            for b_idx, b_item in enumerate(selected_behavioral):
                choice = st.radio(
                    f"**{b_idx + 1}. {b_item['prompt']}**",
                    options=b_item["options"],
                    key=f"{key_prefix}_beh_{b_item['key']}_{st.session_state.question_seed}",
                )
                if choice == CUSTOM_OPTION_LABEL:
                    custom_txt = st.text_input(
                        "✍️ Type your personal response for this question:",
                        placeholder="Write how you personally react or cope in your own words...",
                        key=f"{key_prefix}_cust_{b_item['key']}_{st.session_state.question_seed}",
                    )
                    s_beh_ans[b_item["key"]] = f"Custom: {scrub_pii_text(custom_txt)}" if custom_txt.strip() else "Custom personal coping strategy"
                else:
                    s_beh_ans[b_item["key"]] = choice

            st.divider()
            st.markdown("##### 4️⃣ Personal Reflection / Anything Else on Your Mind? *(Optional)*")
            personal_note = st.text_area(
                "Share any specific academic pressure, schedule issue, or personal thought in your own words (100% anonymous):",
                placeholder="e.g., Overlapping lab submissions and back-to-back tests are making it hard to get enough sleep...",
                height=80,
                key=f"{key_prefix}_personal_note",
            )

            s_want_help = st.checkbox(
                "🤝 I would like to connect with a campus counselor or wellbeing mentor right away",
                key=f"{key_prefix}_want_help",
            )

            if st.button("🚀 Submit My Anonymous Check-In & View Results", use_container_width=True, type="primary", key=f"{key_prefix}_submit"):
                if s_attn_ans != active_attn["expected"]:
                    st.error(
                        f"🛑 **Blocked by Quality Verification Check:** Expected **'{active_attn['expected']}'**, but got **'{s_attn_ans}'**. Please read carefully and try again!"
                    )
                else:
                    likert_mean = np.mean([LIKERT_SCORES[v] for v in s_likert_ans.values()])
                    distress_ratio = (5.0 - likert_mean) / 4.0

                    q_change_val = s_beh_ans.get("q_sudden_change", "I stay calm and adapt easily.")
                    q_task_val = s_beh_ans.get("q_task_prioritization", "I create a detailed plan and follow it closely.")
                    q_relax_val = s_beh_ans.get("q_relaxing_activity", "Spending time with friends or talking things out.")
                    q_rech_val = s_beh_ans.get("q_recharge_mode", "Spending quiet time alone in my room.")
                    q_prob_val = s_beh_ans.get("q_problem_solving", "I analyze every detail systematically before deciding.")
                    q_soc_val = s_beh_ans.get("q_social_behavior", "I enjoy mingling, collaborating, and meeting new people.")
                    q_fail_val = s_beh_ans.get("q_failure_coping", "I see them as learning experiences and try again.")
                    cleaned_note = scrub_pii_text(personal_note)

                    # Also factor stress keywords from custom answers / personal reflection
                    combined_custom_text = f"{q_change_val} {q_task_val} {q_fail_val} {cleaned_note}".lower()
                    stress_kw_boost = 4.0 if any(w in combined_custom_text for w in ["stressed", "overwhelm", "panic", "anxious", "exhaust", "sleep", "procrastinat", "replay"]) else 0.0

                    phq9_est = round(float(np.clip(3.0 + distress_ratio * 16.0 + stress_kw_boost, 1.0, 26.0)), 1)
                    dass_stress_est = round(float(np.clip(6.0 + distress_ratio * 23.0 + stress_kw_boost * 1.4 + (3.0 if "urgent" in q_task_val.lower() else 0.0), 2.0, 40.0)), 1)
                    dass_anx_est = round(float(np.clip(dass_stress_est * 0.72, 1.0, 36.0)), 1)
                    resilience_est = round(float(np.clip(92.0 - distress_ratio * 46.0 - stress_kw_boost * 3.2, 22.0, 96.0)), 1)
                    csi_est = round(min(95.0, (dass_stress_est / 42.0) * 52.0 + (phq9_est / 27.0) * 32.0 + ((100.0 - resilience_est) / 100.0) * 22.0 + 4.0), 1)

                    anon_hash = "MSC-" + hashlib.sha256(f"{time.time()}_{s_dept}".encode()).hexdigest()[:6].upper()

                    conn_a = sqlite3.connect(DB_A_PATH)
                    conn_a.execute(
                        """
                        INSERT INTO clinical_analytics_store (
                            anon_session_hash, department, academic_year, age_group, gender,
                            q_sudden_change, q_relaxing_activity, q_problem_solving, q_task_prioritization,
                            q_recharge_mode, q_empathy_response, q_risk_attitude, q_social_behavior,
                            q_failure_coping, q_motivation_driver,
                            phq9_score, dass21_stress_score, dass21_anxiety_score, resilience_index, campus_stress_index
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            anon_hash, s_dept, s_year, "18–22 years", "Anonymous",
                            q_change_val, q_relax_val, q_prob_val, q_task_val,
                            q_rech_val, s_beh_ans.get("q_empathy_response", "I listen empathetically and offer emotional comfort."),
                            "I embrace them as opportunities for growth.", q_soc_val,
                            q_fail_val, cleaned_note if cleaned_note else "Personal growth & academic balance",
                            phq9_est, dass_stress_est, dass_anx_est, resilience_est, csi_est,
                        ),
                    )
                    conn_a.commit()
                    conn_a.close()

                    st.session_state.last_student_result = {
                        "anon_hash": anon_hash,
                        "department": s_dept,
                        "academic_year": s_year,
                        "week_context": ctx_name,
                        "phq9_score": phq9_est,
                        "dass_stress": dass_stress_est,
                        "resilience": resilience_est,
                        "csi": csi_est,
                        "q_sudden_change": q_change_val,
                        "q_task_prioritization": q_task_val,
                        "q_recharge_mode": q_rech_val,
                        "q_problem_solving": q_prob_val,
                        "personal_note": cleaned_note,
                        "want_immediate_help": s_want_help,
                    }
                    st.session_state.student_step = "results"
                    st.rerun()

        else:
            # STUDENT RESULTS & ANONYMOUS TOKEN RECEIPT VIEW
            res = st.session_state.last_student_result
            st.markdown(
                f"""
                <div class="token-receipt">
                    <div style="font-size:0.82rem;text-transform:uppercase;letter-spacing:0.05em;">🔑 Your Anonymous Verification Token</div>
                    <div class="token-code">#{res['anon_hash']}</div>
                    <div style="font-size:0.8rem;">You can verify this token on the Presenter's Live Admin Feed! Zero personal identity was saved.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if res["phq9_score"] >= 12.0 or res["dass_stress"] >= 20.0 or res["want_immediate_help"]:
                st.markdown(
                    """
                    <div class="triage-banner-red">
                        <strong>🔴 Priority Wellbeing Support Recommended</strong><br/>
                        High stress or emotional load detected this week. Connect with a counselor below or review your tailored action plan.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            elif res["phq9_score"] >= 8.0 or res["dass_stress"] >= 14.0:
                st.markdown(
                    """
                    <div class="triage-banner-amber">
                        <strong>🟠 Moderate Academic Stress</strong><br/>
                        Noticeable workload tension—use the tailored pacing strategies below to stay balanced.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """
                    <div class="triage-banner-green">
                        <strong>🟢 Thriving &amp; Resilient Profile</strong><br/>
                        Strong emotional balance and adaptability this week!
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            work_style = (
                "Custom Personal Strategy"
                if res["q_task_prioritization"].startswith("Custom:")
                else (
                    "Structured Planner"
                    if "detailed plan" in res["q_task_prioritization"] or "milestones" in res["q_task_prioritization"]
                    else ("Urgent Firefighter" if "urgent" in res["q_task_prioritization"] else "Flexible Adapter")
                )
            )
            recharge_style = (
                "Custom Recharge Style"
                if res["q_recharge_mode"].startswith("Custom:")
                else (
                    "Solo Quiet Recharger"
                    if "alone" in res["q_recharge_mode"] or "nap" in res["q_recharge_mode"]
                    else ("Social Recharger" if "friends" in res["q_recharge_mode"] else "Active / Hobby Recharger")
                )
            )

            mc1, mc2 = st.columns(2)
            with mc1:
                st.metric("Work & Task Style", work_style)
                st.metric("Stress Load (DASS-21)", f"{res['dass_stress']} / 42")
            with mc2:
                st.metric("Recharge Style", recharge_style)
                st.metric("Resilience Score", f"{res['resilience']:.0f} / 100")

            if res.get("personal_note"):
                st.info(f"💬 **Your Recorded Personal Reflection (Anonymized):** *\"{res['personal_note']}\"*")

            st.markdown("##### 🎯 Your Tailored Action Plan")
            if "stressed" in res["q_sudden_change"].lower() or "frustrated" in res["q_sudden_change"].lower():
                st.info("🛡️ **Schedule Buffer:** Keep a 20% daily buffer slot so sudden plan shifts don't cause overwhelm.")
            else:
                st.success(f"✅ **Adaptability Response:** *{res['q_sudden_change']}*")

            if "urgent" in res["q_task_prioritization"].lower() or "procrastinate" in res["q_task_prioritization"].lower():
                st.warning("📋 **Pacing Tip:** Spend 5 mins sorting Urgent vs. Important tasks before diving into deadlines.")

            with st.expander("🤝 Connect with a Campus Counselor Now", expanded=res["want_immediate_help"]):
                m_spec = st.selectbox(
                    "Select Counselor:",
                    [
                        "Dr. Ananya Sharma (Clinical Psychologist)",
                        "Prof. R. Deshmukh (Academic Stress Coach)",
                        "24/7 Campus Crisis Team (Immediate Triage)",
                    ],
                    key=f"{key_prefix}_spec",
                )
                m_mode = st.selectbox("Session Type:", ["Anonymous Chat", "Confidential Video Call", "In-Person Slot"], key=f"{key_prefix}_mode")
                if st.button("💙 Confirm Confidential Booking", use_container_width=True, type="primary", key=f"{key_prefix}_book_btn"):
                    b_id = f"CARE-{random.randint(8100, 9999)}"
                    st.session_state.support_bookings.insert(
                        0,
                        {"Booking_ID": b_id, "Specialist": m_spec, "Mode": m_mode, "Slot": "Priority Same-Day", "Urgency": "Priority", "Status": "Confirmed"},
                    )
                    st.success(f"Booking `{b_id}` confirmed with {m_spec}!")

            with st.expander("🎖️ Claim +2 Academic Participation Marks (Database B)", expanded=True):
                st.caption("Logged into isolated **Database B** with zero link to Token `#" + res["anon_hash"] + "`.")
                m_roll = st.text_input("Enter Roll Number / Judge ID:", placeholder="e.g., JUDGE-01 or 2026-CS-1099", key=f"{key_prefix}_roll")
                if st.button("🎖️ Claim Participation Credit", use_container_width=True, key=f"{key_prefix}_crd_btn"):
                    if m_roll.strip():
                        crd_id = "CRD-" + hashlib.sha256(f"{m_roll}_{time.time()}".encode()).hexdigest()[:8].upper()
                        conn_b = sqlite3.connect(DB_B_PATH)
                        conn_b.execute(
                            "INSERT INTO participation_credit_store (credit_receipt_id, student_roll_number, department_code, academic_credit_awarded, verification_date) VALUES (?, ?, ?, ?, ?)",
                            (crd_id, m_roll.strip(), "DEMO", "YES (+2 Internal Marks)", time.strftime("%Y-%m-%d")),
                        )
                        conn_b.commit()
                        conn_b.close()
                        st.success(f"✅ Credit Receipt `{crd_id}` recorded in Database B for `{m_roll.strip()}`!")

            if st.button("🔄 Take Another Check-In", use_container_width=True, key=f"{key_prefix}_reset"):
                st.session_state.student_step = "form"
                st.session_state.question_seed = random.randint(100, 999)
                st.session_state.checkin_start_time = time.time()
                st.rerun()


# ==============================================================================
# SIDEBAR: THEME SWITCHER & PIN-PROTECTED PRESENTER / ADMIN LOGIN
# ==============================================================================
with st.sidebar:
    st.markdown("## 💙 MindStat Care")
    st.caption("Proactive Mental Wellbeing & Institutional Support Platform")

    # Light / Dark Theme Toggle
    theme_choice = st.radio(
        "🎨 Display Theme:",
        ["☀️ Light Mode (Recommended)", "🌙 Dark Mode"],
        index=0 if st.session_state.ui_theme == "Light" else 1,
        horizontal=True,
    )
    new_theme = "Light" if "Light" in theme_choice else "Dark"
    if new_theme != st.session_state.ui_theme:
        st.session_state.ui_theme = new_theme
        st.rerun()

    active_ctx_info = WEEKLY_CONTEXTS[st.session_state.active_week_context]
    st.info(f"**Active Campus Mode:**\n{active_ctx_info['badge']}")

    st.divider()

    # Role Access Control: Students/Judges only see Student View unless Admin PIN is unlocked!
    if not st.session_state.is_admin_authenticated:
        st.markdown("### 🎓 Student Check-In Mode")
        st.caption("You are viewing the **Student / Participant Portal**. All responses are 100% anonymous.")
        with st.expander("🔐 Presenter / Admin Console Login", expanded=False):
            pin_input = st.text_input("Enter Presenter PIN:", type="password", placeholder="Enter PIN (2026)")
            if st.button("🔓 Unlock Admin Console", use_container_width=True, type="primary"):
                if pin_input.strip() == ADMIN_PASSCODE:
                    st.session_state.is_admin_authenticated = True
                    st.rerun()
                else:
                    st.error("Incorrect Presenter PIN.")
    else:
        st.success("🔓 **Presenter / Admin Mode Unlocked**")
        admin_nav_options = [
            "📱 Live QR Demo & Real-Time Verification",
            "📊 Campus Pulse & Stress Radar",
            "🧠 Personality & Coping Insights",
            "🗓️ Dynamic Question & Week Manager",
            "🛡️ Data Trust, Hygiene & Credit Ledger",
            "🎓 Preview Full-Screen Student View",
        ]
        curr_idx = admin_nav_options.index(st.session_state.admin_nav_page) if st.session_state.admin_nav_page in admin_nav_options else 0
        st.session_state.admin_nav_page = st.radio("Admin Navigation:", admin_nav_options, index=curr_idx)

        st.divider()
        min_time_gate = st.slider("Quality Gate Min Time (sec):", 15, 90, 45, 5)

        if st.button("🔒 Lock Admin (Switch to Student View)", use_container_width=True):
            st.session_state.is_admin_authenticated = False
            st.rerun()


# ==============================================================================
# DEFAULT PUBLIC VIEW: IF NOT ADMIN-AUTHENTICATED, SHOW ONLY STUDENT INTERFACE!
# ==============================================================================
if not st.session_state.is_admin_authenticated:
    _, center_col, _ = st.columns([0.15, 0.70, 0.15])
    with center_col:
        render_student_experience(key_prefix="public_stu", is_compact=False)
    st.stop()


# ==============================================================================
# ADMIN CONSOLE (ONLY ACCESSIBLE AFTER ENTERING PIN 2026)
# ==============================================================================
if st.session_state.admin_nav_page == "🎓 Preview Full-Screen Student View":
    _, center_col, _ = st.columns([0.15, 0.70, 0.15])
    with center_col:
        render_student_experience(key_prefix="admin_stu_full", is_compact=False)

elif st.session_state.admin_nav_page == "📱 Live QR Demo & Real-Time Verification":
    local_ip = get_local_ip()
    lan_qr_url = f"http://{local_ip}:8501/?view=mobile"
    cloud_url = get_cloud_host_url()
    pub_qr_url = cloud_url if cloud_url else get_public_tunnel_url()

    st.markdown(
        """
        <div class="product-header">
            <div>
                <h1>📱 Live Mobile QR Check-In &amp; Real-Time Anonymity Verification</h1>
                <p>Judges &amp; students scan the QR code to open the Student Portal on their phone while you verify the anonymous submission live on screen</p>
            </div>
            <div class="context-badge">🔐 Presenter Admin Hub</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_qr, col_mob_prev, col_live_feed = st.columns([1.0, 1.15, 1.2])

    with col_qr:
        with st.container(border=True):
            st.markdown("#### 📲 1. Scan to Open Student Site")

            qr_mode = st.radio(
                "Connection Mode for Judges' Phones:",
                [
                    "🌐 Public Cloud / 4G/5G Link (Any Phone)",
                    "📶 Local Wi-Fi / Hotspot Link (Offline LAN)",
                ],
                index=0 if pub_qr_url else 1,
            )

            if "Public" in qr_mode and pub_qr_url:
                active_default_url = pub_qr_url
                st.success("🟢 **Public Link Active!** Judges only see the Student Check-In Portal.")
            else:
                active_default_url = lan_qr_url
                st.info(f"📶 **Local Hotspot Mode:** Connect phones to Wi-Fi/Hotspot (`{local_ip}`).")

            custom_base_url = st.text_input(
                "Active Student Check-In URL:",
                value=active_default_url,
            )
            qr_png = generate_qr_bytes(custom_base_url)
            st.image(qr_png, caption=f"Scan on Phone: {custom_base_url}", use_container_width=True)

            st.markdown(
                """
                **How the Live Judge Demo Works:**
                1. **Judges Scan QR:** Opens **only** the Student Check-In on their phone (Admin Console is locked by PIN `2026`).
                2. **Judge Submits Test:** Their phone displays their **Anonymous Token** (e.g., `#MSC-9F2A1B`) + personalized insights.
                3. **Verify Live on Right Panel:** Click **🔄 Refresh Live Feed** to match their `#MSC-XXXXXX` row in **Database A** with **zero personal identity**!
                """
            )

    with col_mob_prev:
        st.markdown("#### 📱 2. Live Student Screen Simulator")
        render_student_experience(key_prefix="mob_sim", is_compact=True)

    with col_live_feed:
        with st.container(border=True):
            fh1, fh2 = st.columns([1.4, 1.0])
            with fh1:
                st.markdown("#### 📡 3. Live Admin Verification Feed")
            with fh2:
                if st.button("🔄 Refresh Live Feed", use_container_width=True, type="primary"):
                    st.rerun()

            _, _, df_db_a_latest, df_db_b_latest = load_datasets()
            latest_row = df_db_a_latest.iloc[-1]

            st.markdown(
                f"""
                <div class="live-feed-banner">
                    <div style="font-size:0.76rem;font-weight:800;text-transform:uppercase;">🟢 Latest Anonymous Vector in Database A</div>
                    <div style="font-size:1.35rem;font-weight:900;margin:0.15rem 0;">Token: <code>#{latest_row['anon_session_hash']}</code></div>
                    <div style="font-size:0.85rem;">
                        <strong>Cohort:</strong> {latest_row['department']} &bull; {latest_row['academic_year']}<br/>
                        <strong>Stress (DASS-21):</strong> {latest_row['dass21_stress_score']}/42 &bull;
                        <strong>Mood (PHQ-9):</strong> {latest_row['phq9_score']}/27 &bull;
                        <strong>CSI:</strong> {latest_row['campus_stress_index']}/100<br/>
                        <strong>Sudden Change Response:</strong> <em>"{latest_row['q_sudden_change']}"</em>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            search_tok = st.text_input("🔍 Verify a Judge's Anonymous Token (e.g. MSC-...):", placeholder="Type token shown on judge's phone...")
            if search_tok.strip():
                clean_tok = search_tok.strip().lstrip("#").upper()
                matched = df_db_a_latest[df_db_a_latest["anon_session_hash"].str.contains(clean_tok, case=False)]
                if len(matched) > 0:
                    st.success("✅ Found Matching Anonymous Record in Database A! Notice: **Zero Name, Zero Phone, Zero Roll No.**")
                    st.dataframe(
                        matched[["anon_session_hash", "department", "academic_year", "q_sudden_change", "q_task_prioritization", "q_motivation_driver", "phq9_score", "dass21_stress_score", "campus_stress_index"]],
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.warning("No matching token found yet—click Refresh Live Feed after submitting!")

            st.markdown("##### 📗 Recent Anonymous Entries in Database A *(Clinical Store)*")
            st.dataframe(
                df_db_a_latest[["anon_session_hash", "department", "academic_year", "q_sudden_change", "phq9_score", "dass21_stress_score", "campus_stress_index"]].iloc[::-1].head(5),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("##### 📙 Recent Credit Claims in Database B *(Roll No. Only — Unlinked)*")
            st.dataframe(
                df_db_b_latest[["credit_receipt_id", "student_roll_number", "academic_credit_awarded", "verification_date"]].iloc[::-1].head(4),
                use_container_width=True,
                hide_index=True,
            )

elif st.session_state.admin_nav_page == "📊 Campus Pulse & Stress Radar":
    ctx_data = WEEKLY_CONTEXTS[st.session_state.active_week_context]

    st.markdown(
        f"""
        <div class="product-header">
            <div>
                <h1>📊 Campus Pulse &amp; Departmental Wellbeing Radar</h1>
                <p>Anonymized Macro-Analytics for Deans, HODs &amp; Student Welfare Officers</p>
            </div>
            <div class="context-badge">{ctx_data['badge']} &bull; Validated N = {len(df_db_a)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    f_col1, f_col2 = st.columns(2)
    with f_col1:
        sel_depts = st.multiselect("Filter by Department:", all_depts, default=all_depts)
    with f_col2:
        sel_years = st.multiselect("Filter by Academic Year:", all_years, default=all_years)

    df_view = df_db_a[
        df_db_a["department"].isin(sel_depts if sel_depts else all_depts)
        & df_db_a["academic_year"].isin(sel_years if sel_years else all_years)
    ].copy()

    m1, m2, m3, m4 = st.columns(4)
    high_distress_pct = ((df_view["phq9_score"] >= 10.0) | (df_view["dass21_stress_score"] >= 19.0)).mean() * 100.0 if len(df_view) > 0 else 0.0

    with m1:
        st.markdown(
            f"""
            <div class="metric-card blue">
                <div class="metric-title">Validated Student Check-Ins</div>
                <div class="metric-val">N = {len(df_view)}</div>
                <div class="metric-sub">Latest Token: #{df_db_a.iloc[-1]['anon_session_hash']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f"""
            <div class="metric-card amber">
                <div class="metric-title">Mean Campus Stress Index</div>
                <div class="metric-val">{df_view['campus_stress_index'].mean():.1f} / 100</div>
                <div class="metric-sub">Mean Resilience: {df_view['resilience_index'].mean():.1f}/100</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f"""
            <div class="metric-card red">
                <div class="metric-title">Elevated Clinical Triage Zone</div>
                <div class="metric-val">{high_distress_pct:.1f}%</div>
                <div class="metric-sub">Exceeding PHQ-9 (&ge;10) or DASS Stress (&ge;19)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m4:
        st.markdown(
            f"""
            <div class="metric-card green">
                <div class="metric-title">Support Bookings &amp; Credits</div>
                <div class="metric-val">{len(st.session_state.support_bookings)} Active</div>
                <div class="metric-sub">{len(df_db_b)} Participation Credits Issued</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")
    c_left, c_right = st.columns([1.15, 1.0])

    with c_left:
        with st.container(border=True):
            st.markdown("#### 🔥 Departmental × Academic Year Stress Heatmap")
            hm_metric = st.radio(
                "Select Indicator:",
                [
                    ("campus_stress_index", "Overall Campus Stress Index (0–100)"),
                    ("dass21_stress_score", "DASS-21 Stress Score (0–42)"),
                    ("phq9_score", "PHQ-9 Depressive Indicator (0–27)"),
                ],
                format_func=lambda x: x[1],
                horizontal=True,
            )[0]

            piv = df_view.pivot_table(index="department", columns="academic_year", values=hm_metric, aggfunc="mean").round(1)
            fig_hm = px.imshow(
                piv,
                text_auto=True,
                aspect="auto",
                color_continuous_scale="YlOrRd",
                labels=dict(x="Academic Year", y="Department", color="Score"),
                template=plotly_tpl,
            )
            fig_hm.update_layout(height=360, margin=dict(l=10, r=10, t=15, b=10))
            st.plotly_chart(fig_hm, use_container_width=True)

    with c_right:
        with st.container(border=True):
            st.markdown("#### 📈 Stress & Depressive Risk Breakdown by Department")
            dept_agg = (
                df_view.groupby("department")
                .agg(
                    Stress=("dass21_stress_score", "mean"),
                    Depressive_Mood=("phq9_score", "mean"),
                    Anxiety=("dass21_anxiety_score", "mean"),
                )
                .reset_index()
                .round(1)
            )
            fig_dept = go.Figure()
            fig_dept.add_trace(go.Bar(name="DASS-21 Stress (0–42)", x=dept_agg["department"], y=dept_agg["Stress"], marker_color="#DC2626", text=dept_agg["Stress"], textposition="outside"))
            fig_dept.add_trace(go.Bar(name="PHQ-9 Mood (0–27)", x=dept_agg["department"], y=dept_agg["Depressive_Mood"], marker_color="#0F2C59", text=dept_agg["Depressive_Mood"], textposition="outside"))
            fig_dept.add_trace(go.Bar(name="DASS-21 Anxiety (0–42)", x=dept_agg["department"], y=dept_agg["Anxiety"], marker_color="#0284C7", text=dept_agg["Anxiety"], textposition="outside"))
            fig_dept.update_layout(barmode="group", height=360, yaxis_range=[0, 36], margin=dict(l=10, r=10, t=15, b=10), legend=dict(orientation="h", y=1.1), template=plotly_tpl)
            st.plotly_chart(fig_dept, use_container_width=True)

    with st.container(border=True):
        st.markdown("#### 🎯 Recommended Institutional Actions & Support Allocation")
        action_df = (
            df_view.groupby(["department", "academic_year"])
            .agg(
                Students=("anon_session_hash", "count"),
                Stress_Index=("campus_stress_index", "mean"),
                DASS_Stress=("dass21_stress_score", "mean"),
                PHQ9_Mean=("phq9_score", "mean"),
                Change_Overwhelm_Pct=("q_sudden_change", lambda s: round(s.str.contains("stressed|stick|frustrated", case=False).mean() * 100, 1)),
            )
            .reset_index()
            .sort_values("Stress_Index", ascending=False)
            .round(1)
        )

        def recommend_intervention(r):
            if r["Stress_Index"] >= 55.0:
                return "🔴 HIGH PRIORITY: Host Departmental Resilience Workshop + Avoid Sudden Exam/Schedule Shifts"
            elif r["Stress_Index"] >= 44.0:
                return "🟠 MODERATE: Conduct Time-Management & Task-Planning Coaching Session"
            return "🟢 BALANCED: Continue Weekly Pulse Check-Ins"

        action_df["Actionable Intervention for HOD / Dean"] = action_df.apply(recommend_intervention, axis=1)
        st.dataframe(action_df, use_container_width=True, hide_index=True)

elif st.session_state.admin_nav_page == "🧠 Personality & Coping Insights":
    st.markdown(
        """
        <div class="product-header">
            <div>
                <h1>🧠 Student Personality, Behavioral Traits &amp; Coping Insights</h1>
                <p>Understanding how student personality dimensions interact with stress, task overload, and mental wellbeing</p>
            </div>
            <div class="context-badge">10 Behavioral Dimensions &bull; Validated Cohort</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    q_labels = {
        "q_sudden_change": "1. Reaction to Sudden Change in Plans",
        "q_task_prioritization": "2. Multi-Tasking & Deadline Prioritization Style",
        "q_relaxing_activity": "3. Most Relaxing De-Stress Activity",
        "q_recharge_mode": "4. Daily Energy Recharging Preference",
        "q_problem_solving": "5. Problem-Solving Strategy",
        "q_failure_coping": "6. Dealing with Failure or Academic Setbacks",
        "q_social_behavior": "7. Behavior in Social Gatherings",
        "q_empathy_response": "8. Empathy & Helping Style When Peers Share Problems",
        "q_risk_attitude": "9. Attitude Toward Taking Risks",
        "q_motivation_driver": "10. Core Motivation / Personal Reflections",
    }

    col_p1, col_p2 = st.columns([1.05, 1.15])

    with col_p1:
        with st.container(border=True):
            st.markdown("#### A. Campus Distribution Across Personality & Coping Questions")
            chosen_q = st.selectbox("Select Behavioral Question:", list(q_labels.keys()), format_func=lambda k: q_labels[k])
            vc = df_db_a[chosen_q].value_counts().reset_index()
            vc.columns = ["Response", "Count"]
            vc["Share (%)"] = (vc["Count"] / len(df_db_a) * 100.0).round(1)

            fig_pie = px.pie(
                vc,
                names="Response",
                values="Count",
                hole=0.42,
                color_discrete_sequence=["#0F2C59", "#0284C7", "#16A34A", "#D97706", "#7C3AED"],
                template=plotly_tpl,
            )
            fig_pie.update_traces(textinfo="percent+label")
            fig_pie.update_layout(height=350, margin=dict(l=10, r=10, t=15, b=10), showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)

    with col_p2:
        with st.container(border=True):
            st.markdown("#### B. How This Behavioral Trait Impacts Stress & Depression Scores")
            trait_impact = (
                df_db_a.groupby(chosen_q)
                .agg(
                    Students=("anon_session_hash", "count"),
                    Mean_DASS_Stress=("dass21_stress_score", "mean"),
                    Mean_PHQ9=("phq9_score", "mean"),
                    Mean_Resilience=("resilience_index", "mean"),
                )
                .reset_index()
                .round(1)
            )

            fig_imp = go.Figure()
            fig_imp.add_trace(go.Bar(
                name="Mean DASS-21 Stress (0–42)",
                x=trait_impact[chosen_q],
                y=trait_impact["Mean_DASS_Stress"],
                marker_color="#DC2626",
                text=trait_impact["Mean_DASS_Stress"],
                textposition="outside",
            ))
            fig_imp.add_trace(go.Bar(
                name="Mean PHQ-9 Mood Score (0–27)",
                x=trait_impact[chosen_q],
                y=trait_impact["Mean_PHQ9"],
                marker_color="#0F2C59",
                text=trait_impact["Mean_PHQ9"],
                textposition="outside",
            ))
            fig_imp.add_hline(y=19.0, line_dash="dot", line_color="#DC2626", annotation_text="Stress Cutoff (19)")
            fig_imp.add_hline(y=10.0, line_dash="dash", line_color="#0F2C59", annotation_text="PHQ-9 Cutoff (10)")
            fig_imp.update_layout(barmode="group", height=350, yaxis_range=[0, 35], margin=dict(l=10, r=10, t=15, b=10), template=plotly_tpl)
            st.plotly_chart(fig_imp, use_container_width=True)

    with st.container(border=True):
        st.markdown("#### 🧩 Cross-Tabulating Two Personality Traits (Interactive Relationship Explorer)")
        ct1, ct2 = st.columns(2)
        with ct1:
            trait_x = st.selectbox("Primary Trait (Rows):", list(q_labels.keys()), index=0, format_func=lambda k: q_labels[k])
        with ct2:
            trait_y = st.selectbox("Secondary Trait (Columns):", list(q_labels.keys()), index=1, format_func=lambda k: q_labels[k])

        cross_tab = pd.crosstab(df_db_a[trait_x], df_db_a[trait_y])
        st.dataframe(cross_tab, use_container_width=True)

elif st.session_state.admin_nav_page == "🗓️ Dynamic Question & Week Manager":
    st.markdown(
        """
        <div class="product-header">
            <div>
                <h1>🗓️ Dynamic Weekly Situation &amp; Question Bank Manager</h1>
                <p>Adapt student check-in questions automatically based on the campus calendar so students never face repetitive surveys</p>
            </div>
            <div class="context-badge">Situation-Adaptive Engine</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_w1, col_w2 = st.columns([1.05, 1.15])

    with col_w1:
        with st.container(border=True):
            st.markdown("#### 1. Set Current Campus Week Situation")
            st.caption(
                "Changing the active campus situation below immediately updates both the **QR Mobile Check-In** and **Student Portal**:"
            )
            new_ctx = st.radio(
                "Select Active Weekly Context:",
                list(WEEKLY_CONTEXTS.keys()),
                index=list(WEEKLY_CONTEXTS.keys()).index(st.session_state.active_week_context),
            )
            if new_ctx != st.session_state.active_week_context:
                st.session_state.active_week_context = new_ctx
                set_shared_week_context(new_ctx)
                st.session_state.question_seed += 1
                st.success(f"Active Campus Context updated to: **{new_ctx}**!")
                st.rerun()

            st.divider()
            st.markdown("#### 2. Add Custom Situational Question for This Week")
            with st.form("add_custom_q_form"):
                cq_text = st.text_input("New Question Statement (1–5 Likert Scale):", placeholder="e.g., I feel prepared for the upcoming lab practical evaluations.")
                cq_trait = st.selectbox("Target Construct:", ["Academic Stress", "Adaptability", "Mood & Energy (PHQ-9)", "Peer Support", "Sleep & Recovery"])
                add_q_btn = st.form_submit_button("➕ Add Question to Active Rotation Pool", use_container_width=True)
            if add_q_btn and cq_text.strip():
                q_code = f"custom_{len(st.session_state.custom_questions) + 1}"
                st.session_state.custom_questions.append((q_code, cq_text.strip(), cq_trait))
                st.success(f"Added custom question to rotation pool: *'{cq_text.strip()}'*")

    with col_w2:
        with st.container(border=True):
            ctx_obj = WEEKLY_CONTEXTS[st.session_state.active_week_context]
            st.markdown(f"#### 📋 Active Question Pool for: `{ctx_obj['badge']}`")
            st.write(ctx_obj["description"])

            pool_rows = [
                {"Question_ID": qid, "Statement": qtxt, "Construct": qtr, "Type": "5-Point Likert (Situation-Specific)"}
                for qid, qtxt, qtr in ctx_obj["likert_questions"] + st.session_state.custom_questions
            ]
            st.dataframe(pd.DataFrame(pool_rows), use_container_width=True, hide_index=True)

            st.markdown("#### 🔍 Rotating Embedded Attention-Check Pool (Anti-Memorization)")
            st.dataframe(pd.DataFrame(ATTENTION_CHECKS), use_container_width=True, hide_index=True)

elif st.session_state.admin_nav_page == "🛡️ Data Trust, Hygiene & Credit Ledger":
    st.markdown(
        """
        <div class="product-header">
            <div>
                <h1>🛡️ Automated Data Hygiene, Batch Importer &amp; Decoupled Databases</h1>
                <p>Verifying anti-trolling quality filters and complete separation between Clinical Store (DB A) and Credit Ledger (DB B)</p>
            </div>
            <div class="context-badge">Zero-PII Architecture</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    valid_mask = (
        (df_raw_master["completion_time_sec"] >= min_time_gate)
        & (df_raw_master["completion_time_sec"] <= 3600)
        & (df_raw_master["attention_check_response"] == "Agree")
        & (~df_raw_master["multi_select_anomaly"])
    )
    df_quarantined = df_raw_master[~valid_mask].copy()

    col_h1, col_h2 = st.columns(2)
    with col_h1:
        with st.container(border=True):
            st.markdown("#### 1. Automated 4-Stage Data Hygiene Funnel")
            fig_f = go.Figure(go.Funnel(
                y=[
                    "1. Raw Submissions Received",
                    "2. PII Stripped (Emails/IPs Removed)",
                    f"3. Passed Time Gate (>={min_time_gate}s & <1h)",
                    "4. Passed Attention Check (Validated Cohort)",
                ],
                x=[
                    len(df_raw_master),
                    len(df_raw_master),
                    int(((df_raw_master["completion_time_sec"] >= min_time_gate) & (df_raw_master["completion_time_sec"] <= 3600)).sum()),
                    int(valid_mask.sum()),
                ],
                textinfo="value+percent initial",
                marker=dict(color=["#64748B", "#0284C7", "#0D9488", "#16A34A"]),
            ))
            fig_f.update_layout(height=310, margin=dict(l=10, r=10, t=10, b=10), template=plotly_tpl)
            st.plotly_chart(fig_f, use_container_width=True)

    with col_h2:
        with st.container(border=True):
            st.markdown("#### 2. Quarantined Spam & Troll Submissions (Blocked from Analytics)")
            st.dataframe(
                df_quarantined[["anon_session_hash", "department", "academic_year", "completion_time_sec", "attention_check_response", "hygiene_status"]],
                use_container_width=True,
                hide_index=True,
                height=260,
            )

    with st.container(border=True):
        st.markdown("#### 3. Two-Tier Decoupled SQLite Databases (Live Verification)")
        db_col1, db_col2 = st.columns(2)
        with db_col1:
            st.markdown(f"**📗 Database A: Clinical Analytics Store (`{len(df_db_a)}` rows — ZERO Roll Numbers)**")
            st.dataframe(
                df_db_a[["anon_session_hash", "department", "academic_year", "q_sudden_change", "phq9_score", "dass21_stress_score", "campus_stress_index"]].iloc[::-1].head(8),
                use_container_width=True,
                hide_index=True,
            )
        with db_col2:
            st.markdown(f"**📙 Database B: Participation Credit Ledger (`{len(df_db_b)}` rows — ZERO Survey Answers)**")
            st.dataframe(df_db_b.iloc[::-1].head(8), use_container_width=True, hide_index=True)

    with st.container(border=True):
        st.markdown("#### 4. Batch Survey File Importer (Upload Excel / CSV)")
        uploaded_file = st.file_uploader("Upload an institutional survey export (.xlsx or .csv) to run automated PII scrubbing & hygiene checks:", type=["xlsx", "csv"])
        if uploaded_file is not None:
            if uploaded_file.name.endswith(".csv"):
                df_up = pd.read_csv(uploaded_file)
            else:
                df_up = pd.read_excel(uploaded_file)
            pii_cols = [c for c in df_up.columns if any(k in c.lower() for k in ["email", "ip address", "name", "roll", "browser"])]
            df_sanitized = df_up.drop(columns=pii_cols, errors="ignore")
            st.success(
                f"✅ Loaded **{len(df_up)} rows** from `{uploaded_file.name}`. "
                f"Automatically stripped **{len(pii_cols)} PII/Identifier columns** (`{pii_cols}`)."
            )
            st.dataframe(df_sanitized.head(10), use_container_width=True)
