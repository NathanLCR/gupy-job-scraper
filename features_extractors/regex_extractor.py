"""
job_description_extractor.py
────────────────────────────
Extracts structured information from Brazilian tech job descriptions (Gupy format).

Extracted fields
────────────────
  hard_skills      – Technical / tool skills listed as mandatory requirements
  soft_skills      – Behavioural / interpersonal skills (from keywords or explicit section)
  nice_to_have     – Skills listed as "Diferenciais" / "Desejáveis" (not in mandatory)
  years_experience – Numeric years of experience mentioned (e.g. "5+ anos")
  salary           – Salary / stipend value if present, else "Not specified"
  contract_type    – CLT / PJ / Estágio / Freelance etc., else "Not specified"

Usage
─────
  python job_description_extractor.py          # runs on Test.csv, prints JSON
  import job_description_extractor as je
  result = je.extract(some_description_string)
"""

import re
import html
import json
import pandas as pd
from pathlib import Path

# ════════════════════════════════════════════════════════════════════════════
#  1. SECTION-HEADER PATTERNS  (Portuguese job post conventions)
# ════════════════════════════════════════════════════════════════════════════

# Mandatory / hard requirements block
_SEC_MANDATORY = (
    r'Requisitos\s+(?:'
    r'e\s+qualifica[çc][õo]es'
    r'|Obrigat[óo]rios?'
    r'|T[ée]cnicos?'
    r')'
)

# Nice-to-have / differentiators block
_SEC_NICE = (
    r'(?:'
    r'Diferenciais?\s+(?:Valorizados?|Desej[áa]veis?)?'
    r'|Requisitos\s+Desej[áa]veis?'
    r'|Habilidades?\s+Desej[áa]veis?'
    r')'
)

# Explicit soft-skills section (sometimes present)
_SEC_SOFT = (
    r'(?:'
    r'Soft\s*[Ss]kills?'
    r'|Habilidades?\s+Comportamentais?'
    r'|Compet[êe]ncias?\s+Socioemocionais?'
    r')'
)

# "Additional info" section — used as a stop anchor
_SEC_ADD = r'Informa[çc][õo]es\s+adicionais'


# ════════════════════════════════════════════════════════════════════════════
#  2. ENTITY REGEX PATTERNS
# ════════════════════════════════════════════════════════════════════════════

# ── Years of experience ──────────────────────────────────────────────────────
# Matches: "5 anos", "5+ anos", "Mínimo de 5 anos", "3 a 5 anos de experiência"
# A trailing optional phrase captures context like "com Python"
RE_EXPERIENCE = re.compile(
    r'(?:M[íi]nimo\s+de\s+)?'                          # optional "Mínimo de"
    r'(\d+)\s*'                                          # lower bound
    r'(?:a\s+(\d+)\s+)?'                                 # optional upper bound ("3 a 5")
    r'\+?\s*'
    r'anos?\s+de\s+experi[êe]ncia'                       # "anos de experiência"
    r'(?:\s+(?:com|em|como)\s+(?P<ctx>[^,\.;]{0,60}))?', # optional context
    re.I,
)

# ── Salary ───────────────────────────────────────────────────────────────────
# Covers:  R$ 5.000  |  R$ 5.000 – R$ 8.000  |  salário a combinar  |
#          Bolsa ... R$ XXX  |  remuneração ... R$ XXX
RE_SALARY = re.compile(
    r'(?:'
    r'R\$\s*[\d\.]+(?:,\d+)?'                            # R$ 5.000,00
    r'(?:\s*[-–]\s*R\$\s*[\d\.]+(?:,\d+)?)?'            # optional range
    r'|(?:sal[áa]rio|bolsa|remuner[aação]{3,9})'         # label keyword
    r'[^R\n]{0,40}'
    r'(?:R\$\s*[\d\.]+(?:,\d+)?|a\s+combinar)'          # value or "a combinar"
    r')',
    re.I,
)

# ── Contract type ─────────────────────────────────────────────────────────────
# Stops at line break, semicolon, or two consecutive upper-case chars (new section)
RE_CONTRACT = re.compile(
    r'Contrata[çc][aã]o\s*:\s*'
    r'([A-Za-zÀ-ú /]+?)'          # value — letters/slash/spaces only
    r'(?=\s*[;\n\d]|\s{2,}|\s+[A-ZÁÉÍÓÚ]{2}|$)',
    re.I,
)

# ── Hard skills keyword set ───────────────────────────────────────────────────
RE_HARD = re.compile(
    r'(?<!\w)'   # no leading word char (poor-man negative lookbehind for .)
    r'('
    # Languages
    r'Python|Java(?:Script)?|TypeScript|C#|\.NET|PHP|Ruby|Go(?:lang)?|'
    r'Kotlin|Swift|Rust|Scala|'
    r'R(?=\b)'      # R (stats language) — only as whole word
    r'|'
    # Front-end frameworks / libs
    r'Angular(?:\.?[Jj][Ss])?|React(?:\.?[Jj][Ss])?|Vue(?:\.?[Jj][Ss])?|'
    r'Next(?:\.?[Jj][Ss])?|Nuxt(?:\.?[Jj][Ss])?|'
    r'Tailwind(?:\s*CSS)?|'
    r'HTML\d?|CSS\d?|SASS|SCSS|'
    r'|'
    # Back-end frameworks & web servers
    r'Node(?:\.?[Jj][Ss])?|Django|Flask|FastAPI|'
    r'Spring\s*Boot?|Laravel|Express(?:\.?[Jj][Ss])?|'
    r'Rails|Ruby\s+on\s+Rails|'
    r'Apache|Nginx|'
    r'|'
    # Auth / ORM / API layer
    r'Prisma|NextAuth(?:\.?[Jj][Ss])?|tRPC|'
    r'|'
    # Data / ML / AI
    r'TensorFlow|PyTorch|scikit-?learn|Pandas|NumPy|Matplotlib|'
    r'LangChain|LangGraph|LlamaIndex|Hugging\s*Face|'
    r'Airflow|Spark|Hadoop|Databricks|'
    r'|'
    # Cloud & DevOps
    r'AWS|Azure|GCP|Google\s+Cloud|'
    r'Docker|Kubernetes|Terraform|Ansible|'
    r'CI[/\-]CD|Jenkins|GitHub\s+Actions|'
    r'|'
    # Databases
    r'MySQL|PostgreSQL|MongoDB|Redis|Oracle|SQL\s*Server|SQLite|'
    r'DynamoDB|Cassandra|Elasticsearch|'
    r'|'
    # APIs & messaging
    r'REST(?:ful)?|GraphQL|gRPC|Kafka|RabbitMQ|'
    r'|'
    # Version control & collaboration
    r'Git(?:Hub|Lab)?|GIT|'
    r'Jira|Confluence|'
    r'|'
    # Methodologies
    r'Scrum|Kanban|'
    r'|'
    # Testing
    r'Selenium|Cypress|Jest|JUnit|Pytest|'
    r'|'
    # OS / Shell
    r'Linux|Unix|Bash|PowerShell|'
    r'|'
    # Design
    r'Figma|Sketch'
    r')'
    r'(?!\w)',   # no trailing word char
    re.I,
)

# ── Soft skills keyword set ───────────────────────────────────────────────────
RE_SOFT = re.compile(
    r'(?<!\w)('
    r'comunica[çc][aã]o\s*(?:clara|eficaz|assertiva)?'
    r'|lideran[çc]a'
    r'|trabalho\s+em\s+equipe'
    r'|autonomia'
    r'|proatividade|proativo'
    r'|organiza[çc][aã]o'
    r'|criatividade'
    r'|inovação'
    r'|gest[aã]o\s+do\s+tempo'
    r'|flexibilidade'
    r'|empatia'
    r'|adaptabilidade'
    r'|colabora[çc][aã]o'
    r'|mentor(?:ia)?'
    r'|resolu[çc][aã]o\s+de\s+problemas'
    r'|pensamento\s+cr[íi]tico'
    r'|intelig[êe]ncia\s+emocional'
    r'|bom\s+humor'
    r'|protagonismo'
    r')(?!\w)',
    re.I,
)


# ════════════════════════════════════════════════════════════════════════════
#  3. HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _clean(text: str) -> str:
    """Strip HTML entities and collapse whitespace."""
    text = html.unescape(text or "")
    text = re.sub(r'<[^>]+>', ' ', text)          # remove any leftover tags
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\u200b|\u00a0', ' ', text)    # zero-width / nbsp
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _section(text: str, header: str, stop: str | None = None) -> str:
    """Return the text block starting at `header` and ending at `stop`."""
    end = rf'(?:{stop})' if stop else r'$'
    m = re.search(rf'(?:{header})(.*?)(?:{end})', text, re.S | re.I)
    return m.group(1).strip() if m else ""


# ════════════════════════════════════════════════════════════════════════════
#  4. TECH-STACK DETECTION
# ════════════════════════════════════════════════════════════════════════════

# ── Canonical-token normaliser ───────────────────────────────────────────────
# Maps every spelling variant that RE_HARD can produce → one stable token.
# All tokens are lowercase to allow case-insensitive set membership tests.

_CANON: dict[str, str] = {
    # JavaScript / Node
    "javascript": "javascript", "js": "javascript",
    "node": "nodejs", "node.js": "nodejs", "nodejs": "nodejs",
    "nodej": "nodejs",                          # edge-case truncation
    "express": "express", "express.js": "express",
    # TypeScript
    "typescript": "typescript",
    # React / Next
    "react": "react", "react.js": "react", "reactjs": "react",
    "next": "nextjs", "next.js": "nextjs", "nextjs": "nextjs",
    # Angular
    "angular": "angular", "angular.js": "angular", "angularjs": "angular",
    # Vue / Nuxt
    "vue": "vue", "vue.js": "vue", "vuejs": "vue",
    "nuxt": "nuxtjs", "nuxt.js": "nuxtjs", "nuxtjs": "nuxtjs",
    # Databases
    "mongodb": "mongodb", "mongo": "mongodb",
    "postgresql": "postgresql", "postgres": "postgresql",
    "mysql": "mysql",
    "sqlite": "sqlite",
    "redis": "redis",
    # Languages
    "python": "python",
    "ruby": "ruby",
    "php": "php",
    # Frameworks
    "django": "django",
    "rails": "rails", "ruby on rails": "rails",
    "laravel": "laravel",
    # Web servers
    "apache": "apache",
    "nginx": "nginx",
    # Cloud
    "linux": "linux",
    # T3-stack specifics
    "tailwind": "tailwind", "tailwind css": "tailwind",
    "trpc": "trpc",
    "prisma": "prisma",
    "nextauth": "nextauth", "nextauth.js": "nextauth",
}

def _normalise(skill: str) -> str:
    """Return canonical token for a detected skill string, or the lowercased original."""
    return _CANON.get(skill.lower().strip(), skill.lower().strip())


# ── Stack definitions (canonical tokens only) ────────────────────────────────
# Each value is a frozenset of required canonical tokens.
# For stacks that imply a language implicitly (e.g. LAMP → PHP implies Linux
# is the OS), all components listed are treated as required signals.

TECH_STACKS: dict[str, frozenset[str]] = {
    "MERN":     frozenset({"mongodb", "express", "react",   "nodejs"}),
    "MEAN":     frozenset({"mongodb", "express", "angular", "nodejs"}),
    "MEVN":     frozenset({"mongodb", "express", "vue",     "nodejs"}),
    "PERN":     frozenset({"postgresql", "express", "react", "nodejs"}),
    "LAMP":     frozenset({"linux", "apache", "mysql", "php"}),
    "LEMP":     frozenset({"linux", "nginx",  "mysql", "php"}),
    "T3":       frozenset({"typescript", "trpc", "tailwind", "nextjs", "prisma", "nextauth"}),
    "JAMstack": frozenset({"javascript"}),          # intentionally minimal — augment if needed
    "Next.js":  frozenset({"nextjs", "react"}),
    "Nuxt":     frozenset({"nuxtjs", "vue"}),
    "Django":   frozenset({"python", "django"}),
    "Rails":    frozenset({"ruby", "rails"}),
}

# Regex to catch explicit stack-name mentions in the raw text
# (e.g. a recruiter writes "stack MERN" or "MERN stack")
_RE_STACK_MENTION = re.compile(
    r'\b(MERN|MEAN|MEVN|PERN|LAMP|LEMP|T3|JAMstack|'
    r'Next\.?js\s+stack|Nuxt\s+stack|Django\s+stack|Rails\s+stack)\b',
    re.I,
)

PARTIAL_THRESHOLD = 0.5   # fraction of components required for a "partial" match


def detect_stacks(
    all_skills: list[str],
    raw_text: str = "",
) -> dict[str, list[str]]:
    """
    Given a flat list of detected skills (hard + nice-to-have combined),
    return which tech stacks are present.

    Parameters
    ──────────
    all_skills  – combined hard_skills + nice_to_have from extract()
    raw_text    – cleaned description text (used for explicit name mentions)

    Returns
    ───────
    {
      "detected": ["MERN", ...],   # all required components found
      "partial":  ["T3", ...],     # ≥ PARTIAL_THRESHOLD components found
      "mentioned": ["LAMP", ...],  # explicitly named in the text
    }
    """
    canonical = {_normalise(s) for s in all_skills}

    detected:  list[str] = []
    partial:   list[str] = []

    for stack_name, required in TECH_STACKS.items():
        found = required & canonical
        ratio = len(found) / len(required)
        if ratio == 1.0:
            detected.append(stack_name)
        elif ratio >= PARTIAL_THRESHOLD:
            partial.append(stack_name)

    # Direct text mentions (recruiter wrote the acronym)
    mentioned = list({
        m.group(1).upper().replace(" STACK", "").replace(".JS", ".js")
        for m in _RE_STACK_MENTION.finditer(raw_text)
    })

    return {
        "detected":  sorted(detected),
        "partial":   sorted(partial),
        "mentioned": sorted(mentioned),
    }


def extract(raw: str) -> dict:
    """
    Extract structured fields from a raw job-description string.

    Returns
    ───────
    {
      "hard_skills":       list[str],
      "soft_skills":       list[str],
      "nice_to_have":      list[str],
      "years_experience":  list[dict],   # {"min": int, "max": int|None, "context": str}
      "salary":            list[str],
      "contract_type":     list[str],
      "tech_stacks": {
          "detected":  list[str],        # all components found in the description
          "partial":   list[str],        # ≥50 % of components found
          "mentioned": list[str],        # acronym explicitly written (e.g. "MERN stack")
      },
    }
    """
    text = _clean(raw)

    # ── Isolate sections ──────────────────────────────────────────────────
    mandatory_text = _section(text, _SEC_MANDATORY,
                               stop=rf'{_SEC_NICE}|{_SEC_SOFT}|{_SEC_ADD}')
    niceohave_text = _section(text, _SEC_NICE, stop=_SEC_ADD)
    soft_section   = _section(text, _SEC_SOFT, stop=rf'{_SEC_NICE}|{_SEC_ADD}')

    # Fall back to full text if mandatory section not found
    hard_source = mandatory_text or text

    # ── Hard skills (from mandatory section) ─────────────────────────────
    hard_skills = sorted({s for s in RE_HARD.findall(hard_source) if s.strip()})

    # ── Nice-to-have skills (from differentials section, deduplicated) ───
    nice_skills = sorted(
        {s for s in RE_HARD.findall(niceohave_text) if s.strip()} - set(hard_skills)
    ) if niceohave_text else []

    # ── Soft skills (dedicated section + keyword scan across full text) ──
    soft_source = soft_section + " " + text
    soft_skills = sorted({m.lower() for m in RE_SOFT.findall(soft_source)})

    # ── Years of experience ───────────────────────────────────────────────
    exp_list = []
    for m in RE_EXPERIENCE.finditer(text):
        entry = {
            "min": int(m.group(1)),
            "max": int(m.group(2)) if m.group(2) else None,
            "context": (m.group("ctx") or "").strip(),
        }
        # Guard against false positives: skip if min > 20 or max > 20
        if entry["min"] <= 20 and (entry["max"] is None or entry["max"] <= 20):
            exp_list.append(entry)

    # Deduplicate by (min, max)
    seen = set()
    years_experience = e["min"] or e["max"] or none

    # ── Salary ────────────────────────────────────────────────────────────
    salary = RE_SALARY.findall(text) or None

    # ── Contract type ─────────────────────────────────────────────────────
    contract = [c.strip() for c in RE_CONTRACT.findall(text)] or ["CLT"]

    # # ── Tech stacks ───────────────────────────────────────────────────────
    # stacks = detect_stacks(hard_skills + nice_skills, raw_text=text)

    return {
        "hard_skills":      hard_skills,
        "soft_skills":      soft_skills,
        "nice_to_have":     nice_skills,
        "years_experience": years_experience,
        "salary":           salary,
        "contract_type":    contract,
    }