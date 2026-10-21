"""Builds vocabularies."""

import json
import os
import os.path
import re
import shutil
import sys
import textwrap
import yaml
from pathlib import Path

import jinja2
from pyoxigraph import Store, parse, serialize, RdfFormat, QueryResultsFormat, Quad, NamedNode, Literal

SCRIPTS_DIR = Path("scripts")
SRC_DIR = Path("src")
VOCABS_SRC_DIR = Path("src") / "vocabs"
BUILT_DIR = Path("built")
DEST_DIR = Path("docs")

ANTORA_COMPONENT_DIR = BUILT_DIR
ANTORA_ROOT_MODULE_DIR = ANTORA_COMPONENT_DIR / "modules" / "ROOT"
ANTORA_PLAYBOOK = sys.argv[1]

SKOS_URL = "{site_url}/{scheme_name}.skos.ttl"
SHACL_URL = "{site_url}/{scheme_name}.shacl.ttl"


def read_turtle_prefixes(src_file):
    prefixes = dict()
    with src_file.open() as f:
        for line in f:
            if line.startswith("@prefix"):
                whitespace = re.compile(r'\s+')
                parts = whitespace.split(line)
                prefixes[parts[1].partition(":")[0]] = parts[2].lstrip("<").rstrip(">")
    return prefixes 



def generate_skos_ontology(src_file, vocab, playbook):
    prefixes = read_turtle_prefixes(src_file)
    vocab.add(Quad(NamedNode("https://modellen.netbeheernederland.nl/controlled-vocabularies/marktpartijen"), NamedNode("http://purl.org/dc/terms/source"), Literal("https://github.com/Netbeheer-Nederland/controlled-vocabularies/blob/main/scripts/build.py", datatype=NamedNode("http://www.w3.org/2001/XMLSchema#anyURI"))))
    vocab.dump(ANTORA_ROOT_MODULE_DIR / "attachments" / src_file.name, format=RdfFormat.TRIG, prefixes=prefixes)  # NOTE: Because there is only a single graph object, this will be Turtle.


def generate_shacl_ontology(src_file, vocab, playbook):
    # Parse query and serialize to dictionary
    scheme = json.loads(
        vocab.query(
            """
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX dcterms: <http://purl.org/dc/terms/>
        PREFIX owl: <http://www.w3.org/2002/07/owl>
        SELECT *
        WHERE {
            ?iri a skos:ConceptScheme ;
                dcterms:subject ?subject ;
                dcterms:type ?type ;
                skos:notation ?notation ;
                dcterms:title ?title .
        }
    """
        ).serialize(format=QueryResultsFormat.JSON)
    )["results"]["bindings"][0]

    terms = sorted(
        json.loads(
            vocab.query(
                f"""
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX owl: <http://www.w3.org/2002/07/owl>
        SELECT *
        WHERE {{
            ?iri a skos:Concept ;
                skos:prefLabel ?prefLabel ;
                skos:notation ?notation ;
                skos:inScheme ?scheme .
                OPTIONAL {{ ?iri owl:deprecated ?deprecated }}
        }}
    """
            ).serialize(format=QueryResultsFormat.JSON)
        )["results"]["bindings"],
        key=lambda t: t["iri"]["value"],
    )

    scheme_name = scheme["notation"]["value"]

    shacl_template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(SCRIPTS_DIR / "templates")
    ).get_template("scheme.shacl.ttl.jinja2")
    shacl = shacl_template.render(scheme=scheme, terms=terms)

    with (ANTORA_ROOT_MODULE_DIR / "attachments" / f"{scheme_name}.shacl.ttl").open("wt") as f:
        f.write(shacl)


def generate_antora_page(src_file, vocab, playbook):
    # TODO: The querying is duplicate in the `generate_shacl_ontology` which I think is undesired.
    scheme = json.loads(
        vocab.query(
            """
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX dcterms: <http://purl.org/dc/terms/>
        PREFIX owl: <http://www.w3.org/2002/07/owl>
        SELECT *
        WHERE {
            ?iri a skos:ConceptScheme ;
                dcterms:subject ?subject ;
                dcterms:type ?type ;
                skos:notation ?notation ;
                dcterms:title ?title .
        }
    """
        ).serialize(format=QueryResultsFormat.JSON)
    )["results"]["bindings"][0]

    terms = sorted(
        json.loads(
            vocab.query(
                f"""
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX owl: <http://www.w3.org/2002/07/owl>
        SELECT *
        WHERE {{
            ?iri a skos:Concept ;
                skos:prefLabel ?prefLabel ;
                skos:notation ?notation ;
                skos:inScheme ?scheme .
                OPTIONAL {{ ?iri owl:deprecated ?deprecated }}
        }}
    """
            ).serialize(format=QueryResultsFormat.JSON)
        )["results"]["bindings"],
        key=lambda t: t["iri"]["value"],
    )
    
    scheme_name = scheme["notation"]["value"]

    skos_url = SKOS_URL.format(site_url=playbook["site"]["url"], scheme_name=scheme_name)
    shacl_url = SHACL_URL.format(site_url=playbook["site"]["url"], scheme_name=scheme_name)

    adoc_template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(SCRIPTS_DIR / "templates")
    ).get_template("scheme.adoc.jinja2")

    adoc = adoc_template.render(scheme=scheme, terms=terms, skos_url=skos_url, shacl_url=shacl_url)

    with (ANTORA_ROOT_MODULE_DIR / "pages" / f"{scheme_name}.adoc").open("wt") as f:
        f.write(adoc)


def open_vocabulary(src_file):
    # NOTE: For now only Turtle is supported.
    vocab = Store()

    for st in parse(path=src_file, format=RdfFormat.TURTLE):
        vocab.add(st)

    return vocab


def write_nav():
    with (ANTORA_ROOT_MODULE_DIR / "nav.adoc").open("a") as f:
        f.write(f"* Vocabularies\n")
        for vocab in VOCABS_SRC_DIR.glob("*.ttl"):
            f.write(f"** xref:{vocab.name.replace('.skos.ttl', '.adoc')}[]")


def prepare_build_dir():
    if BUILT_DIR.exists():
        shutil.rmtree(BUILT_DIR)
    shutil.copytree(SRC_DIR / "docs", BUILT_DIR)

    for family in ["attachments", "examples", "images", "partials", "pages"]:
        (ANTORA_ROOT_MODULE_DIR / family).mkdir(exist_ok=True)



def relocate_skos_schemes():
    for skos_file in (ANTORA_ROOT_MODULE_DIR / "attachments").glob("*.skos.ttl"):
        shutil.copy(skos_file, DEST_DIR)


def relocate_shacl_shapes():
    for shacl_file in (ANTORA_ROOT_MODULE_DIR / "attachments").glob("*.shacl.ttl"):
        shutil.copy(shacl_file, DEST_DIR)


def run_antora():
    os.system(f"npx antora {ANTORA_PLAYBOOK}")


def read_playbook(playbook_file):
    with open(playbook_file) as f:
        playbook = yaml.safe_load(f)

    return playbook


def build():
    prepare_build_dir()
    playbook = read_playbook(ANTORA_PLAYBOOK)

    for src_file in {f for f in VOCABS_SRC_DIR.iterdir() if f.name.endswith(".ttl")}:
        vocab = open_vocabulary(src_file)
        generate_skos_ontology(
            src_file,
            vocab,
            playbook
        )
        generate_shacl_ontology(
            src_file,
            vocab,
            playbook
        )
        generate_antora_page(
            src_file,
            vocab,
            playbook
        )

    write_nav()

    run_antora()
    relocate_skos_schemes()
    relocate_shacl_shapes()
    (DEST_DIR / ".nojekyll").touch()  # Disables GitHub's default Jekyll CI/CD pipeline.


if __name__ == "__main__":
    build()
