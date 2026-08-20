"""
Canonical Taxonomy and Skill Alias Normalization Service.
Aligns extracted skill entities with standard ESCO and O*NET taxonomies.
"""

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from database import SessionLocal
from entities import SkillAlias, TaxonomyNode
from schemas.analytics import NormalizedSkillItem, TaxonomyNodeResponse


# Default hierarchical taxonomy categories (ESCO / O*NET aligned)
DEFAULT_TAXONOMY_TREE = [
    {
        "code": "CAT-BACKEND",
        "name": "Backend & APIs",
        "type": "category",
        "description": "Server-side architectures, API design, microservices, and backend programming languages.",
        "children": [
            {
                "code": "ESCO-001",
                "name": "Server-Side Programming",
                "type": "esco_skill",
                "description": "Core backend languages (Python, Java, Go, C#, Rust, Node.js)",
            },
            {
                "code": "ESCO-002",
                "name": "API Architecture & Protocols",
                "type": "esco_skill",
                "description": "REST, GraphQL, gRPC, WebSockets, OpenAPI",
            },
        ],
    },
    {
        "code": "CAT-FRONTEND",
        "name": "Frontend & Web",
        "type": "category",
        "description": "Client-side interfaces, web frameworks, responsive UI, and state management.",
        "children": [
            {
                "code": "ESCO-003",
                "name": "Web Frameworks & Libraries",
                "type": "esco_skill",
                "description": "React, Vue, Angular, Next.js, Svelte",
            },
            {
                "code": "ESCO-004",
                "name": "Core Web Technologies",
                "type": "esco_skill",
                "description": "JavaScript, TypeScript, HTML5, CSS3/Tailwind",
            },
        ],
    },
    {
        "code": "CAT-DEVOPS",
        "name": "Cloud & DevOps",
        "type": "category",
        "description": "Cloud infrastructure, containerization, orchestration, and CI/CD automation.",
        "children": [
            {
                "code": "ESCO-005",
                "name": "Containerization & Orchestration",
                "type": "esco_skill",
                "description": "Docker, Kubernetes, Helm, OpenShift",
            },
            {
                "code": "ESCO-006",
                "name": "Cloud Infrastructure Platforms",
                "type": "esco_skill",
                "description": "AWS, GCP, Microsoft Azure, Terraform, Infrastructure as Code",
            },
        ],
    },
    {
        "code": "CAT-DATA-AI",
        "name": "Data & AI",
        "type": "category",
        "description": "Data engineering, machine learning pipelines, deep learning, and generative AI.",
        "children": [
            {
                "code": "ESCO-007",
                "name": "Machine Learning & AI",
                "type": "esco_skill",
                "description": "PyTorch, TensorFlow, Scikit-learn, Large Language Models",
            },
            {
                "code": "ESCO-008",
                "name": "Data Engineering & Analytics",
                "type": "esco_skill",
                "description": "Apache Spark, Pandas, NumPy, Airflow, ETL",
            },
        ],
    },
    {
        "code": "CAT-DATABASE",
        "name": "Databases & Storage",
        "type": "category",
        "description": "Relational, NoSQL, in-memory caching, and distributed message brokers.",
        "children": [
            {
                "code": "ESCO-009",
                "name": "Relational Databases",
                "type": "esco_skill",
                "description": "PostgreSQL, MySQL, Oracle, SQLite",
            },
            {
                "code": "ESCO-010",
                "name": "NoSQL & Distributed Caches",
                "type": "esco_skill",
                "description": "MongoDB, Redis, Elasticsearch, Apache Kafka",
            },
        ],
    },
    {
        "code": "CAT-MOBILE",
        "name": "Mobile Development",
        "type": "category",
        "description": "Native and cross-platform mobile application development.",
        "children": [
            {
                "code": "ESCO-011",
                "name": "Mobile Frameworks",
                "type": "esco_skill",
                "description": "Flutter, React Native, Swift/iOS, Kotlin/Android",
            },
        ],
    },
    {
        "code": "CAT-METHODOLOGY",
        "name": "Methodologies & Soft Skills",
        "type": "category",
        "description": "Software lifecycle methodologies, teamwork, leadership, and communication.",
        "children": [
            {
                "code": "ESCO-012",
                "name": "Agile & Project Delivery",
                "type": "esco_skill",
                "description": "Scrum, Kanban, Agile, CI/CD Workflows",
            },
        ],
    },
]

# Canonical Skill Definitions mapped to aliases and ESCO / O*NET metadata
CANONICAL_SKILL_DEFINITIONS = [
    # Cloud & DevOps
    {
        "canonical_name": "Kubernetes",
        "aliases": ["k8s", "kubernetes", "kube", "k8s cluster", "k8s clusters", "k8s administration"],
        "category": "Cloud & DevOps",
        "esco_uri": "http://data.europa.eu/esco/skill/kubernetes",
        "onet_code": "15-1251.00",
    },
    {
        "canonical_name": "Docker",
        "aliases": ["docker", "dockerfile", "docker compose", "docker-compose", "docker container"],
        "category": "Cloud & DevOps",
        "esco_uri": "http://data.europa.eu/esco/skill/docker",
        "onet_code": "15-1251.00",
    },
    {
        "canonical_name": "Amazon Web Services (AWS)",
        "aliases": ["aws", "amazon web services", "amazon aws", "aws cloud"],
        "category": "Cloud & DevOps",
        "esco_uri": "http://data.europa.eu/esco/skill/aws",
        "onet_code": "15-1251.00",
    },
    {
        "canonical_name": "Google Cloud Platform (GCP)",
        "aliases": ["gcp", "google cloud", "google cloud platform", "google cloud engine"],
        "category": "Cloud & DevOps",
        "esco_uri": "http://data.europa.eu/esco/skill/gcp",
        "onet_code": "15-1251.00",
    },
    {
        "canonical_name": "Microsoft Azure",
        "aliases": ["azure", "ms azure", "microsoft azure", "azure cloud"],
        "category": "Cloud & DevOps",
        "esco_uri": "http://data.europa.eu/esco/skill/azure",
        "onet_code": "15-1251.00",
    },
    {
        "canonical_name": "Terraform",
        "aliases": ["terraform", "iac", "infrastructure as code"],
        "category": "Cloud & DevOps",
        "esco_uri": "http://data.europa.eu/esco/skill/terraform",
        "onet_code": "15-1251.00",
    },
    {
        "canonical_name": "CI/CD",
        "aliases": ["ci/cd", "cicd", "ci-cd", "continuous integration", "github actions", "gitlab ci", "jenkins"],
        "category": "Cloud & DevOps",
        "esco_uri": "http://data.europa.eu/esco/skill/cicd",
        "onet_code": "15-1251.00",
    },
    {
        "canonical_name": "Git",
        "aliases": ["git", "github", "gitlab", "bitbucket", "version control"],
        "category": "Cloud & DevOps",
        "esco_uri": "http://data.europa.eu/esco/skill/git",
        "onet_code": "15-1251.00",
    },
    # Backend & APIs
    {
        "canonical_name": "Python",
        "aliases": ["python", "py", "python3", "python 3", "cpython"],
        "category": "Backend & APIs",
        "esco_uri": "http://data.europa.eu/esco/skill/python",
        "onet_code": "15-1252.00",
    },
    {
        "canonical_name": "FastAPI",
        "aliases": ["fastapi", "fast api", "fast-api"],
        "category": "Backend & APIs",
        "esco_uri": "http://data.europa.eu/esco/skill/fastapi",
        "onet_code": "15-1252.00",
    },
    {
        "canonical_name": "Django",
        "aliases": ["django", "django rest framework", "drf"],
        "category": "Backend & APIs",
        "esco_uri": "http://data.europa.eu/esco/skill/django",
        "onet_code": "15-1252.00",
    },
    {
        "canonical_name": "Flask",
        "aliases": ["flask", "flask-restful"],
        "category": "Backend & APIs",
        "esco_uri": "http://data.europa.eu/esco/skill/flask",
        "onet_code": "15-1252.00",
    },
    {
        "canonical_name": "Node.js",
        "aliases": ["node", "nodejs", "node.js", "node js"],
        "category": "Backend & APIs",
        "esco_uri": "http://data.europa.eu/esco/skill/nodejs",
        "onet_code": "15-1252.00",
    },
    {
        "canonical_name": "Java",
        "aliases": ["java", "java 8", "java 11", "java 17", "java 21", "core java", "openjdk"],
        "category": "Backend & APIs",
        "esco_uri": "http://data.europa.eu/esco/skill/java",
        "onet_code": "15-1252.00",
    },
    {
        "canonical_name": "Spring Boot",
        "aliases": ["spring", "spring boot", "springboot", "spring-boot", "spring framework"],
        "category": "Backend & APIs",
        "esco_uri": "http://data.europa.eu/esco/skill/spring",
        "onet_code": "15-1252.00",
    },
    {
        "canonical_name": "Go",
        "aliases": ["go", "golang", "go-lang"],
        "category": "Backend & APIs",
        "esco_uri": "http://data.europa.eu/esco/skill/golang",
        "onet_code": "15-1252.00",
    },
    {
        "canonical_name": "Rust",
        "aliases": ["rust", "rust-lang", "rustlang"],
        "category": "Backend & APIs",
        "esco_uri": "http://data.europa.eu/esco/skill/rust",
        "onet_code": "15-1252.00",
    },
    {
        "canonical_name": "C# / .NET",
        "aliases": ["c#", "csharp", ".net", "dotnet", ".net core", "asp.net", "asp.net core", "c#.net"],
        "category": "Backend & APIs",
        "esco_uri": "http://data.europa.eu/esco/skill/csharp",
        "onet_code": "15-1252.00",
    },
    {
        "canonical_name": "GraphQL",
        "aliases": ["graphql", "graph-ql", "apollo graphql"],
        "category": "Backend & APIs",
        "esco_uri": "http://data.europa.eu/esco/skill/graphql",
        "onet_code": "15-1252.00",
    },
    {
        "canonical_name": "REST API",
        "aliases": ["rest", "restful", "rest api", "restful api", "apis", "api design"],
        "category": "Backend & APIs",
        "esco_uri": "http://data.europa.eu/esco/skill/rest-api",
        "onet_code": "15-1252.00",
    },
    # Frontend & Web
    {
        "canonical_name": "React",
        "aliases": ["react", "reactjs", "react.js", "react 18", "react hooks"],
        "category": "Frontend & Web",
        "esco_uri": "http://data.europa.eu/esco/skill/react",
        "onet_code": "15-1254.00",
    },
    {
        "canonical_name": "Next.js",
        "aliases": ["next", "nextjs", "next.js", "next 14", "next 15"],
        "category": "Frontend & Web",
        "esco_uri": "http://data.europa.eu/esco/skill/nextjs",
        "onet_code": "15-1254.00",
    },
    {
        "canonical_name": "Vue.js",
        "aliases": ["vue", "vuejs", "vue.js", "vue 3", "vue2", "nuxt", "nuxtjs"],
        "category": "Frontend & Web",
        "esco_uri": "http://data.europa.eu/esco/skill/vuejs",
        "onet_code": "15-1254.00",
    },
    {
        "canonical_name": "Angular",
        "aliases": ["angular", "angularjs", "angular 2+", "angular 17"],
        "category": "Frontend & Web",
        "esco_uri": "http://data.europa.eu/esco/skill/angular",
        "onet_code": "15-1254.00",
    },
    {
        "canonical_name": "TypeScript",
        "aliases": ["ts", "typescript", "type-script"],
        "category": "Frontend & Web",
        "esco_uri": "http://data.europa.eu/esco/skill/typescript",
        "onet_code": "15-1254.00",
    },
    {
        "canonical_name": "JavaScript",
        "aliases": ["js", "javascript", "ecmascript", "es6", "vanilla js"],
        "category": "Frontend & Web",
        "esco_uri": "http://data.europa.eu/esco/skill/javascript",
        "onet_code": "15-1254.00",
    },
    {
        "canonical_name": "HTML5 / CSS3",
        "aliases": ["html", "html5", "css", "css3", "sass", "scss", "tailwind", "tailwindcss"],
        "category": "Frontend & Web",
        "esco_uri": "http://data.europa.eu/esco/skill/html",
        "onet_code": "15-1254.00",
    },
    # Databases & Storage
    {
        "canonical_name": "PostgreSQL",
        "aliases": ["postgres", "postgresql", "pgsql", "postgre", "postgres database"],
        "category": "Databases & Storage",
        "esco_uri": "http://data.europa.eu/esco/skill/postgresql",
        "onet_code": "15-1242.00",
    },
    {
        "canonical_name": "MySQL",
        "aliases": ["mysql", "my-sql", "mariadb"],
        "category": "Databases & Storage",
        "esco_uri": "http://data.europa.eu/esco/skill/mysql",
        "onet_code": "15-1242.00",
    },
    {
        "canonical_name": "MongoDB",
        "aliases": ["mongo", "mongodb", "mongo-db", "nosql mongodb"],
        "category": "Databases & Storage",
        "esco_uri": "http://data.europa.eu/esco/skill/mongodb",
        "onet_code": "15-1242.00",
    },
    {
        "canonical_name": "Redis",
        "aliases": ["redis", "redis-cache", "redis cluster"],
        "category": "Databases & Storage",
        "esco_uri": "http://data.europa.eu/esco/skill/redis",
        "onet_code": "15-1242.00",
    },
    {
        "canonical_name": "Elasticsearch",
        "aliases": ["elasticsearch", "elastic search", "elk", "elastic", "opensearch"],
        "category": "Databases & Storage",
        "esco_uri": "http://data.europa.eu/esco/skill/elasticsearch",
        "onet_code": "15-1242.00",
    },
    {
        "canonical_name": "Apache Kafka",
        "aliases": ["kafka", "apache kafka", "kafka streams"],
        "category": "Databases & Storage",
        "esco_uri": "http://data.europa.eu/esco/skill/kafka",
        "onet_code": "15-1242.00",
    },
    # Data & AI
    {
        "canonical_name": "Machine Learning",
        "aliases": ["ml", "machine learning", "machine-learning", "deep learning", "ai", "artificial intelligence"],
        "category": "Data & AI",
        "esco_uri": "http://data.europa.eu/esco/skill/machine-learning",
        "onet_code": "15-2051.00",
    },
    {
        "canonical_name": "Large Language Models",
        "aliases": ["llm", "llms", "large language models", "generative ai", "genai", "rag", "langchain", "llamaindex"],
        "category": "Data & AI",
        "esco_uri": "http://data.europa.eu/esco/skill/llm",
        "onet_code": "15-2051.00",
    },
    {
        "canonical_name": "PyTorch",
        "aliases": ["pytorch", "torch"],
        "category": "Data & AI",
        "esco_uri": "http://data.europa.eu/esco/skill/pytorch",
        "onet_code": "15-2051.00",
    },
    {
        "canonical_name": "TensorFlow",
        "aliases": ["tensorflow", "tf", "keras"],
        "category": "Data & AI",
        "esco_uri": "http://data.europa.eu/esco/skill/tensorflow",
        "onet_code": "15-2051.00",
    },
    {
        "canonical_name": "Pandas / NumPy",
        "aliases": ["pandas", "numpy", "scipy", "scikit-learn", "sklearn"],
        "category": "Data & AI",
        "esco_uri": "http://data.europa.eu/esco/skill/pandas",
        "onet_code": "15-2051.00",
    },
    {
        "canonical_name": "Apache Spark",
        "aliases": ["spark", "pyspark", "apache spark", "databricks"],
        "category": "Data & AI",
        "esco_uri": "http://data.europa.eu/esco/skill/spark",
        "onet_code": "15-2051.00",
    },
    # Mobile
    {
        "canonical_name": "Flutter",
        "aliases": ["flutter", "dart", "dart/flutter"],
        "category": "Mobile Development",
        "esco_uri": "http://data.europa.eu/esco/skill/flutter",
        "onet_code": "15-1252.00",
    },
    {
        "canonical_name": "Swift / iOS",
        "aliases": ["swift", "ios", "swiftui", "objective-c", "cocoa"],
        "category": "Mobile Development",
        "esco_uri": "http://data.europa.eu/esco/skill/swift",
        "onet_code": "15-1252.00",
    },
    {
        "canonical_name": "Kotlin / Android",
        "aliases": ["kotlin", "android", "jetpack compose", "android sdk"],
        "category": "Mobile Development",
        "esco_uri": "http://data.europa.eu/esco/skill/kotlin",
        "onet_code": "15-1252.00",
    },
    # Methodologies & Soft Skills
    {
        "canonical_name": "Agile / Scrum",
        "aliases": ["agile", "scrum", "kanban", "sprints", "jira"],
        "category": "Methodologies & Soft Skills",
        "esco_uri": "http://data.europa.eu/esco/skill/agile",
        "onet_code": "15-1299.00",
    },
]

# Fast in-memory lookup cache for alias -> metadata
_ALIAS_LOOKUP_CACHE: Dict[str, Dict[str, Any]] = {}


def _init_in_memory_cache():
    """Build the fallback in-memory alias dictionary."""
    global _ALIAS_LOOKUP_CACHE
    if not _ALIAS_LOOKUP_CACHE:
        cache = {}
        for entry in CANONICAL_SKILL_DEFINITIONS:
            canon = entry["canonical_name"]
            cat = entry["category"]
            esco = entry.get("esco_uri")
            onet = entry.get("onet_code")
            meta = {
                "canonical_name": canon,
                "category": cat,
                "esco_uri": esco,
                "onet_code": onet,
            }
            # Also register the canonical name itself (lowercased)
            cache[canon.lower()] = meta
            for alias in entry["aliases"]:
                cache[alias.strip().lower()] = meta
        _ALIAS_LOOKUP_CACHE = cache


_init_in_memory_cache()


def seed_default_taxonomy(db: Session) -> Dict[str, int]:
    """
    Idempotently seeds default taxonomy categories and skill aliases into the database.
    """
    _init_in_memory_cache()
    nodes_created = 0
    aliases_created = 0

    # 1. Seed Taxonomy Nodes
    for root_cat in DEFAULT_TAXONOMY_TREE:
        existing_root = db.scalar(
            select(TaxonomyNode).where(TaxonomyNode.code == root_cat["code"])
        )
        if not existing_root:
            existing_root = TaxonomyNode(
                code=root_cat["code"],
                name=root_cat["name"],
                type=root_cat["type"],
                description=root_cat.get("description"),
                parent_id=None,
            )
            db.add(existing_root)
            db.flush()
            nodes_created += 1

        # Seed children if present
        for child in root_cat.get("children", []):
            existing_child = db.scalar(
                select(TaxonomyNode).where(TaxonomyNode.code == child["code"])
            )
            if not existing_child:
                new_child = TaxonomyNode(
                    code=child["code"],
                    name=child["name"],
                    type=child["type"],
                    description=child.get("description"),
                    parent_id=existing_root.id,
                )
                db.add(new_child)
                nodes_created += 1

    # 2. Seed Skill Aliases
    seen_aliases = set()
    for entry in CANONICAL_SKILL_DEFINITIONS:
        canon = entry["canonical_name"]
        cat = entry["category"]
        esco = entry.get("esco_uri")
        onet = entry.get("onet_code")

        all_aliases = set(entry["aliases"])
        all_aliases.add(canon.lower())

        for alias_str in all_aliases:
            alias_clean = alias_str.strip().lower()
            if not alias_clean or alias_clean in seen_aliases:
                continue
            seen_aliases.add(alias_clean)
            existing = db.scalar(
                select(SkillAlias).where(SkillAlias.alias == alias_clean)
            )
            if not existing:
                alias_obj = SkillAlias(
                    alias=alias_clean,
                    canonical_name=canon,
                    category=cat,
                    esco_uri=esco,
                    onet_code=onet,
                )
                db.add(alias_obj)
                aliases_created += 1

    db.commit()
    return {"nodes_created": nodes_created, "aliases_created": aliases_created}


def normalize_skill(skill: str, db: Optional[Session] = None) -> NormalizedSkillItem:
    """
    Normalizes a single skill string to its canonical ESCO / O*NET representation.
    """
    if not skill or not skill.strip():
        return NormalizedSkillItem(
            raw_skill=skill,
            canonical_name=skill,
            category="technical",
        )

    clean_raw = skill.strip()
    clean_lower = clean_raw.lower()

    # 1. DB Lookup if session provided
    if db is not None:
        alias_record = db.scalar(
            select(SkillAlias).where(SkillAlias.alias == clean_lower)
        )
        if alias_record:
            return NormalizedSkillItem(
                raw_skill=clean_raw,
                canonical_name=alias_record.canonical_name,
                category=alias_record.category,
                esco_uri=alias_record.esco_uri,
                onet_code=alias_record.onet_code,
            )

    # 2. In-memory fallback lookup
    _init_in_memory_cache()
    if clean_lower in _ALIAS_LOOKUP_CACHE:
        info = _ALIAS_LOOKUP_CACHE[clean_lower]
        return NormalizedSkillItem(
            raw_skill=clean_raw,
            canonical_name=info["canonical_name"],
            category=info["category"],
            esco_uri=info.get("esco_uri"),
            onet_code=info.get("onet_code"),
        )

    # 3. Default fallback: Cleaned raw name
    return NormalizedSkillItem(
        raw_skill=clean_raw,
        canonical_name=clean_raw.title() if len(clean_raw) > 3 else clean_raw.upper(),
        category="technical",
        esco_uri=None,
        onet_code=None,
    )


def normalize_skills(skills: List[str], db: Optional[Session] = None) -> List[NormalizedSkillItem]:
    """
    Batch normalizes a list of skills, preserving raw values while mapping to canonical entities.
    """
    results: List[NormalizedSkillItem] = []
    seen_canonical = set()

    for s in skills:
        norm = normalize_skill(s, db=db)
        if norm.canonical_name not in seen_canonical:
            results.append(norm)
            seen_canonical.add(norm.canonical_name)

    return results


def get_canonical_alias_map(db: Optional[Session] = None) -> Dict[str, Dict[str, Any]]:
    """
    Returns a full dictionary of alias_lower -> metadata.
    """
    _init_in_memory_cache()
    alias_map = dict(_ALIAS_LOOKUP_CACHE)

    if db is not None:
        db_aliases = db.scalars(select(SkillAlias)).all()
        for rec in db_aliases:
            alias_map[rec.alias.lower()] = {
                "canonical_name": rec.canonical_name,
                "category": rec.category,
                "esco_uri": rec.esco_uri,
                "onet_code": rec.onet_code,
            }

    return alias_map


def get_taxonomy_tree(db: Session) -> List[TaxonomyNodeResponse]:
    """
    Retrieves the full hierarchical taxonomy tree with nested children.
    """
    # Ensure taxonomy is seeded
    total_nodes = db.scalar(select(TaxonomyNode.id))
    if not total_nodes:
        seed_default_taxonomy(db)

    # Fetch all root nodes (parent_id is NULL)
    roots = db.scalars(
        select(TaxonomyNode).where(TaxonomyNode.parent_id.is_(None)).order_by(TaxonomyNode.id)
    ).all()

    result = []
    for root in roots:
        children_nodes = [
            TaxonomyNodeResponse(
                id=c.id,
                code=c.code,
                name=c.name,
                type=c.type,
                description=c.description,
                parent_id=c.parent_id,
                children=[],
            )
            for c in (root.children or [])
        ]
        result.append(
            TaxonomyNodeResponse(
                id=root.id,
                code=root.code,
                name=root.name,
                type=root.type,
                description=root.description,
                parent_id=root.parent_id,
                children=children_nodes,
            )
        )

    return result
