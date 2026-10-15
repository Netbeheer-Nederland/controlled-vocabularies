"""Builds vocabularies."""

import os
import os.path
from pathlib import Path
import json
import textwrap
import shutil
import jinja2
import sys
import yaml
from pyoxigraph import Store, parse, RdfFormat, QueryResultsFormat

# Paths: src/
DOCS_SRC = Path("src") / "docs"
VOCABS_SRC = Path("src") / "waardelijsten"

# Paths: build/
BUILD_DIR = Path("build")
ANTORA_ROOT_COMPONENT_DIR = BUILD_DIR / "docs"
ANTORA_ROOT_MODULE_DIR = ANTORA_ROOT_COMPONENT_DIR / "modules" / "ROOT"

# Paths: docs/
DOCS_DIR = Path("docs")

# Paths: scripts/
SCRIPTS_DIR = Path("scripts")
TEMPLATES_DIR = SCRIPTS_DIR / "templates"

ANTORA_PLAYBOOK = sys.argv[1]


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
                owl:versionIRI ?versionIri ;
                owl:versionInfo ?version ;
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
        f.write(f"* Waardelijsten\n")
        for vocab in VOCABS_SRC.glob("*.ttl"):
            f.write(f"** xref::{vocab.with_suffix('.adoc').name}[]")


def prepare_build_dir():
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)


def read_playbook(playbook_file):
    with open(playbook_file) as f:
        playbook = yaml.safe_load(f)

    return playbook


def build_vocabulary(src_dir):
    vocab_name = src_dir.stem
    vocabulary_dir = BUILD_DIR / "waardelijsten" / vocab_name
    vocabulary_dir.mkdir(parents=True)

    playbook = read_playbook(ANTORA_PLAYBOOK)

    for vocab_version in src_dir.glob("*.ttl"):
        scheme, terms = read_vocabulary(vocab_version)
        version = scheme["version"]["value"]
        title = scheme["title"]["value"]
        skos_iri = f"{playbook['site']['url']}/{vocab_name}/{version}/skos.ttl"
        shacl_iri = f"{playbook['site']['url']}/{vocab_name}/{version}/shacl.ttl"
        component_version = vocabulary_dir / version
        root_module = component_version / "modules" / "ROOT"
        root_module.mkdir(parents=True)

        (root_module / "pages").mkdir()
        (root_module / "attachments").mkdir()
        (root_module / "examples").mkdir()
        (root_module / "partials").mkdir()
        (root_module / "images").mkdir()

        # Write Antora component version descriptor.
        with (component_version / "antora.yml").open("wt") as f:
            f.write(
                textwrap.dedent(
                    f"""
                name: {vocab_name}
                title: {title}
                version: '{version}'
                nav:
                - modules/ROOT/nav.adoc
            """
                ).lstrip()
            )

        # Write page.
        adoc_template = jinja2.Environment(
            loader=jinja2.FileSystemLoader(TEMPLATES_DIR)
        ).get_template("scheme.adoc.jinja2")

        adoc = adoc_template.render(scheme=scheme, terms=terms, skos_iri=skos_iri, shacl_iri=shacl_iri)

        with (root_module / "pages" / "index.adoc").open("wt") as f:
            f.write(adoc)

        # Write SKOS ontology.
        shutil.copy(vocab_version, root_module / "attachments" / f"{vocab_name}-{version}.skos.ttl")

        # Write SHACL ontology.
        shacl_template = jinja2.Environment(
            loader=jinja2.FileSystemLoader(TEMPLATES_DIR)
        ).get_template("scheme.shacl.ttl.jinja2")
        shacl = shacl_template.render(scheme=scheme, terms=terms, shacl_iri=shacl_iri)

        with (root_module / "attachments" / f"{vocab_name}-{version}.shacl.ttl").open("wt") as f:
            f.write(shacl)


def run_antora():
    os.system(f"npx antora {ANTORA_PLAYBOOK}")


def build_antora_root_component_version():
    shutil.copytree(DOCS_SRC, ANTORA_ROOT_COMPONENT_DIR)


def relocate_artifacts():
    for artifact in DOCS_DIR.glob("**/_attachments/*.ttl"):
        shutil.copy(artifact, artifact.parents[1] / "".join(artifact.suffixes[-2:]).lstrip("."))


def write_navs(nav):
    with (ANTORA_ROOT_MODULE_DIR / "nav.adoc").open("wt") as f:
        f.write(nav)

    for vocab in {f for f in (BUILD_DIR / "waardelijsten").glob("*/*") if Path(f).is_dir()}:
        with (vocab / "modules" / "ROOT" / "nav.adoc").open("w") as f:
            f.write(nav)

def setup_uri_redirects():
    playbook = read_playbook(ANTORA_PLAYBOOK)
    site_url = playbook["site"]["url"]
    for vocab in {f for f in (BUILD_DIR / "waardelijsten").iterdir() if Path(f).is_dir()}:
        latest_version = next(reversed(sorted(d.name for d in vocab.iterdir())))
        with (DOCS_DIR / vocab.name / "index.html").open("w") as doc:
            doc.write(f"""
                <!DOCTYPE html>
                <meta charset="utf-8">
                <link rel="canonical" href="{site_url}/{vocab.stem}/{latest_version}/index.html">
                <script>location="{site_url}/{vocab.name}/{latest_version}/index.html"</script>
                <meta http-equiv="refresh" content="0; url={vocab.stem}/{latest_version}/index.html">
                <meta name="robots" content="noindex">
                <title>Redirect Notice</title>
                <h1>Redirect Notice</h1>
                <p>The page you requested has been relocated to <a href="{site_url}/{vocab.stem}/{latest_version}/index.html">{site_url}/{vocab.stem}/{latest_version}/index.html</a>.</p>
            """)


def build():
    prepare_build_dir()
    build_antora_root_component_version()

    nav = (ANTORA_ROOT_MODULE_DIR / "nav.adoc").read_text() + "\n"
    nav += "* Waardelijsten\n"

    for vocab_src in {f for f in VOCABS_SRC.iterdir() if Path(f).is_dir()}:
        build_vocabulary(vocab_src)

        nav += f"** xref:{vocab_src.stem}::index.adoc[]\n"

    write_navs(nav)

    run_antora()
    relocate_artifacts()
    setup_uri_redirects()
    (DOCS_DIR / ".nojekyll").touch()  # Disables GitHub's default Jekyll CI/CD pipeline.


if __name__ == "__main__":
    build()
