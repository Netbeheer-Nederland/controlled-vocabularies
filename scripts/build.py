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
from pyld import jsonld
from pyoxigraph import Store, parse, serialize, RdfFormat, QueryResultsFormat, Quad, NamedNode, Literal

SCRIPTS_DIR = Path("scripts")
SRC_DIR = Path("src")
VOCABS_SRC_DIR = Path("src") / "vocabs"
BUILT_DIR = Path("built")
DEST_DIR = Path("docs")

ANTORA_COMPONENT_DIR = BUILT_DIR
ANTORA_ROOT_MODULE_DIR = ANTORA_COMPONENT_DIR / "modules" / "ROOT"
ANTORA_PLAYBOOK = sys.argv[1]

SKOS_URL = "{site_url}/{scheme_name}.skos.jsonld"
SHACL_URL = "{site_url}/{scheme_name}.shacl.ttl"


def generate_skos_ontology(src_file, playbook):
    skos_src_dict = yaml.safe_load(src_file.read_text())
    skos_ctx_dict = json.loads((VOCABS_SRC_DIR / "_context.jsonld").read_text())

    # Creating new dict to control insertion order for neater formatting.
    skos_dict = {**skos_ctx_dict}

    # Concept scheme.
    git_ref = "main"

    skos_dict.update({
        "id": skos_src_dict["id"],
        "@type": ["skos:Concept", "owl:Ontology"],
        "source": f"https://github.com/Netbeheer-Nederland/{playbook['site']['url'].split('/')[-1]}/blob/{git_ref}/{src_file.name}",
        "notation": skos_src_dict["id"].split("/")[-1]
    })

    # Copy remaining keys from source in sorted order.
    for key in sorted(skos_src_dict):
        if key in ["id", "@type", "terms"]:
            continue
        skos_dict[key] = skos_src_dict[key]

    # Concepts.
    skos_dict["terms"] = dict()
    for term_name, term in skos_src_dict["terms"].items():
        skos_dict["terms"][term_name] = {
            "id": f"{skos_src_dict['id']}#{term_name}",
            "@type": "skos:Concept",
            "prefLabel": term["prefLabel"]
        }
        for key in sorted(term):  # Copy remaining keys from source in sorted order.
            if key in ["id", "@type", "prefLabel"]:
                continue
            skos_dict["terms"][term_name][key] = term[key]

        skos_dict["terms"][term_name].update({
            "inScheme": skos_src_dict["id"],
            "topConceptOf": skos_src_dict["id"]
        })

    skos_file = (ANTORA_ROOT_MODULE_DIR / "attachments" / f"{skos_dict['notation']}.skos.jsonld")
    with skos_file.open("wt") as f:
        json.dump(skos_dict, f, indent=2)

    return skos_dict


def generate_shacl_ontology(skos_dict, playbook):
    scheme_name = skos_dict["notation"]

    shacl_template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(SCRIPTS_DIR / "templates")
    ).get_template("scheme.shacl.ttl.jinja2")
    shacl = shacl_template.render(scheme=skos_dict)

    with (ANTORA_ROOT_MODULE_DIR / "attachments" / f"{scheme_name}.shacl.ttl").open("wt") as f:
        f.write(shacl)


def generate_antora_page(skos_dict, playbook):
    scheme_name = skos_dict["notation"]

    skos_url = SKOS_URL.format(site_url=playbook["site"]["url"], scheme_name=scheme_name)
    shacl_url = SHACL_URL.format(site_url=playbook["site"]["url"], scheme_name=scheme_name)

    adoc_template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(SCRIPTS_DIR / "templates")
    ).get_template("scheme.adoc.jinja2")

    adoc = adoc_template.render(scheme=skos_dict, skos_url=skos_url, shacl_url=shacl_url)

    with (ANTORA_ROOT_MODULE_DIR / "pages" / f"{scheme_name}.adoc").open("wt") as f:
        f.write(adoc)


def write_nav():
    with (ANTORA_ROOT_MODULE_DIR / "nav.adoc").open("a") as f:
        f.write(f"* Vocabularies\n")
        for vocab in VOCABS_SRC_DIR.glob("*.yml"):
            f.write(f"** xref:{vocab.name.replace('.skos.yml', '.adoc')}[]")


def prepare_build_dir():
    if BUILT_DIR.exists():
        shutil.rmtree(BUILT_DIR)
    shutil.copytree(SRC_DIR / "docs", BUILT_DIR)

    for family in ["attachments", "examples", "images", "partials", "pages"]:
        (ANTORA_ROOT_MODULE_DIR / family).mkdir(exist_ok=True)


def relocate_skos_schemes():
    for skos_file in (ANTORA_ROOT_MODULE_DIR / "attachments").glob("*.skos.jsonld"):
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

    for src_file in {f for f in VOCABS_SRC_DIR.iterdir() if f.name.endswith(".yml")}:
        skos_dict = generate_skos_ontology(src_file, playbook)
        generate_shacl_ontology(skos_dict, playbook)
        generate_antora_page(skos_dict, playbook)

    write_nav()
    run_antora()
    relocate_skos_schemes()
    relocate_shacl_shapes()
    (DEST_DIR / ".nojekyll").touch()  # Disables GitHub's default Jekyll CI/CD pipeline.


if __name__ == "__main__":
    build()
