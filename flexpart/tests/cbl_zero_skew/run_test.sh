#!/usr/bin/env bash
set -euo pipefail

test_dir="$(cd "$(dirname "$0")" && pwd)"
source_file="${1:-"$test_dir/../../src/cbl_mod.f90"}"
compiler="${FC:-gfortran}"
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/flexpart-cbl-zero-skew.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT

"$compiler" -J"$work_dir" -I"$work_dir" -c "$test_dir/par_mod.f90" \
  -o "$work_dir/par_mod.o"
"$compiler" -J"$work_dir" -I"$work_dir" -c "$test_dir/com_mod.f90" \
  -o "$work_dir/com_mod.o"
"$compiler" -J"$work_dir" -I"$work_dir" -c "$test_dir/random_mod.f90" \
  -o "$work_dir/random_mod.o"
"$compiler" -J"$work_dir" -I"$work_dir" -c "$source_file" \
  -o "$work_dir/cbl_mod.o"
"$compiler" -J"$work_dir" -I"$work_dir" \
  "$test_dir/test_cbl_zero_skew.f90" \
  "$work_dir/par_mod.o" "$work_dir/com_mod.o" "$work_dir/random_mod.o" \
  "$work_dir/cbl_mod.o" -o "$work_dir/test_cbl_zero_skew"
"$work_dir/test_cbl_zero_skew"
