# Third-party front-end components

Served locally so the browser never loads code or fonts from third-party hosts. Every file is
pinned by version and checksum; this list is the inventory of front-end components (M-02).

| File | Package | Version | Licence | Source | SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `vendor/htmx-2.0.11.min.js` | `htmx.org` | 2.0.11 | 0BSD | npm tarball `dist/htmx.min.js` | `d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717` |
| `fonts/inter-latin-wght-5.3.0.woff2` | `@fontsource-variable/inter` | 5.3.0 | OFL-1.1 | npm tarball `files/inter-latin-wght-normal.woff2` | `3100e775e8616cd2611beecfa23a4263d7037586789b43f035236a2e6fbd4c62` |
| `fonts/plus-jakarta-sans-latin-wght-5.3.0.woff2` | `@fontsource-variable/plus-jakarta-sans` | 5.3.0 | OFL-1.1 | npm tarball `files/plus-jakarta-sans-latin-wght-normal.woff2` | `153fc85b70298beeb1d61a5f723331649e7f23bb77302a66e61cb3e2fbdb5e79` |
| `fonts/jetbrains-mono-latin-wght-5.3.0.woff2` | `@fontsource-variable/jetbrains-mono` | 5.3.0 | OFL-1.1 | npm tarball `files/jetbrains-mono-latin-wght-normal.woff2` | `18be452724bfdc236c074ca94a249a7f41a86752c7d04ab258ce9ed5651f6a7e` |

Build tool (not shipped to the browser): Tailwind CSS standalone CLI 4.3.3,
`tailwindcss-linux-x64`, SHA-256 `dc61b3ac6b8c9ca874c0cc4c57b2409791a64c5540404ca5f5367360babc313a`,
pinned in `docker/Dockerfile`.

npm tarballs were checked against the registry's `dist.integrity` (SHA-512) before extraction.
Font licences: `fonts/LICENSE-*.txt`.

Update: download the new version from the npm tarball, verify the integrity, rename the file,
update the reference (`src/templates/base.html` or `src/assets/app.css`) and this table.
