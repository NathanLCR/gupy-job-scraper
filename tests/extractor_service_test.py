import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.extractor_service import parse_salary
from features_extractors.regex_extractor import extract, _clean

class TestExtractorService(unittest.TestCase):

    def test_parse_salary(self):
        salary_1 = "Salario de R$ 30.000 a R$ 40.000"
        self.assertEqual(parse_salary(salary_1), 30000)

        salary_2 = "Salario a combinar"
        self.assertEqual(parse_salary(salary_2), None)

        salary_3 = ""
        self.assertEqual(parse_salary(salary_3), None)

        salary_4 = "Salario de R$ 30000"
        self.assertEqual(parse_salary(salary_4), 30000)

    def test_parse_experience_level(self):
        job_desc = "Requisitos: Mínimo de 3 anos de experiência com Python."
        features = extract(job_desc)
        self.assertEqual(features["years_experience"], 3)

        job_desc_range = "Desejável 2 a 5 anos de experiência em Java."
        features_range = extract(job_desc_range)
        self.assertEqual(features_range["years_experience"], 2)

    def test_parse_contract_type(self):
        job_desc = "Contratação: Pessoa Jurídica (PJ)"
        features = extract(job_desc)
        self.assertIn("Pessoa Jurídica (PJ)", features["contract_type"])
        job_desc_2 = "Vaga para desenvolvedor"
        features_2 = extract(job_desc_2)
        self.assertEqual(features_2["contract_type"], ["CLT"])

    def test_parse_job_skills(self):
        job_desc = """
        Requisitos:
        - Python e Django
        - Experiência com AWS
        Soft Skills:
        - Proatividade e boa comunicação
        """
        features = extract(job_desc)
        
        self.assertIn("Python", features["hard_skills"])
        self.assertIn("Django", features["hard_skills"])
        self.assertIn("AWS", features["hard_skills"])
        
        self.assertIn("proatividade", features["soft_skills"])
        self.assertIn("comunicação", features["soft_skills"])

    def test_clean_text(self):
        html_text = "<div>Vaga de <b>Engenheiro</b> &nbsp; de Dados</div>"
        cleaned = _clean(html_text)
        self.assertEqual(cleaned, "Vaga de Engenheiro de Dados")

    def test_parse_nice_to_have(self):
        job_desc = """
        Requisitos: Python.
        Desejável: Docker e Kubernetes.
        """
        features = extract(job_desc)
        self.assertIn("Docker", features["nice_to_have"])
        self.assertIn("Kubernetes", features["nice_to_have"])
        self.assertIn("Python", features["hard_skills"])
        self.assertNotIn("Python", features["nice_to_have"])

    def test_full_job_description(self):
        job_description = """
        Você é apaixonado(a) por tecnologia e inovação? 💡 
        No Grupo SysMap – que reúne SysMap Solutions, 
        TriggoLabs e triggo.ai – acreditamos que grandes
        resultados nascem de pessoas incríveis. Somos uma 
        empresa brasileira de tecnologia que, desde 1999, 
        ajuda organizações a superar desafios complexos e 
        acelerar sua transformação digital. Nossa atuação 
        abrange diversos segmentos, como Telecom, Varejo, 
        Educação, Financeiro, Indústria/Cosméticos e Energia, 
        sempre com foco em soluções inovadoras e de alto impacto. 
        Candidate-se agora e construa o futuro da tecnologia conosco!
        Responsabilidades e atribuiçõesDesenvolver e manter aplicações mobile 
        utilizando React Native e TypeScript;Criar componentes reutilizáveis 
        com React (Hooks e Context);Implementar e gerenciar estados da aplicação 
        utilizando Redux e/ou Zustand;Consumir e integrar APIs REST de forma eficiente 
        e segura;Trabalhar em conjunto com times de produto e design para garantir 
        aderência ao Design System;Utilizar Styled Components para construção de 
        interfaces consistentes e escaláveis;Participar da definição e evolução da
        arquitetura baseada em Microfrontends;Implementar eventos de analytics 
        utilizando Google Analytics (GA);Utilizar Firebase Remote Config para 
        controle de features e configurações dinâmicas;Atuar nos processos de build, 
        versionamento e deploy das aplicações mobile;Contribuir com pipelines de CI/CD, 
        garantindo qualidade e automação das entregas;Seguir boas práticas de versionamento 
        de código com Gitflow.Requisitos e qualificaçõesCore:Experiência com React Native;
        Sólidos conhecimentos em React (Hooks e Context API);Conhecimento em TypeScript;
        Gerenciamento de Estado:Experiência com Redux;Conhecimento em Zustand.UI e Design:
        Experiência com Design Systems;Utilização de Styled Components para estilização.
        Consumo de APIs:Integração com APIs REST.Build e Deploy:Android:Conhecimento em 
        Gradle.iOS:Uso do Xcode;Publicação e testes via TestFlight.CI/CD:Criação e
        manutenção de pipelines com GitHub Actions;Versionamento seguindo Gitflow.
        Ecossistema:Uso de Firebase, especialmente Remote Config;Implementação de 
        eventos de analytics (GA).ArquiteturaExperiência ou familiaridade com
        Microfrontends aplicados ao contexto mobile ou front-end.Informações 
        adicionais 
        """
        hard_skills = sorted([
            "CI/CD", "Design System", "Firebase",
            "GitHub Actions", "Gitflow", "Google Analytics", "Gradle",
            "Microfrontends", "REST API", "React", "React Native", "Redux",
            "Styled Components", "TestFlight", "TypeScript", "Xcode", "Zustand"
        ])
        features = extract(job_description)
        self.assertEqual(features["hard_skills"], hard_skills)
        self.assertEqual(features["soft_skills"], ["inovação"])
        self.assertEqual(features["nice_to_have"], [])
        self.assertEqual(features["years_experience"], None)
        self.assertEqual(features["contract_type"], ["CLT"])
        self.assertEqual(features["salary"], None)
if __name__ == "__main__":
    unittest.main()
