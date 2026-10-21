# NBNL Profile Group &emdash; Controlled Vocabularies

Controlled vocabularies published and maintained by Netbeheer Nederland for use in the NBNL Profile Group.

## Building

You'll need to have installed:

* Python
* Node.js

First make sure you have an environment activated which satisfies the Python requirements specified in `pyproject.toml`, and the Node.js requirements in `package.json`.

. Then simply call the build script with the Antora playbook you wish to use:

```
$ python scripts/build.py antora-playbook.local.yml
```

This script processes the source Antora componenet version, generates artifacts and embeds those. Then, it calls `antora` with the passed in playbook to render the
documentation site.

> [!note]
> The intermediate built files which Antora takes as input can be found in `built`. This may be useful when debugging.
