# Vendored front-end libraries

Served locally so the browser never loads code from third-party hosts. Every file is pinned by
version and checksum; listed here for the inventory of third-party components (M-02).

| File | Package | Version | Source | SHA-256 |
| --- | --- | --- | --- | --- |
| `htmx-2.0.11.min.js` | `htmx.org` | 2.0.11 | npm tarball `dist/htmx.min.js` | `d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717` |

Update: download the new version from the npm tarball, compare the checksum, rename the file,
update the `<script>` tag in `src/templates/base.html` and this table.
