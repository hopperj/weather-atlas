#!/bin/bash
# By LB
# run OpenMP simulations
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
MM='FLEXPART AUTOMATIC OPTIONS TEST'

warning() {
    printf "%-68s[$YELLOW%10s$NC]\n" "$@" "SKIPPED"
    return 0
}

report() {
    if [ $? -eq 0 ]; then
        printf "%-68s[$GREEN%10s$NC]\n" "$@" "OK"
        return 0
    else
        printf "%-68s[$RED%10s$NC]\n" "$@" "FAILED"
        return 1
    fi
}
#
# initial conditions
#
warning "[$MM] $PWD"
#
# Change to directory of this script
#
cd $(dirname $0)
#
# Check for Flexpart executable build before
#
test -f ../src/FLEXPART
report "[$MM] executable: ../src/FLEXPART" || exit 1
ln -s ../src/FLEXPART .
ln -s ../src/FLEXPART_ETA .
test -d ./default_options
report "[$MM] default options: ./default_options" || exit 1
cp -rf ./default_options ./current
#
# Different options tests
#
STATUS=0
TESTSRUN=0
#
# run Options test with restart output disabled
#
sed "/LCONVECTION=/c\ LCONVECTION=   0," ./default_options/COMMAND > ./current/COMMAND
sed -i "/LTURBULENCE=/c\ LTURBULENCE=   0," ./current/COMMAND
sed -i "/IPOUT=/c\ IPOUT=   1," ./current/COMMAND

# Aerosol particles to capture settling speeds, dry and wet deposition in output
sed "/SPECNUM_REL=/c\ SPECNUM_REL=   40," ./default_options/RELEASES > ./current/RELEASES

sed "/output/c\./output_omp1/" ./pathnames > ./pathnames_omp1
sed "/output/c\./output_omp32/" ./pathnames > ./pathnames_omp32
mkdir -p ./output_omp1/
mkdir -p ./output_omp32/
export OMP_NUM_THREADS=1
./FLEXPART pathnames_omp1
export OMP_NUM_THREADS=32
./FLEXPART pathnames_omp32

sed "/output/c\./output_omp1_eta/" ./pathnames > ./pathnames_omp1
sed "/output/c\./output_omp32_eta/" ./pathnames > ./pathnames_omp32
mkdir -p ./output_omp1_eta/
mkdir -p ./output_omp32_eta/
export OMP_NUM_THREADS=1
./FLEXPART_ETA pathnames_omp1
export OMP_NUM_THREADS=32
./FLEXPART_ETA pathnames_omp32

report "[$MM] TEST $TESTRUN (OpenMP)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
#
# FINAL
#
echo "[$MM] Tests failed: $STATUS / $TESTSRUN"
#
# Return collective error status
#
exit $STATUS
