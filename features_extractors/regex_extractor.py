import re
import html
import json
import pandas as pd
from pathlib import Path

_SEC_MANDATORY = (
    r'(?:'
    r'Requisitos\s+(?:e\s+qualifica[çc][õo]es|Obrigat[óo]rios?|T[ée]cnicos?)'
    r'|O\s+que\s+esperamos\s+de\s+voc[êe]'
    r'|O\s+que\s+voc[êe]\s+precisa\s+ter'
    r'|Requisitos?:?'
    r')'
)

_SEC_NICE = (
    r'(?:'
    r'Diferenciais?\s+(?:Valorizados?|Desej[áa]veis?)?'
    r'|Requisitos\s+Desej[áa]veis?'
    r'|Habilidades?\s+Desej[áa]veis?'
    r'|Voc[êe]\s+se\s+destacar[áa]\s+se\s+tiver'
    r'|Desej[áa]veis?:?'
    r'|Desej[áa]vel:?'
    r'|Diferenciais?:?'
    r')'
)

_SEC_SOFT = (
    r'(?:'
    r'Soft\s*[Ss]kills?'
    r'|Habilidades?\s+Comportamentais?'
    r'|Compet[êe]ncias?\s+Socioemocionais?'
    r')'
)

_SEC_ADD = r'Informa[çc][õo]es\s+adicionais'

RE_EXPERIENCE = re.compile(
    r'(?:M[íi]nimo\s+de\s+)?'
    r'(\d+)\s*'
    r'(?:a\s+(\d+)\s+)?'
    r'\+?\s*'
    r'anos?\s+de\s+experi[êe]ncia'
    r'(?:\s+(?:com|em|como)\s+(?P<ctx>[^,\.;]{0,60}))?',
    re.I,
)

RE_SALARY = re.compile(
    r'(?:'
    r'R\$\s*[\d\.]+(?:,\d+)?'
    r'(?:\s*[-–]\s*R\$\s*[\d\.]+(?:,\d+)?)?'
    r'|(?:sal[áa]rio|bolsa|remuner[aação]{3,9})'
    r'[^R\n]{0,40}'
    r'(?:R\$\s*[\d\.]+(?:,\d+)?|a\s+combinar)'
    r')',
    re.I,
)

RE_CONTRACT = re.compile(
    r'[Cc]ontrata[çc][ãaAÃ][oO]\s*:\s*'
    r'([A-Za-zÀ-ú \(\)/]+?)'
    r'(?=\s*[;\n\d]|\s{2,}|\s+[A-ZÁÉÍÓÚ]{2}|$)'
)

RE_HARD = re.compile(
    r'(?<!\w)'
    r'('
    r'Python|Java(?:Script)?|TypeScript|C#|\.NET|PHP|Ruby|Go(?:lang)?|'
    r'Kotlin|Swift|Rust|Scala|'
    r'R(?=\b)'
    r'|'
    r'Angular(?:\.?[Jj][Ss])?|React(?:\.?[Jj][Ss])?|Vue(?:\.?[Jj][Ss])?|'
    r'Next(?:\.?[Jj][Ss])?|Nuxt(?:\.?[Jj][Ss])?|'
    r'Tailwind(?:\s*CSS)?|'
    r'HTML\d?|CSS\d?|SASS|SCSS|'
    r'|'
    r'Node(?:\.?[Jj][Ss])?|Django|Flask|FastAPI|'
    r'Spring(?:\s*Boot)?|Laravel|Express(?:\.?[Jj][Ss])?|'
    r'Rails|Ruby\s+on\s+Rails|'
    r'Apache|Nginx|Tomcat|'
    r'|'
    r'Prisma|NextAuth(?:\.?[Jj][Ss])?|tRPC|'
    r'JPA|Hibernate|Entity\s*Framework|'
    r'JWT|OAuth|'
    r'|'
    r'TensorFlow|PyTorch|scikit-?learn|Pandas|NumPy|Matplotlib|'
    r'LangChain|LangGraph|LlamaIndex|Hugging\s*Face|'
    r'Airflow|Spark|Hadoop|Databricks|'
    r'|'
    r'AWS|Azure|GCP|Google\s+Cloud|'
    r'Docker|Kubernetes|Terraform|Ansible|'
    r'CI[/\-]CD|Jenkins|GitHub\s+Actions|'
    r'|'
    r'MySQL|PostgreSQL|MongoDB|Redis|Oracle|SQL\s*Server|SQLite|'
    r'DynamoDB|Cassandra|Elasticsearch|'
    r'|'
    r'REST(?:ful)?(?:\s+APIs?)?|GraphQL|gRPC|Kafka|RabbitMQ|SOAP|Web\s*Services?|'
    r'|'
    r'Git(?:Hub|Lab)?|GIT|'
    r'Jira|Confluence|'
    r'|'
    r'SAP(?: PI/PO| ERP)?|'
    r'|'
    r'Scrum|Kanban|Clean\s+Architecture|SOLID|DDD|TDD|'
    r'|'
    r'Selenium|Cypress|Jest|JUnit|Pytest|'
    r'|'
    r'Linux|Unix|Bash|PowerShell|Maven|Gradle|'
    r'|'
    r'Figma|Sketch'
    r')'
    r'(?!\w)',
    re.I,
)

RE_SOFT = re.compile(
    r'(?<!\w)('
    r'comunica[çc][aã]o\s*(?:clara|eficaz|assertiva)?'
    r'|lideran[çc]a'
    r'|trabalho\s+em\s+equipe'
    r'|autonomia'
    r'|proatividade|proativo'
    r'|organiza[çc][aã]o'
    r'|criatividade'
    r'|inova[çc][aã]o'
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
    r'|senso\s+de\s+dono'
    r'|perfil\s+anal[íi]tico'
    r')(?!\w)',
    re.I,
)

def _clean(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\u200b|\u00a0', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def _section(text: str, header: str, stop: str | None = None) -> str:
    end = rf'(?:{stop}|$)' if stop else r'$'
    m = re.search(rf'(?:{header})(.*?)(?:{end})', text, re.S | re.I)
    return m.group(1).strip() if m else ""

_CANON: dict[str, str] = {
    "javascript": "javascript", "js": "javascript",
    "node": "nodejs", "node.js": "nodejs", "nodejs": "nodejs",
    "nodej": "nodejs",
    "express": "express", "express.js": "express",
    "typescript": "typescript",
    "react": "react", "react.js": "react", "reactjs": "react",
    "next": "nextjs", "next.js": "nextjs", "nextjs": "nextjs",
    "angular": "angular", "angular.js": "angular", "angularjs": "angular",
    "vue": "vue", "vue.js": "vue", "vuejs": "vue",
    "nuxt": "nuxtjs", "nuxt.js": "nuxtjs", "nuxtjs": "nuxtjs",
    "mongodb": "mongodb", "mongo": "mongodb",
    "postgresql": "postgresql", "postgres": "postgresql",
    "mysql": "mysql",
    "sqlite": "sqlite",
    "redis": "redis",
    "python": "python",
    "ruby": "ruby",
    "php": "php",
    "django": "django",
    "rails": "rails", "ruby on rails": "rails",
    "laravel": "laravel",
    "apache": "apache",
    "nginx": "nginx",
    "linux": "linux",
    "tailwind": "tailwind", "tailwind css": "tailwind",
    "trpc": "trpc",
    "prisma": "prisma",
    "nextauth": "nextauth", "nextauth.js": "nextauth",
}

def _normalise(skill: str) -> str:
    return _CANON.get(skill.lower().strip(), skill.lower().strip())

TECH_STACKS: dict[str, frozenset[str]] = {
    "MERN":     frozenset({"mongodb", "express", "react",   "nodejs"}),
    "MEAN":     frozenset({"mongodb", "express", "angular", "nodejs"}),
    "MEVN":     frozenset({"mongodb", "express", "vue",     "nodejs"}),
    "PERN":     frozenset({"postgresql", "express", "react", "nodejs"}),
    "LAMP":     frozenset({"linux", "apache", "mysql", "php"}),
    "LEMP":     frozenset({"linux", "nginx",  "mysql", "php"}),
    "T3":       frozenset({"typescript", "trpc", "tailwind", "nextjs", "prisma", "nextauth"}),
    "JAMstack": frozenset({"javascript"}),
    "Next.js":  frozenset({"nextjs", "react"}),
    "Nuxt":     frozenset({"nuxtjs", "vue"}),
    "Django":   frozenset({"python", "django"}),
    "Rails":    frozenset({"ruby", "rails"}),
}

_RE_STACK_MENTION = re.compile(
    r'\b(MERN|MEAN|MEVN|PERN|LAMP|LEMP|T3|JAMstack|'
    r'Next\.?js\s+stack|Nuxt\s+stack|Django\s+stack|Rails\s+stack)\b',
    re.I,
)

PARTIAL_THRESHOLD = 0.5


def detect_stacks(
    all_skills: list[str],
    raw_text: str = "",
) -> dict[str, list[str]]:
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
    text = _clean(raw)

    mandatory_text = _section(text, _SEC_MANDATORY,
                                stop=rf'{_SEC_NICE}|{_SEC_SOFT}|{_SEC_ADD}')
    niceohave_text = _section(text, _SEC_NICE, stop=_SEC_ADD)
    soft_section   = _section(text, _SEC_SOFT, stop=rf'{_SEC_NICE}|{_SEC_ADD}')

    hard_source = mandatory_text or text
    hard_skills = sorted({s for s in RE_HARD.findall(hard_source) if s.strip()})

    nice_skills = sorted(
        {s for s in RE_HARD.findall(niceohave_text) if s.strip()} - set(hard_skills)
    ) if niceohave_text else []

    soft_source = soft_section + " " + text
    soft_skills = sorted({m.lower() for m in RE_SOFT.findall(soft_source)})

    exp_list = []
    for m in RE_EXPERIENCE.finditer(text):
        entry = {
            "min": int(m.group(1)),
            "max": int(m.group(2)) if m.group(2) else None,
            "context": (m.group("ctx") or "").strip(),
        }
        if entry["min"] <= 20 and (entry["max"] is None or entry["max"] <= 20):
            exp_list.append(entry)

    if exp_list:
        e = exp_list[0]
        years_experience = e["min"] or e["max"] or None
    else:
        years_experience = None

    salary = RE_SALARY.findall(text) or None
    contract = [c.strip() for c in RE_CONTRACT.findall(text)] or ["CLT"]

    stacks = detect_stacks(hard_skills + nice_skills, raw_text=text)
    combined_stacks = list(set(stacks["detected"] + stacks["partial"] + stacks["mentioned"]))

    for stack in combined_stacks:
        hard_skills.append(stack)
        components = TECH_STACKS.get(stack)
        if components:
            hard_skills.extend([c.capitalize() if len(c) > 3 else c.upper() for c in components])

    hard_skills = sorted(list(set(hard_skills)))

    return {
        "hard_skills":      hard_skills,
        "soft_skills":      soft_skills,
        "nice_to_have":     nice_skills,
        "years_experience": years_experience,
        "salary":           salary,
        "contract_type":    contract,
        "tech_stack":       combined_stacks,
    }