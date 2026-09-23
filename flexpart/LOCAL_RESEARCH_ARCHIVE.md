# FLEXPART local research archive

Snapshot assembled on 2026-07-20.

## Code

This directory contains the extracted FLEXPART 11.1 release source, including:

- `src/` — Fortran model source;
- `options/` and `options.reference/` — run configuration and species data;
- `examples/` — aerosol, nuclear, and tracer examples;
- `tests/` — regression and physics tests;
- `containers/` — Docker/Podman and Singularity/Apptainer recipes;
- `documentation/docs/` — the source Markdown for the FLEXPART 11 manual.

The preserved source archive is `flexpart_11.1.orig.tar.gz`, downloaded from
Debian's mirror of the FLEXPART 11.1 upstream source package:

<https://deb.debian.org/debian/pool/main/f/flexpart/flexpart_11.1.orig.tar.gz>

SHA-256:

`f01758e7bfc3861b6f0b923666b0f4547fa8ca687921ddc6fb234c79e92564c3`

The canonical development repository is:

<https://gitlab.phaidra.org/flexpart/flexpart>

The canonical GitLab host repeatedly timed out during this snapshot, so the
versioned upstream tarball was used instead of an incomplete clone.

## Research material

See [`docs/README.md`](docs/README.md) for the reading order and paper index.
The broader title-level literature search is in
[`docs/literature_title_matches.csv`](docs/literature_title_matches.csv).

