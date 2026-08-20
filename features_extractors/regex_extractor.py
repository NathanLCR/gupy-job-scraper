"""
Tier 1 High-Speed Exact Skill & Entity Extractor.
Uses an expanded Aho-Corasick Trie and compiled regular expressions
covering 300+ tech terms, cloud providers, frameworks, and certifications (<5ms).
"""

import collections
import html
import re
from typing import Any, Dict, List, Optional, Set, Tuple


# ==============================================================================
# SECTION HEADERS & CONTEXT BOUNDARIES
# ==============================================================================

_SEC_MANDATORY = (
    r'(?:'
    r'Requisitos\s+(?:e\s+qualifica[çc][õo]es|Obrigat[óo]rios?|T[ée]cnicos?)'
    r'|O\s+que\s+esperamos\s+de\s+voc[êe]'
    r'|O\s+que\s+voc[êe]\s+precisa\s+ter'
    r'|Requirements|Required\s+Skills|Mandatory\s+Requirements'
    r'|What\s+you\s+need|What\s+we\s+expect'
    r'|Requisitos?:?'
    r')'
)

_SEC_NICE = (
    r'(?:'
    r'Diferenciais?\s+(?:Valorizados?|Desej[áa]veis?)?'
    r'|Requisitos\s+Desej[áa]veis?'
    r'|Habilidades?\s+Desej[áa]veis?'
    r'|Voc[êe]\s+se\s+destacar[áa]\s+se\s+tiver'
    r'|Nice\s+to\s+have|Preferred\s+Skills|Bonus\s+Points|Desirable'
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
    r'|Behavioral\s+Skills|Interpersonal\s+Skills'
    r')'
)

_SEC_ADD = r'(?:Informa[çc][õo]es\s+adicionais|Additional\s+Information|Benef[íi]cios|Benefits)'

RE_EXPERIENCE = re.compile(
    r'(?:M[íi]nimo\s+de\s+|Minimum\s+of\s+|At\s+least\s+)?'
    r'(\d+)\s*'
    r'(?:a\s+(\d+)|to\s+(\d+))?\s*'
    r'\+?\s*'
    r'(?:anos?|years?)\s+(?:de\s+experi[êe]ncia|of\s+experience)'
    r'(?:\s+(?:com|em|como|with|in)\s+(?P<ctx>[^,\.;\n]{0,60}))?',
    re.I,
)

RE_SALARY = re.compile(
    r'(?:'
    r'(?:R\$|\$|€|£)\s*[\d\.,]+(?:\s*[-–—to\s]+\s*(?:R\$|\$|€|£)?\s*[\d\.,]+)?'
    r'|(?:sal[áa]rio|salary|bolsa|remuner[aação]{3,9}|compensation|pay)'
    r'[^R\$€£\n]{0,40}'
    r'(?:(?:R\$|\$|€|£)\s*[\d\.,]+|a\s+combinar|competitive|negotiable)'
    r')',
    re.I,
)

RE_CONTRACT = re.compile(
    r'(?:[Cc]ontrata[çc][ãaAÃ][oO]|[Cc]ontract\s*[Tt]ype)\s*:\s*'
    r'([A-Za-zÀ-ú \(\)/\-]+?)'
    r'(?=\s*[;\n\d]|\s{2,}|\s+[A-ZÁÉÍÓÚ]{2}|$)'
)

RE_SENIORITY = re.compile(
    r'\b('
    r'Estagi[áa]r?io|Intern(?:ship)?|'
    r'J[úu]nior|Jr\.?|Junior|'
    r'Pleno|Pl\.?|Mid(?:-|\s*)Level|'
    r'S[êe]nior|Sr\.?|Senior|'
    r'Especialista|Specialist|Staff|'
    r'Consultor|Consultant|'
    r'Lideran[çc]a|Tech\s+Lead|Team\s+Lead|Lead|'
    r'Principal|Architect|Arquiteto|'
    r'Gerente|Manager|Engineering\s+Manager|Diretor|Director|VP|Head'
    r')\b',
    re.I,
)

RE_SOFT = re.compile(
    r'(?<!\w)('
    r'comunica[çc][aã]o\s*(?:clara|eficaz|assertiva)?|communication'
    r'|lideran[çc]a|leadership'
    r'|trabalho\s+em\s+equipe|teamwork|team\s+player'
    r'|autonomia|autonomy'
    r'|proatividade|proativo|proactive|proactivity'
    r'|organiza[çc][aã]o|organization|organizational\s+skills'
    r'|criatividade|creativity|creative'
    r'|inova[çc][aã]o|innovation|innovative'
    r'|gest[aã]o\s+do\s+tempo|time\s+management'
    r'|flexibilidade|flexibility|adaptability|adaptabilidade'
    r'|empatia|empathy'
    r'|colabora[çc][aã]o|collaboration|collaborative'
    r'|mentor(?:ia)?|mentorship|mentoring'
    r'|resolu[çc][aã]o\s+de\s+problemas|problem\s+solving'
    r'|pensamento\s+cr[íi]tico|critical\s+thinking'
    r'|intelig[êe]ncia\s+emocional|emotional\s+intelligence'
    r'|bom\s+humor'
    r'|protagonismo|ownership|senso\s+de\s+dono'
    r'|perfil\s+anal[íi]tico|analytical\s+skills|analytical\s+thinking'
    r'|negotiation|negocia[çc][aã]o'
    r'|resilience|resili[êe]ncia'
    r')(?!\w)',
    re.I,
)


# ==============================================================================
# 300+ CANONICAL TECH SKILLS, CLOUD, FRAMEWORKS, DEVOPS & CERTIFICATIONS
# ==============================================================================

_CANON: dict[str, str] = {
    # Programming Languages
    "python": "python",
    "py": "python",
    "javascript": "javascript",
    "js": "javascript",
    "typescript": "typescript",
    "ts": "typescript",
    "java": "java",
    "c#": "csharp",
    "csharp": "csharp",
    "c++": "cpp",
    "cpp": "cpp",
    "c": "c",
    ".net": "dotnet",
    "dotnet": "dotnet",
    "asp.net": "aspnet",
    "aspnet": "aspnet",
    "php": "php",
    "ruby": "ruby",
    "go": "go",
    "golang": "go",
    "kotlin": "kotlin",
    "swift": "swift",
    "rust": "rust",
    "scala": "scala",
    "r": "r",
    "dart": "dart",
    "elixir": "elixir",
    "clojure": "clojure",
    "haskell": "haskell",
    "lua": "lua",
    "julia": "julia",
    "perl": "perl",
    "solidity": "solidity",
    "shell": "shell",
    "bash": "bash",
    "powershell": "powershell",
    "sql": "sql",
    "html": "html",
    "html5": "html",
    "css": "css",
    "css3": "css",
    "sass": "sass",
    "scss": "sass",
    "graphql": "graphql",

    # Frontend Frameworks & Libraries
    "react": "react",
    "react.js": "react",
    "reactjs": "react",
    "react native": "react-native",
    "react-native": "react-native",
    "angular": "angular",
    "angular.js": "angular",
    "angularjs": "angular",
    "angular 2+": "angular",
    "vue": "vue",
    "vue.js": "vue",
    "vuejs": "vue",
    "vue 3": "vue",
    "next": "nextjs",
    "next.js": "nextjs",
    "nextjs": "nextjs",
    "nuxt": "nuxtjs",
    "nuxt.js": "nuxtjs",
    "nuxtjs": "nuxtjs",
    "svelte": "svelte",
    "sveltekit": "sveltekit",
    "solidjs": "solidjs",
    "solid.js": "solidjs",
    "astro": "astro",
    "remix": "remix",
    "gatsby": "gatsby",
    "flutter": "flutter",
    "ionic": "ionic",
    "electron": "electron",
    "tauri": "tauri",
    "swiftui": "swiftui",
    "jetpack compose": "jetpack-compose",

    # Styling & UI Components
    "tailwind": "tailwindcss",
    "tailwind css": "tailwindcss",
    "tailwindcss": "tailwindcss",
    "bootstrap": "bootstrap",
    "material ui": "material-ui",
    "mui": "material-ui",
    "chakra ui": "chakra-ui",
    "ant design": "ant-design",
    "shadcn": "shadcn-ui",
    "shadcn ui": "shadcn-ui",
    "styled components": "styled-components",
    "styled-components": "styled-components",
    "emotion": "emotion",
    "design system": "design-system",
    "design systems": "design-system",
    "figma": "figma",
    "sketch": "sketch",
    "storybook": "storybook",

    # State Management & Frontend Tools
    "redux": "redux",
    "redux toolkit": "redux-toolkit",
    "rtk": "redux-toolkit",
    "zustand": "zustand",
    "mobx": "mobx",
    "recoil": "recoil",
    "pinia": "pinia",
    "vuex": "vuex",
    "rxjs": "rxjs",
    "vite": "vite",
    "webpack": "webpack",
    "rollup": "rollup",
    "parcel": "parcel",
    "babel": "babel",
    "esbuild": "esbuild",
    "turbopack": "turbopack",
    "microfrontends": "microfrontends",
    "micro-frontends": "microfrontends",

    # Backend Frameworks
    "node": "nodejs",
    "node.js": "nodejs",
    "nodejs": "nodejs",
    "nodej": "nodejs",
    "express": "express",
    "express.js": "express",
    "nestjs": "nestjs",
    "nest.js": "nestjs",
    "fastify": "fastify",
    "koa": "koa",
    "django": "django",
    "flask": "flask",
    "fastapi": "fastapi",
    "celery": "celery",
    "tornado": "tornado",
    "spring": "spring",
    "spring boot": "spring-boot",
    "spring-boot": "spring-boot",
    "spring cloud": "spring-cloud",
    "quarkus": "quarkus",
    "micronaut": "micronaut",
    "laravel": "laravel",
    "symfony": "symfony",
    "rails": "rails",
    "ruby on rails": "rails",
    "sinatra": "sinatra",
    "phoenix": "phoenix",
    "gin": "gin",
    "echo": "echo",
    "fiber": "fiber",
    "actix": "actix",
    "actix-web": "actix",
    "axum": "axum",
    "rocket": "rocket",

    # APIs, Communication & Protocols
    "rest": "rest-api",
    "rest api": "rest-api",
    "apis rest": "rest-api",
    "restful": "rest-api",
    "grpc": "grpc",
    "trpc": "trpc",
    "soap": "soap",
    "websocket": "websockets",
    "websockets": "websockets",
    "web services": "web-services",
    "openapi": "openapi",
    "swagger": "swagger",

    # ORMs & Data Access
    "prisma": "prisma",
    "typeorm": "typeorm",
    "drizzle": "drizzle-orm",
    "drizzle orm": "drizzle-orm",
    "hibernate": "hibernate",
    "jpa": "jpa",
    "entity framework": "entity-framework",
    "ef core": "entity-framework",
    "sqlalchemy": "sqlalchemy",
    "alembic": "alembic",
    "mongoose": "mongoose",

    # Relational & NoSQL Databases
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "mysql": "mysql",
    "mariadb": "mariadb",
    "sqlite": "sqlite",
    "oracle": "oracle",
    "oracle database": "oracle",
    "sql server": "sql-server",
    "mssql": "sql-server",
    "mongodb": "mongodb",
    "mongo": "mongodb",
    "redis": "redis",
    "memcached": "memcached",
    "cassandra": "cassandra",
    "dynamodb": "dynamodb",
    "couchdb": "couchdb",
    "couchbase": "couchbase",
    "neo4j": "neo4j",
    "cockroachdb": "cockroachdb",
    "tidb": "tidb",
    "supabase": "supabase",
    "firebase": "firebase",

    # Data Warehouses, Big Data & Analytics
    "snowflake": "snowflake",
    "bigquery": "bigquery",
    "redshift": "redshift",
    "clickhouse": "clickhouse",
    "databricks": "databricks",
    "spark": "spark",
    "apache spark": "spark",
    "pyspark": "pyspark",
    "hadoop": "hadoop",
    "apache hadoop": "hadoop",
    "hive": "hive",
    "flink": "flink",
    "apache flink": "flink",
    "beam": "beam",
    "apache beam": "beam",
    "dbt": "dbt",
    "airflow": "airflow",
    "apache airflow": "airflow",
    "prefect": "prefect",
    "dagster": "dagster",
    "luigi": "luigi",
    "trino": "trino",
    "presto": "presto",
    "kafka": "kafka",
    "apache kafka": "kafka",
    "rabbitmq": "rabbitmq",
    "nats": "nats",
    "pulsar": "pulsar",
    "kinesis": "aws-kinesis",

    # Vector Databases & Search Engines
    "elasticsearch": "elasticsearch",
    "opensearch": "opensearch",
    "solr": "solr",
    "pgvector": "pgvector",
    "pinecone": "pinecone",
    "milvus": "milvus",
    "qdrant": "qdrant",
    "chromadb": "chromadb",
    "chroma": "chromadb",
    "weaviate": "weaviate",
    "faiss": "faiss",

    # Cloud Providers & Services
    "aws": "aws",
    "amazon web services": "aws",
    "azure": "azure",
    "microsoft azure": "azure",
    "gcp": "gcp",
    "google cloud": "gcp",
    "google cloud platform": "gcp",
    "oci": "oci",
    "oracle cloud": "oci",
    "alibaba cloud": "alibaba-cloud",
    "ibm cloud": "ibm-cloud",
    "digitalocean": "digitalocean",
    "heroku": "heroku",
    "vercel": "vercel",
    "netlify": "netlify",
    "cloudflare": "cloudflare",
    "lambda": "aws-lambda",
    "aws lambda": "aws-lambda",
    "s3": "aws-s3",
    "ec2": "aws-ec2",
    "ecs": "aws-ecs",
    "eks": "aws-eks",
    "sqs": "aws-sqs",
    "sns": "aws-sns",
    "cloudwatch": "aws-cloudwatch",

    # DevOps, Containers & Infrastructure
    "docker": "docker",
    "docker compose": "docker-compose",
    "kubernetes": "kubernetes",
    "k8s": "kubernetes",
    "helm": "helm",
    "openshift": "openshift",
    "podman": "podman",
    "nomad": "nomad",
    "rancher": "rancher",
    "istio": "istio",
    "linkerd": "linkerd",
    "envoy": "envoy",
    "nginx": "nginx",
    "apache": "apache",
    "traefik": "traefik",
    "caddy": "caddy",
    "tomcat": "tomcat",
    "terraform": "terraform",
    "terragrunt": "terragrunt",
    "ansible": "ansible",
    "pulumi": "pulumi",
    "puppet": "puppet",
    "chef": "chef",
    "cloudformation": "cloudformation",
    "bicep": "bicep",
    "vagrant": "vagrant",
    "linux": "linux",
    "unix": "unix",
    "ubuntu": "ubuntu",
    "debian": "debian",
    "centos": "centos",
    "rhel": "rhel",
    "alpine": "alpine",

    # CI/CD & Build Tools
    "ci/cd": "cicd",
    "ci-cd": "cicd",
    "cicd": "cicd",
    "continuous integration": "cicd",
    "jenkins": "jenkins",
    "github actions": "github-actions",
    "gitlab ci": "gitlab-ci",
    "gitlab-ci": "gitlab-ci",
    "argocd": "argocd",
    "circleci": "circleci",
    "travis ci": "travis-ci",
    "bitbucket pipelines": "bitbucket-pipelines",
    "azure devops": "azure-devops",
    "tekton": "tekton",
    "spinnaker": "spinnaker",
    "maven": "maven",
    "gradle": "gradle",
    "ant": "ant",
    "xcode": "xcode",
    "testflight": "testflight",

    # Version Control & Collaboration
    "git": "git",
    "github": "github",
    "gitlab": "gitlab",
    "bitbucket": "bitbucket",
    "gitflow": "gitflow",
    "jira": "jira",
    "confluence": "confluence",
    "trello": "trello",
    "linear": "linear",
    "asana": "asana",
    "notion": "notion",

    # AI, ML & Data Science
    "tensorflow": "tensorflow",
    "pytorch": "pytorch",
    "keras": "keras",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "xgboost": "xgboost",
    "lightgbm": "lightgbm",
    "catboost": "catboost",
    "opencv": "opencv",
    "pandas": "pandas",
    "numpy": "numpy",
    "scipy": "scipy",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "plotly": "plotly",
    "nltk": "nltk",
    "spacy": "spacy",
    "hugging face": "hugging-face",
    "huggingface": "hugging-face",
    "transformers": "transformers",
    "langchain": "langchain",
    "langgraph": "langgraph",
    "llamaindex": "llamaindex",
    "ollama": "ollama",
    "vllm": "vllm",
    "mlflow": "mlflow",
    "kubeflow": "kubeflow",
    "wandb": "wandb",
    "weights & biases": "wandb",
    "machine learning": "machine-learning",
    "deep learning": "deep-learning",
    "nlp": "nlp",
    "computer vision": "computer-vision",
    "llm": "llm",
    "llms": "llm",
    "genai": "generative-ai",
    "generative ai": "generative-ai",
    "rag": "rag",

    # Testing & QA
    "selenium": "selenium",
    "cypress": "cypress",
    "playwright": "playwright",
    "jest": "jest",
    "vitest": "vitest",
    "mocha": "mocha",
    "chai": "chai",
    "jasmine": "jasmine",
    "pytest": "pytest",
    "unittest": "unittest",
    "junit": "junit",
    "testng": "testng",
    "mockito": "mockito",
    "robot framework": "robot-framework",
    "postman": "postman",
    "insomnia": "insomnia",
    "jmeter": "jmeter",
    "k6": "k6",
    "sonarqube": "sonarqube",
    "appium": "appium",
    "cucumber": "cucumber",

    # Security & Identity
    "jwt": "jwt",
    "oauth": "oauth",
    "oauth2": "oauth",
    "oauth 2.0": "oauth",
    "openid connect": "openid-connect",
    "oidc": "openid-connect",
    "saml": "saml",
    "nextauth": "nextauth",
    "nextauth.js": "nextauth",
    "keycloak": "keycloak",
    "auth0": "auth0",
    "okta": "okta",
    "vault": "hashicorp-vault",
    "hashicorp vault": "hashicorp-vault",
    "cyberark": "cyberark",
    "splunk": "splunk",
    "datadog": "datadog",
    "grafana": "grafana",
    "prometheus": "prometheus",
    "new relic": "new-relic",
    "dynatrace": "dynatrace",
    "owasp": "owasp",
    "soc 2": "soc-2",

    # Architecture & Paradigms
    "clean architecture": "clean-architecture",
    "solid": "solid",
    "ddd": "ddd",
    "tdd": "tdd",
    "bdd": "bdd",
    "microservices": "microservices",
    "serverless": "serverless",
    "event-driven": "event-driven",
    "design patterns": "design-patterns",
    "scrum": "scrum",
    "kanban": "kanban",
    "agile": "agile",

    # Enterprise & ERP
    "sap": "sap",
    "sap erp": "sap",
    "sap pi/po": "sap",
    "salesforce": "salesforce",
    "google analytics": "google-analytics",
    "ga": "google-analytics",

    # Certifications
    "aws solutions architect": "cert-aws-solutions-architect",
    "aws certified solutions architect": "cert-aws-solutions-architect",
    "aws certified developer": "cert-aws-developer",
    "aws certified devops": "cert-aws-devops",
    "azure solutions architect": "cert-azure-solutions-architect",
    "azure devops engineer": "cert-azure-devops",
    "gcp cloud architect": "cert-gcp-architect",
    "cka": "cert-cka",
    "ckad": "cert-ckad",
    "cissp": "cert-cissp",
    "ceh": "cert-ceh",
    "comptia security+": "cert-comptia-secplus",
    "pmp": "cert-pmp",
    "scrum master": "cert-scrum-master",
    "psm": "cert-scrum-master",
    "csm": "cert-scrum-master",
}

_DISPLAY: dict[str, str] = {
    # Languages
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "java": "Java",
    "csharp": "C#",
    "cpp": "C++",
    "c": "C",
    "dotnet": ".NET",
    "aspnet": "ASP.NET",
    "php": "PHP",
    "ruby": "Ruby",
    "go": "Go",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "rust": "Rust",
    "scala": "Scala",
    "r": "R",
    "dart": "Dart",
    "elixir": "Elixir",
    "clojure": "Clojure",
    "haskell": "Haskell",
    "lua": "Lua",
    "julia": "Julia",
    "perl": "Perl",
    "solidity": "Solidity",
    "shell": "Shell",
    "bash": "Bash",
    "powershell": "PowerShell",
    "sql": "SQL",
    "html": "HTML",
    "css": "CSS",
    "sass": "SASS",
    "graphql": "GraphQL",

    # Frontend
    "react": "React",
    "react-native": "React Native",
    "angular": "Angular",
    "vue": "Vue.js",
    "nextjs": "Next.js",
    "nuxtjs": "Nuxt.js",
    "svelte": "Svelte",
    "sveltekit": "SvelteKit",
    "solidjs": "Solid.js",
    "astro": "Astro",
    "remix": "Remix",
    "gatsby": "Gatsby",
    "flutter": "Flutter",
    "ionic": "Ionic",
    "electron": "Electron",
    "tauri": "Tauri",
    "swiftui": "SwiftUI",
    "jetpack-compose": "Jetpack Compose",
    "tailwindcss": "Tailwind CSS",
    "bootstrap": "Bootstrap",
    "material-ui": "Material UI",
    "chakra-ui": "Chakra UI",
    "ant-design": "Ant Design",
    "shadcn-ui": "shadcn/ui",
    "styled-components": "Styled Components",
    "emotion": "Emotion",
    "design-system": "Design System",
    "figma": "Figma",
    "sketch": "Sketch",
    "storybook": "Storybook",
    "redux": "Redux",
    "redux-toolkit": "Redux Toolkit",
    "zustand": "Zustand",
    "mobx": "MobX",
    "recoil": "Recoil",
    "pinia": "Pinia",
    "vuex": "Vuex",
    "rxjs": "RxJS",
    "vite": "Vite",
    "webpack": "Webpack",
    "rollup": "Rollup",
    "parcel": "Parcel",
    "babel": "Babel",
    "esbuild": "esbuild",
    "turbopack": "Turbopack",
    "microfrontends": "Microfrontends",

    # Backend
    "nodejs": "Node.js",
    "express": "Express.js",
    "nestjs": "NestJS",
    "fastify": "Fastify",
    "koa": "Koa",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "celery": "Celery",
    "tornado": "Tornado",
    "spring": "Spring",
    "spring-boot": "Spring Boot",
    "spring-cloud": "Spring Cloud",
    "quarkus": "Quarkus",
    "micronaut": "Micronaut",
    "laravel": "Laravel",
    "symfony": "Symfony",
    "rails": "Ruby on Rails",
    "sinatra": "Sinatra",
    "phoenix": "Phoenix",
    "gin": "Gin",
    "echo": "Echo",
    "fiber": "Fiber",
    "actix": "Actix",
    "axum": "Axum",
    "rocket": "Rocket",
    "rest-api": "REST API",
    "grpc": "gRPC",
    "trpc": "tRPC",
    "soap": "SOAP",
    "websockets": "WebSockets",
    "web-services": "Web Services",
    "openapi": "OpenAPI",
    "swagger": "Swagger",
    "prisma": "Prisma",
    "typeorm": "TypeORM",
    "drizzle-orm": "Drizzle ORM",
    "hibernate": "Hibernate",
    "jpa": "JPA",
    "entity-framework": "Entity Framework",
    "sqlalchemy": "SQLAlchemy",
    "alembic": "Alembic",
    "mongoose": "Mongoose",

    # DB & Data
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mariadb": "MariaDB",
    "sqlite": "SQLite",
    "oracle": "Oracle",
    "sql-server": "SQL Server",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "memcached": "Memcached",
    "cassandra": "Cassandra",
    "dynamodb": "DynamoDB",
    "couchdb": "CouchDB",
    "couchbase": "Couchbase",
    "neo4j": "Neo4j",
    "cockroachdb": "CockroachDB",
    "tidb": "TiDB",
    "supabase": "Supabase",
    "firebase": "Firebase",
    "snowflake": "Snowflake",
    "bigquery": "BigQuery",
    "redshift": "Amazon Redshift",
    "clickhouse": "ClickHouse",
    "databricks": "Databricks",
    "spark": "Spark",
    "pyspark": "PySpark",
    "hadoop": "Hadoop",
    "hive": "Hive",
    "flink": "Flink",
    "beam": "Apache Beam",
    "dbt": "dbt",
    "airflow": "Airflow",
    "prefect": "Prefect",
    "dagster": "Dagster",
    "luigi": "Luigi",
    "trino": "Trino",
    "presto": "Presto",
    "kafka": "Kafka",
    "rabbitmq": "RabbitMQ",
    "nats": "NATS",
    "pulsar": "Apache Pulsar",
    "aws-kinesis": "AWS Kinesis",

    # Vector DB & Search
    "elasticsearch": "Elasticsearch",
    "opensearch": "OpenSearch",
    "solr": "Solr",
    "pgvector": "pgvector",
    "pinecone": "Pinecone",
    "milvus": "Milvus",
    "qdrant": "Qdrant",
    "chromadb": "ChromaDB",
    "weaviate": "Weaviate",
    "faiss": "FAISS",

    # Cloud & DevOps
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "Google Cloud",
    "oci": "Oracle Cloud",
    "alibaba-cloud": "Alibaba Cloud",
    "ibm-cloud": "IBM Cloud",
    "digitalocean": "DigitalOcean",
    "heroku": "Heroku",
    "vercel": "Vercel",
    "netlify": "Netlify",
    "cloudflare": "Cloudflare",
    "aws-lambda": "AWS Lambda",
    "aws-s3": "Amazon S3",
    "aws-ec2": "Amazon EC2",
    "aws-ecs": "Amazon ECS",
    "aws-eks": "Amazon EKS",
    "aws-sqs": "Amazon SQS",
    "aws-sns": "Amazon SNS",
    "aws-cloudwatch": "CloudWatch",
    "docker": "Docker",
    "docker-compose": "Docker Compose",
    "kubernetes": "Kubernetes",
    "helm": "Helm",
    "openshift": "OpenShift",
    "podman": "Podman",
    "nomad": "Nomad",
    "rancher": "Rancher",
    "istio": "Istio",
    "linkerd": "Linkerd",
    "envoy": "Envoy",
    "nginx": "Nginx",
    "apache": "Apache",
    "traefik": "Traefik",
    "caddy": "Caddy",
    "tomcat": "Tomcat",
    "terraform": "Terraform",
    "terragrunt": "Terragrunt",
    "ansible": "Ansible",
    "pulumi": "Pulumi",
    "puppet": "Puppet",
    "chef": "Chef",
    "cloudformation": "CloudFormation",
    "bicep": "Bicep",
    "vagrant": "Vagrant",
    "linux": "Linux",
    "unix": "Unix",
    "ubuntu": "Ubuntu",
    "debian": "Debian",
    "centos": "CentOS",
    "rhel": "RHEL",
    "alpine": "Alpine Linux",
    "cicd": "CI/CD",
    "jenkins": "Jenkins",
    "github-actions": "GitHub Actions",
    "gitlab-ci": "GitLab CI",
    "argocd": "ArgoCD",
    "circleci": "CircleCI",
    "travis-ci": "Travis CI",
    "bitbucket-pipelines": "Bitbucket Pipelines",
    "azure-devops": "Azure DevOps",
    "tekton": "Tekton",
    "spinnaker": "Spinnaker",
    "maven": "Maven",
    "gradle": "Gradle",
    "ant": "Ant",
    "xcode": "Xcode",
    "testflight": "TestFlight",
    "git": "Git",
    "github": "GitHub",
    "gitlab": "GitLab",
    "bitbucket": "Bitbucket",
    "gitflow": "Gitflow",
    "jira": "Jira",
    "confluence": "Confluence",
    "trello": "Trello",
    "linear": "Linear",
    "asana": "Asana",
    "notion": "Notion",

    # AI/ML
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "keras": "Keras",
    "scikit-learn": "scikit-learn",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "catboost": "CatBoost",
    "opencv": "OpenCV",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "scipy": "SciPy",
    "matplotlib": "Matplotlib",
    "seaborn": "Seaborn",
    "plotly": "Plotly",
    "nltk": "NLTK",
    "spacy": "spaCy",
    "hugging-face": "Hugging Face",
    "transformers": "Transformers",
    "langchain": "LangChain",
    "langgraph": "LangGraph",
    "llamaindex": "LlamaIndex",
    "ollama": "Ollama",
    "vllm": "vLLM",
    "mlflow": "MLflow",
    "kubeflow": "Kubeflow",
    "wandb": "Weights & Biases",
    "machine-learning": "Machine Learning",
    "deep-learning": "Deep Learning",
    "nlp": "NLP",
    "computer-vision": "Computer Vision",
    "llm": "LLMs",
    "generative-ai": "Generative AI",
    "rag": "RAG",

    # Testing & Security
    "selenium": "Selenium",
    "cypress": "Cypress",
    "playwright": "Playwright",
    "jest": "Jest",
    "vitest": "Vitest",
    "mocha": "Mocha",
    "chai": "Chai",
    "jasmine": "Jasmine",
    "pytest": "Pytest",
    "unittest": "unittest",
    "junit": "JUnit",
    "testng": "TestNG",
    "mockito": "Mockito",
    "robot-framework": "Robot Framework",
    "postman": "Postman",
    "insomnia": "Insomnia",
    "jmeter": "JMeter",
    "k6": "k6",
    "sonarqube": "SonarQube",
    "appium": "Appium",
    "cucumber": "Cucumber",
    "jwt": "JWT",
    "oauth": "OAuth",
    "openid-connect": "OpenID Connect",
    "saml": "SAML",
    "nextauth": "NextAuth.js",
    "keycloak": "Keycloak",
    "auth0": "Auth0",
    "okta": "Okta",
    "hashicorp-vault": "Vault",
    "cyberark": "CyberArk",
    "splunk": "Splunk",
    "datadog": "Datadog",
    "grafana": "Grafana",
    "prometheus": "Prometheus",
    "new-relic": "New Relic",
    "dynatrace": "Dynatrace",
    "owasp": "OWASP",
    "soc-2": "SOC 2",
    "clean-architecture": "Clean Architecture",
    "solid": "SOLID",
    "ddd": "DDD",
    "tdd": "TDD",
    "bdd": "BDD",
    "microservices": "Microservices",
    "serverless": "Serverless",
    "event-driven": "Event-Driven Architecture",
    "design-patterns": "Design Patterns",
    "scrum": "Scrum",
    "kanban": "Kanban",
    "agile": "Agile",
    "sap": "SAP",
    "salesforce": "Salesforce",
    "google-analytics": "Google Analytics",

    # Certifications
    "cert-aws-solutions-architect": "AWS Certified Solutions Architect",
    "cert-aws-developer": "AWS Certified Developer",
    "cert-aws-devops": "AWS Certified DevOps Engineer",
    "cert-azure-solutions-architect": "Azure Solutions Architect",
    "cert-azure-devops": "Azure DevOps Engineer",
    "cert-gcp-architect": "GCP Cloud Architect",
    "cert-cka": "CKA (Certified Kubernetes Administrator)",
    "cert-ckad": "CKAD (Certified Kubernetes Application Developer)",
    "cert-cissp": "CISSP",
    "cert-ceh": "CEH",
    "cert-comptia-secplus": "CompTIA Security+",
    "cert-pmp": "PMP",
    "cert-scrum-master": "Scrum Master (PSM/CSM)",
}


# ==============================================================================
# AHO-CORASICK / SKILL TRIE MATCHER
# ==============================================================================

class TrieNode:
    __slots__ = ("children", "output", "fail")

    def __init__(self):
        self.children: Dict[str, "TrieNode"] = {}
        self.output: List[Tuple[str, str]] = []  # (original_keyword, canonical_id)
        self.fail: Optional["TrieNode"] = None


class SkillTrieMatcher:
    """
    High-performance Aho-Corasick Trie matching 300+ technical terms and multi-word phrases.
    Enforces word boundaries so short tokens ('R', 'C', 'Go') do not trigger false positives.
    """

    def __init__(self, vocab_map: Dict[str, str]):
        self.root = TrieNode()
        self._build_trie(vocab_map)
        self._build_failure_links()

    def _build_trie(self, vocab_map: Dict[str, str]):
        for keyword, canon in vocab_map.items():
            node = self.root
            lowered = keyword.lower()
            for char in lowered:
                if char not in node.children:
                    node.children[char] = TrieNode()
                node = node.children[char]
            node.output.append((keyword, canon))

    def _build_failure_links(self):
        queue = collections.deque()
        for char, child in self.root.children.items():
            child.fail = self.root
            queue.append(child)

        while queue:
            current = queue.popleft()
            for char, child in current.children.items():
                fallback = current.fail
                while fallback is not None and char not in fallback.children:
                    fallback = fallback.fail
                child.fail = fallback.children[char] if fallback and char in fallback.children else self.root
                child.output.extend(child.fail.output)
                queue.append(child)

    def find_matches(self, text: str) -> List[Tuple[str, str, int, int]]:
        """
        Returns a list of tuples: (matched_keyword, canonical_id, start_idx, end_idx)
        with strict word boundary enforcement and longest-match span deduplication.
        """
        raw_matches: List[Tuple[str, str, int, int]] = []
        node = self.root
        lowered = text.lower()
        n = len(lowered)

        for i, char in enumerate(lowered):
            while node is not None and char not in node.children:
                node = node.fail
            if node is None:
                node = self.root
                continue
            node = node.children[char]

            if node.output:
                for kw, canon in node.output:
                    kw_len = len(kw)
                    start_idx = i - kw_len + 1
                    end_idx = i + 1

                    # Check left boundary
                    if start_idx > 0:
                        left_char = lowered[start_idx - 1]
                        if left_char.isalnum() or left_char in ("_", "#", "+"):
                            continue

                    # Check right boundary
                    if end_idx < n:
                        right_char = lowered[end_idx]
                        if right_char.isalnum() or right_char in ("_", "#", "+"):
                            continue

                    # Special rule for single letter 'r' or 'c': must be isolated
                    if len(kw.strip()) == 1 and kw.lower() in ("r", "c"):
                        # Ensure not part of common Portuguese or English single letter words
                        if start_idx > 0 and lowered[start_idx - 1] not in (" ", "\n", "\t", "(", "[", "/", ","):
                            continue

                    raw_matches.append((kw, canon, start_idx, end_idx))

        # Longest-match span resolution: longer matches suppress sub-matches within the same span
        raw_matches.sort(key=lambda m: (-(m[3] - m[2]), m[2]))
        kept_matches: List[Tuple[str, str, int, int]] = []
        for m in raw_matches:
            start_m, end_m = m[2], m[3]
            is_subspan = False
            for k in kept_matches:
                start_k, end_k = k[2], k[3]
                if start_k <= start_m and end_m <= end_k:
                    is_subspan = True
                    break
            if not is_subspan:
                kept_matches.append(m)

        return kept_matches


# Instantiate singleton SkillTrieMatcher
TRIE_MATCHER = SkillTrieMatcher(_CANON)


# ==============================================================================
# COMPILED REGEX FALLBACK / COMPLEMENTARY MATCHERS
# ==============================================================================

RE_HARD = re.compile(
    r'(?<!\w)'
    r'('
    r'Python|Java(?:Script)?|TypeScript|C#|C\+\+|\.NET|PHP|Ruby|Go(?:lang)?|'
    r'Kotlin|Swift|Rust|Scala|'
    r'R(?=\b)|'
    r'React\s+Native|Angular(?:\.?[Jj][Ss])?|React(?:\.?[Jj][Ss])?|Vue(?:\.?[Jj][Ss])?|'
    r'Next(?:\.?[Jj][Ss])?|Nuxt(?:\.?[Jj][Ss])?|Svelte(?:Kit)?|Solid(?:\.?[Jj][Ss])?|'
    r'Tailwind(?:\s*CSS)?|Bootstrap|Material\s*UI|Chakra\s*UI|Ant\s*Design|'
    r'HTML\d?|CSS\d?|SASS|SCSS|'
    r'Node(?:\.?[Jj][Ss])?|Django|Flask|FastAPI|'
    r'Spring(?:\s*Boot|\s*Cloud)?|Laravel|Symfony|Express(?:\.?[Jj][Ss])?|Nest(?:\.?[Jj][Ss])?|Fastify|'
    r'Rails|Ruby\s+on\s+Rails|'
    r'Apache|Nginx|Tomcat|'
    r'Prisma|TypeORM|NextAuth(?:\.?[Jj][Ss])?|tRPC|'
    r'JPA|Hibernate|Entity\s*Framework|SQLAlchemy|Alembic|'
    r'JWT|OAuth\d?|SAML|Keycloak|Auth0|'
    r'Redux|Zustand|MobX|Styled\s+Components|Design\s+Systems?|'
    r'TensorFlow|PyTorch|Keras|scikit-?learn|Pandas|NumPy|Matplotlib|Seaborn|OpenCV|'
    r'LangChain|LangGraph|LlamaIndex|Hugging\s*Face|Transformers|Ollama|vLLM|'
    r'Airflow|Spark|Hadoop|Databricks|Snowflake|BigQuery|dbt|Flink|'
    r'AWS|Azure|GCP|Google\s+Cloud|'
    r'Docker|Kubernetes|k8s|Terraform|Ansible|Helm|OpenShift|'
    r'CI[/\-]CD|Jenkins|GitHub\s+Actions|GitLab\s*CI|ArgoCD|'
    r'MySQL|PostgreSQL|Postgres|MongoDB|Redis|Oracle|SQL\s*Server|SQLite|'
    r'DynamoDB|Cassandra|Elasticsearch|OpenSearch|pgvector|Pinecone|Qdrant|Milvus|ChromaDB|'
    r'APIs?\s+REST|REST(?:ful)?(?:\s+APIs?)?|GraphQL|gRPC|Kafka|RabbitMQ|SOAP|Web\s*Services?|'
    r'Git(?:Hub|Lab|Hub\s+Actions)?|GIT|Gitflow|'
    r'Jira|Confluence|'
    r'SAP(?: PI/PO| ERP)?|'
    r'Scrum|Kanban|Clean\s+Architecture|SOLID|DDD|TDD|BDD|Microservices|'
    r'Selenium|Cypress|Playwright|Jest|JUnit|Pytest|Vitest|'
    r'Firebase|Google\s+Analytics|GA\b|'
    r'Microfrontends|'
    r'Linux|Unix|Ubuntu|Debian|CentOS|RHEL|Bash|PowerShell|Maven|Gradle|'
    r'Xcode|TestFlight|'
    r'Figma|Sketch|Storybook'
    r')'
    r'(?!\w)',
    re.I,
)


def _clean(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\u200b|\u00a0', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _section(text: str, header: str, stop: Optional[str] = None) -> str:
    end = rf'(?:{stop}|$)' if stop else r'$'
    m = re.search(rf'(?:{header})(.*?)(?:{end})', text, re.S | re.I)
    return m.group(1).strip() if m else ""


def _normalise(skill: str) -> str:
    return _CANON.get(skill.lower().strip(), skill.lower().strip())


def normalise_skill_label(skill: str) -> str:
    canonical = _normalise(skill)
    return _DISPLAY.get(canonical, skill.upper() if len(skill) <= 2 else skill.strip())


TECH_STACKS: dict[str, frozenset[str]] = {
    "MERN":     frozenset({"mongodb", "express", "react",   "nodejs"}),
    "MEAN":     frozenset({"mongodb", "express", "angular", "nodejs"}),
    "MEVN":     frozenset({"mongodb", "express", "vue",     "nodejs"}),
    "PERN":     frozenset({"postgresql", "express", "react", "nodejs"}),
    "LAMP":     frozenset({"linux", "apache", "mysql", "php"}),
    "LEMP":     frozenset({"linux", "nginx",  "mysql", "php"}),
    "T3":       frozenset({"typescript", "trpc", "tailwindcss", "nextjs", "prisma", "nextauth"}),
    "JAMstack": frozenset({"javascript", "html", "css"}),
    "Next.js":  frozenset({"nextjs", "react"}),
    "Nuxt":     frozenset({"nuxtjs", "vue"}),
    "Django":   frozenset({"python", "django"}),
    "Rails":    frozenset({"ruby", "rails"}),
    "Spring":   frozenset({"java", "spring-boot"}),
    "Serverless": frozenset({"aws-lambda", "nodejs"}),
    "MLOps":    frozenset({"python", "docker", "kubernetes", "mlflow"}),
    "DataOps":  frozenset({"python", "airflow", "dbt", "snowflake"}),
}

_RE_STACK_MENTION = re.compile(
    r'\b(MERN|MEAN|MEVN|PERN|LAMP|LEMP|T3|JAMstack|MLOps|DataOps|'
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
        # Avoid false positives for small stacks: if 2 items, require both.
        min_threshold = PARTIAL_THRESHOLD
        if len(required) <= 2:
            min_threshold = 1.0

        if ratio == 1.0:
            detected.append(stack_name)
        elif ratio >= min_threshold:
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
    """
    Tier 1 fast extraction using Trie & regex pattern cascades.
    Returns structured dictionary of attributes in <5ms.
    """
    text = _clean(raw)

    mandatory_text = _section(
        text, _SEC_MANDATORY,
        stop=rf'{_SEC_NICE}|{_SEC_SOFT}|{_SEC_ADD}'
    )
    niceohave_text = _section(text, _SEC_NICE, stop=rf'{_SEC_SOFT}|{_SEC_ADD}')
    soft_section   = _section(text, _SEC_SOFT, stop=rf'{_SEC_NICE}|{_SEC_ADD}')

    # Extract nice_to_have first using regex and trie
    nice_raw_re = set(RE_HARD.findall(niceohave_text)) if niceohave_text else set()
    nice_raw_trie = {m[0] for m in TRIE_MATCHER.find_matches(niceohave_text)} if niceohave_text else set()
    nice_raw = nice_raw_re | nice_raw_trie

    # Extract hard skills from everything EXCEPT niceohave_text
    hard_source = text.replace(niceohave_text, "") if niceohave_text else text
    hard_raw_re = {s for s in RE_HARD.findall(hard_source) if s.strip()}
    hard_raw_trie = {m[0] for m in TRIE_MATCHER.find_matches(hard_source)}
    hard_raw = hard_raw_re | hard_raw_trie

    # Deduplicate and normalize
    seen_norm = set()
    deduped_hard = []
    all_hard_matches = sorted(list(hard_raw), key=len, reverse=True)

    for s in all_hard_matches:
        norm = _normalise(s)
        if norm not in seen_norm:
            seen_norm.add(norm)
            display = normalise_skill_label(s)
            deduped_hard.append(display)

    hard_skills = sorted(deduped_hard)

    # Filter nice_to_have so it does not duplicate hard_skills
    deduped_nice = []
    all_nice_matches = sorted(list(nice_raw), key=len, reverse=True)
    for s in all_nice_matches:
        norm = _normalise(s)
        if norm not in seen_norm:
            seen_norm.add(norm)
            display = normalise_skill_label(s)
            deduped_nice.append(display)

    nice_skills = sorted(deduped_nice)

    soft_source = soft_section + " " + text
    soft_skills = sorted({m.lower() for m in RE_SOFT.findall(soft_source)})

    exp_list = []
    for m in RE_EXPERIENCE.finditer(text):
        min_val = int(m.group(1))
        max_val = int(m.group(2) or m.group(3)) if (m.group(2) or m.group(3)) else None
        entry = {
            "min": min_val,
            "max": max_val,
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

    # Seniority extraction
    seniority_matches = RE_SENIORITY.findall(text)
    seniority = None
    if seniority_matches:
        mapping = {
            "jr": "Júnior", "jr.": "Júnior", "júnior": "Júnior", "junior": "Júnior",
            "pl": "Pleno", "pl.": "Pleno", "pleno": "Pleno", "mid-level": "Pleno", "mid level": "Pleno",
            "sr": "Sênior", "sr.": "Sênior", "sênior": "Sênior", "senior": "Sênior",
            "estagiário": "Estagiário", "estagiario": "Estagiário", "estag": "Estagiário", "intern": "Estagiário", "internship": "Estagiário",
            "especialista": "Especialista", "specialist": "Especialista", "staff": "Staff",
            "lead": "Lead", "tech lead": "Tech Lead", "liderança": "Liderança",
            "principal": "Principal", "architect": "Architect", "arquiteto": "Arquiteto",
            "manager": "Gerente", "gerente": "Gerente", "director": "Diretor", "diretor": "Diretor",
        }
        main_match = seniority_matches[0].lower().strip()
        seniority = mapping.get(main_match, main_match.capitalize())

    stacks = detect_stacks(hard_skills + nice_skills, raw_text=text)
    combined_stacks = list(set(stacks["detected"] + stacks["partial"] + stacks["mentioned"]))

    for stack in combined_stacks:
        hard_skills.append(stack)
        components = TECH_STACKS.get(stack)
        if components:
            hard_skills.extend([normalise_skill_label(c) for c in components])

    hard_skills = sorted(list(set(hard_skills)))

    return {
        "hard_skills":      hard_skills,
        "soft_skills":      soft_skills,
        "nice_to_have":     nice_skills,
        "years_experience": years_experience,
        "seniority":        seniority,
        "salary":           salary,
        "contract_type":    contract,
        "tech_stack":       combined_stacks,
    }
