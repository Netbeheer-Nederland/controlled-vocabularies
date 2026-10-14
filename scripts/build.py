"""Builds vocabularies."""

import os
import os.path
from pathlib import Path
import json
import textwrap
import shutil
import jinja2
from pyoxigraph import Store, parse, RdfFormat, QueryResultsFormat

SCRIPTS_DIR = Path("scripts")
SRC_DIR = Path("src")
VOCABS_SRC_DIR = Path("src") / "waardelijsten"
BUILD_DIR = Path("build")
DOCS_DIR = Path("docs")

ANTORA_COMPONENT_DIR = BUILD_DIR / "docs"
ANTORA_ROOT_MODULE_DIR = ANTORA_COMPONENT_DIR / "modules" / "ROOT"
ANTORA_PLAYBOOK = Path("antora-playbook.local.yml")


def generate_skos_ontology(scheme, terms, src_file, dst=None):
    if not dst:
        dst = BUILD_DIR / Path(scheme["notation"]["value"]).with_suffix(".skos.ttl")
    shutil.copy(src_file, dst)

    # NOTE: Currently the source file is not processed, i.e. equal to the
    # built file.
    # TODO: Add version metadata which has the Git ref as value.

    return dst


def generate_shacl_ontology(scheme, terms, src_file, dst=None):
    if not dst:
        dst = BUILD_DIR / Path(scheme["notation"]["value"]).with_suffix(".shacl.ttl")

    shacl_template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(SCRIPTS_DIR / "templates")
    ).get_template("scheme.shacl.ttl.jinja2")
    shacl = shacl_template.render(scheme=scheme, terms=terms)

    with dst.open("wt") as f:
        f.write(shacl)

    return dst


def generate_antora_page(scheme, terms, src_file, dst=None):
    if not dst:
        dst = (BUILD_DIR / scheme["notation"]["value"]).with_suffix(".adoc")

    adoc_template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(SCRIPTS_DIR / "templates")
    ).get_template("scheme.adoc.jinja2")

    adoc = adoc_template.render(scheme=scheme, terms=terms)

    with dst.open("wt") as f:
        f.write(adoc)

    return dst


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
        SELECT *
        WHERE {
            ?uri a skos:ConceptScheme ;
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
                """
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX adms: <http://www.w3.org/ns/adms#>
        SELECT *
        WHERE {
            ?uri a skos:Concept ;
                skos:prefLabel ?prefLabel ;
                adms:status ?status ;
                skos:notation ?notation .
        }
    """
            ).serialize(format=QueryResultsFormat.JSON)
        )["results"]["bindings"],
        key=lambda t: t["uri"]["value"],
    )

    return scheme, terms


def write_nav():
    with (ANTORA_ROOT_MODULE_DIR / "nav.adoc").open("w") as f:
        for info_page in SRC_DIR.glob("*.adoc"):
            if info_page.name != "index.adoc":
                f.write(f"* xref::{info_page.name}[]\n")
        f.write(f"* Begrippenlijsten\n")
        for vocab in VOCABS_SRC_DIR.glob("*.ttl"):
            f.write(f"** xref::{vocab.with_suffix('.adoc').name}[]")


def prepare_build_dir():
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)


def create_antora_component():
    os.makedirs(ANTORA_COMPONENT_DIR)
    os.makedirs(ANTORA_ROOT_MODULE_DIR / "pages")
    os.makedirs(ANTORA_ROOT_MODULE_DIR / "attachments")

    # Write Antora component version descriptor.
    with (ANTORA_COMPONENT_DIR / "antora.yml").open("wt") as f:
        f.write(
            textwrap.dedent(
                """
            name: ROOT
            title: NBNL Begrippenlijsten
            version: ~
            nav:
            - modules/ROOT/nav.adoc
        """
            ).lstrip()
        )

    # Copy pages
    for page_file in SRC_DIR.glob("*.adoc"):
        shutil.copy(page_file, ANTORA_ROOT_MODULE_DIR / "pages")


def relocate_skos_schemes():
    for skos_file in (ANTORA_ROOT_MODULE_DIR / "attachments").glob("*.skos.ttl"):
        shutil.copy(skos_file, DOCS_DIR)


def relocate_shacl_shapes():
    for shacl_file in (ANTORA_ROOT_MODULE_DIR / "attachments").glob("*.shacl.ttl"):
        shutil.copy(shacl_file, DOCS_DIR)


def run_antora():
    os.system(f"npx antora {ANTORA_PLAYBOOK}")


def build():
    prepare_build_dir()
    create_antora_component()

    for src_file in {f for f in VOCABS_SRC_DIR.iterdir() if f.name.endswith(".ttl")}:
        scheme, terms = read_vocabulary(src_file)
        scheme_name = scheme["notation"]["value"]

        generate_skos_ontology(
            scheme,
            terms,
            src_file,
            ANTORA_ROOT_MODULE_DIR / "attachments" / f"{scheme_name}.skos.ttl",
        )
        generate_shacl_ontology(
            scheme,
            terms,
            src_file,
            ANTORA_ROOT_MODULE_DIR / "attachments" / f"{scheme_name}.shacl.ttl",
        )
        generate_antora_page(
            scheme,
            terms,
            src_file,
            ANTORA_ROOT_MODULE_DIR / "pages" / f"{scheme_name}.adoc",
        )

    write_nav()

    run_antora()
    relocate_skos_schemes()
    relocate_shacl_shapes()
    (DOCS_DIR / ".nojekyll").touch()  # Disables GitHub's default Jekyll CI/CD pipeline.


if __name__ == "__main__":
    build()
