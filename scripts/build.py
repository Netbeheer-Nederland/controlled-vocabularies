"""Builds vocabularies."""

import json
import os
import os.path
import shutil
import sys
import textwrap
import yaml
from pathlib import Path

import jinja2
from pyoxigraph import Store, parse, RdfFormat, QueryResultsFormat

SCRIPTS_DIR = Path("scripts")
SRC_DIR = Path("src")
VOCABS_SRC_DIR = Path("src") / "vocabs"
BUILT_DIR = Path("built")
DEST_DIR = Path("docs")

ANTORA_COMPONENT_DIR = BUILT_DIR
ANTORA_ROOT_MODULE_DIR = ANTORA_COMPONENT_DIR / "modules" / "ROOT"
ANTORA_PLAYBOOK = sys.argv[1]


def generate_skos_ontology(src_file, dst_file, data):
    shutil.copy(src_file, dst_file)

    # NOTE: Currently the source file is not processed, i.e. equal to the
    # built file.
    # TODO: Add version metadata which has the Git ref as value.

    return dst_file


def generate_shacl_ontology(src_file, dst_file, data):
    shacl_template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(SCRIPTS_DIR / "templates")
    ).get_template("scheme.shacl.ttl.jinja2")
    shacl = shacl_template.render(scheme=data["scheme"], terms=data["terms"])

    with dst_file.open("wt") as f:
        f.write(shacl)

    return dst_file


def generate_antora_page(src_file, dst_file, data):
    adoc_template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(SCRIPTS_DIR / "templates")
    ).get_template("scheme.adoc.jinja2")

    adoc = adoc_template.render(scheme=data["scheme"], terms=data["terms"], skos_url=data["skos_url"], shacl_url=data["shacl_url"])

    with dst_file.open("wt") as f:
        f.write(adoc)

    return dst_file


def open_vocabulary(src_file):
    # NOTE: For now only Turtle is supported.
    vocab = Store()

    for st in parse(path=src_file, format=RdfFormat.TURTLE):
        vocab.add(st)

    return vocab


def read_vocabulary(src_file):
    vocab = open_vocabulary(src_file)

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

    return scheme, terms


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
        scheme, terms = read_vocabulary(src_file)
        scheme_name = scheme["notation"]["value"]
        skos_url = f"{playbook['site']['url']}/{scheme_name}.skos.ttl"
        shacl_url = f"{playbook['site']['url']}/{scheme_name}.shacl.ttl"

        generate_skos_ontology(
            src_file,
            ANTORA_ROOT_MODULE_DIR / "attachments" / f"{scheme_name}.skos.ttl",
            data={
                "scheme": scheme,
                "terms": terms,
                "shacl_url": shacl_url
            }
        )
        generate_shacl_ontology(
            src_file,
            ANTORA_ROOT_MODULE_DIR / "attachments" / f"{scheme_name}.shacl.ttl",
            data={
                "scheme": scheme,
                "terms": terms
            }
        )
        generate_antora_page(
            src_file,
            ANTORA_ROOT_MODULE_DIR / "pages" / f"{scheme_name}.adoc",
            data={
                "scheme": scheme,
                "terms": terms,
                "skos_url": skos_url,
                "shacl_url": shacl_url
            }
        )

    write_nav()

    run_antora()
    relocate_skos_schemes()
    relocate_shacl_shapes()
    (DEST_DIR / ".nojekyll").touch()  # Disables GitHub's default Jekyll CI/CD pipeline.


if __name__ == "__main__":
    build()
